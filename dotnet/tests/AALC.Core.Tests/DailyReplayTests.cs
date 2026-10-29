using AALC.Core.Features.Daily;
using AALC.Core.Features.Mail;
using AALC.Runtime.Daily;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;
using AALC.Runtime.Replay;
using Xunit;

namespace AALC.Core.Tests;

public sealed class DailyReplayTests
{
    [Theory]
    [InlineData("daily-exp-thread-three")]
    [InlineData("daily-entry-failure")]
    public async Task SyntheticDailyScenariosUseTheProductionRunner(string name)
    {
        var scenario = Load(name);
        var events = new List<RunEvent>();
        var session = new DailyScenarioSession(scenario, events.Add);
        var result = await new DailyRunner(session, _ => throw new InvalidOperationException("场景不应进入邮件任务"))
            .RunAsync(scenario.Options, default);
        var acceptance = session.Evaluate(result);

        Assert.True(acceptance.Passed, $"{acceptance.Reason}: {result.Outcome}, {result.Reason}");
        Assert.True(acceptance.AllStepsObserved);
        Assert.True(acceptance.AllExpectedActionsPerformed);
        Assert.Contains(events, entry => entry.Action == "Progress" && !string.IsNullOrWhiteSpace(entry.Detail));
        Assert.Contains(events, entry => entry.Rule == "automation.observe" && entry.Action == "Observed");
        if (name == "daily-exp-thread-three")
        {
            Assert.Equal(4, session.Actions.Count(action => action.Rule == "daily.luxcavation.increase-count"));
            Assert.Equal(2, session.Actions.Count(action => action.Rule == "battle.confirm-settlement"));
        }
        else Assert.DoesNotContain(session.Actions, action => action.Rule == "daily.thread.tab");
    }

    [Fact]
    public async Task ModuleConversionRemainsAvailableWithLuxcavationDisabled()
    {
        DailyScenarioTarget[] home = [new("home/mail_assets.png", new(50, 50)), new("home/window_assets.png", new(100, 50))];
        var scenario = new DailyScenario("modules-only", "synthetic-contract", "test",
            new() { RunLuxcavation = false, ConvertModules = true },
            [new(home, [], AdvanceAfterObservation: true),
                new([new("home/enkephalin_box_assets.png", new(200, 600))], [new("daily.modules.open", Target: new(200, 600))]),
                new([new("enkephalin/all_in_disabled_assets.png", new(800, 330)), new("enkephalin/enkephalin_cancel_assets.png", new(500, 530))],
                    [new("daily.modules.close", Target: new(500, 530))]), new(home, [])]);
        var session = new DailyScenarioSession(scenario);
        var result = await new DailyRunner(session, _ => throw new InvalidOperationException()).RunAsync(scenario.Options, default);
        Assert.True(session.Evaluate(result).Passed, result.Reason);
        Assert.Equal(["daily.modules.open", "daily.modules.close"], session.Actions.Select(action => action.Rule));
    }

    [Fact]
    public async Task ACompletedRunWithAnUnperformedFinalActionFailsAcceptance()
    {
        var source = Load("daily-exp-thread-three");
        var steps = source.Steps.ToArray();
        steps[^1] = steps[^1] with { ExpectedActions = [new("battle.extra")] };
        var scenario = source with { Steps = steps };
        var session = new DailyScenarioSession(scenario);
        var result = await new DailyRunner(session, _ => throw new InvalidOperationException()).RunAsync(scenario.Options, default);
        Assert.Equal(RunOutcome.Completed, result.Outcome);
        Assert.Equal("scenario.missing-actions", session.Evaluate(result).Reason);
    }

    [Fact]
    public async Task ReplayRejectsAWrongCoordinateBeforeAdvancing()
    {
        var scenario = new DailyScenario("coordinate", "synthetic-contract", "test", new(),
            [new([], [new("test.click", Target: new(40, 50))]), new([], [])]);
        var session = new DailyScenarioSession(scenario);
        var frame = await session.ObserveAsync([], default);
        await Assert.ThrowsAsync<InvalidDataException>(() => session.ClickAsync(frame, new(41, 50), "test.click", default).AsTask());
        Assert.Empty(session.Actions);
        Assert.False(session.AllStepsObserved);
        Assert.Equal("scenario.contract-violation", session.Evaluate(new(RunOutcome.Completed, scenario.ExpectedReason, 1, 0)).Reason);
    }

    [Fact]
    public async Task ReplayRejectsAWrongKeyAndCancelledInput()
    {
        var scenario = new DailyScenario("key", "synthetic-contract", "test", new(),
            [new([], [new("test.key", DailyScenarioActionKind.Key, Key: GameKey.Enter)])]);
        var session = new DailyScenarioSession(scenario);
        var frame = await session.ObserveAsync([], default);
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => session.KeyAsync(frame, GameKey.Enter, "test.key", cancellation.Token).AsTask());
        await Assert.ThrowsAsync<InvalidDataException>(() => session.KeyAsync(frame, GameKey.P, "test.key", default).AsTask());
        Assert.Empty(session.Actions);
    }

    [Fact]
    public async Task MatchingFailedOutcomeStillRequiresTheSpecificReason()
    {
        var scenario = new DailyScenario("reason", "synthetic-contract", "test", new(), [new([], [])],
            RunOutcome.Failed, "mail.timeout");
        var session = new DailyScenarioSession(scenario);
        await session.ObserveAsync([], default);
        Assert.Equal("scenario.reason-mismatch", session.Evaluate(new(RunOutcome.Failed, "different.error", 1, 0)).Reason);
    }

    private static DailyScenario Load(string name) => DailyScenario.Load(Path.Combine(AppContext.BaseDirectory,
        "scenarios", "daily", name + ".json"));
}
