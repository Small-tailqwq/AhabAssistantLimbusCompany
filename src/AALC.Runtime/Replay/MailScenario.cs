using System.Text.Json;
using System.Text.Json.Serialization;
using AALC.Core.Features.Mail;
using AALC.Runtime.Mail;

namespace AALC.Runtime.Replay;

public sealed record ScenarioStep(MailControl[] Visible, MailControl? ExpectedClick = null);
public sealed record MailScenario(string Id, string Evidence, string Source, ScenarioStep[] Steps,
    RunOutcome ExpectedOutcome = RunOutcome.Completed, bool HoldLastFrame = false,
    string ExpectedReason = "mail.returned-home")
{
    public static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase, WriteIndented = true,
        Converters = { new JsonStringEnumConverter() }
    };
    public static MailScenario Load(string path) =>
        JsonSerializer.Deserialize<MailScenario>(File.ReadAllText(path), Json)
        ?? throw new InvalidDataException("场景文件为空");
}

public sealed record ScenarioAcceptance(bool Passed, string Reason, bool AllStepsObserved,
    bool AllExpectedActionsPerformed);

public sealed class ScenarioSession(MailScenario scenario) : IMailObserver, IMailInput, IRunClock
{
    private int step;
    private bool clicked;
    private long frame;
    private readonly bool[] observed = new bool[scenario.Steps.Length];
    private readonly bool[] actionsPerformed = new bool[scenario.Steps.Length];
    private string? violation;
    public TimeSpan Elapsed { get; private set; }
    public List<MailControl> Actions { get; } = [];
    public bool AllStepsObserved => observed.Length > 0 && observed.All(value => value);
    public bool AllExpectedActionsPerformed => scenario.Steps
        .Select((value, index) => !value.ExpectedClick.HasValue || actionsPerformed[index]).All(value => value);

    public ScenarioAcceptance Evaluate(RunResult result)
    {
        var reason = violation is not null ? "scenario.contract-violation"
            : result.Outcome != scenario.ExpectedOutcome ? "scenario.outcome-mismatch"
            : result.Reason != scenario.ExpectedReason ? "scenario.reason-mismatch"
            : !AllStepsObserved ? "scenario.unobserved-steps"
            : !AllExpectedActionsPerformed ? "scenario.missing-actions"
            : "scenario.accepted";
        return new(reason == "scenario.accepted", reason, AllStepsObserved, AllExpectedActionsPerformed);
    }

    private InvalidDataException ContractViolation(string message)
    {
        violation = message;
        return new(message);
    }

    public ValueTask<MailObservation> ObserveAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (scenario.Steps.Length == 0 || step >= scenario.Steps.Length)
            throw ContractViolation("场景缺少下一次观察");
        observed[step] = true;
        var hits = scenario.Steps[step].Visible.Select((control, index) =>
            new TemplateHit(control, new PixelPoint(100 + index * 50, 100), 1, "scenario:" + control)).ToArray();
        return ValueTask.FromResult(new MailObservation(new(++frame, 2560, 1440, 0, Elapsed.Ticks), hits));
    }

    public ValueTask ClickAsync(TemplateHit target, FrameIdentity identity, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (identity.Id != frame || clicked || scenario.Steps[step].ExpectedClick != target.Control)
            throw ContractViolation($"场景 {scenario.Id} 第 {step + 1} 步出现非预期动作 {target.Control}");
        clicked = true;
        actionsPerformed[step] = true;
        Actions.Add(target.Control);
        return ValueTask.CompletedTask;
    }

    public ValueTask DelayAsync(TimeSpan delay, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (scenario.Steps[step].ExpectedClick.HasValue && !clicked)
            throw ContractViolation($"场景 {scenario.Id} 第 {step + 1} 步缺少预期动作");
        Elapsed += delay;
        clicked = false;
        if (step < scenario.Steps.Length - 1) step++;
        else if (!scenario.HoldLastFrame) throw ContractViolation("场景耗尽但流程没有完成");
        return ValueTask.CompletedTask;
    }
}

