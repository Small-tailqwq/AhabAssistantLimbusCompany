using AALC.Runtime;
using System.Collections.ObjectModel;
using System.IO;
using System.Text.Json;
using AALC.Core.Features.Daily;
using AALC.Core.Features.Mirror;
using AALC.Platform.Windows;
using AALC.Runtime.Configuration;
using AALC.Runtime.Daily;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;
using AALC.Runtime.Tools;
using AALC.Vision;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace AALC.Desktop;

public partial class DayTeamItem(string name, int number) : ObservableObject
{
    public string Name { get; } = name;
    [ObservableProperty] private int teamNumber = number;
}

public partial class MainViewModel
{
    [ObservableProperty] private string ocrModelsDirectory = "";
    [ObservableProperty] private bool runLuxcavation = true;
    [ObservableProperty, NotifyPropertyChangedFor(nameof(BatchPreview))] private int expCount = 1;
    [ObservableProperty, NotifyPropertyChangedFor(nameof(BatchPreview))] private int threadCount = 3;
    [ObservableProperty] private int teamNumber = 1;
    [ObservableProperty] private bool selectTeamByOrder;
    [ObservableProperty, NotifyPropertyChangedFor(nameof(BatchPreview))] private bool useContinuousCombat;
    [ObservableProperty, NotifyPropertyChangedFor(nameof(BatchPreview))] private int maxContinuousCombat = 1;
    [ObservableProperty] private bool expTeamByDay;
    [ObservableProperty] private bool threadTeamByDay;
    [ObservableProperty] private bool handleChoiceEvents = true;
    [ObservableProperty] private bool convertModules = true;
    [ObservableProperty] private bool claimRewards;
    [ObservableProperty] private bool claimMail = true;
    [ObservableProperty] private bool claimMissions = true;
    [ObservableProperty] private bool claimSeasonMissions;
    [ObservableProperty] private bool claimPassLevels;
    [ObservableProperty] private bool buyStamina;
    [ObservableProperty] private int refillTier = 2;
    [ObservableProperty] private bool grandetMode;
    public string[] RefillTiers { get; } = ["不兑换", "第一档", "第二档", "第三档"];
    public ObservableCollection<DayTeamItem> ExpDayTeams { get; } = [];
    public ObservableCollection<DayTeamItem> ThreadDayTeams { get; } = [];
    public string BatchPreview
    {
        get
        {
            string Batches(int count) => count == 0 ? "不运行" : string.Join(" + ",
                DailyPlan.Batches(count, UseContinuousCombat, MaxContinuousCombat).GroupBy(size => size)
                    .Select(group => $"{group.Key} 次 × {group.Count()} 批"));
            return $"经验：{Batches(ExpCount)}\n纺锤：{Batches(ThreadCount)}";
        }
    }

    private void LoadDailySettings(DesktopSettings settings)
    {
        OcrModelsDirectory = settings.OcrModelsDirectory;
        if (string.IsNullOrWhiteSpace(OcrModelsDirectory))
            OcrModelsDirectory = Directory.Exists(RepositoryPaths.OcrModels(RepositoryRoot)) ? RepositoryPaths.OcrModels(RepositoryRoot) : "";
        var options = settings.Daily ?? new DailyOptions();
        DailyPlan.Validate(options);
        RunLuxcavation = options.RunLuxcavation;
        ExpCount = options.ExpCount;
        ThreadCount = options.ThreadCount;
        TeamNumber = options.TeamNumber;
        SelectTeamByOrder = options.SelectTeamByOrder;
        UseContinuousCombat = options.UseContinuousCombat;
        MaxContinuousCombat = options.MaxContinuousCombat;
        ExpTeamByDay = options.ExpTeamByDay;
        ThreadTeamByDay = options.ThreadTeamByDay;
        HandleChoiceEvents = options.HandleChoiceEvents;
        ConvertModules = options.ConvertModules;
        ClaimRewards = options.ClaimRewards;
        ClaimMail = options.ClaimMail;
        ClaimMissions = options.ClaimMissions;
        ClaimSeasonMissions = options.ClaimSeasonMissions;
        ClaimPassLevels = options.ClaimPassLevels;
        BuyStamina = options.BuyStamina;
        RefillTier = options.RefillTier;
        GrandetMode = options.GrandetMode;
        string[] expDays = ["周一、周二", "周三、周四", "周五、周六", "周日"];
        string[] threadDays = ["周一 · 色欲", "周二 · 怠惰", "周三 · 暴食", "周四 · 忧郁", "周五 · 傲慢", "周六 · 嫉妒", "周日 · 暴怒"];
        for (var i = 0; i < expDays.Length; i++) ExpDayTeams.Add(new(expDays[i], options.ExpTeams[i]));
        for (var i = 0; i < threadDays.Length; i++) ThreadDayTeams.Add(new(threadDays[i], options.ThreadTeams[i]));
    }

    private DailyOptions GetDailyOptions() => new()
    {
        RunLuxcavation = RunLuxcavation, ExpCount = ExpCount, ThreadCount = ThreadCount,
        TeamNumber = TeamNumber, SelectTeamByOrder = SelectTeamByOrder,
        UseContinuousCombat = UseContinuousCombat, MaxContinuousCombat = MaxContinuousCombat,
        ExpTeamByDay = ExpTeamByDay, ExpTeams = ExpDayTeams.Select(item => item.TeamNumber).ToArray(),
        ThreadTeamByDay = ThreadTeamByDay, ThreadTeams = ThreadDayTeams.Select(item => item.TeamNumber).ToArray(),
        HandleChoiceEvents = HandleChoiceEvents, ConvertModules = ConvertModules,
        ClaimRewards = ClaimRewards, ClaimMail = ClaimMail, ClaimMissions = ClaimMissions,
        ClaimSeasonMissions = ClaimSeasonMissions,
        ClaimPassLevels = ClaimPassLevels, BuyStamina = BuyStamina, RefillTier = RefillTier, GrandetMode = GrandetMode
    };

    private void SaveDesktopSettings()
    {
        var options = GetDailyOptions();
        DailyPlan.Validate(options);
        var mirror = GetMirrorOptions();
        MirrorPlan.ValidateConfiguration(mirror);
        var executable = "";
        if (!string.IsNullOrWhiteSpace(GameDirectory))
        {
            GameDirectory = GameInstallation.RequireDirectory(GameDirectory);
            executable = Path.Combine(GameDirectory, GameInstallation.ExecutableName);
        }
        settingsStore.Save(new(RepositoryRoot, GameLanguage, GameTheme, options, OcrModelsDirectory, mirror, executable, GetAppSettings()));
    }

    [RelayCommand(CanExecute = nameof(CanConfigure))]
    private void SaveDailySettings()
    {
        try
        {
            SaveDesktopSettings();
            Error = "";
            Status = "日常配置已保存";
        }
        catch (Exception exception) { Error = exception.Message; }
    }

    private bool CanRunDaily() => !IsRunning && SelectedWindow is not null;

    [RelayCommand(CanExecute = nameof(CanRunDaily))]
    private async Task RunDailyAsync()
    {
        var options = GetDailyOptions();
        try { DailyPlan.Validate(options); SaveDesktopSettings(); }
        catch (Exception exception) { Error = exception.Message; return; }
        var selected = SelectedWindow!;
        var root = RepositoryRoot;
        var models = OcrModelsDirectory;
        var templates = new TemplateOptions(GameLanguage, GameTheme);
        RequestMonitor();
        await RunAsync(async token =>
        {
            var directory = EvidencePaths.RequireExternalPath(Path.Combine(EvidencePaths.ResolveRoot(), "recordings", "daily", DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")));
            Directory.CreateDirectory(directory);
            File.WriteAllText(Path.Combine(directory, "options.json"), JsonSerializer.Serialize(options));
            using var events = new StreamWriter(Path.Combine(directory, "events.jsonl")) { AutoFlush = true };
            void Report(RunEvent item) { events.WriteLine(JsonSerializer.Serialize(item)); Publish(item); }
            using var window = new GameWindow(selected);
            using var matcher = new TemplateMatcher(root, templates);
            using var observer = new GameObserver(window, matcher, models, directory);
            observer.FrameCaptured += UpdatePreview;
            var session = new GameSession(observer, window, new SystemRunClock(), Report, DailyRunner.TimeoutFor(options));
            var runner = new DailyRunner(session, async cancellationToken =>
            {
                var mailObserver = new MailObserver(window, matcher, Path.Combine(directory, "mail"));
                mailObserver.FrameCaptured += UpdatePreview;
                return await new MailRunner(mailObserver, window, new SystemRunClock())
                    .RunAsync(TimeSpan.FromSeconds(30), Report, cancellationToken);
            });
            var result = await runner.RunAsync(options, token);
            File.WriteAllText(Path.Combine(directory, "result.json"), JsonSerializer.Serialize(result));
            return result;
        });
    }
}
