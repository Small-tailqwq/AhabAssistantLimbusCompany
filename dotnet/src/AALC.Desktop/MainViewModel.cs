using System.Collections.ObjectModel;
using System.IO;
using System.Text.Json;
using System.Runtime.InteropServices;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Media.Imaging;
using Avalonia.Platform;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using AALC.Platform.Windows;
using AALC.Runtime;
using AALC.Runtime.Configuration;
using AALC.Runtime.Mail;
using AALC.Runtime.Replay;
using AALC.Vision;

namespace AALC.Desktop;

public sealed record ScenarioItem(string Name, string Path)
{
    public string DisplayName => Name switch
    {
        "mail-empty" => "空邮箱", "mail-rewards" => "领取奖励",
        "mail-unknown" => "无法识别的画面", _ => Name
    };
}
public sealed record ChoiceItem(string Key, string Name);

public partial class MainViewModel : ObservableObject
{
    private readonly SettingsStore settingsStore;
    private CancellationTokenSource? cancellation;
    public Task? ActiveRun { get; private set; }
    public ObservableCollection<GameWindowInfo> Windows { get; } = [];
    public ObservableCollection<ScenarioItem> Scenarios { get; } = [];
    public ObservableCollection<string> Messages { get; } = [];
    public ChoiceItem[] Languages { get; } = [new("zh_cn", "中文"), new("en", "English")];
    public ChoiceItem[] Themes { get; } = [new("default", "默认"), new("dark", "暗色")];
    [ObservableProperty] private ChoiceItem? selectedLanguage;
    [ObservableProperty] private ChoiceItem? selectedTheme;
    [ObservableProperty] private string repositoryRoot = "";
    [ObservableProperty] private string gameLanguage = "zh_cn";
    [ObservableProperty] private string gameTheme = "default";
    [ObservableProperty, NotifyPropertyChangedFor(nameof(HasStatus))] private string status = "";
    public bool HasStatus => Status.Length > 0;
    [ObservableProperty] private string error = "";
    [ObservableProperty, NotifyPropertyChangedFor(nameof(HasReplayResult))] private string replaySummary = "";
    public bool HasReplayResult => ReplaySummary.Length > 0;
    [ObservableProperty, NotifyPropertyChangedFor(nameof(HasPreview))] private WriteableBitmap? preview;
    [ObservableProperty] private string frameLabel = "";
    [ObservableProperty] private string elapsedLabel = "—";
    [ObservableProperty] private bool hasMessages;
    public bool HasPreview => Preview is not null;
    /// <summary>游戏任务开始时请求切到运行监控页，受“开始任务时切到运行监控”控制。</summary>
    public event Action? MonitorRequested;
    private void RequestMonitor() { if (ShowMonitorOnRun) MonitorRequested?.Invoke(); }
    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(RunMailCommand))]
    [NotifyCanExecuteChangedFor(nameof(RunDailyCommand))]
    [NotifyCanExecuteChangedFor(nameof(RunMirrorCommand))]
    [NotifyCanExecuteChangedFor(nameof(CaptureScreenshotCommand))]
    private GameWindowInfo? selectedWindow;
    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(ReplayCommand))]
    private ScenarioItem? selectedScenario;
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(CanConfigure))]
    [NotifyCanExecuteChangedFor(nameof(RunMailCommand))]
    [NotifyCanExecuteChangedFor(nameof(RunDailyCommand))]
    [NotifyCanExecuteChangedFor(nameof(RunMirrorCommand))]
    [NotifyCanExecuteChangedFor(nameof(ReplayCommand))]
    [NotifyCanExecuteChangedFor(nameof(StopCommand))]
    [NotifyCanExecuteChangedFor(nameof(SaveDailySettingsCommand))]
    [NotifyCanExecuteChangedFor(nameof(SaveMirrorSettingsCommand))]
    [NotifyCanExecuteChangedFor(nameof(AddMirrorTeamCommand))]
    [NotifyCanExecuteChangedFor(nameof(RemoveMirrorTeamCommand))]
    [NotifyCanExecuteChangedFor(nameof(MoveMirrorTeamUpCommand))]
    [NotifyCanExecuteChangedFor(nameof(MoveMirrorTeamDownCommand))]
    [NotifyCanExecuteChangedFor(nameof(RefreshWindowsCommand))]
    [NotifyCanExecuteChangedFor(nameof(CheckLocalizationCommand))]
    [NotifyCanExecuteChangedFor(nameof(InstallLocalizationCommand))]
    [NotifyCanExecuteChangedFor(nameof(DisableTutorialsCommand))]
    [NotifyCanExecuteChangedFor(nameof(EnableTutorialsCommand))]
    [NotifyCanExecuteChangedFor(nameof(CaptureScreenshotCommand))]
    [NotifyCanExecuteChangedFor(nameof(SearchGameDirectoryCommand))]
    [NotifyCanExecuteChangedFor(nameof(SaveSettingsCommand))]
    private bool isRunning;
    public bool CanConfigure => !IsRunning;
    private bool CanRunMail() => !IsRunning && SelectedWindow is not null;
    private bool CanReplay() => !IsRunning && SelectedScenario is not null;

    public MainViewModel(SettingsStore store)
    {
        settingsStore = store;
        var settings = store.Load();
        RepositoryRoot = string.IsNullOrEmpty(settings.RepositoryRoot)
            ? RepositoryPaths.Discover(Environment.CurrentDirectory) ?? RepositoryPaths.Discover(AppContext.BaseDirectory) ?? ""
            : settings.RepositoryRoot;
        GameLanguage = settings.GameLanguage;
        GameTheme = settings.GameTheme;
        SelectedLanguage = Languages.Single(item => item.Key == GameLanguage);
        SelectedTheme = Themes.Single(item => item.Key == GameTheme);
        LoadDailySettings(settings);
        LoadMirrorSettings(settings);
        GameDirectory = Path.GetDirectoryName(settings.GameExecutablePath) ?? "";
        LoadAppSettings(settings.App ?? new());
        LoadScenarios();
    }

    partial void OnSelectedLanguageChanged(ChoiceItem? value) { if (value is not null) GameLanguage = value.Key; }
    partial void OnSelectedThemeChanged(ChoiceItem? value) { if (value is not null) GameTheme = value.Key; }

    private void LoadScenarios()
    {
        Scenarios.Clear();
        var folder = Path.Combine(RepositoryRoot, "dotnet", "scenarios");
        if (Directory.Exists(folder))
            foreach (var file in Directory.EnumerateFiles(folder, "*.json").Order())
                Scenarios.Add(new(Path.GetFileNameWithoutExtension(file), file));
        SelectedScenario = Scenarios.FirstOrDefault();
    }

    [RelayCommand(CanExecute = nameof(CanConfigure))]
    private void RefreshWindows()
    {
        try
        {
            Windows.Clear();
            foreach (var window in GameWindow.Find()) Windows.Add(window);
            SelectedWindow = Windows.FirstOrDefault();
            Error = Windows.Count == 0 ? "未找到 Limbus Company 窗口，请先启动游戏。" : "";
        }
        catch (Exception exception) { Error = exception.Message; }
    }

    [RelayCommand(CanExecute = nameof(CanConfigure))]
    private void SaveSettings()
    {
        try
        {
            if (!Directory.Exists(Path.Combine(RepositoryRoot, "assets", "images")))
                throw new InvalidDataException("资源仓库中没有 assets/images");
            SaveDesktopSettings();
            LoadScenarios();
            Error = "";
            Status = "设置已保存";
        }
        catch (Exception exception) { Error = exception.Message; }
    }

    [RelayCommand(CanExecute = nameof(IsRunning))]
    public void Stop() => cancellation?.Cancel();

    [RelayCommand(CanExecute = nameof(CanReplay))]
    private async Task ReplayAsync()
    {
        var scenarioItem = SelectedScenario!;
        ScenarioAcceptance? acceptance = null;
        ReplaySummary = "";
        await RunAsync(async token =>
        {
            var scenario = MailScenario.Load(scenarioItem.Path);
            var session = new ScenarioSession(scenario);
            var result = await new MailRunner(session, session, session).RunAsync(TimeSpan.FromSeconds(30), Publish, token);
            acceptance = session.Evaluate(result);
            var passed = acceptance.Passed;
            Dispatcher.UIThread.Invoke(() =>
                ReplaySummary = $"{scenarioItem.DisplayName}：{(passed ? "符合预期" : "与预期不符")}，观察 {result.Observations} 帧。");
            return result;
        });
        if (acceptance is not null)
        {
            Status = "";
            Error = acceptance.Passed ? "" : acceptance.Reason;
        }
        else ReplaySummary = "场景未能完成。";
    }

    [RelayCommand(CanExecute = nameof(CanRunMail))]
    private async Task RunMailAsync()
    {
        var selected = SelectedWindow!;
        var root = RepositoryRoot;
        var options = new TemplateOptions(GameLanguage, GameTheme);
        RequestMonitor();
        await RunAsync(async token =>
        {
            var directory = EvidencePaths.RequireExternalPath(Path.Combine(EvidencePaths.ResolveRoot(), "recordings", "mail", DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")));
            Directory.CreateDirectory(directory);
            using var events = new StreamWriter(Path.Combine(directory, "events.jsonl")) { AutoFlush = true };
            using var window = new GameWindow(selected);
            using var matcher = new TemplateMatcher(root, options);
            var observer = new MailObserver(window, matcher, directory);
            observer.FrameCaptured += UpdatePreview;
            var result = await new MailRunner(observer, window, new SystemRunClock()).RunAsync(TimeSpan.FromSeconds(30), e =>
            {
                events.WriteLine(JsonSerializer.Serialize(e));
                Publish(e);
            }, token);
            File.WriteAllText(Path.Combine(directory, "result.json"), JsonSerializer.Serialize(result));
            return result;
        });
    }

    private async Task RunAsync(Func<CancellationToken, Task<RunResult>> operation)
    {
        cancellation = new();
        IsRunning = true;
        Status = "运行中";
        Error = "";
        Messages.Clear();
        HasMessages = false;
        ElapsedLabel = "0.0 s";
        try
        {
            var task = Task.Run(() => operation(cancellation.Token));
            ActiveRun = task;
            var result = await task;
            Status = result.Outcome switch { RunOutcome.Completed => "已完成", RunOutcome.Cancelled => "已停止", _ => "未完成" };
            if (result.Outcome == RunOutcome.Failed) Error = result.Reason;
        }
        catch (Exception exception)
        {
            Status = "未完成";
            Error = exception.Message;
        }
        finally
        {
            cancellation.Dispose();
            cancellation = null;
            IsRunning = false;
            ActiveRun = null;
        }
    }

    private static WriteableBitmap CreateBitmap(PixelFrame frame)
    {
        var bitmap = new WriteableBitmap(new PixelSize(frame.Identity.Width, frame.Identity.Height),
            new Vector(96, 96), PixelFormat.Bgra8888, AlphaFormat.Opaque);
        using (var buffer = bitmap.Lock())
            for (var y = 0; y < frame.Identity.Height; y++)
                Marshal.Copy(frame.Bgra, y * frame.Identity.Width * 4,
                    buffer.Address + y * buffer.RowBytes, frame.Identity.Width * 4);
        return bitmap;
    }

    private void UpdatePreview(PixelFrame frame) => Dispatcher.UIThread.Invoke(() =>
    {
        var old = Preview;
        Preview = CreateBitmap(frame);
        old?.Dispose();
        FrameLabel = $"{frame.Identity.Width} × {frame.Identity.Height} · 第 {frame.Identity.Id} 帧";
    });

    private void Publish(RunEvent item) => Dispatcher.UIThread.Invoke(() =>
    {
        if (item.Rule is "mirror.route.map" or "mirror.route.scan") return;
        if ((item.Rule.StartsWith("daily.", StringComparison.Ordinal) || item.Rule.StartsWith("mirror.", StringComparison.Ordinal)
            || item.Rule.StartsWith("battle.", StringComparison.Ordinal) || item.Rule.StartsWith("automation.", StringComparison.Ordinal)
            || item.Rule.StartsWith("team.", StringComparison.Ordinal)) &&
            (item.Action != "Progress" || string.IsNullOrWhiteSpace(item.Detail))) return;
        var description = item.Rule switch
        {
            "mail.open" => "打开邮箱", "mail.claim-all" => "领取全部",
            "mail.confirm-rewards" => "确认奖励", "mail.close-after-confirm" => "关闭邮箱",
            "mail.close-without-confirm" => "关闭空邮箱", "mail.returned-home" => "已返回主界面",
            "mail.wait-home" => "等待返回主界面", "mail.wait-confirm-dismissal" => "等待奖励确认结束",
            "mail.wait-claim-result" => "等待领取结果", "mail.wait-recognized-state" => "等待识别页面",
            "mail.cancelled" => "任务已停止", "mail.timeout" => "等待超时", _ => item.Detail ?? item.Rule
        };
        if (item.Action is not ("Sent" or "Complete"))
        {
            Messages.Add($"{item.ElapsedMilliseconds / 1000:0.0}s  {description}");
            HasMessages = true;
            ElapsedLabel = $"{item.ElapsedMilliseconds / 1000:0.0} s";
        }
    });
}

