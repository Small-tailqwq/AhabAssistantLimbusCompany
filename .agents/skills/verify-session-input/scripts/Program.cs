using AALC.Core.Automation;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;

var failures = 0;
foreach (var kind in new[] { "click", "key", "drag", "path" })
foreach (var mode in new[] { "ExpiredAtEntry", "StaleFrame", "DeadlineDuringPublication", "StaleDuringPublication" })
{
    var clock = new Clock();
    var input = new Input();
    GameSession session = null!;
    session = new GameSession(new Vision(), input, clock, item =>
    {
        if (mode == "DeadlineDuringPublication" && item.Action is "Click" or "Key" or "Drag") clock.Advance();
        if (mode == "StaleDuringPublication" && item.Action is "Click" or "Key" or "Drag")
            session.ObserveControlsAsync([], default).AsTask().GetAwaiter().GetResult();
    }, TimeSpan.FromSeconds(2));
    var frame = await session.ObserveControlsAsync([], default);
    if (mode == "ExpiredAtEntry") clock.Advance();
    if (mode == "StaleFrame") await session.ObserveControlsAsync([], default);
    string? error = null;
    try
    {
        await (kind switch
        {
            "click" => session.ClickAsync(frame, new(1, 1), "probe", default),
            "key" => session.KeyAsync(frame, GameKey.Enter, "probe", default),
            "drag" => session.DragAsync(frame, new(1, 1), new(2, 2), TimeSpan.FromMilliseconds(20), "probe", default),
            _ => session.DragPathAsync(frame, [new(1, 1), new(2, 2)], TimeSpan.FromMilliseconds(20), "probe", default)
        });
    }
    catch (Exception exception) when (exception is TimeoutException or InvalidOperationException) { error = exception.GetType().Name; }
    var pass = input.Sends == 0 && error is not null;
    Console.WriteLine($"{(pass ? "PASS" : "FAIL")} {mode}/{kind}: sends={input.Sends}, elapsedMs={clock.Elapsed.TotalMilliseconds}, error={error}");
    if (!pass) failures++;
}
return failures == 0 ? 0 : 1;

sealed class Clock : IRunClock
{
    public TimeSpan Elapsed { get; private set; }
    public void Advance() => Elapsed += TimeSpan.FromSeconds(2);
    public ValueTask DelayAsync(TimeSpan delay, CancellationToken ct) { ct.ThrowIfCancellationRequested(); Elapsed += delay; return ValueTask.CompletedTask; }
}
sealed class Input : IGameInput
{
    public int Sends { get; private set; }
    private ValueTask Send(CancellationToken ct) { ct.ThrowIfCancellationRequested(); Sends++; return ValueTask.CompletedTask; }
    public ValueTask ClickAtAsync(PixelPoint point, FrameIdentity frame, CancellationToken ct) => Send(ct);
    public ValueTask KeyPressAsync(GameKey key, FrameIdentity frame, CancellationToken ct) => Send(ct);
    public ValueTask DragAsync(PixelPoint from, PixelPoint to, TimeSpan duration, FrameIdentity frame, CancellationToken ct) => Send(ct);
    public ValueTask DragPathAsync(IReadOnlyList<PixelPoint> path, TimeSpan duration, FrameIdentity frame, CancellationToken ct) => Send(ct);
}
sealed class Vision : IGameVision
{
    private long id;
    public ValueTask<GameFrame> ObserveAsync(IReadOnlyList<ImageQuery> queries, CancellationToken ct) =>
        ValueTask.FromResult(new GameFrame(new(new(++id, 128, 96, 1, 0), new byte[128 * 96 * 4]), []));
    public ValueTask<IReadOnlyList<RecognizedText>> ReadTextAsync(GameFrame frame, CancellationToken ct, PixelRect? region = null,
        int scale = 1, TextPreprocessing preprocessing = TextPreprocessing.None) => ValueTask.FromResult<IReadOnlyList<RecognizedText>>([]);
}
