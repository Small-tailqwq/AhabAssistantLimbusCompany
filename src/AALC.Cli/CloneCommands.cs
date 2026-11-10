using System.Text.Json;
using AALC.Core.Features.Daily;
using AALC.Core.Features.Mirror;
using AALC.Platform.Windows.DesktopClone;
using AALC.Runtime;
using AALC.Runtime.Configuration;
using AALC.Runtime.DesktopClone;
using AALC.Runtime.Mail;

namespace AALC.Cli;

/// <summary>
/// 无窗口的分身实机验证：隐藏宿主启动分身，核对开关回显，运行不消耗资源的日常并验证停止，最后注销。
/// 不打开可见窗口、不抢焦点，主桌面可以继续运行其他自动化。
/// </summary>
internal static class CloneCommands
{
    private static readonly TimeSpan StartTimeout = TimeSpan.FromSeconds(150);
    private static readonly TimeSpan EchoTimeout = TimeSpan.FromSeconds(5);
    private static readonly TimeSpan RunTimeout = TimeSpan.FromMinutes(6);
    private static readonly TimeSpan MirrorRunTimeout = TimeSpan.FromMinutes(90);
    private static readonly TimeSpan LogoffTimeout = TimeSpan.FromSeconds(30);

    private sealed class Observer(Action<string> report, string? framePath = null) : ICloneRunObserver
    {
        public int Frames { get; private set; }
        public TaskCompletionSource FirstEvent { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public void OnEvent(RunEvent item)
        {
            report($"event {item.Rule} {item.Detail}");
            FirstEvent.TrySetResult();
        }
        public void OnFrame(long id, byte[] jpeg)
        {
            if (Frames++ == 0) report($"first frame {id} {jpeg.Length} bytes");
            if (framePath is null) return;
            try { File.WriteAllBytes(framePath, jpeg); }
            catch (IOException) { }
        }
        public void OnMirrorQueue(string path)
        {
            report($"mirror queue {path}");
            try { File.Delete(path); }
            catch (IOException) { }
        }
    }

    private static string LogDirectory(string dataRoot)
    {
        var logs = EvidencePaths.RequireExternalPath(Path.Combine(dataRoot, "clone", "logs"));
        Directory.CreateDirectory(logs);
        return logs;
    }

    private static Action<string> OpenReport(string logs, string prefix)
    {
        var output = new StreamWriter(Path.Combine(logs, $"{prefix}-{DateTime.Now:yyyyMMdd-HHmmss}.log")) { AutoFlush = true };
        var gate = new object();
        return message =>
        {
            var line = $"{DateTime.Now:HH:mm:ss.fff} {message}";
            lock (gate) { output.WriteLine(line); Console.WriteLine(line); }
        };
    }

    private static WindowsCloneSystem OpenSystem(string executable, string dataRoot)
    {
        var directory = Path.GetDirectoryName(executable)!;
        return new(Path.Combine(directory, "clone-host", "AAALC.CloneHost.exe"),
            start => (executable, CloneProtocol.WorkerArguments(start, dataRoot), directory));
    }

    /// <summary>
    /// 无窗口地在分身内运行镜牢并领取结算奖励，用保存的配置，配置文件只读，队伍轮换只记入日志。
    /// 进度写入日志，最新一帧写入 mirror-latest.jpg；在日志目录创建 stop-mirror 文件即协作式停止，然后注销。
    /// </summary>
    public static async Task<int> MirrorAsync(string[] args, CancellationToken ct)
    {
        if (args.Length != 3 || !int.TryParse(args[2], out var runs)) throw new ArgumentException("clone-mirror <AAALC.exe> <runs>");
        var executable = Path.GetFullPath(args[1]);
        var settings = SettingsStore.OpenDefault().Load();
        var options = (settings.Mirror ?? throw new InvalidDataException("没有保存的镜牢配置")) with { Runs = runs, ClaimRewards = true };
        MirrorPlan.Validate(options);
        var dataRoot = EvidencePaths.ResolveRoot();
        var logs = LogDirectory(dataRoot);
        var stopFile = Path.Combine(logs, "stop-mirror");
        File.Delete(stopFile);
        var Report = OpenReport(logs, "mirror");
        var system = OpenSystem(executable, dataRoot);
        var compatibility = system.CheckCompatibility(null);
        foreach (var item in compatibility.Items) Report($"check {item.Status} {item.Name}: {item.Detail}");
        if (!compatibility.Supported) return 1;
        using var controller = new DesktopCloneController(system, new ClonePipeServer($"AAALC.mirror.{Environment.ProcessId}", Report), Report);
        var passed = false;
        try
        {
            using var starting = CancellationTokenSource.CreateLinkedTokenSource(ct);
            starting.CancelAfter(StartTimeout);
            await controller.StartAsync(new(ShowWindow: false), starting.Token);
            Report($"ready session={controller.Snapshot.SessionId} runs={runs}");
            using var running = CancellationTokenSource.CreateLinkedTokenSource(ct);
            running.CancelAfter(MirrorRunTimeout * runs);
            using var watcher = new Timer(_ => { if (File.Exists(stopFile)) running.Cancel(); }, null, TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(1));
            var request = new CloneTaskRequest(CloneTaskRequest.MirrorKind, settings.RepositoryRoot, settings.OcrModelsDirectory,
                settings.GameLanguage, settings.GameTheme, Mirror: options);
            var observer = new Observer(Report, Path.Combine(logs, "mirror-latest.jpg"));
            var result = await controller.RunAsync(request.Save(), observer, running.Token);
            Report($"run {result.Outcome} {result.Reason} observations={result.Observations} frames={observer.Frames}");
            passed = result.Outcome == RunOutcome.Completed;
        }
        catch (Exception exception) when (exception is not OperationCanceledException || !ct.IsCancellationRequested)
        {
            Report($"failed {exception}");
        }
        finally
        {
            var stopped = await controller.ShutdownAsync(LogoffTimeout);
            var probe = system.ProbeChildSession();
            Report($"logoff stopped={stopped} child={probe.Id} stale={probe.Stale} state={controller.Snapshot.State}");
            passed = passed && stopped && probe.Id is null;
        }
        Report(passed ? "PASSED" : "FAILED");
        return passed ? 0 : 1;
    }

    public static async Task<int> VerifyAsync(string[] args, string? root, CancellationToken ct)
    {
        if (args.Length is < 2 or > 3 || (args.Length == 3 && args[2] != "--run"))
            throw new ArgumentException("clone-verify <AAALC.exe> [--run]");
        var executable = Path.GetFullPath(args[1]);
        var dataRoot = EvidencePaths.ResolveRoot();
        var Report = OpenReport(LogDirectory(dataRoot), "verify");
        var system = OpenSystem(executable, dataRoot);
        var compatibility = system.CheckCompatibility(null);
        foreach (var item in compatibility.Items) Report($"check {item.Status} {item.Name}: {item.Detail}");
        if (!compatibility.Supported) return 1;
        using var controller = new DesktopCloneController(system, new ClonePipeServer($"AAALC.verify.{Environment.ProcessId}", Report), Report);
        var passed = false;
        try
        {
            using var starting = CancellationTokenSource.CreateLinkedTokenSource(ct);
            starting.CancelAfter(StartTimeout);
            await controller.StartAsync(new(ShowWindow: false), starting.Token);
            Report($"ready session={controller.Snapshot.SessionId}");
            await VerifyToggleAsync(controller.SetMuted, () => controller.Snapshot.Muted, "mute", Report);
            await VerifyToggleAsync(controller.SetInputBlocked, () => controller.Snapshot.InputBlocked, "input", Report);
            passed = args.Length != 3 || await VerifyTasksAsync(controller, root, Report, ct);
        }
        catch (Exception exception) when (exception is not OperationCanceledException || !ct.IsCancellationRequested)
        {
            Report($"failed {exception}");
        }
        finally
        {
            var stopped = await controller.ShutdownAsync(LogoffTimeout);
            var probe = system.ProbeChildSession();
            Report($"logoff stopped={stopped} child={probe.Id} stale={probe.Stale} state={controller.Snapshot.State}");
            passed = passed && stopped && probe.Id is null;
        }
        Report(passed ? "PASSED" : "FAILED");
        return passed ? 0 : 1;
    }

    private static async Task VerifyToggleAsync(Action<bool> set, Func<bool> read, string name, Action<string> report)
    {
        foreach (var value in new[] { true, false })
        {
            set(value);
            using var timeout = new CancellationTokenSource(EchoTimeout);
            while (read() != value) await Task.Delay(50, timeout.Token);
            report($"toggle {name}={value} echoed");
        }
    }

    private static async Task<bool> VerifyTasksAsync(DesktopCloneController controller, string? repository, Action<string> report, CancellationToken ct)
    {
        var root = repository ?? throw new ArgumentException("找不到资源仓库");
        var models = Path.Combine(root, "assets", "models", "ocr");
        // 全部关闭后日常只回到主界面，用来验证分身内启动游戏和任务链路，不消耗游戏资源。
        var options = new DailyOptions { RunLuxcavation = false, ExpCount = 0, ThreadCount = 0, ConvertModules = false, ClaimRewards = false, BuyStamina = false };
        CloneTaskRequest Request() => new(CloneTaskRequest.DailyKind, root, models, "zh_cn", "default", Daily: options);

        var observer = new Observer(report);
        using (var running = CancellationTokenSource.CreateLinkedTokenSource(ct))
        {
            running.CancelAfter(RunTimeout);
            var completed = await controller.RunAsync(Request().Save(), observer, running.Token);
            report($"run {completed.Outcome} {completed.Reason} observations={completed.Observations} frames={observer.Frames}");
            if (completed.Outcome != RunOutcome.Completed) return false;
        }

        var stopping = new Observer(report);
        using var cancellation = CancellationTokenSource.CreateLinkedTokenSource(ct);
        var run = controller.RunAsync(Request().Save(), stopping, cancellation.Token);
        await Task.WhenAny(stopping.FirstEvent.Task, Task.Delay(TimeSpan.FromSeconds(30), ct));
        cancellation.Cancel();
        var stopped = await run;
        report($"stop {stopped.Outcome} {stopped.Reason} state={controller.Snapshot.State}");
        return stopped.Outcome != RunOutcome.Failed;
    }
}
