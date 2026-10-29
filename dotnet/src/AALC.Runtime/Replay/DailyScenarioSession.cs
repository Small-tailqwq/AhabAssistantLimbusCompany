using AALC.Core.Features.Daily;
using AALC.Core.Features.Mail;
using AALC.Runtime.Daily;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;

namespace AALC.Runtime.Replay;

public sealed class DailyScenarioSession(DailyScenario scenario, Action<RunEvent>? publish = null) : IGameSession
{
    private readonly string runId = Guid.NewGuid().ToString("N");
    private readonly bool[] observed = new bool[scenario.Steps.Length];
    private readonly int[] performed = new int[scenario.Steps.Length];
    private int step;
    private long frameId;
    private int frameStep;
    private bool violation;
    public TimeSpan Elapsed { get; private set; }
    public int Observations { get; private set; }
    public List<DailyScenarioAction> Actions { get; } = [];
    public bool AllStepsObserved => observed.Length > 0 && observed.All(value => value);
    public bool AllExpectedActionsPerformed => scenario.Steps
        .Select((value, index) => performed[index] == value.ExpectedActions.Length).All(value => value);

    public ScenarioAcceptance Evaluate(RunResult result)
    {
        var reason = violation ? "scenario.contract-violation"
            : result.Outcome != scenario.ExpectedOutcome ? "scenario.outcome-mismatch"
            : result.Reason != scenario.ExpectedReason ? "scenario.reason-mismatch"
            : !AllStepsObserved ? "scenario.unobserved-steps"
            : !AllExpectedActionsPerformed ? "scenario.missing-actions" : "scenario.accepted";
        return new(reason == "scenario.accepted", reason, AllStepsObserved, AllExpectedActionsPerformed);
    }

    public ValueTask<GameFrame> ObserveAsync(IReadOnlyList<ImageQuery> queries, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (scenario.Steps.Length == 0) throw ContractViolation("日常场景缺少观察步骤");
        if (observed[step] && scenario.Steps[step].AdvanceAfterObservation
            && performed[step] == scenario.Steps[step].ExpectedActions.Length)
        {
            if (step == scenario.Steps.Length - 1) throw ContractViolation("日常场景没有声明等待帧的后继");
            step++;
        }
        observed[step] = true;
        frameStep = step;
        var identity = new FrameIdentity(++frameId, scenario.Width, scenario.Height, 0, Elapsed.Ticks);
        var targets = scenario.Steps[step].Targets.Where(target => double.IsFinite(target.Score)
                && queries.Any(query => query.Asset == target.Asset && target.Score >= query.Threshold))
            .Select(target => new VisualTarget(target.Asset, target.Center,
                target.Bounds ?? new(target.Center.X - 20, target.Center.Y - 10, 40, 20), target.Score)).ToArray();
        Observations++;
        Emit("automation.observe", "Observed");
        return ValueTask.FromResult(new GameFrame(new(identity, new byte[checked(scenario.Width * scenario.Height * 4)]), targets));
    }

    public ValueTask<IReadOnlyList<RecognizedText>> ReadTextAsync(GameFrame frame, CancellationToken cancellationToken,
        PixelRect? region = null, int scale = 1, TextPreprocessing preprocessing = TextPreprocessing.None)
    {
        CheckFrame(frame, cancellationToken);
        var text = scenario.Steps[frameStep].Text ?? [];
        return ValueTask.FromResult<IReadOnlyList<RecognizedText>>(text.Where(entry => region is null
            || region.Value.Contains(entry.Bounds.X + entry.Bounds.Width / 2, entry.Bounds.Y + entry.Bounds.Height / 2)).ToArray());
    }

    public ValueTask ClickAsync(GameFrame frame, PixelPoint target, string rule, CancellationToken cancellationToken)
    {
        CheckFrame(frame, cancellationToken);
        CheckPoint(target);
        Perform(new(rule, Target: target));
        return ValueTask.CompletedTask;
    }

    public ValueTask KeyAsync(GameFrame frame, GameKey key, string rule, CancellationToken cancellationToken)
    {
        CheckFrame(frame, cancellationToken);
        Perform(new(rule, DailyScenarioActionKind.Key, Key: key));
        return ValueTask.CompletedTask;
    }

    public ValueTask DragAsync(GameFrame frame, PixelPoint from, PixelPoint to, TimeSpan duration,
        string rule, CancellationToken cancellationToken)
    {
        CheckFrame(frame, cancellationToken);
        CheckPoint(from); CheckPoint(to);
        Perform(new(rule, DailyScenarioActionKind.Drag, From: from, To: to));
        Elapsed += duration;
        return ValueTask.CompletedTask;
    }

    public ValueTask DelayAsync(TimeSpan duration, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        Elapsed += duration;
        return ValueTask.CompletedTask;
    }

    public void Report(string rule, string message) => Emit(rule, "Progress", message);

    private void Perform(DailyScenarioAction action)
    {
        var current = scenario.Steps[step];
        var index = performed[step];
        if (!observed[step] || index >= current.ExpectedActions.Length)
            throw ContractViolation($"场景 {scenario.Id} 第 {step + 1} 步出现额外动作 {action.Rule}");
        var expected = current.ExpectedActions[index];
        if (expected.Rule != action.Rule || expected.Kind != action.Kind
            || expected.Target.HasValue && expected.Target != action.Target
            || expected.Key.HasValue && expected.Key != action.Key
            || expected.From.HasValue && expected.From != action.From
            || expected.To.HasValue && expected.To != action.To)
            throw ContractViolation($"场景 {scenario.Id} 第 {step + 1} 步预期 {expected.Rule}，实际 {action.Rule}");
        performed[step]++;
        Actions.Add(action);
        Emit(action.Rule, "Sent", target: action.Target?.ToString() ?? action.Key?.ToString()
            ?? $"{action.From}>{action.To}");
        if (performed[step] == current.ExpectedActions.Length && !current.AdvanceAfterObservation
            && step < scenario.Steps.Length - 1) step++;
    }

    private void CheckFrame(GameFrame frame, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (frame.Identity.Id != frameId) throw ContractViolation("日常场景输入使用了过期观察帧");
    }

    private void CheckPoint(PixelPoint point)
    {
        if (point.X < 0 || point.X >= scenario.Width || point.Y < 0 || point.Y >= scenario.Height)
            throw ContractViolation("日常场景输入超出客户区");
    }

    private InvalidDataException ContractViolation(string message)
    {
        violation = true;
        return new(message);
    }

    private void Emit(string rule, string action, string? detail = null, string? target = null) =>
        publish?.Invoke(new(runId, frameId, "Daily", rule, action, target, Elapsed.TotalMilliseconds, detail));
}
