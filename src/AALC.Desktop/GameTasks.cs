using System.IO;
using System.Diagnostics;
using System.Text.Json;
using AALC.Core.Features.Daily;
using AALC.Core.Features.Mirror;
using AALC.Platform.Windows;
using AALC.Runtime;
using AALC.Runtime.Automation;
using AALC.Runtime.Configuration;
using AALC.Runtime.Daily;
using AALC.Runtime.Mail;
using AALC.Runtime.Mirror;
using AALC.Vision;

namespace AALC.Desktop;

/// <param name="Selected">主桌面选中的窗口；分身内进程没有选择，使用会话内唯一的游戏窗口。</param>
/// <param name="LaunchArguments">窗口不存在时启动游戏的参数，见 <see cref="GameHost.OpenAsync"/>。</param>
internal sealed record GameTaskContext(string RepositoryRoot, string OcrModelsDirectory, TemplateOptions Templates,
    GameWindowInfo? Selected, string Executable, string LaunchArguments, Action<RunEvent> Publish, Action<PixelFrame> FrameCaptured);

/// <summary>主窗口与分身内进程共用的任务组装，二者运行同一套流程代码。</summary>
internal static class GameTasks
{
    public static async Task<RunResult> RunLaunchAsync(GameTaskContext context, LaunchSettings plan, DailyOptions daily,
        MirrorOptions mirror, Func<MirrorTeamOptions[], CancellationToken, Task> saveQueue, CancellationToken token)
    {
        var observations = 0;
        var elapsed = 0.0;
        if (plan.Daily || plan.Harvest)
        {
            var options = plan.Daily ? daily with { ConvertModules = plan.Harvest || daily.ConvertModules }
                : daily with { RunLuxcavation = false, ConvertModules = true, ClaimRewards = false };
            var result = await RunDailyAsync(context, options, token);
            if (result.Outcome != RunOutcome.Completed) return result;
            observations += result.Observations;
            elapsed += result.ElapsedMilliseconds;
        }
        token.ThrowIfCancellationRequested();
        if (plan.Mirror)
        {
            var result = await RunMirrorAsync(context, mirror, saveQueue, token);
            return result with { Observations = observations + result.Observations, ElapsedMilliseconds = elapsed + result.ElapsedMilliseconds };
        }
        return new(RunOutcome.Completed, "一键启动任务已完成", observations, elapsed);
    }

    private static string NewRecording(string kind)
    {
        var directory = EvidencePaths.RequireExternalPath(Path.Combine(EvidencePaths.ResolveRoot(), "recordings", kind, DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")));
        Directory.CreateDirectory(directory);
        return directory;
    }

    private static async Task<RunResult> RunRecordedAsync(GameTaskContext context, string kind, object options,
        Func<string, Action<RunEvent>, Task<RunResult>> operation, CancellationToken token)
    {
        RecordingStorage.Prune(EvidencePaths.ResolveRoot());
        var directory = NewRecording(kind);
        File.WriteAllText(Path.Combine(directory, "options.json"), JsonSerializer.Serialize(options));
        using var events = new StreamWriter(Path.Combine(directory, "events.jsonl")) { AutoFlush = true };
        void Report(RunEvent item) { events.WriteLine(JsonSerializer.Serialize(item)); context.Publish(item); }
        Report(new("", 0, kind, "run.recording", "Progress", directory, 0, directory));
        var started = Stopwatch.GetTimestamp();
        RunResult result;
        try { result = await operation(directory, Report); }
        catch (OperationCanceledException) when (token.IsCancellationRequested)
        {
            result = new(RunOutcome.Cancelled, "已停止", 0, Stopwatch.GetElapsedTime(started).TotalMilliseconds);
        }
        catch (Exception exception)
        {
            Report(new("", 0, kind, "run.error", "Error", null, Stopwatch.GetElapsedTime(started).TotalMilliseconds, exception.ToString()));
            result = new(RunOutcome.Failed, exception.Message, 0, Stopwatch.GetElapsedTime(started).TotalMilliseconds);
        }
        File.WriteAllText(Path.Combine(directory, "result.json"), JsonSerializer.Serialize(result));
        return result;
    }

    public static Task<RunResult> RunDailyAsync(GameTaskContext context, DailyOptions options, CancellationToken token) =>
        RunRecordedAsync(context, "daily", options, async (directory, report) =>
    {
        GameSession? session = null;
        using var window = await GameHost.OpenAsync(context.Selected, context.Executable,
            message => report(new("", 0, "Daily", "game.launch", "Progress", null, 0, message)), token, context.LaunchArguments);
        using var matcher = new TemplateMatcher(context.RepositoryRoot, context.Templates);
        using var observer = new GameObserver(window, matcher, context.OcrModelsDirectory, directory, RecordingStorage.KeptFrames);
        observer.FrameCaptured += context.FrameCaptured;
        session = new GameSession(observer, window, new SystemRunClock(), report, DailyRunner.TimeoutFor(options), restarter: window);
        await window.EnsureResolutionAsync(token);
        if (window.Launched) session.Report("game.launch", "已启动游戏");
        var runner = new DailyRunner(session, async cancellationToken =>
        {
            var mailObserver = new MailObserver(window, matcher, Path.Combine(directory, "mail"));
            mailObserver.FrameCaptured += context.FrameCaptured;
            return await new MailRunner(mailObserver, window, new SystemRunClock())
                .RunAsync(TimeSpan.FromSeconds(30), report, cancellationToken);
        });
        return await runner.RunAsync(options, token);
    }, token);

    public static Task<RunResult> RunMirrorAsync(GameTaskContext context, MirrorOptions options,
        Func<MirrorTeamOptions[], CancellationToken, Task> saveQueue, CancellationToken token) =>
        RunRecordedAsync(context, "mirror", options, async (directory, report) =>
    {
        using var map = new MirrorMapReader(Path.Combine(context.RepositoryRoot, "assets", "model", "best.onnx"),
            Path.Combine(EvidencePaths.ResolveRoot(), "learning", "maps"), directory);
        void Report(RunEvent item)
        {
            if (item.Rule is "mirror.route.entered" or "mirror.route.failed") map.CompleteLearningSegment();
            report(item);
        }
        GameSession? session = null;
        using var window = await GameHost.OpenAsync(context.Selected, context.Executable,
            message => Report(new("", 0, "Mirror", "game.launch", "Progress", null, 0, message)), token, context.LaunchArguments);
        using var matcher = new TemplateMatcher(context.RepositoryRoot, context.Templates);
        using var observer = new GameObserver(window, matcher, context.OcrModelsDirectory, directory, RecordingStorage.KeptFrames);
        observer.FrameCaptured += context.FrameCaptured;
        session = new GameSession(observer, window, new SystemRunClock(), Report, MirrorRunner.TimeoutFor(options), "Mirror", window);
        await window.EnsureResolutionAsync(token);
        if (window.Launched)
        {
            session.Report("game.launch", "已启动游戏");
            if (!await DailyNavigation.ReturnHomeAsync(session, token))
                return new(RunOutcome.Failed, "启动游戏后未能进入主界面", session.Observations, session.Elapsed.TotalMilliseconds);
        }
        var runner = new MirrorRunner(session, map, saveQueue);
        return await runner.RunAsync(options, token);
    }, token);
}
