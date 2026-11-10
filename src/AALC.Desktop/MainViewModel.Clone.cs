using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using AALC.Core.Features.Mirror;
using AALC.Platform.Windows.DesktopClone;
using AALC.Runtime;
using AALC.Runtime.Configuration;
using AALC.Runtime.DesktopClone;
using AALC.Runtime.Mail;
using AALC.Vision;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace AALC.Desktop;

public sealed record CloneCheckRow(string Name, string Detail, bool Passed, bool Warning, bool Failed);

public partial class MainViewModel : ICloneRunObserver
{
    private static readonly TimeSpan CloneLogoffTimeout = TimeSpan.FromSeconds(30);
    private DesktopCloneController? cloneController;
    private WindowsCloneSystem? cloneSystem;
    private Action? confirmedCloneAction;
    private bool cloneRiskAccepted;
    private bool cloneCheckedOnce;
    private bool cloneMuted;
    private bool cloneInputBlocked;
    private bool cloneWindowVisible;

    public ObservableCollection<CloneCheckRow> CloneChecks { get; } = [];
    [ObservableProperty] private bool cloneChecked;
    [ObservableProperty] private bool runTasksInClone;
    [ObservableProperty] private bool showCloneOnStart = true;
    [ObservableProperty] private bool ignoreCloneRemoteWarning;
    [ObservableProperty] private string cloneStatus = "未启动";
    [ObservableProperty] private string cloneError = "";
    [ObservableProperty] private bool cloneNeedsElevation;
    [ObservableProperty] private bool cloneCanEnableRemoteDesktop;
    [ObservableProperty] private string cloneConfirmation = "";
    [ObservableProperty] private string cloneConfirmLabel = "";
    [ObservableProperty] private bool cloneConfirmationDanger;
    [ObservableProperty] private bool cloneConfirming;
    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCloneCommand))]
    [NotifyCanExecuteChangedFor(nameof(StopCloneCommand))]
    [NotifyPropertyChangedFor(nameof(CloneIdle))]
    private bool cloneActive;
    [ObservableProperty, NotifyPropertyChangedFor(nameof(CloneIdle))]
    [NotifyCanExecuteChangedFor(nameof(StartCloneCommand))]
    private bool cloneBusy;
    [ObservableProperty] private bool cloneConnected;
    public bool CloneIdle => !CloneActive && !CloneBusy;

    public bool CloneWindowVisible
    {
        get => cloneWindowVisible;
        set { if (SetProperty(ref cloneWindowVisible, value)) cloneController?.ShowWindow(value); }
    }
    public bool CloneMuted
    {
        get => cloneMuted;
        set { if (SetProperty(ref cloneMuted, value)) cloneController?.SetMuted(value); }
    }
    public bool CloneInputBlocked
    {
        get => cloneInputBlocked;
        set { if (SetProperty(ref cloneInputBlocked, value)) cloneController?.SetInputBlocked(value); }
    }

    private WindowsCloneSystem CloneSystem => cloneSystem ??= new(
        Path.Combine(AppContext.BaseDirectory, "clone-host", "AAALC.CloneHost.exe"), WorkerCommand);

    /// <summary>首次使用时创建，不计入主界面启动。</summary>
    private DesktopCloneController Clone
    {
        get
        {
            if (cloneController is not null) return cloneController;
            var server = new ClonePipeServer(log: LogClone);
            cloneController = new(CloneSystem, server, LogClone);
            cloneController.Changed += () => Dispatcher.UIThread.Post(ApplyCloneSnapshot);
            return cloneController;
        }
    }

    private static (string, string, string) WorkerCommand(CloneWorkerStart start)
    {
        var executable = Environment.ProcessPath ?? throw new CloneException("无法确定 AAALC 程序路径");
        return (executable, CloneProtocol.WorkerArguments(start, EvidencePaths.ResolveRoot()), Path.GetDirectoryName(executable)!);
    }

    private static void LogClone(string message)
    {
        try
        {
            var path = EvidencePaths.RequireExternalPath(Path.Combine(EvidencePaths.ResolveRoot(), "clone", "logs", $"root-{DateTime.Now:yyyyMMdd}.log"));
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            lock (CloneLogLock) File.AppendAllText(path, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} {message}\n");
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or InvalidDataException) { }
    }
    private static readonly object CloneLogLock = new();

    private void LoadCloneSettings(CloneSettings settings)
    {
        RunTasksInClone = settings.RunTasksInClone;
        ShowCloneOnStart = settings.ShowWindowOnStart;
        IgnoreCloneRemoteWarning = settings.IgnoreRemoteControlWarning;
    }

    private CloneSettings GetCloneSettings() => new(RunTasksInClone, ShowCloneOnStart, IgnoreCloneRemoteWarning);

    private void SaveCloneSettings()
    {
        if (applyingAgentSettings) return;
        try { settingsStore.Save(settingsStore.Load() with { DesktopClone = GetCloneSettings() }); }
        catch (Exception exception) { CloneError = exception.Message; }
    }

    partial void OnRunTasksInCloneChanged(bool value) => SaveCloneSettings();
    partial void OnShowCloneOnStartChanged(bool value) => SaveCloneSettings();
    partial void OnIgnoreCloneRemoteWarningChanged(bool value) => SaveCloneSettings();

    private void ApplyCloneSnapshot()
    {
        if (cloneController is null) return;
        var snapshot = cloneController.Snapshot;
        CloneActive = snapshot.IsActive || snapshot.State is CloneState.Connecting or CloneState.LaunchingWorker or CloneState.Ready or CloneState.Running or CloneState.Stopping;
        CloneConnected = snapshot.State is CloneState.Ready or CloneState.Running;
        if (snapshot.State == CloneState.Error)
        {
            CloneError = snapshot.Status;
            CloneStatus = "出错";
        }
        else
        {
            CloneStatus = snapshot.SessionId is { } session && CloneConnected ? $"{snapshot.Status} · Session {session}" : snapshot.Status;
            if (snapshot.State != CloneState.Idle) CloneError = "";
        }
        SetProperty(ref cloneWindowVisible, snapshot.WindowVisible, nameof(CloneWindowVisible));
        SetProperty(ref cloneMuted, snapshot.Muted, nameof(CloneMuted));
        SetProperty(ref cloneInputBlocked, snapshot.InputBlocked, nameof(CloneInputBlocked));
    }

    /// <summary>进入页面时读取一次环境，之后由兼容性检查按钮刷新。</summary>
    public void EnterClonePage()
    {
        if (cloneCheckedOnce) return;
        cloneCheckedOnce = true;
        CheckCloneCommand.Execute(null);
    }

    public void RestoreCloneAutoruns()
    {
        if (!AutorunGuard.IsActive) return;
        try { AutorunGuard.Restore(); }
        catch (Exception exception) { LogClone($"恢复登录自启动策略失败：{exception.Message}"); }
    }

    [RelayCommand]
    private async Task CheckCloneAsync()
    {
        var system = CloneSystem;
        var owned = cloneController?.Snapshot.SessionId;
        try
        {
            var result = await Task.Run(() => system.CheckCompatibility(owned));
            CloneChecks.Clear();
            foreach (var item in result.Items)
                CloneChecks.Add(new(item.Name, item.Detail, item.Status == CloneCheckStatus.Passed, item.Status == CloneCheckStatus.Warning, item.Status == CloneCheckStatus.Failed));
            CloneNeedsElevation = result.NeedsElevation;
            CloneCanEnableRemoteDesktop = result.CanEnableRemoteDesktop;
            CloneChecked = true;
        }
        catch (Exception exception) { CloneError = exception.Message; }
    }

    private bool CanStartClone() => CloneIdle;

    [RelayCommand(CanExecute = nameof(CanStartClone))]
    private async Task StartCloneAsync()
    {
        CancelCloneConfirmation();
        CloneBusy = true;
        try
        {
            var compatibility = await Task.Run(() => CloneSystem.CheckCompatibility(null));
            var warnings = compatibility.Items.Where(item => item is { Name: "远程控制软件" }).Select(item => item.Detail).ToArray();
            if (compatibility.Supported && warnings.Length > 0 && !IgnoreCloneRemoteWarning && !cloneRiskAccepted)
            {
                AskClone(warnings[0], "继续启动", false, () =>
                {
                    cloneRiskAccepted = true;
                    StartCloneCommand.Execute(null);
                });
                return;
            }
            await Clone.StartAsync(new(ShowCloneOnStart), CancellationToken.None);
        }
        catch (Exception exception) { CloneError = exception.Message; }
        finally
        {
            CloneBusy = false;
            ApplyCloneSnapshot();
            await CheckCloneAsync();
        }
    }

    private bool CanStopClone() => CloneActive;

    [RelayCommand(CanExecute = nameof(CanStopClone))]
    private void StopClone() => AskClone("这会停止分身任务并关闭分身桌面中的所有程序。", "停止并注销", true, () => _ = LogoffCloneAsync());

    private async Task LogoffCloneAsync()
    {
        Stop();
        CloneBusy = true;
        try
        {
            if (!await Clone.ShutdownAsync(CloneLogoffTimeout) && CloneError.Length == 0) CloneError = "Windows 尚未确认 Child Session 已注销，请重试";
        }
        catch (Exception exception) { CloneError = exception.Message; }
        finally
        {
            CloneBusy = false;
            ApplyCloneSnapshot();
            await CheckCloneAsync();
        }
    }

    [RelayCommand]
    private void EnableCloneRemoteDesktop() => AskClone(
        "这会开启 Windows 远程桌面及其防火墙例外，允许符合 Windows 权限规则的设备通过网络请求远程连接。", "开启远程桌面", false, () => _ = EnableRemoteDesktopAsync());

    private async Task EnableRemoteDesktopAsync()
    {
        CloneBusy = true;
        try { await Task.Run(() => CloneSystem.EnableRemoteDesktop(CancellationToken.None)); }
        catch (Exception exception) { CloneError = exception.Message; }
        finally
        {
            CloneBusy = false;
            await CheckCloneAsync();
        }
    }

    [RelayCommand]
    private void RestartElevated()
    {
        try
        {
            var information = new ProcessStartInfo(Environment.ProcessPath!) { UseShellExecute = true, Verb = "runas" };
            foreach (var argument in Environment.GetCommandLineArgs().Skip(1)) information.ArgumentList.Add(argument);
            Process.Start(information)?.Dispose();
            (Avalonia.Application.Current?.ApplicationLifetime as IClassicDesktopStyleApplicationLifetime)?.Shutdown();
        }
        // 用户在 UAC 提示上选择“否”。
        catch (Win32Exception exception) when (exception.NativeErrorCode == 1223) { }
        catch (Exception exception) { CloneError = exception.Message; }
    }

    private void AskClone(string text, string label, bool danger, Action action)
    {
        CloneConfirmation = text;
        CloneConfirmLabel = label;
        CloneConfirmationDanger = danger;
        confirmedCloneAction = action;
        CloneConfirming = true;
    }

    [RelayCommand]
    private void ConfirmClone()
    {
        var action = confirmedCloneAction;
        CancelCloneConfirmation();
        action?.Invoke();
    }

    [RelayCommand]
    private void CancelCloneConfirmation()
    {
        confirmedCloneAction = null;
        CloneConfirming = false;
    }

    private async Task RunInCloneAsync(CloneTaskRequest request)
    {
        var clone = Clone;
        var show = ShowCloneOnStart;
        if (!clone.Snapshot.IsActive && !IgnoreCloneRemoteWarning && !cloneRiskAccepted)
        {
            var compatibility = await Task.Run(() => CloneSystem.CheckCompatibility(null));
            if (compatibility.Items.FirstOrDefault(item => item is { Name: "远程控制软件" }) is { } risk)
            {
                Error = $"{risk.Detail}。请先在桌面分身页确认后启动";
                return;
            }
        }
        RequestMonitor();
        await RunAsync(async token =>
        {
            try
            {
                await clone.StartAsync(new(show), token);
                return await clone.RunAsync(request.Save(), this, token);
            }
            catch (OperationCanceledException) when (token.IsCancellationRequested) { return new(RunOutcome.Cancelled, "已停止", 0, 0); }
        }, request.Kind);
    }

    void ICloneRunObserver.OnEvent(RunEvent item) => Publish(item);

    void ICloneRunObserver.OnFrame(long id, byte[] jpeg)
    {
        try { UpdatePreview(FramePreview.Decode(id, jpeg)); }
        catch (InvalidDataException exception) { LogClone(exception.Message); }
    }

    void ICloneRunObserver.OnMirrorQueue(string path)
    {
        try
        {
            var teams = JsonSerializer.Deserialize<MirrorTeamOptions[]>(File.ReadAllText(path)) ?? throw new InvalidDataException("分身队伍队列为空");
            File.Delete(path);
            Dispatcher.UIThread.Post(() => { ReplaceMirrorTeams(teams); SaveDesktopSettings(); });
        }
        catch (Exception exception) when (exception is IOException or JsonException or InvalidDataException or UnauthorizedAccessException)
        {
            LogClone($"读取分身队伍队列失败：{exception.Message}");
        }
    }

    /// <summary>关闭窗口时调用，<paramref name="timeout"/> 是 5 秒关闭预算的剩余部分。</summary>
    public Task ShutdownCloneAsync(TimeSpan timeout) =>
        cloneController is null || timeout <= TimeSpan.Zero ? Task.CompletedTask : cloneController.ShutdownAsync(timeout);

    public void DisposeClone() => cloneController?.Dispose();
}
