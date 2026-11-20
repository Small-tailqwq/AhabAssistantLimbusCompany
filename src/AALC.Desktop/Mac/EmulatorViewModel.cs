using AALC.Platform.Android;
using AALC.Runtime;
using AALC.Runtime.Configuration;
using AALC.Runtime.Mail;
using AALC.Runtime.Replay;
using Avalonia.Media.Imaging;
using Avalonia.Threading;
using AALC.Shared;
using AALC.Vision;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace AALC.Desktop.Mac;

public sealed record FieldOption(string Value, string Label)
{
    public override string ToString() => Label;
}

public partial class EmulatorViewModel : ObservableObject
{
    private readonly SettingsStore store;
    private readonly AdbClient adb = AdbClient.Local();
    private CancellationTokenSource? stopping;
    public Task? Active { get; private set; }
    public IReadOnlyList<FieldOption> Languages { get; } = [new("en", "English"), new("zh_cn", "简体中文")];
    public IReadOnlyList<FieldOption> Themes { get; } = [new("default", "默认"), new("dark", "深色")];
    public IReadOnlyList<FieldOption> Scenarios { get; } = [new("mail-rewards", "有待领取奖励"), new("mail-empty", "没有新邮件"), new("mail-unknown", "无法识别的画面")];
    [ObservableProperty] private FieldOption scenario;
    [ObservableProperty] private FieldOption theme;
    [ObservableProperty, NotifyPropertyChangedFor(nameof(HasPreview))] private WriteableBitmap? preview;
    public bool HasPreview => Preview is not null;
    [ObservableProperty] private FieldOption language;
    [ObservableProperty] private string repository;
    [ObservableProperty] private string port = "";
    [ObservableProperty] private string status = "请启动模拟器和游戏，然后刷新设备。";
    [ObservableProperty] private string error = "";
    [ObservableProperty] private IReadOnlyList<AdbDevice> devices = [];
    [ObservableProperty, NotifyPropertyChangedFor(nameof(DeviceLabel), nameof(DeviceSelected)),
        NotifyCanExecuteChangedFor(nameof(CaptureCommand), nameof(MailCommand))]
    private AdbDevice? selected;
    [ObservableProperty, NotifyPropertyChangedFor(nameof(Idle)),
        NotifyCanExecuteChangedFor(nameof(ConnectCommand), nameof(RefreshCommand), nameof(CaptureCommand), nameof(MailCommand), nameof(ReplayCommand), nameof(StopCommand))]
    private bool busy;
    public bool Idle => !Busy;
    public bool DeviceSelected => Selected is not null;
    public string DeviceLabel => DeviceSelected ? "已选设备" : "未选设备";
    private bool HasDevice => Idle && Selected is not null;

    public EmulatorViewModel(SettingsStore store)
    {
        this.store = store;
        var settings = store.Load();
        scenario = Scenarios[0];
        theme = Themes.FirstOrDefault(o => o.Value == settings.GameTheme) ?? Themes[0];
        language = File.Exists(Path.Combine(store.DirectoryPath, "settings.json"))
            ? Languages.FirstOrDefault(o => o.Value == settings.GameLanguage) ?? Languages[0] : Languages[0];
        var resources = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "Resources"));
        repository = new[] { settings.RepositoryRoot, resources, AppContext.BaseDirectory,
            RepositoryPaths.Discover(Environment.CurrentDirectory), RepositoryPaths.Discover(AppContext.BaseDirectory) }
            .FirstOrDefault(path => !string.IsNullOrWhiteSpace(path) && Directory.Exists(Path.Combine(path, "assets", "images"))) ?? "";
    }

    [RelayCommand(CanExecute = nameof(Idle))]
    private Task RefreshAsync() => RunAsync(token => ListDevicesAsync(Selected?.Serial, token));

    [RelayCommand(CanExecute = nameof(Idle))]
    private Task ConnectAsync() => RunAsync(async token =>
    {
        if (!int.TryParse(Port, out var port) || port is < 1 or > 65535)
            throw new ArgumentException("请输入模拟器设置中的本机 ADB 端口（1–65535）。");
        await adb.ConnectLocalAsync(port, token);
        return await ListDevicesAsync($"127.0.0.1:{port}", token);
    });

    private async Task<string> ListDevicesAsync(string? serial, CancellationToken token)
    {
        Selected = null;
        Devices = [];
        Devices = await adb.DevicesAsync(token);
        Selected = Devices.SingleOrDefault(d => d.Serial == serial) ?? (Devices.Count == 1 ? Devices[0] : null);
        return Devices.Count == 0 ? "未找到已授权的设备，请检查 ADB 调试开关及连接端口。"
            : Selected is null ? "发现多个设备，请选择目标模拟器。" : $"已选择 {Selected.Serial}";
    }

    [RelayCommand(CanExecute = nameof(HasDevice))]
    private Task CaptureAsync()
    {
        var selected = Selected!;
        return RunAsync(token => Task.Run(async () =>
        {
            using var device = await adb.AttachAsync(selected, token);
            var output = Path.Combine(EvidencePaths.ResolveRoot(), "screenshots", $"adb-{DateTime.Now:yyyyMMdd-HHmmss-fff}.png");
            var frame = await AttachedGameTasks.CaptureAsync(device, output, token);
            ShowFrame(frame);
            return $"已保存 {frame.Identity.Width}×{frame.Identity.Height} 截图：{output}";
        }, token));
    }

    [RelayCommand(CanExecute = nameof(HasDevice))]
    private Task MailAsync()
    {
        var selected = Selected!;
        var root = Repository;
        var language = Language.Value;
        var theme = Theme.Value;
        return RunAsync(token => Task.Run(async () =>
        {
            if (!Directory.Exists(Path.Combine(root, "assets", "images"))) throw new DirectoryNotFoundException("请选择含 assets/images 的资源仓库。");
            var settings = store.Load() with { RepositoryRoot = root, GameLanguage = language, GameTheme = theme };
            store.Save(settings);
            using var device = await adb.AttachAsync(selected, token);
            RecordingStorage.Prune(EvidencePaths.ResolveRoot());
            var result = await AttachedGameTasks.MailAsync(device, root, new TemplateOptions(language, theme), ShowEvent, ShowFrame, token);
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
    });

    private void ShowEvent(RunEvent item) => Dispatcher.UIThread.Invoke(() =>
        Status = $"{item.ElapsedMilliseconds / 1000:0.0}s · {item.Detail ?? item.Rule}");

    [RelayCommand(CanExecute = nameof(Idle))]
    private Task ReplayAsync()
    {
        var path = Path.Combine(Repository, "scenarios", Scenario.Value + ".json");
        return RunAsync(token => Task.Run(async () =>
        {
            var replay = new ScenarioSession(MailScenario.Load(path));
            var result = await new MailRunner(replay, replay, replay).RunAsync(TimeSpan.FromSeconds(30), ShowEvent, token);
            token.ThrowIfCancellationRequested();
            var acceptance = replay.Evaluate(result);
            if (!acceptance.Passed) throw new InvalidOperationException(acceptance.Reason);
            return $"离线回放符合预期，共观察 {result.Observations} 帧。";
        }, token));
    }

    private async Task RunAsync(Func<CancellationToken, Task<string>> operation)
    {
        if (Busy) return;
        using var cancellation = new CancellationTokenSource();
        stopping = cancellation;
        Busy = true;
        Error = "";
        Status = "运行中…";
        try
        {
            var task = operation(cancellation.Token);
            Active = task;
            Status = await task;
        }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { Status = "已停止"; }
        catch (Exception e) { Error = e.Message; Status = ""; }
        finally { Active = null; stopping = null; Busy = false; }
    }

    [RelayCommand(CanExecute = nameof(Busy))]
    public void Stop() => stopping?.Cancel();
}
