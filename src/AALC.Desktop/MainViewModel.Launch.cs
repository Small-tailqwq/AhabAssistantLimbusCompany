using AALC.Core.Features.Daily;
using AALC.Core.Features.Mirror;
using AALC.Runtime.Configuration;
using AALC.Runtime.DesktopClone;
using AALC.Runtime.Mail;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace AALC.Desktop;

public partial class MainViewModel
{
    [ObservableProperty] private bool launchDaily = true;
    [ObservableProperty] private bool launchHarvest;
    [ObservableProperty] private bool launchMirror;

    private LaunchSettings GetLaunchSettings() => new(LaunchDaily, LaunchHarvest, LaunchMirror);

    private static DailyOptions HarvestOptions(DailyOptions options) => options with
    {
        RunLuxcavation = false, ConvertModules = true, ClaimRewards = false
    };

    [RelayCommand(CanExecute = nameof(CanConfigure))]
    private void SaveLaunchSettings() => SaveSettings();

    [RelayCommand(CanExecute = nameof(CanConfigure))]
    private async Task RunLaunchAsync()
    {
        var plan = GetLaunchSettings();
        var daily = GetDailyOptions();
        var mirror = GetMirrorOptions();
        try
        {
            if (!plan.Daily && !plan.Harvest && !plan.Mirror) throw new ArgumentException("请至少选择一项任务");
            DailyPlan.Validate(daily);
            if (plan.Mirror) MirrorPlan.Validate(mirror);
            SaveDesktopSettings();
        }
        catch (Exception exception) { Error = exception.Message; return; }
        if (RunTasksInClone)
        {
            await RunInCloneAsync(new(CloneTaskRequest.LaunchKind, RepositoryRoot, OcrModelsDirectory,
                GameLanguage, GameTheme, Daily: daily, Mirror: mirror, Launch: plan));
            return;
        }
        var context = NewTaskContext();
        RequestMonitor();
        await RunAsync(token => GameTasks.RunLaunchAsync(context, plan, daily, mirror, SaveMirrorQueueAsync, token), "launch");
    }

    private async Task SaveMirrorQueueAsync(MirrorTeamOptions[] teams, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        await Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() => { ReplaceMirrorTeams(teams); SaveDesktopSettings(); });
    }
}
