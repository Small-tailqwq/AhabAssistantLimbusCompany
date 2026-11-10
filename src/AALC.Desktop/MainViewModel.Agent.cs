using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using AALC.Platform.Windows;
using AALC.Runtime;
using AALC.Runtime.Agent;
using AALC.Runtime.Configuration;
using AALC.Runtime.DesktopClone;
using AALC.Runtime.Mail;
using AALC.Runtime.Tools;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.Input;

namespace AALC.Desktop;

public sealed record AgentEvent(long Sequence, DateTimeOffset At, RunEvent Event);

public partial class MainViewModel
{
    private AgentPipeServer? agentServer;
    private readonly Queue<AgentEvent> agentEvents = new();
    private long agentSequence;
    private string? agentTaskId;
    private string? agentTaskKind;
    private DateTimeOffset? agentStartedAt;
    private DateTimeOffset? agentFinishedAt;
    private RunResult? agentResult;
    private PixelFrame? agentFrame;
    private string? agentRecording;
    private bool applyingAgentSettings;
    private Task? agentOperation;
    private string? agentActivity;
    private GameWindow? agentIdleWindow;
    private string? agentActionToken;
    private IDisposable? agentWindowExpiry;

    public void StartAgentServer()
    {
        try
        {
            agentServer = new(settingsStore.DirectoryPath, async (request, ct) =>
            {
                return await Dispatcher.UIThread.InvokeAsync(() => DispatchAgentAsync(request, ct));
            });
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        { Error = $"Agent 接口启动失败：{exception.Message}"; }
    }

    public void DisposeAgentServer() { ReleaseAgentWindow(); agentServer?.Dispose(); }

    private void ReleaseAgentWindow()
    {
        agentWindowExpiry?.Dispose(); agentWindowExpiry = null;
        agentIdleWindow?.Dispose(); agentIdleWindow = null;
        agentActionToken = null;
    }

    private void BeginAgentRun(string kind)
    {
        ReleaseAgentWindow();
        agentTaskId = Guid.NewGuid().ToString("N");
        agentTaskKind = kind;
        agentStartedAt = DateTimeOffset.UtcNow;
        agentFinishedAt = null;
        agentResult = null;
        agentRecording = null;
        agentFrame = null;
        agentEvents.Clear();
    }

    private void RecordAgentEvent(RunEvent item)
    {
        if (item.Rule == "run.recording") agentRecording = item.Target;
        agentEvents.Enqueue(new(++agentSequence, DateTimeOffset.UtcNow, item));
        while (agentEvents.Count > 1000) agentEvents.Dequeue();
    }

    private static AgentEvent? EventSummary(AgentEvent? item)
    {
        if (item is null) return null;
        var detail = item.Event.Rule.StartsWith("automation.", StringComparison.Ordinal) ? null : item.Event.Detail;
        if (detail is { Length: > 512 }) detail = detail[..512] + "…";
        return item with { Event = item.Event with { Detail = detail } };
    }

    private object AgentStatus() => new
    {
        processId = Environment.ProcessId, profile = settingsStore.DirectoryPath,
        isRunning = IsRunning, activity = agentActivity, status = Status, error = Error,
        taskId = agentTaskId, kind = agentTaskKind, startedAt = agentStartedAt, finishedAt = agentFinishedAt,
        result = agentResult is null ? null : new { outcome = agentResult.Outcome.ToString(), agentResult.Reason, agentResult.Observations, agentResult.ElapsedMilliseconds },
        recordingDirectory = agentRecording, lastSequence = agentSequence, lastEvent = EventSummary(agentEvents.LastOrDefault()),
        lastProgress = EventSummary(agentEvents.LastOrDefault(item => !item.Event.Rule.StartsWith("automation.", StringComparison.Ordinal))),
        frame = agentFrame is null ? null : new { identity = agentFrame.Identity, ageMilliseconds = Stopwatch.GetElapsedTime(agentFrame.Identity.CapturedAt).TotalMilliseconds },
        gameWindows = GameWindow.Find(), selectedWindow = SelectedWindow,
        clone = new { active = CloneActive, status = CloneStatus, error = CloneError }
    };

    private string ConfigurationRevision(DesktopSettings settings) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(
        AgentConfiguration.Revision(settings) + AgentConfiguration.Revision(settingsStore.Load()))));

    private object AgentConfigurationSnapshot()
    {
        var settings = CurrentSettings();
        return new { revision = ConfigurationRevision(settings), settings, profile = settingsStore.DirectoryPath, appliesTo = "next-run" };
    }

    private async Task<object> DispatchAgentAsync(AgentRequest request, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        var args = request.Arguments;
        switch (request.Operation)
        {
            case "status": return AgentStatus();
            case "config.get": return AgentConfigurationSnapshot();
            case "events":
            {
                var after = args.GetProperty("after").GetInt64();
                var limit = args.GetProperty("limit").GetInt32();
                if (after < 0 || limit is < 1 or > 200) throw new ArgumentException("after 须非负，limit 须为 1–200");
                var items = agentEvents.Where(item => item.Sequence > after).Take(limit).ToArray();
                return new { taskId = agentTaskId, events = items, nextCursor = items.LastOrDefault()?.Sequence ?? after,
                    oldestSequence = agentEvents.FirstOrDefault()?.Sequence, lastSequence = agentSequence };
            }
            case "config.patch":
            {
                RequireAgentIdle();
                if (CloneActive || CloneBusy) throw new InvalidOperationException("请先停止桌面分身再修改配置");
                var current = CurrentSettings();
                if (args.GetProperty("revision").GetString() != ConfigurationRevision(current))
                    throw new InvalidOperationException("配置已变化，请重新读取配置和 revision");
                var settings = AgentConfiguration.Patch(current, args.GetProperty("patch"));
                if (!Directory.Exists(Path.Combine(settings.RepositoryRoot, "assets", "images"))) throw new ArgumentException("资源仓库中没有 assets/images");
                if (!string.IsNullOrWhiteSpace(settings.OcrModelsDirectory) && !Directory.Exists(settings.OcrModelsDirectory))
                    throw new DirectoryNotFoundException("OCR 模型目录不存在");
                if (!string.IsNullOrWhiteSpace(settings.GameExecutablePath)) GameInstallation.RequireDirectory(Path.GetDirectoryName(settings.GameExecutablePath)!);
                settingsStore.Save(settings);
                applyingAgentSettings = true;
                try
                {
                    RepositoryRoot = settings.RepositoryRoot;
                    GameLanguage = settings.GameLanguage; GameTheme = settings.GameTheme;
                    SelectedLanguage = Languages.Single(item => item.Key == GameLanguage);
                    SelectedTheme = Themes.Single(item => item.Key == GameTheme);
                    GameDirectory = Path.GetDirectoryName(settings.GameExecutablePath) ?? "";
                    LoadDailySettings(settings); LoadMirrorSettings(settings);
                    LoadAppSettings(settings.App ?? new()); LoadCloneSettings(settings.DesktopClone ?? new());
                    var launch = settings.Launch ?? new();
                    LaunchDaily = launch.Daily; LaunchHarvest = launch.Harvest; LaunchMirror = launch.Mirror;
                    LoadScenarios();
                }
                finally { applyingAgentSettings = false; }
                return AgentConfigurationSnapshot();
            }
            case "task.start":
            {
                RequireAgentIdle();
                Error = "";
                agentOperation = args.GetProperty("kind").GetString() switch
                {
                    "launch" => RunLaunchAsync(), "daily" => RunDailyAsync(), "harvest" => RunHarvestAsync(), "mirror" => RunMirrorAsync(),
                    _ => throw new ArgumentException("kind 须为 launch、daily、harvest 或 mirror")
                };
                if (!IsRunning && Error.Length > 0) throw new InvalidOperationException(Error);
                return AgentStatus();
            }
            case "task.stop":
                if (args.TryGetProperty("taskId", out var id) && id.ValueKind == JsonValueKind.String && id.GetString() != agentTaskId)
                    throw new InvalidOperationException("任务编号已变化，拒绝停止其他任务");
                Stop();
                return AgentStatus();
            case "game.launch":
                RequireAgentIdle();
                agentOperation = LaunchGameAsync();
                return AgentStatus();
            case "game.close":
                RequireAgentIdle();
                agentOperation = CloseGameAsync();
                return AgentStatus();
            case "screenshot": return await AgentScreenshotAsync(ct);
            case "game.action":
            {
                RequireAgentIdle();
                if (args.GetProperty("actionToken").GetString() != agentActionToken || agentIdleWindow is null || agentFrame is null)
                    throw new InvalidOperationException("截图操作令牌已失效，请在空闲时重新获取截图");
                var window = agentIdleWindow;
                var frame = agentFrame.Identity;
                var action = args.GetProperty("action").GetString();
                PixelPoint? point = null;
                GameKey? key = null;
                if (action == "click") point = new(args.GetProperty("x").GetInt32(), args.GetProperty("y").GetInt32());
                else if (action == "key" && args.GetProperty("key").GetString() is { } name && Enum.TryParse<GameKey>(name, true, out var parsed) && Enum.IsDefined(parsed)) key = parsed;
                else throw new ArgumentException("action 须为 click（x/y）或 key（GameKey 名称）");
                agentActionToken = null;
                agentIdleWindow = null;
                agentWindowExpiry?.Dispose(); agentWindowExpiry = null;
                try
                {
                    await RunAsync(async token =>
                    {
                        using var linked = CancellationTokenSource.CreateLinkedTokenSource(ct, token);
                        Publish(new("", frame.Id, "Agent", "agent.action", "Requested", point?.ToString() ?? key?.ToString(), 0, action));
                        if (point is { } target) await window.ClickAtAsync(target, frame, linked.Token);
                        else await window.KeyPressAsync(key!.Value, frame, linked.Token);
                        return new(RunOutcome.Completed, "恢复动作已发送，请重新截图核对结果", 0, 0);
                    }, "game.action");
                }
                finally { window.Dispose(); }
                return AgentStatus();
            }
            default: throw new ArgumentException($"未知 Agent 操作：{request.Operation}");
        }
    }

    private void RequireAgentIdle()
    {
        if (IsRunning || agentOperation is { IsCompleted: false }) throw new InvalidOperationException("AAALC 正在运行，请先停止任务并等待 isRunning=false");
    }

    private async Task<object> AgentScreenshotAsync(CancellationToken ct)
    {
        var source = "observation";
        PixelFrame? capturedFrame = null;
        string? captureActionToken = null;
        if (!IsRunning && !CloneActive)
        {
            ReleaseAgentWindow();
            var selected = SelectedWindow is { } selection && GameWindow.Find().Contains(selection) ? selection : GameWindow.Find().FirstOrDefault();
            if (selected is null) throw new InvalidOperationException("未找到游戏窗口");
            // 截图期间也占用任务槽，UI 无法同时开始另一个运行器。
            var previousStatus = Status;
            await RunAsync(async token =>
            {
                using var linked = CancellationTokenSource.CreateLinkedTokenSource(ct, token);
                var window = new GameWindow(selected);
                try
                {
                    var captured = await window.CaptureAsync(linked.Token);
                    linked.Token.ThrowIfCancellationRequested();
                    capturedFrame = captured;
                    UpdatePreview(captured);
                    await Dispatcher.UIThread.InvokeAsync(() =>
                    {
                        agentIdleWindow = window;
                        agentActionToken = Guid.NewGuid().ToString("N");
                        captureActionToken = agentActionToken;
                        agentWindowExpiry = DispatcherTimer.RunOnce(ReleaseAgentWindow, TimeSpan.FromSeconds(5));
                    });
                }
                catch { window.Dispose(); throw; }
                return new(RunOutcome.Completed, "已获取游戏截图", 1, 0);
            }, "screenshot", recordAgentRun: false);
            source = "capture";
            if (capturedFrame is null) throw new InvalidOperationException(Error.Length > 0 ? Error : "截图已停止");
            Status = previousStatus;
        }
        var frame = capturedFrame ?? agentFrame ?? throw new InvalidOperationException("运行器尚未产生截图，请稍后重试");
        using var bitmap = CreateBitmap(frame);
        using var output = new MemoryStream();
        bitmap.Save(output);
        var directory = EvidencePaths.RequireExternalPath(Path.Combine(EvidencePaths.ResolveRoot(), "screenshots"));
        Directory.CreateDirectory(directory);
        var path = EvidencePaths.RequireExternalPath(Path.Combine(directory, $"agent-{DateTime.Now:yyyyMMdd-HHmmss-fff}-{Guid.NewGuid():N}.png"));
        var png = output.ToArray();
        await File.WriteAllBytesAsync(path, png, ct);
        return new { source = CloneActive ? "clone-preview" : source, frame = frame.Identity, ageMilliseconds = Stopwatch.GetElapsedTime(frame.Identity.CapturedAt).TotalMilliseconds,
            path, actionToken = captureActionToken, mimeType = "image/png", data = Convert.ToBase64String(png) };
    }

    [RelayCommand(CanExecute = nameof(CanConfigure))]
    private async Task LaunchGameAsync()
    {
        var executable = GameExecutable();
        var selected = SelectedWindow;
        await RunAsync(async token =>
        {
            using var host = await GameHost.OpenAsync(selected, executable, message => Publish(new("", 0, "Game", "game.launch", "Progress", null, 0, message)), token);
            return new(RunOutcome.Completed, "游戏窗口已就绪", 0, 0);
        }, "game.launch");
        if (agentResult?.Outcome == RunOutcome.Completed) RefreshWindows();
    }

    [RelayCommand(CanExecute = nameof(CanConfigure))]
    private async Task CloseGameAsync()
    {
        var selected = SelectedWindow is { } selection && GameWindow.Find().Contains(selection) ? selection : GameWindow.Find().FirstOrDefault();
        await RunAsync(async token =>
        {
            if (selected is not null)
            {
                await GameHost.CloseAsync(selected,
                    message => Publish(new("", 0, "Game", "game.close", "Progress", null, 0, message)), token);
            }
            return new(RunOutcome.Completed, "游戏已关闭", 0, 0);
        }, "game.close");
        Windows.Clear();
        foreach (var window in GameWindow.Find()) Windows.Add(window);
        SelectedWindow = Windows.FirstOrDefault();
    }

    [RelayCommand(CanExecute = nameof(CanConfigure))]
    private async Task RunHarvestAsync()
    {
        try { SaveDesktopSettings(); }
        catch (Exception exception) { Error = exception.Message; return; }
        var options = HarvestOptions(GetDailyOptions());
        if (RunTasksInClone)
        {
            await RunInCloneAsync(new(CloneTaskRequest.DailyKind, RepositoryRoot, OcrModelsDirectory, GameLanguage, GameTheme, Daily: options));
            return;
        }
        var context = NewTaskContext();
        RequestMonitor();
        await RunAsync(token => GameTasks.RunDailyAsync(context, options, token), "harvest");
    }
}
