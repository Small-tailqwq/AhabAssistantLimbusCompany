using System.Collections.ObjectModel;
using AALC.Platform.Android;
using AALC.Runtime;
using AALC.Runtime.Configuration;
using AALC.Runtime.Mail;
using AALC.Runtime.Replay;
using AALC.Shared;
using AALC.Vision;
using Avalonia.Media.Imaging;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace AALC.Desktop;

public partial class MainViewModel : ObservableObject
{
    private readonly SettingsStore settingsStore;
    private readonly AdbClient adb = AdbClient.Local();
    private CancellationTokenSource? stopping;
    public Task? ActiveRun { get; private set; }
    public event Action? MonitorRequested;
    public event Action? ConnectionSettingsRequested;
    [RelayCommand] private void ConnectionSettings() => ConnectionSettingsRequested?.Invoke();
    public ObservableCollection<string> Messages { get; } = [];
    public ChoiceItem[] Languages { get; } = [new("en", "English"), new("zh_cn", "中文")];
    public ChoiceItem[] Themes { get; } = [new("default", "默认"), new("dark", "暗色")];
    public ScenarioItem[] Scenarios { get; private set; }
    [ObservableProperty] private ScenarioItem? selectedScenario;
    [ObservableProperty] private ChoiceItem selectedTheme;
    [ObservableProperty] private ChoiceItem selectedLanguage;
    [ObservableProperty] private string repositoryRoot;
    [ObservableProperty] private string port = "";
    [ObservableProperty, NotifyPropertyChangedFor(nameof(HasStatus))] private string status = "未选设备，请刷新或在设置中连接。";
    [ObservableProperty] private string error = "";
    [ObservableProperty] private string elapsedLabel = "—";
    [ObservableProperty] private string frameLabel = "";
    [ObservableProperty] private bool hasMessages;
    [ObservableProperty, NotifyPropertyChangedFor(nameof(HasReplayResult))] private string replaySummary = "";
    [ObservableProperty, NotifyPropertyChangedFor(nameof(HasPreview))] private WriteableBitmap? preview;
    [ObservableProperty] private IReadOnlyList<AdbDevice> devices = [];
    [ObservableProperty, NotifyCanExecuteChangedFor(nameof(CaptureScreenshotCommand), nameof(RunMailCommand))]
    private AdbDevice? selectedDevice;
    [ObservableProperty, NotifyPropertyChangedFor(nameof(CanConfigure)),
        NotifyCanExecuteChangedFor(nameof(ConnectCommand), nameof(RefreshDevicesCommand), nameof(CaptureScreenshotCommand),
            nameof(RunMailCommand), nameof(ReplayCommand), nameof(SaveSettingsCommand), nameof(StopCommand))]
    private bool isRunning;
    public bool CanConfigure => !IsRunning;
    private bool HasDevice => CanConfigure && SelectedDevice is not null;
    public bool HasPreview => Preview is not null;
    public bool HasStatus => Status.Length > 0;
    public bool HasReplayResult => ReplaySummary.Length > 0;

    public MainViewModel(SettingsStore store)
    {
        settingsStore = store;
        var settings = store.Load();
        selectedTheme = Themes.FirstOrDefault(o => o.Key == settings.GameTheme) ?? Themes[0];
        selectedLanguage = File.Exists(Path.Combine(store.DirectoryPath, "settings.json"))
            ? Languages.FirstOrDefault(o => o.Key == settings.GameLanguage) ?? Languages[0] : Languages[0];
        var resources = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "Resources"));
        repositoryRoot = new[] { settings.RepositoryRoot, resources, AppContext.BaseDirectory,
            RepositoryPaths.Discover(Environment.CurrentDirectory), RepositoryPaths.Discover(AppContext.BaseDirectory) }
            .FirstOrDefault(path => !string.IsNullOrWhiteSpace(path) && Directory.Exists(Path.Combine(path, "assets", "images"))) ?? "";
        Scenarios = LoadScenarios();
        selectedScenario = Scenarios.FirstOrDefault();
        LoadAppSettings(settings.App ?? new());
    }

    private ScenarioItem[] LoadScenarios() => new[] { "mail-rewards", "mail-empty", "mail-unknown" }
        .Select(name => new ScenarioItem(name, Path.Combine(RepositoryRoot, "scenarios", name + ".json"))).Where(item => File.Exists(item.Path)).ToArray();

    [RelayCommand(CanExecute = nameof(CanConfigure))]
    private void SaveSettings()
    {
        try
        {
            if (!Directory.Exists(Path.Combine(RepositoryRoot, "assets", "images")))
                throw new DirectoryNotFoundException("资源仓库中没有 assets/images。");
            settingsStore.Save(settingsStore.Load() with { RepositoryRoot = RepositoryRoot, GameLanguage = SelectedLanguage.Key,
                GameTheme = SelectedTheme.Key, App = GetAppSettings() });
            Scenarios = LoadScenarios();
            OnPropertyChanged(nameof(Scenarios));
            SelectedScenario = Scenarios.FirstOrDefault();
            Error = "";
            Status = "设置已保存";
        }
        catch (Exception e) { Error = e.Message; }
    }

    [RelayCommand(CanExecute = nameof(CanConfigure))]
    private Task RefreshDevicesAsync() => RunAsync(token => ListDevicesAsync(SelectedDevice?.Serial, token));

    [RelayCommand(CanExecute = nameof(CanConfigure))]
    private Task ConnectAsync() => RunAsync(async token =>
    {
        if (!int.TryParse(Port, out var port) || port is < 1 or > 65535)
            throw new ArgumentException("请输入模拟器设置中的本机 ADB 端口（1–65535）。");
        await adb.ConnectLocalAsync(port, token);
        return await ListDevicesAsync($"127.0.0.1:{port}", token);
    });

    private async Task<string> ListDevicesAsync(string? serial, CancellationToken token)
    {
        SelectedDevice = null;
        Devices = [];
        Devices = await adb.DevicesAsync(token);
        SelectedDevice = Devices.SingleOrDefault(d => d.Serial == serial) ?? (Devices.Count == 1 ? Devices[0] : null);
        return Devices.Count == 0 ? "未找到已授权的设备，请检查 ADB 调试开关及连接端口。"
            : SelectedDevice is null ? "发现多个设备，请选择目标模拟器。" : $"已选择 {SelectedDevice.Serial}";
    }

    [RelayCommand(CanExecute = nameof(HasDevice))]
    private Task CaptureScreenshotAsync()
    {
        var selected = SelectedDevice!;
        if (ShowMonitorOnRun) MonitorRequested?.Invoke();
        return RunAsync(token => Task.Run(async () =>
        {
            using var device = await adb.AttachAsync(selected, token);
            var output = Path.Combine(EvidencePaths.ResolveRoot(), "screenshots", $"adb-{DateTime.Now:yyyyMMdd-HHmmss-fff}.png");
            var frame = await AttachedGameTasks.CaptureAsync(device, output, token);
            ShowFrame(frame);
            return $"截图已保存：{output}";
        }, token));
    }

    [RelayCommand] private void OpenScreenshotDirectory() =>
        OpenDirectory(() => EvidencePaths.RequireExternalPath(Path.Combine(EvidencePaths.ResolveRoot(), "screenshots")));

    [RelayCommand(CanExecute = nameof(HasDevice))]
    private Task RunMailAsync()
    {
        var selected = SelectedDevice!;
        var root = RepositoryRoot;
        var options = new TemplateOptions(SelectedLanguage.Key, SelectedTheme.Key);
        if (ShowMonitorOnRun) MonitorRequested?.Invoke();
        return RunAsync(token => Task.Run(async () =>
        {
            using var device = await adb.AttachAsync(selected, token);
            RecordingStorage.Prune(EvidencePaths.ResolveRoot());
            var result = await AttachedGameTasks.MailAsync(device, root, options, ShowEvent, ShowFrame, token);
            token.ThrowIfCancellationRequested();
            if (result.Outcome != RunOutcome.Completed) throw new InvalidOperationException($"邮件任务未完成：{result.Reason}");
            return $"邮件任务完成，共观察 {result.Observations} 帧。";
        }, token));
    }

    private void ShowFrame(PixelFrame frame) => Dispatcher.UIThread.Invoke(() =>
    {
        var previous = Preview;
        Preview = FrameBitmap.Create(frame);
        previous?.Dispose();
        FrameLabel = $"{frame.Identity.Width} × {frame.Identity.Height} · 第 {frame.Identity.Id} 帧";
    });

    private void ShowEvent(RunEvent item) => Dispatcher.UIThread.Invoke(() =>
    {
        if (!RunEventDisplay.IsShown(item)) return;
        ElapsedLabel = $"{item.ElapsedMilliseconds / 1000:0.0} s";
        Messages.Add($"{ElapsedLabel}  {item.Detail ?? item.Rule}");
        HasMessages = true;
    });

    [RelayCommand(CanExecute = nameof(CanConfigure))]
    private async Task ReplayAsync()
    {
        var scenario = SelectedScenario;
        ReplaySummary = "";
        await RunAsync(token => Task.Run(async () =>
        {
            if (scenario is null) throw new InvalidOperationException("没有可回放的邮件场景，请检查资源仓库。");
            var replay = new ScenarioSession(MailScenario.Load(scenario.Path));
            var result = await new MailRunner(replay, replay, replay).RunAsync(TimeSpan.FromSeconds(30), ShowEvent, token);
            token.ThrowIfCancellationRequested();
            var acceptance = replay.Evaluate(result);
            if (!acceptance.Passed) throw new InvalidOperationException(acceptance.Reason);
            return $"{scenario.DisplayName}：符合预期，观察 {result.Observations} 帧。";
        }, token));
        ReplaySummary = Status;
    }

    private Task RunAsync(Func<CancellationToken, Task<string>> operation)
    {
        if (IsRunning) return Task.CompletedTask;
        return ActiveRun = ExecuteAsync(operation);
    }

    private async Task ExecuteAsync(Func<CancellationToken, Task<string>> operation)
    {
        using var cancellation = new CancellationTokenSource();
        stopping = cancellation;
        IsRunning = true;
        Error = "";
        Status = "运行中";
        Messages.Clear();
        HasMessages = false;
        ElapsedLabel = "—";
        try
        {
            Status = await operation(cancellation.Token);
        }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { Status = "已停止"; }
        catch (Exception e) { Error = e.Message; Status = $"未完成：{e.Message}"; }
        finally { ActiveRun = null; stopping = null; IsRunning = false; }
    }

    [RelayCommand(CanExecute = nameof(IsRunning))]
    public void Stop() => stopping?.Cancel();
}
