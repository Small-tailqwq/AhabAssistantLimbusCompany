using AALC.Core.Automation;
using AALC.Runtime.Automation;
using AALC.Runtime.Daily;
using AALC.Runtime.Mail;
using AALC.Runtime.Replay;

var root = Path.GetFullPath(args[0]);
var source = DailyScenario.Load(Path.Combine(root, "scenarios/daily/daily-exp-thread-three.json"));
var failures = 0;
foreach (var (name, beforeCheckpoint, secondBatch, threadBatch) in new[]
{
    ("KeepCompletedCheckpoint", false, false, false),
    ("NoRepeatBeforeCheckpoint", true, false, false),
    ("ResumeNextExperienceBatch", true, true, false),
    ("ResumeThreadAfterExperience", true, false, true)
})
{
    var first = source.Steps.Take(10).ToArray();
    DailyScenarioStep[] steps;
    if (beforeCheckpoint)
    {
        first[9] = first[9] with { ExpectedActions = [new("daily.home.confirm-settlement", Target: new(550, 415))] };
        steps = threadBatch ? [.. first, .. source.Steps.Skip(10)]
            : [.. first, .. source.Steps.Take(10), source.Steps[^1]];
    }
    else steps = [.. first, .. source.Steps.Take(10), source.Steps[^1]];
    var scenario = source with { Options = source.Options with { ExpCount = secondBatch ? 6 : 3, ThreadCount = threadBatch ? 3 : 0 }, Steps = steps };
    var session = new RestartProbe(new(scenario), beforeCheckpoint);
    var result = await new DailyRunner(session, _ => throw new InvalidOperationException()).RunAsync(scenario.Options, default);
    var starts = session.Inner.Actions.Count(action => action.Rule == "battle.start");
    var planned = secondBatch || threadBatch ? 2 : 1;
    var recovered = session.Inner.Actions.Count(action => action.Rule == "daily.home.confirm-settlement");
    var pass = result.Outcome == RunOutcome.Completed && session.Faulted && starts == planned && recovered == (beforeCheckpoint ? 1 : 0);
    Console.WriteLine($"{(pass ? "PASS" : "FAIL")} {name}: outcome={result.Outcome}, restarts={(session.Faulted ? 1 : 0)}, battleStarts={starts}, plannedBatches={planned}, recoveredSettlements={recovered}, reason={result.Reason}");
    if (!pass) failures++;
}
return failures == 0 ? 0 : 1;

sealed class RestartProbe(DailyScenarioSession inner, bool beforeCheckpoint) : IGameSession
{
    public DailyScenarioSession Inner => inner;
    public bool Faulted { get; private set; }
    public TimeSpan Elapsed => inner.Elapsed;
    public int Observations => inner.Observations;
    public async ValueTask<GameFrame> ObserveAsync(IReadOnlyList<ImageQuery> queries, CancellationToken ct)
    {
        var frame = await inner.ObserveAsync(queries, ct);
        var text = await inner.ReadTextAsync(frame, ct);
        if (!Faulted && (beforeCheckpoint ? text.Any(item => item.Text == "战斗胜利")
                : inner.Actions.Any(action => action.Rule == "battle.confirm-settlement") && frame.Find("home/mail_assets.png") is not null))
        {
            Faulted = true;
            throw new GameRestartedException("synthetic server failure and restart at completed battle boundary");
        }
        return frame;
    }
    public ValueTask<IReadOnlyList<RecognizedText>> ReadTextAsync(GameFrame frame, CancellationToken ct, PixelRect? region = null,
        int scale = 1, TextPreprocessing preprocessing = TextPreprocessing.None) => inner.ReadTextAsync(frame, ct, region, scale, preprocessing);
    public ValueTask ClickAsync(GameFrame frame, PixelPoint target, string rule, CancellationToken ct) => inner.ClickAsync(frame, target, rule, ct);
    public ValueTask KeyAsync(GameFrame frame, GameKey key, string rule, CancellationToken ct) => inner.KeyAsync(frame, key, rule, ct);
    public ValueTask DragAsync(GameFrame frame, PixelPoint from, PixelPoint to, TimeSpan duration, string rule, CancellationToken ct) => inner.DragAsync(frame, from, to, duration, rule, ct);
    public ValueTask DelayAsync(TimeSpan duration, CancellationToken ct) => inner.DelayAsync(duration, ct);
    public void Report(string rule, string message) => inner.Report(rule, message);
}
