using AALC.Core.Features.Mail;
using AALC.Runtime.Mail;
using AALC.Runtime.Replay;
using Xunit;

namespace AALC.Core.Tests;

public sealed class MailTests
{
    private static MailObservation Frame(long id, params MailControl[] controls) =>
        new(new(id, 2560, 1440, 0, 0), controls.Select(c => new TemplateHit(c, new(10, 10), 0.9, c.ToString())).ToArray());

    [Theory]
    [InlineData("mail-rewards")]
    [InlineData("mail-empty")]
    [InlineData("mail-unknown")]
    public async Task SyntheticContractsMeetAllAcceptanceCriteria(string name)
    {
        var scenario = MailScenario.Load(Path.Combine(AppContext.BaseDirectory, "scenarios", name + ".json"));
        var session = new ScenarioSession(scenario);
        var events = new List<RunEvent>();
        var result = await new MailRunner(session, session, session).RunAsync(TimeSpan.FromSeconds(30), events.Add, default);
        var acceptance = session.Evaluate(result);
        Assert.True(acceptance.Passed, $"{acceptance.Reason}: {result.Outcome}, {result.Reason}");
        Assert.True(acceptance.AllStepsObserved);
        Assert.True(acceptance.AllExpectedActionsPerformed);
        Assert.NotEmpty(events);
        if (name != "mail-unknown") Assert.Single(session.Actions, c => c == MailControl.ClaimAll);
    }

    [Fact]
    public async Task CompletionCannotSkipAnExpectedActionOnTheLastFrame()
    {
        var source = MailScenario.Load(Path.Combine(AppContext.BaseDirectory, "scenarios", "mail-empty.json"));
        var steps = source.Steps.ToArray();
        steps[^1] = steps[^1] with { ExpectedClick = MailControl.HomeMail };
        var scenario = source with { Steps = steps };
        var session = new ScenarioSession(scenario);

        var result = await new MailRunner(session, session, session).RunAsync(TimeSpan.FromSeconds(30), _ => { }, default);
        var acceptance = session.Evaluate(result);

        Assert.Equal(RunOutcome.Completed, result.Outcome);
        Assert.True(acceptance.AllStepsObserved);
        Assert.False(acceptance.AllExpectedActionsPerformed);
        Assert.False(acceptance.Passed);
        Assert.Equal("scenario.missing-actions", acceptance.Reason);
    }

    [Fact]
    public async Task UnexpectedRuntimeErrorDoesNotSatisfyExpectedTimeout()
    {
        var scenario = MailScenario.Load(Path.Combine(AppContext.BaseDirectory, "scenarios", "mail-unknown.json"));
        var session = new ScenarioSession(scenario);
        var result = await new MailRunner(session, session, session).RunAsync(TimeSpan.FromSeconds(30), e =>
        {
            if (e.Action == "Wait") throw new InvalidOperationException("event-sink.failed");
        }, default);
        var acceptance = session.Evaluate(result);

        Assert.Equal(RunOutcome.Failed, result.Outcome);
        Assert.Equal("event-sink.failed", result.Reason);
        Assert.True(acceptance.AllStepsObserved);
        Assert.True(acceptance.AllExpectedActionsPerformed);
        Assert.False(acceptance.Passed);
        Assert.Equal("scenario.reason-mismatch", acceptance.Reason);
    }

    [Fact]
    public async Task ExhaustedScenarioIsAContractViolationEvenWhenTheFailureMatches()
    {
        var scenario = new MailScenario("exhausted", "synthetic-contract", "test", [new([])],
            RunOutcome.Failed, ExpectedReason: "场景耗尽但流程没有完成");
        var session = new ScenarioSession(scenario);
        var result = await new MailRunner(session, session, session).RunAsync(TimeSpan.FromSeconds(2), _ => { }, default);
        var acceptance = session.Evaluate(result);

        Assert.Equal(scenario.ExpectedOutcome, result.Outcome);
        Assert.Equal(scenario.ExpectedReason, result.Reason);
        Assert.False(acceptance.Passed);
        Assert.Equal("scenario.contract-violation", acceptance.Reason);
    }

    [Fact]
    public void AFrameIsOnlyObservedAfterTheObserverIsCalled()
    {
        var scenario = new MailScenario("unobserved", "synthetic-contract", "test", [new([])]);
        var acceptance = new ScenarioSession(scenario)
            .Evaluate(new(RunOutcome.Completed, "mail.returned-home", 0, 0));

        Assert.False(acceptance.AllStepsObserved);
        Assert.False(acceptance.Passed);
        Assert.Equal("scenario.unobserved-steps", acceptance.Reason);
    }

    [Fact]
    public void RewardConfirmationTakesPrecedenceOverBackgroundControls()
    {
        var decision = MailFlow.Decide(new(MailStage.Claiming), Frame(1, MailControl.Confirm, MailControl.Close, MailControl.ClaimAll));
        Assert.Equal(MailControl.Confirm, decision.Target!.Control);
    }

    [Fact]
    public void ARepeatedClaimButtonIsObservedBeforeClosing()
    {
        var first = MailFlow.Decide(new(MailStage.Claiming), Frame(1, MailControl.ClaimAll, MailControl.Close));
        Assert.Equal(DecisionKind.Wait, first.Kind);
        var second = MailFlow.Decide(first.Next, Frame(2, MailControl.ClaimAll, MailControl.Close));
        Assert.Equal(MailControl.Close, second.Target!.Control);
    }

    [Fact]
    public void UnknownFramesBreakConsecutiveEmptyMailboxObservations()
    {
        var first = MailFlow.Decide(new(MailStage.Claiming), Frame(1, MailControl.ClaimAll, MailControl.Close));
        var unknown = MailFlow.Decide(first.Next, Frame(2));
        var visible = MailFlow.Decide(unknown.Next, Frame(3, MailControl.ClaimAll, MailControl.Close));
        Assert.Equal(DecisionKind.Wait, visible.Kind);
        var repeated = MailFlow.Decide(visible.Next, Frame(4, MailControl.ClaimAll, MailControl.Close));
        Assert.Equal(MailControl.Close, repeated.Target!.Control);
    }

    [Fact]
    public void HomeBehindMailboxIsNotCompletion()
    {
        var decision = MailFlow.Decide(new(MailStage.Closing), Frame(1, MailControl.HomeMail, MailControl.Close));
        Assert.Equal(DecisionKind.Wait, decision.Kind);
        Assert.Equal(DecisionKind.Complete, MailFlow.Decide(decision.Next, Frame(2, MailControl.HomeMail)).Kind);
    }

    [Fact]
    public async Task CancellationAfterObservationPreventsInput()
    {
        using var cancellation = new CancellationTokenSource();
        var port = new TestPort(() => { cancellation.Cancel(); return Frame(1, MailControl.HomeMail); });
        var result = await new MailRunner(port, port, port).RunAsync(TimeSpan.FromSeconds(2), _ => { }, cancellation.Token);
        Assert.Equal(RunOutcome.Cancelled, result.Outcome);
        Assert.Equal(0, port.Clicks);
    }

    [Theory]
    [InlineData(2000)]
    [InlineData(2500)]
    public async Task ObservationAtOrAfterDeadlinePreventsInput(int observationMilliseconds)
    {
        var port = new TestPort(() => Frame(1, MailControl.HomeMail))
        {
            ObservationDuration = TimeSpan.FromMilliseconds(observationMilliseconds)
        };
        var result = await new MailRunner(port, port, port).RunAsync(TimeSpan.FromSeconds(2), _ => { }, default);
        Assert.Equal(RunOutcome.Failed, result.Outcome);
        Assert.Equal("mail.timeout", result.Reason);
        Assert.Equal(1, result.Observations);
        Assert.Equal(0, port.Clicks);
    }

    [Fact]
    public async Task SlowEventPublicationCannotSendInputAfterDeadline()
    {
        var port = new TestPort(() => Frame(1, MailControl.HomeMail));
        var result = await new MailRunner(port, port, port).RunAsync(TimeSpan.FromSeconds(2), e =>
        {
            if (e.Action == "Click") port.DelayAsync(TimeSpan.FromSeconds(2), default).GetAwaiter().GetResult();
        }, default);
        Assert.Equal(RunOutcome.Failed, result.Outcome);
        Assert.Equal("mail.timeout", result.Reason);
        Assert.Equal(0, port.Clicks);
    }

    [Fact]
    public async Task ReusingAFrameFailsWithoutAnotherClick()
    {
        var port = new TestPort(() => Frame(1, MailControl.HomeMail));
        var result = await new MailRunner(port, port, port).RunAsync(TimeSpan.FromSeconds(2), _ => { }, default);
        Assert.Equal(RunOutcome.Failed, result.Outcome);
        Assert.Equal("mail.stale-frame", result.Reason);
        Assert.Equal(1, port.Clicks);
    }

    [Fact]
    public async Task InvalidReplayActionCannotAdvanceToNextFrame()
    {
        var scenario = new MailScenario("wrong", "synthetic-contract", "test",
            [new([MailControl.HomeMail], MailControl.Close), new([MailControl.HomeMail])]);
        var port = new ScenarioSession(scenario);
        var result = await new MailRunner(port, port, port).RunAsync(TimeSpan.FromSeconds(2), _ => { }, default);
        Assert.Equal(RunOutcome.Failed, result.Outcome);
        Assert.Empty(port.Actions);
        Assert.False(port.AllStepsObserved);
        Assert.Equal("scenario.contract-violation", port.Evaluate(result).Reason);
    }

    private sealed class TestPort(Func<MailObservation> observe) : IMailObserver, IMailInput, IRunClock
    {
        public int Clicks { get; private set; }
        public TimeSpan Elapsed { get; private set; }
        public TimeSpan ObservationDuration { get; init; }
        public ValueTask<MailObservation> ObserveAsync(CancellationToken cancellationToken)
        {
            Elapsed += ObservationDuration;
            return ValueTask.FromResult(observe());
        }
        public ValueTask ClickAsync(TemplateHit target, FrameIdentity frame, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Clicks++;
            return ValueTask.CompletedTask;
        }
        public ValueTask DelayAsync(TimeSpan delay, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Elapsed += delay;
            return ValueTask.CompletedTask;
        }
    }
}

