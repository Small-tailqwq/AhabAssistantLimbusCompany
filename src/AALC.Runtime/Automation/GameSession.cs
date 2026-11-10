using System.Text.Json;
using System.Text.RegularExpressions;
using AALC.Core.Features.Daily;
using AALC.Core.Features.Mail;
using AALC.Runtime.Mail;

namespace AALC.Runtime.Automation;

public sealed class GameSession(IGameVision vision, IGameInput input, IRunClock clock,
    Action<RunEvent> publish, TimeSpan timeout, string stage = "Daily", IGameRestarter? restarter = null) : IGameSession
{
    private const int MaxRestarts = 2;
    private int restarts;
    private static readonly ImageQuery[] ConnectionQueries = [new("base/connecting_assets.png"),
        new("base/retry_countdown.png"), new("base/retry.png", 0.9), new("base/try_again.png")];
    private static readonly ImageQuery[] TutorialQueries = [new("home/first_prompt_assets.png"),
        new("home/back_assets.png", Search: SearchMode.Normal)];
    private readonly string runId = Guid.NewGuid().ToString("N");
    private GameFrame? latest;
    private TimeSpan nextTextDialogInspection;
    public TimeSpan Elapsed => clock.Elapsed;
    public int Observations { get; private set; }

    public ValueTask<GameFrame> ObserveAsync(IReadOnlyList<ImageQuery> queries, CancellationToken cancellationToken) =>
        ObserveCoreAsync(queries, true, cancellationToken);

    public ValueTask<GameFrame> ObserveControlsAsync(IReadOnlyList<ImageQuery> queries, CancellationToken cancellationToken) =>
        ObserveCoreAsync(queries, false, cancellationToken);

    private async ValueTask<GameFrame> ObserveCoreAsync(IReadOnlyList<ImageQuery> queries, bool inspectTextDialogs,
        CancellationToken cancellationToken)
    {
        var all = queries.Concat(ConnectionQueries).Concat(TutorialQueries).Distinct().ToArray();
        var tutorialDismissals = 0;
        var retryAt = TimeSpan.MinValue;
        var started = Elapsed;
        TimeSpan? disabledSince = null;
        var serverWasVisible = false;
        while (true)
        {
            Check(cancellationToken);
            var observationStarted = Elapsed;
            latest = await vision.ObserveAsync(all, cancellationToken);
            Observations++;
            Check(cancellationToken);
            Emit("automation.observe", "Observed", null, JsonSerializer.Serialize(new { queries = all, latest.Targets,
                durationMilliseconds = (Elapsed - observationStarted).TotalMilliseconds }));
            if (IsTutorial(latest))
            {
                if (tutorialDismissals++ >= 3)
                    throw new InvalidOperationException("新手提示关闭后仍未消失，请检查游戏界面");
                if (latest.Find("home/back_assets.png") is { } back)
                    await ClickAsync(latest, back.Center, "automation.tutorial.dismiss", cancellationToken);
                else
                    await KeyAsync(latest, GameKey.Escape, "automation.tutorial.dismiss", cancellationToken);
                await DelayAsync(TimeSpan.FromSeconds(1), cancellationToken);
                continue;
            }
            var inspectText = latest.Find("base/try_again.png") is not null
                || inspectTextDialogs && (serverWasVisible || Elapsed >= nextTextDialogInspection
                    || !latest.Targets.Any(target => queries.Any(query => query.Asset == target.Asset)));
            IReadOnlyList<RecognizedText> text = inspectText ? await ReadTextAsync(latest, cancellationToken) : [];
            if (inspectText) nextTextDialogInspection = Elapsed + TimeSpan.FromSeconds(2);
            if (text.Any(x => x.Text.Contains("游戏无法运行")) && text.Any(x => x.Text.Contains("即将关闭游戏")))
                await RestartOrThrowAsync(new InvalidOperationException("游戏报告无法运行，即将关闭；当前会话已不可恢复，需要重新进入游戏"), cancellationToken);
            var error = text.FirstOrDefault(x => x.Text.Contains("服务器发生错误"));
            var later = text.FirstOrDefault(x => x.Text.Contains("请稍后再试"));
            var close = text.FirstOrDefault(x => x.Text.Contains("关闭"));
            var retry = text.FirstOrDefault(x => x.Text.Contains("重试"));
            var server = error is not null && later is not null && close is not null && retry is not null
                && Center(retry).X > Center(close).X
                && Math.Min(Center(retry).Y, Center(close).Y) > Math.Max(error.Bounds.Bottom, later.Bounds.Bottom);
            serverWasVisible = server;
            if (server)
            {
                if (Elapsed - started > TimeSpan.FromSeconds(120))
                    await RestartOrThrowAsync(new TimeoutException("服务器错误持续超过两分钟"), cancellationToken);
                if (Regex.IsMatch(retry!.Text, @"重试\s*\d+")) disabledSince = null;
                else if (RetryEnabled(latest, retry.Bounds))
                {
                    disabledSince = null;
                    if (retryAt == TimeSpan.MinValue || Elapsed - retryAt >= TimeSpan.FromSeconds(5))
                    {
                        Report("daily.connection.retry", "服务器暂不可用，正在重试");
                        await ClickAsync(latest, Center(retry), "daily.connection.retry-server", cancellationToken);
                        retryAt = Elapsed;
                    }
                }
                else
                {
                    disabledSince ??= Elapsed;
                    if (Elapsed - disabledSince >= TimeSpan.FromSeconds(15))
                        await RestartOrThrowAsync(new InvalidOperationException("服务器重试按钮持续不可用，请处理游戏提示后重试"), cancellationToken);
                }
            }
            else if (latest.Find("base/connecting_assets.png") is null && latest.Find("base/retry_countdown.png") is null
                && latest.Find("base/retry.png") is null && latest.Find("base/try_again.png") is null) return latest;
            else if (Elapsed - started > TimeSpan.FromSeconds(120))
                await RestartOrThrowAsync(new TimeoutException("网络连接等待超过两分钟"), cancellationToken);
            else if (latest.Find("base/retry.png") is { } button
                && (retryAt == TimeSpan.MinValue || Elapsed - retryAt >= TimeSpan.FromSeconds(5)))
            {
                Report("daily.connection.retry", "正在重试游戏连接");
                await ClickAsync(latest, button.Center, "daily.connection.retry-template", cancellationToken);
                retryAt = Elapsed;
            }
            await DelayAsync(TimeSpan.FromMilliseconds(500), cancellationToken);
        }
    }

    public async ValueTask<IReadOnlyList<RecognizedText>> ReadTextAsync(GameFrame frame,
        CancellationToken cancellationToken, PixelRect? region = null, int scale = 1, TextPreprocessing preprocessing = TextPreprocessing.None)
    {
        Check(cancellationToken);
        var started = Elapsed;
        var text = await vision.ReadTextAsync(frame, cancellationToken, region, scale, preprocessing);
        Check(cancellationToken);
        Emit("automation.ocr", "Observed", null, JsonSerializer.Serialize(new { region, scale, preprocessing,
            durationMilliseconds = (Elapsed - started).TotalMilliseconds, text }));
        return text;
    }

    public async ValueTask ClickAsync(GameFrame frame, PixelPoint target, string rule, CancellationToken cancellationToken)
    {
        CheckFrame(frame, cancellationToken);
        Emit(rule, "Click", $"{target.X},{target.Y}");
        CheckFrame(frame, cancellationToken);
        await input.ClickAtAsync(target, frame.Identity, cancellationToken);
        Emit(rule, "Sent", $"{target.X},{target.Y}");
        Check(cancellationToken);
    }

    public async ValueTask KeyAsync(GameFrame frame, GameKey key, string rule, CancellationToken cancellationToken)
    {
        CheckFrame(frame, cancellationToken);
        Emit(rule, "Key", key.ToString());
        CheckFrame(frame, cancellationToken);
        await input.KeyPressAsync(key, frame.Identity, cancellationToken);
        Emit(rule, "Sent", key.ToString());
        Check(cancellationToken);
    }

    public async ValueTask DragAsync(GameFrame frame, PixelPoint from, PixelPoint to, TimeSpan duration,
        string rule, CancellationToken cancellationToken)
    {
        CheckFrame(frame, cancellationToken);
        var target = $"{from.X},{from.Y}>{to.X},{to.Y}";
        Emit(rule, "Drag", target);
        CheckFrame(frame, cancellationToken);
        await input.DragAsync(from, to, duration, frame.Identity, cancellationToken);
        Emit(rule, "Sent", target);
        Check(cancellationToken);
    }

    public async ValueTask DragPathAsync(GameFrame frame, IReadOnlyList<PixelPoint> path, TimeSpan duration,
        string rule, CancellationToken cancellationToken)
    {
        CheckFrame(frame, cancellationToken);
        var target = string.Join(">", path.Select(point => $"{point.X},{point.Y}"));
        Emit(rule, "Drag", target);
        CheckFrame(frame, cancellationToken);
        await input.DragPathAsync(path, duration, frame.Identity, cancellationToken);
        Emit(rule, "Sent", target);
        Check(cancellationToken);
    }

    public async ValueTask DelayAsync(TimeSpan duration, CancellationToken cancellationToken)
    {
        Check(cancellationToken);
        var started = Elapsed;
        await clock.DelayAsync(duration < timeout - Elapsed ? duration : timeout - Elapsed, cancellationToken);
        Emit("automation.delay", "Wait", null, JsonSerializer.Serialize(new
            { requestedMilliseconds = duration.TotalMilliseconds, durationMilliseconds = (Elapsed - started).TotalMilliseconds }));
        Check(cancellationToken);
    }

    public void Report(string rule, string message) => Emit(rule, "Progress", null, message);

    public bool CanRestartGame => restarter is not null && restarts < MaxRestarts;

    public void ExtendDeadline(TimeSpan duration) => timeout += duration;

    // 与旧版 retry 一致：连接或服务器错误长时间不可恢复时重启游戏，由调用方回到主界面续跑。
    private async ValueTask RestartOrThrowAsync(Exception failure, CancellationToken cancellationToken)
    {
        if (await RestartGameAsync(failure.Message, cancellationToken)) throw new GameRestartedException(failure.Message);
        throw failure;
    }

    public async ValueTask<bool> RestartGameAsync(string reason, CancellationToken cancellationToken)
    {
        Check(cancellationToken);
        if (restarter is null || restarts >= MaxRestarts) return false;
        restarts++;
        Report("game.restart", $"{reason}，重启游戏（第 {restarts}/{MaxRestarts} 次）");
        await restarter.RestartAsync(cancellationToken);
        latest = null;
        Report("game.restarted", "游戏已重新启动");
        Check(cancellationToken);
        return true;
    }

    private void Emit(string rule, string action, string? target = null, string? detail = null) =>
        publish(new(runId, latest?.Identity.Id ?? 0, stage, rule, action, target, Elapsed.TotalMilliseconds, detail));

    private void Check(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (Elapsed >= timeout) throw new TimeoutException("任务超过运行时限");
    }

    private void CheckFrame(GameFrame frame, CancellationToken cancellationToken)
    {
        Check(cancellationToken);
        if (latest?.Identity != frame.Identity) throw new InvalidOperationException("输入使用了过期观察帧");
    }

    private static PixelPoint Center(RecognizedText text) =>
        new(text.Bounds.X + text.Bounds.Width / 2, text.Bounds.Y + text.Bounds.Height / 2);

    private static bool IsTutorial(GameFrame frame)
    {
        if (frame.Find("home/first_prompt_assets.png") is not { } arrow) return false;
        // 教程与采光翻页箭头同形；Clam 搜索边距会包含邻近翻页按钮，只接受教程固定布局的位置。
        // 1440 高度资源 bbox 为 (2364,665)-(2455,775)，中心容差限于该框中央附近。
        var center = frame.Point(2410, 720);
        return Math.Abs(arrow.Center.X - center.X) <= 24 * frame.Scale
            && Math.Abs(arrow.Center.Y - center.Y) <= 28 * frame.Scale;
    }

    private static bool RetryEnabled(GameFrame frame, PixelRect bounds)
    {
        var count = 0;
        for (var y = Math.Max(0, bounds.Y - 4); y < Math.Min(frame.Identity.Height, bounds.Bottom + 4); y++)
        for (var x = Math.Max(0, bounds.X - 4); x < Math.Min(frame.Identity.Width, bounds.Right + 4); x++)
        {
            var offset = (y * frame.Identity.Width + x) * 4;
            var b = frame.Pixels.Bgra[offset]; var g = frame.Pixels.Bgra[offset + 1]; var r = frame.Pixels.Bgra[offset + 2];
            var maximum = Math.Max(r, Math.Max(g, b));
            var minimum = Math.Min(r, Math.Min(g, b));
            if (maximum > 100 && (maximum - minimum) * 255.0 / maximum > 20 && ++count >= 8) return true;
        }
        return false;
    }
}
