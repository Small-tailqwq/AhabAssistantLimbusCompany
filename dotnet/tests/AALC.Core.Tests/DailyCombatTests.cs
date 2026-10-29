using AALC.Core.Features.Daily;
using AALC.Core.Features.Mail;
using AALC.Runtime.Daily;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;
using AALC.Runtime.Mirror;
using Xunit;

namespace AALC.Core.Tests;

public sealed class DailyCombatTests
{
    [Fact]
    public void ContinuousBatchesAreCalculatedOnceAtTheTaskBoundary()
    {
        Assert.Equal([3, 3, 3, 1], DailyPlan.Batches(10, true, 3));
        Assert.Equal([3], DailyPlan.Batches(3, true, 3));
        Assert.Equal([1, 1, 1], DailyPlan.Batches(3, false, 0));
        Assert.Empty(DailyPlan.Batches(0, true, 3));
        Assert.Throws<ArgumentException>(() => DailyPlan.Batches(3, true, 0));
    }

    [Theory]
    [InlineData("2026-10-26T05:59:59+09:00", 4, 7)]
    [InlineData("2026-10-26T06:00:00+09:00", 1, 1)]
    [InlineData("2026-10-28T06:00:00+09:00", 2, 3)]
    [InlineData("2026-10-30T06:00:00+09:00", 3, 5)]
    public void TeamsFollowTheSeoulSixOClockGameDay(string timestamp, int experience, int thread)
    {
        var options = new DailyOptions { ExpTeamByDay = true, ThreadTeamByDay = true,
            ExpTeams = [1, 2, 3, 4], ThreadTeams = [1, 2, 3, 4, 5, 6, 7] };
        var now = DateTimeOffset.Parse(timestamp);
        Assert.Equal(experience, DailyPlan.TeamFor(options, LuxcavationKind.Experience, now));
        Assert.Equal(thread, DailyPlan.TeamFor(options, LuxcavationKind.Thread, now));
        Assert.Equal(thread, DailyPlan.TeamFor(options, LuxcavationKind.Thread, now.ToUniversalTime()));
    }

    [Fact]
    public void InvalidDailyOptionsAreRejectedBeforeInput()
    {
        DailyPlan.Validate(new());
        Assert.Throws<ArgumentException>(() => DailyPlan.Validate(new() { TeamNumber = 21 }));
        Assert.Throws<ArgumentException>(() => DailyPlan.Validate(new() { ExpCount = -1 }));
        Assert.Throws<ArgumentException>(() => DailyPlan.Validate(new() { MaxContinuousCombat = 11 }));
        Assert.Throws<ArgumentException>(() => DailyPlan.Validate(new() { ThreadTeams = [1] }));
        Assert.Throws<ArgumentException>(() => DailyPlan.Validate(new() { ExpTeams = [1, 0, 1, 1] }));
        Assert.Throws<ArgumentException>(() => DailyPlan.Validate(new() { RefillTier = 4 }));
    }

    [Theory]
    [InlineData(LuxcavationKind.Experience)]
    [InlineData(LuxcavationKind.Thread)]
    public async Task AThreeBattleBatchSetsCountThenSelectsTeamAndConfirmsVictory(LuxcavationKind kind)
    {
        var stage = "entry";
        var entry = kind == LuxcavationKind.Experience ? "luxcavation/exp_enter.png" : "luxcavation/thread_enter_assets.png";
        var session = new FakeSession(() => stage switch
        {
            "entry" => new([entry, "luxcavation/thread_continuous_combat_show_box.png"]),
            "count" => new([entry, "luxcavation/continuous_combat_up_box.png"]),
            "levels" => new(["luxcavation/thread_consume.png", "luxcavation/thread_scroll_bar.png"]),
            "team" => new(["teams/identify_assets.png"]),
            "start" => new(["battle/normal_to_battle_assets.png"]),
            "victory" => new([], [Text("战斗胜利"), Text("确认")]),
            _ => new([])
        });
        session.Action = rule => stage = rule switch
        {
            "daily.luxcavation.open-count" => "count",
            "daily.thread.open-levels" => "levels",
            "daily.luxcavation.choose-level" => "team",
            "team.choose-order" => "start",
            "battle.start" => "victory",
            "battle.confirm-settlement" => "done",
            _ => stage
        };
        var result = await LuxcavationFlow.RunAsync(session, kind, 3, 1, new() { SelectTeamByOrder = true }, default);

        Assert.True(result);
        Assert.Equal(2, session.Actions.Count(rule => rule == "daily.luxcavation.increase-count"));
        Assert.Single(session.Actions, rule => rule == "team.choose-order");
        Assert.Single(session.Actions, rule => rule == "battle.confirm-settlement");
        Assert.Equal("done", stage);
        Assert.True(session.Actions.IndexOf("daily.luxcavation.increase-count") < session.Actions.IndexOf("daily.luxcavation.choose-level"));
        Assert.NotEmpty(session.Reports);
    }

    [Fact]
    public async Task BattleUsesPAndEnterThenRequiresVictoryAndConfirmation()
    {
        var stage = 0;
        var pauseSeen = false;
        var session = new FakeSession(() => stage switch
        {
            0 => new(["battle/normal_to_battle_assets.png"]),
            1 => new(["battle/win_rate_assets.png", "battle/turn_assets.png"]),
            2 when !pauseSeen => Pause(),
            _ => new([], [Text("Battle Victory"), Text("Confirm")])
        });
        FrameSpec Pause() { pauseSeen = true; return new(["battle/pause_assets.png"]); }
        session.Action = rule => stage = rule switch
        {
            "battle.start" => 1,
            "battle.commit-turn" => 2,
            _ => stage
        };
        Assert.True(await BattleFlow.RunAsync(session, 1, true, default));
        Assert.True(session.Actions.IndexOf("battle.win-rate") < session.Actions.IndexOf("battle.commit-turn"));
        Assert.True(session.Actions.IndexOf("battle.commit-turn") < session.Actions.IndexOf("battle.confirm-settlement"));
    }

    [Fact]
    public async Task ContinuingAnExistingBattleDoesNotStartAnotherBatch()
    {
        var committed = false;
        var observed = 0;
        var session = new FakeSession(() => committed
            ? new([], [Text("战斗胜利"), Text("确认")])
            : ++observed == 1 ? new(["battle/win_rate_assets.png"])
                : new(["battle/win_rate_assets.png", "battle/turn_assets.png"]));
        session.Action = rule => { if (rule == "battle.commit-turn") committed = true; };

        Assert.True(await BattleFlow.ContinueAsync(session, 3, true, default));

        Assert.Equal(["battle.win-rate", "battle.commit-turn", "battle.confirm-settlement"], session.Actions);
        Assert.True(session.InputFrames[0] > 1);
        Assert.DoesNotContain("battle.start", session.Reports);
    }

    [Fact]
    public async Task UpgradeOverlayIsDismissedBeforeSettlementOcrAndBackgroundAnimation()
    {
        var phase = 0;
        var observations = 0;
        var session = new FakeSession(() => phase switch
        {
            0 when ++observations == 2 => new(["battle/pause_assets.png"]),
            0 => new(["base/leave_up_assets.png", "battle/pause_assets.png"]),
            1 => new(["base/leave_up_assets.png", "base/leave_up_confirm_assets.png"]),
            _ => new([], [Text("战斗胜利"), Text("确认")])
        });
        session.Action = rule => phase = rule switch
        {
            "battle.leave-overlay" => 1,
            "battle.leave-overlay-confirm" => 2,
            _ => phase
        };
        Assert.True(await BattleFlow.ContinueAsync(session, 1, true, default));
        Assert.Equal(["battle.leave-overlay", "battle.leave-overlay-confirm", "battle.confirm-settlement"], session.Actions);
        Assert.True(session.InputFrames[0] >= 4);
    }

    [Fact]
    public async Task TurnFeedbackAcceptsPointSevenFivePauseWithoutMouseFallback()
    {
        var committed = false;
        var feedback = false;
        var pause = new VisualTarget("battle/pause_assets.png", new(500, 600), new(480, 590, 40, 20), 0.77);
        var session = new FakeSession(() => !committed ? new(["battle/win_rate_assets.png", "battle/turn_assets.png"])
            : !feedback ? Feedback() : new([], [Text("战斗胜利"), Text("确认")]));
        FrameSpec Feedback() { feedback = true; return new(["battle/win_rate_card.png"], ExtraTargets: [pause]); }
        session.Action = rule => { if (rule == "battle.commit-turn") committed = true; };
        Assert.True(await BattleFlow.ContinueAsync(session, 1, true, default));
        Assert.DoesNotContain("battle.mouse-win-rate", session.Actions);
    }

    [Fact]
    public async Task VictoryAnimationAdvancesAtCenterBeforeConfirmation()
    {
        var advanced = false;
        var session = new FakeSession(() => new([], advanced ? [Text("战斗胜利"), Text("确认")] : [Text("战斗胜利")]));
        session.Action = rule => { if (rule == "battle.advance-settlement") advanced = true; };
        Assert.True(await BattleFlow.ContinueAsync(session, 1, true, default));
        Assert.Equal(["battle.advance-settlement", "battle.confirm-settlement"], session.Actions);
        Assert.Equal(new PixelPoint(640, 360), session.Clicks[0]);
    }

    [Theory]
    [InlineData(1)]
    [InlineData(3)]
    public async Task ExperienceChoosesRightmostPointEightCandidateAfterPageIsRecognized(int count)
    {
        const string entry = "luxcavation/exp_enter.png";
        var candidates = new VisualTarget[]
        {
            new(entry, new(500, 600), new(480, 590, 40, 20), 0.91),
            new(entry, new(900, 600), new(880, 590, 40, 20), 0.83)
        };
        using var cancellation = new CancellationTokenSource();
        var panel = false;
        PixelPoint? opened = null;
        PixelPoint? chosen = null;
        var session = new FakeSession(() => new(panel ? ["luxcavation/continuous_combat_up_box.png"] : [],
            ExtraTargets: candidates));
        session.Action = rule =>
        {
            if (rule == "daily.luxcavation.open-count") { panel = true; opened = session.Clicks[^1]; }
            if (rule == "daily.luxcavation.choose-level") { chosen = session.Clicks[^1]; cancellation.Cancel(); }
        };

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => LuxcavationFlow.RunAsync(session,
            LuxcavationKind.Experience, count, 1, new(), cancellation.Token));

        Assert.Equal(new PixelPoint(900, 600), chosen);
        if (count > 1) Assert.Equal(new PixelPoint(1050, 375), opened);
        else Assert.Null(opened);
    }

    [Fact]
    public async Task WeakExperienceCandidatesAloneDoNotRecognizeThePage()
    {
        var candidate = new VisualTarget("luxcavation/exp_enter.png", new(900, 600), new(880, 590, 40, 20), 0.83);
        var session = new FakeSession(() => new([], ExtraTargets: [candidate]));
        Assert.False(await LuxcavationFlow.RunAsync(session, LuxcavationKind.Experience, 1, 1, new(), default));
        Assert.DoesNotContain("daily.luxcavation.choose-level", session.Actions);
        Assert.DoesNotContain("daily.luxcavation.open-count", session.Actions);
    }

    [Fact]
    public async Task ConfirmationWithoutVictoryNeverCountsAsCompletedBattle()
    {
        var started = false;
        var session = new FakeSession(() => started ? new([], [Text("确认")]) : new(["battle/normal_to_battle_assets.png"]));
        session.Action = rule => { if (rule == "battle.start") started = true; };
        Assert.False(await BattleFlow.RunAsync(session, 1, true, default));
        Assert.DoesNotContain("battle.confirm-settlement", session.Actions);
        Assert.Contains("battle.unconfirmed", session.Reports);
    }

    [Fact]
    public async Task MissingTeamPageNeverStartsBattle()
    {
        var session = new FakeSession(() => new([]));
        Assert.False(await TeamSelection.RunAsync(session, 2, true, default));
        Assert.Empty(session.Actions);
    }

    [Fact]
    public async Task UnknownEntryCannotProceedToTeamOrBattle()
    {
        var session = new FakeSession(() => new([]));
        Assert.False(await LuxcavationFlow.RunAsync(session, LuxcavationKind.Experience, 1, 1, new(), default));
        Assert.DoesNotContain("team.choose-order", session.Actions);
        Assert.DoesNotContain("battle.start", session.Actions);
        Assert.Contains("daily.luxcavation.recover", session.Reports);
    }

    [Fact]
    public async Task CancelledBatchDoesNotSendInput()
    {
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        var session = new FakeSession(() => new(["luxcavation/exp_enter.png"]));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => LuxcavationFlow.RunAsync(session,
            LuxcavationKind.Experience, 1, 1, new(), cancellation.Token));
        Assert.Empty(session.Actions);
    }

    [Fact]
    public async Task NamedTeamUsesDetectedTextCoordinates()
    {
        var session = new FakeSession(() => new(["teams/identify_assets.png"], [new("Team 12", 1, new(80, 250, 90, 30))]));
        Assert.True(await TeamSelection.RunAsync(session, 12, false, default));
        Assert.Equal(new(125, 265), session.Clicks.Last());
        Assert.DoesNotContain("team.next-page", session.Actions);
    }

    [Fact]
    public async Task EnabledFirstEventChoiceIsRetriedWithoutSelectingTheSecond()
    {
        var session = new FakeSession(() => new(["event/choices_assets.png"],
            [new("选项", 1, new(400, 180, 40, 40)), new("首项", 1, new(400, 264, 40, 40)),
                new("次项", 1, new(400, 363, 40, 40))]));
        var handler = new BattleEvents();
        var frame = await session.ObserveAsync(BattleEvents.Queries, default);
        var entries = await session.ReadTextAsync(frame, default);
        for (var i = 0; i < 8; i++) Assert.False((await handler.HandleAsync(session, frame, entries, default)).Failed);
        Assert.True((await handler.HandleAsync(session, frame, entries, default)).Failed);
        Assert.Equal(8, session.Actions.Count(rule => rule == "battle.event.first-choice-ocr"));
        Assert.DoesNotContain("battle.event.next-enabled-choice", session.Actions);
    }

    [Fact]
    public async Task GrayFirstEventChoiceAllowsTheSecondCandidate()
    {
        var session = new FakeSession(() => new(["event/choices_assets.png"],
            [new("选项", 1, new(400, 180, 40, 40)), new("首项", 1, new(400, 264, 40, 40)),
                new("次项", 1, new(400, 363, 40, 40))], 150));
        var frame = await session.ObserveAsync(BattleEvents.Queries, default);
        var result = await new BattleEvents().HandleAsync(session, frame, await session.ReadTextAsync(frame, default), default);
        Assert.True(result.Handled);
        Assert.Single(session.Actions, rule => rule == "battle.event.next-enabled-choice");
    }

    [Theory]
    [InlineData(720)]
    [InlineData(1440)]
    public async Task EventChoiceGeometryScalesWithTheObservedResolution(int height)
    {
        var scale = height / 900.0;
        RecognizedText Entry(string text, int x, int y) => new(text, 1,
            new((int)(x * scale), (int)(y * scale), (int)(80 * scale), (int)(80 * scale)));
        var session = new FakeSession(() => new(["event/choices_assets.png"],
            [Entry("选项", 800, 360), Entry("左侧无关文本", 650, 465), Entry("右侧无关文本", 1200, 465),
                Entry("首项", 800, 465), Entry("次项", 800, 589)], Height: height));
        var frame = await session.ObserveAsync(BattleEvents.Queries, default);
        await new BattleEvents().HandleAsync(session, frame, await session.ReadTextAsync(frame, default), default);
        Assert.Equal(new PixelPoint((int)(840 * scale), (int)(465 * scale) + (int)(80 * scale) / 2), Assert.Single(session.Clicks));
    }

    [Fact]
    public async Task EventChoiceRejectsTextOutsideTheScaledSlotTolerance()
    {
        var session = new FakeSession(() => new(["event/choices_assets.png"],
            [new("选项", 1, new(400, 180, 40, 40)), new("非选项行", 1, new(400, 313, 40, 40))]));
        var frame = await session.ObserveAsync(BattleEvents.Queries, default);
        await new BattleEvents().HandleAsync(session, frame, await session.ReadTextAsync(frame, default), default);
        Assert.Empty(session.Clicks);
    }

    [Theory]
    [InlineData(720)]
    [InlineData(1440)]
    public async Task EventChoicePreservesThePythonSevenTwentyPixelOcrContractAtBothResolutions(int height)
    {
        var scale = height / 720.0;
        RecognizedText Entry(string text, int x, int y, int width, int boxHeight) => new(text, 1,
            new((int)(x * scale), (int)(y * scale), (int)(width * scale), (int)(boxHeight * scale)));
        var session = new FakeSession(() => new(["event/choices_assets.png"],
            [Entry("选项", 720, 116, 72, 22), Entry("献上土偶。", 736, 200, 81, 23),
                Entry("献上罪人。", 736, 299, 82, 23)], Height: height));
        var frame = await session.ObserveAsync(BattleEvents.Queries, default);
        await new BattleEvents().HandleAsync(session, frame, await session.ReadTextAsync(frame, default), default);
        Assert.Equal(new PixelPoint((int)(736 * scale) + (int)(81 * scale) / 2,
            (int)(200 * scale) + (int)(23 * scale) / 2), Assert.Single(session.Clicks));
    }

    [Fact]
    public async Task SingleGrayEventChoiceUsesTheScaledDefaultButtonSpacing()
    {
        var session = new FakeSession(() => new(["event/choices_assets.png"],
            [new("选项", 1, new(830, 180, 40, 40)), new("首项", 1, new(830, 264, 40, 40))], 150));
        var frame = await session.ObserveAsync(BattleEvents.Queries, default);
        await new BattleEvents().HandleAsync(session, frame, await session.ReadTextAsync(frame, default), default);
        Assert.Empty(session.Clicks);
    }

    [Fact]
    public async Task IncompleteEventResultWaitsForPageLayout()
    {
        var session = new FakeSession(() => new([], [Text("判定成功")]));
        var frame = await session.ObserveAsync(BattleEvents.Queries, default);
        var result = await new BattleEvents().HandleAsync(session, frame, await session.ReadTextAsync(frame, default), default);
        Assert.True(result.Handled);
        Assert.False(result.Failed);
        Assert.Empty(session.Actions);
    }

    [Theory]
    [InlineData("应该让谁上前？")]
    [InlineData("检查前方的道路")]
    public async Task ConfirmedNarrationAdvancesWithOneSpace(string question)
    {
        var session = new FakeSession(() => new([], [
            new("暴怒 有利", 1, new(879, 135, 129, 31)), new(question, 1, new(872, 180, 132, 29)),
            new("套索精准地瞄准了我们。", 1, new(75, 338, 182, 22)), new("SKIP", 1, new(1085, 617, 97, 61))]));
        var frame = await session.ObserveAsync(BattleEvents.Queries, default);
        var handler = new BattleEvents();
        var result = await handler.HandleAsync(session, frame, await session.ReadTextAsync(frame, default), default);

        Assert.True(result.Handled);
        Assert.False(result.Failed);
        Assert.Equal(["battle.event.advance-space"], session.Actions);
        Assert.Equal([GameKey.Space], session.Keys);
        Assert.Empty(session.Clicks);
        Assert.Equal(TimeSpan.FromMilliseconds(150), handler.NextObservationDelay);
    }

    [Theory]
    [InlineData(false, true)]
    [InlineData(true, false)]
    public async Task SpaceRequiresBothNarrationAndSkip(bool narration, bool skip)
    {
        var entries = new List<RecognizedText> { new("前往道路尽头", 1, new(872, 180, 132, 29)) };
        if (narration) entries.Add(new("我们准备继续向前方前进。", 1, new(75, 338, 182, 22)));
        if (skip) entries.Add(new("SKIP", 1, new(1085, 617, 97, 61)));
        var session = new FakeSession(() => new([], entries.ToArray()));
        var frame = await session.ObserveAsync(BattleEvents.Queries, default);
        var result = await new BattleEvents().HandleAsync(session, frame, await session.ReadTextAsync(frame, default), default);
        Assert.False(result.Handled);
        Assert.Empty(session.Actions);
    }

    [Fact]
    public async Task ChineseCheckSelectsParticipantThenPerformsAndWaitsForTheResult()
    {
        var phase = 0;
        var probabilities = new RecognizedText[] { new("高", 1, new(100, 580, 50, 30)),
            new("极高", 1, new(250, 580, 60, 30)) };
        var session = new FakeSession(() => phase == 0 ? new([], [.. probabilities, Text("选择一名罪人")])
            : phase == 1 ? new([], [.. probabilities, new("进行判定", 1, new(1000, 600, 100, 30))])
            : phase == 2 ? new([], [Text("判定成功")])
            : new([], [Text("判定成功"), new("继续", 1, new(1000, 600, 100, 30))]));
        session.Action = rule => phase = rule switch
        {
            "battle.event.select-probability-ocr" => 1,
            "battle.event.perform-check-ocr" => 2,
            _ => phase
        };
        var handler = new BattleEvents();
        for (var i = 0; i < 3; i++)
        {
            var frame = await session.ObserveAsync(BattleEvents.Queries, default);
            Assert.True((await handler.HandleAsync(session, frame, await session.ReadTextAsync(frame, default), default)).Handled);
        }
        Assert.Equal(new PixelPoint(280, 640), session.Clicks[0]);
        Assert.Equal(["battle.event.select-probability-ocr", "battle.event.perform-check-ocr"], session.Actions);
        Assert.Contains("battle.event.wait-result", session.Reports);
        phase = 3;
        var finalFrame = await session.ObserveAsync(BattleEvents.Queries, default);
        await handler.HandleAsync(session, finalFrame, await session.ReadTextAsync(finalFrame, default), default);
        Assert.Equal("battle.event.advance-ocr", session.Actions[^1]);
    }

    [Theory]
    [InlineData("判定成功")]
    [InlineData("判定失败")]
    public async Task UnchangedEventNarrationStopsAfterTenSeconds(string outcome)
    {
        var session = new FakeSession(() => new([], [new(outcome, 1, new(890, 481, 92, 28)),
            new("飞来的套索迅速向反方向飞去。", 1, new(76, 384, 230, 22)),
            new("SKIP", 1, new(1087, 618, 95, 60))]));
        var handler = new BattleEvents();
        while (session.Elapsed < TimeSpan.FromSeconds(10))
        {
            var frame = await session.ObserveAsync(BattleEvents.Queries, default);
            Assert.False((await handler.HandleAsync(session, frame, await session.ReadTextAsync(frame, default), default)).Failed);
            await session.DelayAsync(handler.NextObservationDelay, default);
        }
        Assert.Equal(67, session.Keys.Count);
        Assert.All(session.Keys, key => Assert.Equal(GameKey.Space, key));
        Assert.Empty(session.Clicks);
        var last = await session.ObserveAsync(BattleEvents.Queries, default);
        Assert.True((await handler.HandleAsync(session, last, await session.ReadTextAsync(last, default), default)).Failed);
        Assert.Equal(67, session.Keys.Count);
    }

    [Theory]
    [InlineData("event/continue_assets.png")]
    [InlineData("event/proceed_assets.png")]
    [InlineData("event/commence_assets.png")]
    [InlineData("event/skip_assets.png")]
    public async Task EventButtonTemplatesTakePriorityOverNarrationSpace(string asset)
    {
        var session = new FakeSession(() => new([asset], Narration()));
        var frame = await session.ObserveAsync(BattleEvents.Queries, default);
        var handler = new BattleEvents();

        Assert.True((await handler.HandleAsync(session, frame, await session.ReadTextAsync(frame, default), default)).Handled);

        Assert.Equal(["battle.event.advance-template"], session.Actions);
        Assert.Empty(session.Keys);
        Assert.Equal(TimeSpan.FromMilliseconds(500), handler.NextObservationDelay);
    }

    [Theory]
    [InlineData("继续")]
    [InlineData("前进")]
    [InlineData("开始")]
    [InlineData("Continue")]
    [InlineData("Proceed")]
    [InlineData("Commence")]
    public async Task RecognizedBottomRightEventButtonsTakePriorityOverSpace(string label)
    {
        var session = new FakeSession(() => new([], [.. Narration(), new(label, 1, new(1000, 580, 120, 40))]));
        var frame = await session.ObserveAsync(BattleEvents.Queries, default);

        await new BattleEvents().HandleAsync(session, frame, await session.ReadTextAsync(frame, default), default);

        Assert.Equal(["battle.event.advance-ocr"], session.Actions);
        Assert.Empty(session.Keys);
    }

    [Fact]
    public async Task ParticipantCheckTakesPriorityOverNarrationSpace()
    {
        var session = new FakeSession(() => new(["event/perform_the_check_feature_assets.png"],
            [.. Narration(), new("极高", 1, new(250, 580, 60, 30))]));
        var frame = await session.ObserveAsync(BattleEvents.Queries, default);

        await new BattleEvents().HandleAsync(session, frame, await session.ReadTextAsync(frame, default), default);

        Assert.Equal(["battle.event.select-probability-ocr"], session.Actions);
        Assert.Empty(session.Keys);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task SpaceIsFollowedByAFreshObservationThatHandsChoicesBackToTheirHandler(bool mirror)
    {
        var phase = 0;
        var session = new FakeSession(() => phase switch
        {
            0 => new([], Narration()),
            1 => new(["event/choices_assets.png"], [.. Narration(), new("选项", 1, new(830, 180, 40, 40)),
                new("走向道路尽头", 1, new(830, 264, 180, 40))]),
            _ => mirror ? new([MirrorThemeFlow.Map]) : new([], [Text("战斗胜利"), Text("确认")])
        });
        session.Action = rule => phase = rule switch
        {
            "battle.event.advance-space" => 1,
            "battle.event.first-choice-ocr" => 2,
            _ => phase
        };

        Assert.True(mirror ? await MirrorEventFlow.RunAsync(session, default)
            : await BattleFlow.ContinueAsync(session, 1, true, default));

        Assert.Equal([GameKey.Space], session.Keys);
        Assert.Equal("battle.event.advance-space", session.Actions[0]);
        Assert.Equal("battle.event.first-choice-ocr", session.Actions[1]);
        Assert.Equal(TimeSpan.FromMilliseconds(150), session.Delays[0]);
        Assert.Equal(mirror ? [1L, 2L] : new[] { 2L, 3L }, session.InputFrames.Take(2));
        Assert.Equal(mirror ? 3 : 5, session.Observations);
    }

    [Fact]
    public async Task ChangedNarrationRestartsTheTenSecondNoProgressWindow()
    {
        var text = "我们准备继续向前方前进。";
        var session = new FakeSession(() => new([], Narration(text)));
        var handler = new BattleEvents();
        for (var step = 0; step < 107; step++)
        {
            if (step == 40) text = "前方又出现了一条新的道路。";
            var frame = await session.ObserveAsync(BattleEvents.Queries, default);
            Assert.False((await handler.HandleAsync(session, frame, await session.ReadTextAsync(frame, default), default)).Failed);
            await session.DelayAsync(handler.NextObservationDelay, default);
        }
        Assert.True(session.Elapsed > TimeSpan.FromSeconds(16));
        var last = await session.ObserveAsync(BattleEvents.Queries, default);
        Assert.True((await handler.HandleAsync(session, last, await session.ReadTextAsync(last, default), default)).Failed);
        Assert.Equal(107, session.Keys.Count);
    }

    [Fact]
    public async Task MirrorNarrationUsesTheTenSecondNoProgressLimitBeforeItsObservationBudget()
    {
        var session = new FakeSession(() => new([], Narration()));

        Assert.False(await MirrorEventFlow.RunAsync(session, default));

        Assert.Equal(67, session.Keys.Count);
        Assert.Equal(68, session.Observations);
        Assert.InRange(session.Elapsed.TotalSeconds, 10, 10.15);
        Assert.Contains("battle.event.stalled", session.Reports);
    }

    [Fact]
    public async Task AdvancingMirrorNarrationStillHasABoundedObservationBudget()
    {
        var page = 0;
        var session = new FakeSession(() => new([], Narration($"我们继续前往道路的尽头。{++page}")));

        Assert.False(await MirrorEventFlow.RunAsync(session, default));

        Assert.Equal(200, session.Keys.Count);
        Assert.Equal(TimeSpan.FromSeconds(30), session.Elapsed);
        Assert.Contains("mirror.event.timeout", session.Reports);
    }

    private static RecognizedText[] Narration(string text = "我们准备继续向前方前进。") =>
        [new(text, 1, new(75, 338, 300, 22)), new("SKIP", 1, new(1085, 617, 97, 61))];

    [Fact]
    public async Task ARequestedParticipantIsNotRepeatedBeforeTheFeedbackWait()
    {
        var session = new FakeSession(() => new([], [Text("选择一名罪人"), new("极高", 1, new(250, 580, 60, 30))]));
        var handler = new BattleEvents();
        for (var i = 0; i < 8; i++)
        {
            var frame = await session.ObserveAsync(BattleEvents.Queries, default);
            Assert.False((await handler.HandleAsync(session, frame, await session.ReadTextAsync(frame, default), default)).Failed);
        }
        var lastFrame = await session.ObserveAsync(BattleEvents.Queries, default);
        Assert.True((await handler.HandleAsync(session, lastFrame, await session.ReadTextAsync(lastFrame, default), default)).Failed);
        Assert.Equal(["battle.event.select-probability-ocr"], session.Actions);
    }

    [Theory]
    [InlineData(720, true)]
    [InlineData(1440, true)]
    [InlineData(720, false)]
    [InlineData(1440, false)]
    public async Task AnUnselectedPromptRetriesThePortraitAndNeverActsOnItsCheckInstruction(int height, bool template)
    {
        var factor = height / 720;
        PixelRect Rect(int x, int y, int width, int h) => new(x * factor, y * factor, width * factor, h * factor);
        var probability = Rect(816, 607, 46, 24);
        var requests = 0;
        var selected = false;
        var session = new FakeSession(() => selected
            ? new([], [new("进行判定", 1, Rect(1062, 626, 144, 44))], Height: height)
            : new(["event/perform_the_check_feature_assets.png"],
                [new("选择一位罪人来进行判定：", 1, Rect(855, 307, 224, 24)),
                    .. template ? Array.Empty<RecognizedText>() : [new("极高", 1, probability)]],
                ExtraTargets: template ? [new("event/very_high.png", new(839 * factor, 619 * factor), probability, 1)] : [],
                Height: height));
        session.Action = rule =>
        {
            if (rule.StartsWith("battle.event.select-probability") && ++requests == 2) selected = true;
        };
        var handler = new BattleEvents();
        async Task Observe()
        {
            var frame = await session.ObserveAsync(BattleEvents.Queries, default);
            Assert.Equal((true, false), await handler.HandleAsync(session, frame, await session.ReadTextAsync(frame, default), default));
        }

        await Observe();
        await session.DelayAsync(TimeSpan.FromMilliseconds(500), default);
        await Observe();
        Assert.Single(session.Clicks);
        await session.DelayAsync(TimeSpan.FromSeconds(1), default);
        await Observe();
        await Observe();

        var select = template ? "battle.event.select-probability" : "battle.event.select-probability-ocr";
        Assert.Equal([select, select, "battle.event.perform-check-ocr"], session.Actions);
        Assert.Equal([new PixelPoint(839 * factor, 661 * factor), new(839 * factor, 661 * factor), new(1134 * factor, 648 * factor)], session.Clicks);
        Assert.Equal([1L, 3L, 4L], session.InputFrames);
    }

    [Theory]
    [InlineData("进行判定", false)]
    [InlineData("Perform the Check", false)]
    [InlineData("Commence", true)]
    public async Task AnExistingCheckButtonDoesNotRequireSelectingTheParticipantAgain(string label, bool probabilities)
    {
        var session = new FakeSession(() => new([], [new(label, 1, new(1062, 626, 144, 44)),
            .. probabilities ? new RecognizedText[] { new("very high", 1, new(816, 607, 46, 24)) } : []]));
        var frame = await session.ObserveAsync(BattleEvents.Queries, default);

        Assert.Equal((true, false), await new BattleEvents().HandleAsync(session, frame, await session.ReadTextAsync(frame, default), default));
        Assert.Equal(["battle.event.perform-check-ocr"], session.Actions);
    }

    private static RecognizedText Text(string value) => new(value, 1, new(500, 400, 100, 30));
    private sealed record FrameSpec(string[] Assets, RecognizedText[]? Text = null, byte Gray = 0,
        VisualTarget[]? ExtraTargets = null, int Height = 720);

    private sealed class FakeSession(Func<FrameSpec> observe) : IGameSession
    {
        private readonly Dictionary<long, RecognizedText[]> texts = [];
        public Action<string>? Action { get; set; }
        public List<string> Actions { get; } = [];
        public List<string> Reports { get; } = [];
        public List<PixelPoint> Clicks { get; } = [];
        public List<GameKey> Keys { get; } = [];
        public List<long> InputFrames { get; } = [];
        public List<TimeSpan> Delays { get; } = [];
        public TimeSpan Elapsed { get; private set; }
        public int Observations { get; private set; }
        public ValueTask<GameFrame> ObserveAsync(IReadOnlyList<ImageQuery> queries, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var spec = observe();
            var id = ++Observations;
            texts[id] = spec.Text ?? [];
            var width = spec.Height * 16 / 9;
            var pixels = new byte[width * spec.Height * 4];
            if (spec.Gray != 0) Array.Fill(pixels, spec.Gray);
            var targets = spec.Assets.Where(asset => queries.Any(query => query.Asset == asset)).Select(asset =>
            {
                var center = asset == "teams/identify_assets.png" ? new PixelPoint(1200, 100)
                    : asset == "luxcavation/thread_consume.png" ? new(900, 600) : new(500, 600);
                return new VisualTarget(asset, center, new(center.X - 20, center.Y - 10, 40, 20), 1);
            }).Concat(spec.ExtraTargets ?? []).Where(target => queries.Any(query => query.Asset == target.Asset
                && target.Score >= query.Threshold)).ToArray();
            return ValueTask.FromResult(new GameFrame(new(new(id, width, spec.Height, 1, 0), pixels), targets));
        }
        public ValueTask<IReadOnlyList<RecognizedText>> ReadTextAsync(GameFrame frame, CancellationToken cancellationToken,
            PixelRect? region = null, int scale = 1, TextPreprocessing preprocessing = TextPreprocessing.None)
        {
            cancellationToken.ThrowIfCancellationRequested();
            return ValueTask.FromResult<IReadOnlyList<RecognizedText>>(texts[frame.Identity.Id].Where(entry => region is null
                || region.Value.Contains(entry.Bounds.X + entry.Bounds.Width / 2, entry.Bounds.Y + entry.Bounds.Height / 2)).ToArray());
        }
        public ValueTask ClickAsync(GameFrame frame, PixelPoint target, string rule, CancellationToken cancellationToken)
        { Check(frame, target, cancellationToken); InputFrames.Add(frame.Identity.Id); Clicks.Add(target); Actions.Add(rule); Action?.Invoke(rule); return ValueTask.CompletedTask; }
        public ValueTask KeyAsync(GameFrame frame, GameKey key, string rule, CancellationToken cancellationToken)
        { Check(frame, new(0, 0), cancellationToken); InputFrames.Add(frame.Identity.Id); Keys.Add(key); Actions.Add(rule); Action?.Invoke(rule); return ValueTask.CompletedTask; }
        public ValueTask DragAsync(GameFrame frame, PixelPoint from, PixelPoint to, TimeSpan duration, string rule, CancellationToken cancellationToken)
        { Check(frame, from, cancellationToken); Check(frame, to, cancellationToken); Actions.Add(rule); Action?.Invoke(rule); Elapsed += duration; return ValueTask.CompletedTask; }
        public ValueTask DelayAsync(TimeSpan duration, CancellationToken cancellationToken)
        { cancellationToken.ThrowIfCancellationRequested(); Delays.Add(duration); Elapsed += duration; return ValueTask.CompletedTask; }
        public void Report(string rule, string message) => Reports.Add(rule);
        private void Check(GameFrame frame, PixelPoint point, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (frame.Identity.Id != Observations) throw new InvalidOperationException("输入使用了过期观察帧");
            if (point.X < 0 || point.X >= frame.Identity.Width || point.Y < 0 || point.Y >= frame.Identity.Height)
                throw new InvalidOperationException("输入超出客户区");
        }
    }
}
