using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;
using AALC.Runtime.Mirror;
using Xunit;

namespace AALC.Core.Tests;

public sealed class MirrorOrchestrationTests
{
    private const string Entrance = "mirror/road_to_mir/enter_mirror_assets.png";
    private const string Enter = "mirror/road_to_mir/enter_assets.png";
    private const string Infinite = "mirror/road_to_mir/infinity_mirror_enter_assets.png";
    private const string Receipt = "mirror/claim_reward/rewards_acquired_assets.png";
    private const string Map = "mirror/road_in_mir/legend_assets.png";
    private const string Identify = "teams/identify_assets.png";

    [Fact]
    public async Task EntryStartsFromAnAlreadyOpenGameTitle()
    {
        var session = new Session([
            new("daily.home.start-game", [Hit("base/clear_all_caches_assets.png")],
                [Text("清除所有缓存", 1700, 1100), Text("FACE THE SIN", 2000, 1200)]),
            Stage("mirror.entry.navigate", "home/mail_assets.png", "home/window_assets.png", "home/drive_assets.png"),
            Stage(null, Map)]);
        Assert.True(await MirrorEntryFlow.RunAsync(session, new(), default));
        Assert.Equal(["daily.home.start-game", "mirror.entry.navigate"], session.Inputs.Select(input => input.Rule));
        Assert.Equal(0, session.Restarts);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ExpiredProgressIsClearedBeforeStartingTheRequestedRuns(bool confirmation)
    {
        const string confirm = "mirror/road_to_mir/level_confirm_assets.png";
        const string forfeit = "mirror/claim_reward/claim_forfeit_assets.png";
        var stages = new List<FrameState>
        {
            new("mirror.entry.expired-open", [Hit(confirm), Hit(MirrorSettlementFlow.Clear)],
                [Text("当前进度已过期。", 1100, 650), Text("请领取您的奖励。", 1100, 700)]),
            new("mirror.entry.expired-forfeit", [Hit(MirrorSettlementFlow.Clear), Hit(MirrorSettlementFlow.UseModules), Hit(forfeit)], ZeroExpiredRewards())
        };
        if (confirmation) stages.Add(new("mirror.entry.expired-confirm", [Hit(confirm), Hit(MirrorSettlementFlow.Clear)],
            [Text("是否放弃奖励？", 1100, 650), Text("确认", 1500, 980)]));
        stages.AddRange([
            Stage("mirror.entry.enter", Enter, "mirror/road_to_mir/infinity_mirror_locked.png"),
            Stage("mirror.settlement.use-modules", MirrorSettlementFlow.Clear, MirrorSettlementFlow.UseModules),
            Stage("mirror.settlement.acknowledge", Receipt), Stage("mirror.entry.navigate", Entrance),
            Stage("mirror.settlement.use-modules", MirrorSettlementFlow.Clear, MirrorSettlementFlow.UseModules),
            Stage("mirror.settlement.acknowledge", Receipt), Stage(null, Entrance)]);
        var session = new Session(stages);
        var saved = new List<MirrorTeamOptions[]>();

        var result = await Runner(session, saved).RunAsync(new() { Runs = 2, ClaimRewards = true, Teams = Teams() }, default);

        Assert.Equal(RunOutcome.Completed, result.Outcome);
        Assert.Equal(2, saved.Count);
        Assert.Equal(["B", "A"], saved[0].Select(team => team.Name));
        Assert.Equal(["A", "B"], saved[1].Select(team => team.Name));
        Assert.Equal(2, session.Inputs.Count(input => input.Rule == "mirror.settlement.use-modules"));
        Assert.Equal(2, session.Reports.Count(report => report.Rule == "mirror.run.begin"));
        Assert.True(session.Inputs.FindIndex(input => input.Rule == "mirror.entry.enter")
            < session.Inputs.FindIndex(input => input.Rule == "mirror.settlement.use-modules"));
        Assert.Contains(session.Reports, report => report.Rule == "mirror.entry.expired-cleared");
    }

    [Fact]
    public async Task UnconfirmedExpiredCleanupCannotSpendModulesOrRotateTeams()
    {
        var session = new Session([
            new("mirror.entry.expired-open", [Hit("mirror/road_to_mir/level_confirm_assets.png")],
                [Text("当前进度已过期", 1100, 650), Text("请领取您的奖励", 1100, 700)]),
            Stage(null, MirrorSettlementFlow.Clear, MirrorSettlementFlow.UseModules)]);
        var saved = new List<MirrorTeamOptions[]>();

        var result = await Runner(session, saved).RunAsync(new() { Runs = 2, ClaimRewards = true, Teams = Teams() }, default);

        Assert.Equal(RunOutcome.Failed, result.Outcome);
        Assert.Equal("mirror.entry.expired-open", Assert.Single(session.Inputs).Rule);
        Assert.Empty(saved);
        Assert.Contains(session.Reports, report => report.Rule == "mirror.entry.expired-incomplete");
        Assert.Equal(0, session.Restarts);
    }

    [Fact]
    public async Task UnknownConfirmationAfterForfeitingDoesNotClickTheBackgroundEntrance()
    {
        var session = new Session([
            new("mirror.entry.expired-open", [Hit("mirror/road_to_mir/level_confirm_assets.png")],
                [Text("当前进度已过期", 1100, 650), Text("请领取您的奖励", 1100, 700)]),
            new("mirror.entry.expired-forfeit", [Hit(MirrorSettlementFlow.Clear), Hit(MirrorSettlementFlow.UseModules),
                Hit("mirror/claim_reward/claim_forfeit_assets.png")], ZeroExpiredRewards()),
            new(null, [Hit(Enter)], [Text("确认", 1500, 980), Text("未知通知", 1100, 650)])]);

        await Assert.ThrowsAsync<InvalidOperationException>(() => MirrorEntryFlow.RunAsync(session, Teams()[0], default));

        Assert.Equal(["mirror.entry.expired-open", "mirror.entry.expired-forfeit"], session.Inputs.Select(input => input.Rule));
    }

    [Theory]
    [InlineData(0, "10", 1)]
    [InlineData(1, "x100", 1)]
    [InlineData(2, "×1", 1)]
    [InlineData(3, "EXP10", 1)]
    [InlineData(0, "", 1)]
    [InlineData(1, "XO", .71)]
    [InlineData(2, "0", .7)]
    [InlineData(3, "EXPO", .928)]
    public async Task ValuableOrUncertainExpiredRewardsStopWithoutForfeitingSpendingOrRestarting(int field, string value, double confidence)
    {
        var rewards = ZeroExpiredRewards();
        rewards[field] = rewards[field] with { Text = value, Confidence = confidence };
        if (value.Length == 0) rewards = rewards.Where((_, index) => index != field).ToArray();
        var session = new Session([
            new("mirror.entry.expired-open", [Hit("mirror/road_to_mir/level_confirm_assets.png")],
                [Text("当前进度已过期", 1100, 650), Text("请领取您的奖励", 1100, 700)]),
            new(null, [Hit(MirrorSettlementFlow.Clear), Hit(MirrorSettlementFlow.UseModules),
                Hit("mirror/claim_reward/claim_forfeit_assets.png")], rewards)]);
        var saved = new List<MirrorTeamOptions[]>();

        var result = await Runner(session, saved).RunAsync(new() { Runs = 2, ClaimRewards = true, Teams = Teams() }, default);

        Assert.Equal(RunOutcome.Failed, result.Outcome);
        Assert.Contains("奖励未确认全部为零", result.Reason);
        Assert.Equal("mirror.entry.expired-open", Assert.Single(session.Inputs).Rule);
        Assert.Empty(saved);
        Assert.Equal(0, session.Restarts);
    }

    private static RecognizedText[] ZeroExpiredRewards() =>
        [Text("0", 980, 940), Text("x0", 1900, 800), Text("×0", 1900, 880), Text("EXP0", 1900, 970)];

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void InactiveQueuesCanBeSavedButCannotRun(bool hasDisabledTeam)
    {
        var options = new MirrorOptions { Teams = hasDisabledTeam ? [new() { Enabled = false }] : [] };
        MirrorPlan.ValidateConfiguration(options);
        Assert.Throws<ArgumentException>(() => MirrorPlan.Validate(options));
    }

    [Fact]
    public async Task AClaimButtonWithoutCompletionEvidenceCannotSpendModulesOrRotateTheQueue()
    {
        var session = new Session([Stage(null, MirrorSettlementFlow.Claim, MirrorSettlementFlow.UseModules)]);
        var saved = new List<MirrorTeamOptions[]>();
        var result = await Runner(session, saved).RunAsync(new() { ClaimRewards = true, Teams = Teams() }, default);

        Assert.Equal(RunOutcome.Failed, result.Outcome);
        Assert.Empty(session.Inputs);
        Assert.Empty(saved);
        Assert.DoesNotContain(session.Reports, item => item.Rule == "mirror.queue.rotated");
    }

    [Fact]
    public async Task KeepingRewardsCompletesTheRunWithoutChangingTheQueue()
    {
        var session = new Session([Stage(null, MirrorSettlementFlow.Complete, MirrorSettlementFlow.Claim)]);
        var saved = new List<MirrorTeamOptions[]>();
        var teams = Teams();
        var result = await Runner(session, saved).RunAsync(new() { ClaimRewards = false, Teams = teams }, default);

        Assert.Equal(RunOutcome.Completed, result.Outcome);
        Assert.Contains("待领取", result.Reason);
        Assert.Equal(["A", "B"], teams.Select(team => team.Name));
        Assert.Empty(session.Inputs);
        Assert.Empty(saved);
    }

    [Theory]
    [InlineData(2, 1200)]
    [InlineData(4, 600)]
    public async Task ResumedThemeSelectionUsesTheVisibleFloorForTheEventPackPreference(int floor, int selectedX)
    {
        var session = new Session([
            new("mirror.theme.select-pack", [Hit("mirror/theme_pack/feature_theme_pack_assets.png"), Hit(MirrorThemeFlow.Normal),
                Hit(MirrorThemeFlow.Pack, 600, 400), Hit(MirrorThemeFlow.Pack, 1200, 400)],
                [Text($"选择{floor}层主题卡包", 1050, 210), Text("地狱鸡", 400, 700), Text("被遗忘者们", 1000, 700)]),
            new(null, [Hit(Map), Hit(MirrorSettlementFlow.Complete)], [Text($"正在探索第{floor}层", 100, 200)])]);
        var team = new MirrorTeamOptions { Theme = new() { PreferEventPack = true, RefreshLimit = 0,
            NormalWeights = new() { ["chick"] = -5, ["forgot"] = 9 } } };

        var result = await Runner(session, []).RunAsync(new() { ClaimRewards = false, Teams = [team] }, default);

        Assert.Equal(RunOutcome.Completed, result.Outcome);
        var drag = Assert.Single(session.Inputs);
        Assert.Equal("mirror.theme.select-pack", drag.Rule);
        Assert.Equal(selectedX, drag.Target.X);
        Assert.Equal(3, drag.Frame);
        Assert.Contains(session.Reports, report => report.Rule == "mirror.floor" && report.Message == $"进入第 {floor} 层");
    }

    [Fact]
    public async Task AnUnreadableThemeFloorStopsBeforeApplyingAFloorSpecificPreference()
    {
        var session = new Session([Stage(null, "mirror/theme_pack/feature_theme_pack_assets.png", MirrorThemeFlow.Pack)]);

        var result = await Runner(session, []).RunAsync(new() { ClaimRewards = false, Teams = Teams() }, default);

        Assert.Equal(RunOutcome.Failed, result.Outcome);
        Assert.Equal("主题卡包楼层未识别", result.Reason);
        Assert.Empty(session.Inputs);
        Assert.Equal(14, session.Observations);
    }

    [Fact]
    public async Task AThemeFloorHiddenDuringTheTransitionIsReadAgainFromANewFrame()
    {
        var session = new Session([
            new("mirror.theme.select-pack", [Hit("mirror/theme_pack/feature_theme_pack_assets.png"), Hit(MirrorThemeFlow.Normal),
                Hit(MirrorThemeFlow.Pack, 600, 400)], [Text("选择2层主题卡包", 1050, 210), Text("地狱鸡", 400, 700)]),
            new(null, [Hit(Map), Hit(MirrorSettlementFlow.Complete)], [Text("正在探索第2层", 100, 200)])]) { InitialEmptyTextReads = 2 };

        var result = await Runner(session, []).RunAsync(new() { ClaimRewards = false,
            Teams = [new() { Theme = new() { RefreshLimit = 0 } }] }, default);

        Assert.Equal(RunOutcome.Completed, result.Outcome);
        Assert.Equal(5, Assert.Single(session.Inputs).Frame);
        Assert.True(session.Elapsed >= TimeSpan.FromSeconds(1));
        Assert.Contains(session.Reports, report => report.Rule == "mirror.floor" && report.Message == "进入第 2 层");
    }

    [Fact]
    public async Task AnUnreadableMapFloorIsRetriedOnTheNextMapBeforeEnteringItsShop()
    {
        const string coins = "mirror/shop/shop_coins_assets.png";
        const string leave = "mirror/shop/leave_assets.png";
        var session = new Session([
            Stage("mirror.route.select-node", Map, MirrorRouteFlow.Bus),
            Stage("mirror.route.enter-node", Map, MirrorRouteFlow.Bus, MirrorRouteFlow.Enter),
            Stage("mirror.shop.leave", coins, leave),
            new("mirror.route.post-shop-next", [Hit(Map), Hit(MirrorRouteFlow.Bus)], [Text("第2层", 100, 200)]),
            Stage("mirror.route.confirm-selection", Map, MirrorRouteFlow.Bus),
            Stage("mirror.route.select-node", Map, MirrorRouteFlow.Bus),
            Stage("mirror.route.enter-node", Map, MirrorRouteFlow.Bus, MirrorRouteFlow.Enter),
            Stage("mirror.shop.leave", coins, leave),
            Stage(null, Map, MirrorSettlementFlow.Complete)]);
        var team = new MirrorTeamOptions { Shop = new() { Purchases = MirrorShopPurchases.None, Heal = false, Enhance = false } };

        var result = await new MirrorRunner(session, new ShopMapReader()).RunAsync(new() { ClaimRewards = false, Teams = [team] }, default);

        Assert.Equal(RunOutcome.Completed, result.Outcome);
        Assert.Equal(["处理镜牢商店", "处理第 2 层商店"], session.Reports.Where(report => report.Rule == "mirror.shop.begin")
            .Select(report => report.Message));
    }

    [Fact]
    public async Task AConfirmedThemeFloorIsKeptForTheFollowingShop()
    {
        const string coins = "mirror/shop/shop_coins_assets.png";
        const string leave = "mirror/shop/leave_assets.png";
        var session = new Session([
            new("mirror.theme.select-pack", [Hit("mirror/theme_pack/feature_theme_pack_assets.png"), Hit(MirrorThemeFlow.Normal),
                Hit(MirrorThemeFlow.Pack, 600, 400)], [Text("选择3层主题卡包", 1050, 210), Text("地狱鸡", 400, 700)]),
            new("mirror.route.select-node", [Hit(Map), Hit(MirrorRouteFlow.Bus)], [Text("正在探索第3层", 100, 200)]),
            Stage("mirror.route.enter-node", Map, MirrorRouteFlow.Bus, MirrorRouteFlow.Enter),
            Stage("mirror.shop.leave", coins, leave),
            Stage(null, Map, MirrorSettlementFlow.Complete)]);
        var team = new MirrorTeamOptions { Theme = new() { RefreshLimit = 0 },
            Shop = new() { SkipFloors = [3] } };

        var result = await new MirrorRunner(session, new ShopMapReader()).RunAsync(new() { ClaimRewards = false, Teams = [team] }, default);

        Assert.Equal(RunOutcome.Completed, result.Outcome);
        Assert.Contains(session.Reports, report => report.Rule == "mirror.floor" && report.Message == "进入第 3 层");
        Assert.Contains(session.Reports, report => report.Rule == "mirror.shop.begin" && report.Message == "处理第 3 层商店");
        Assert.Equal(["mirror.theme.select-pack", "mirror.route.select-node", "mirror.route.enter-node", "mirror.shop.leave"],
            session.Inputs.Select(input => input.Rule));
    }

    [Fact]
    public async Task AConfirmedShopExitNotifiesTheRouteToUseWOnTheNextMap()
    {
        const string coins = "mirror/shop/shop_coins_assets.png";
        const string leave = "mirror/shop/leave_assets.png";
        var session = new Session([
            Stage("mirror.route.select-node", Map, MirrorRouteFlow.Bus),
            Stage("mirror.route.enter-node", Map, MirrorRouteFlow.Bus, MirrorRouteFlow.Enter),
            Stage("mirror.shop.leave", coins, leave),
            Stage("mirror.route.post-shop-next", Map, MirrorRouteFlow.Bus),
            Stage("mirror.route.enter-node", Map, MirrorRouteFlow.Enter),
            Stage(null, Map, MirrorSettlementFlow.Complete)]);
        var team = new MirrorTeamOptions { Shop = new() { Purchases = MirrorShopPurchases.None, Heal = false, Enhance = false } };

        var result = await new MirrorRunner(session, new ShopMapReader()).RunAsync(new() { ClaimRewards = false, Teams = [team] }, default);

        Assert.Equal(RunOutcome.Completed, result.Outcome);
        Assert.Equal(["mirror.route.select-node", "mirror.route.enter-node", "mirror.shop.leave", "mirror.route.post-shop-next",
            "mirror.route.enter-node"], session.Inputs.Select(input => input.Rule));
        Assert.Single(session.Reports, report => report.Rule == "mirror.route.post-shop");
    }

    [Fact]
    public async Task ResumingInsideTheShopCanLeaveAndUseWWithoutAnyCachedHistory()
    {
        var session = new Session([
            Stage("mirror.shop.leave", "mirror/shop/shop_coins_assets.png", "mirror/shop/leave_assets.png"),
            new("mirror.route.post-shop-next", [Hit(Map), Hit(MirrorRouteFlow.Bus)], [Text("正在探索第3层", 100, 200)]),
            Stage("mirror.route.enter-node", Map, MirrorRouteFlow.Enter),
            Stage(null, Map, MirrorSettlementFlow.Complete)]);
        var team = new MirrorTeamOptions { Shop = new() { Purchases = MirrorShopPurchases.None, Heal = false, Enhance = false } };

        var result = await new MirrorRunner(session, new NoMapReader()).RunAsync(new() { ClaimRewards = false, Teams = [team] }, default);

        Assert.Equal(RunOutcome.Completed, result.Outcome);
        Assert.Equal(["mirror.shop.leave", "mirror.route.post-shop-next", "mirror.route.enter-node"], session.Inputs.Select(input => input.Rule));
    }

    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    public async Task ResumingFloorThreePlansOnlyTheObservedRemainingNodesFromTheCurrentBus(int remaining)
    {
        var session = new Session([
            new("mirror.route.select-node", [Hit(Map), Hit(MirrorRouteFlow.Bus)], [Text("正在探索第3层", 100, 200)]),
            Stage("mirror.route.enter-node", Map, MirrorRouteFlow.Enter),
            Stage(null, Map, MirrorSettlementFlow.Complete)]);
        var reader = new RemainingMapReader(remaining);

        var result = await new MirrorRunner(session, reader).RunAsync(new() { ClaimRewards = false, Teams = Teams() }, default);

        Assert.Equal(RunOutcome.Completed, result.Outcome);
        Assert.Equal(new PixelPoint(80, 720), Assert.Single(reader.Buses));
        Assert.Equal(new PixelPoint(592, 760), session.Inputs[0].Target);
        Assert.Equal(["mirror.route.select-node", "mirror.route.enter-node"], session.Inputs.Select(input => input.Rule));
        Assert.Equal(remaining, reader.NodeCount);
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task QueueRotationNeedsBothARewardReceiptAndTheReturnedEntrance(bool receipt, bool returned)
    {
        var stages = new List<FrameState>
        {
            Stage("mirror.settlement.use-modules", MirrorSettlementFlow.Clear, MirrorSettlementFlow.UseModules)
        };
        if (receipt) stages.Add(Stage("mirror.settlement.acknowledge", Receipt));
        stages.Add(returned ? Stage(null, Entrance) : Stage(null));
        var session = new Session(stages);
        var saved = new List<MirrorTeamOptions[]>();

        var result = await Runner(session, saved).RunAsync(new() { ClaimRewards = true, Teams = Teams() }, default);

        Assert.Equal(receipt && returned ? RunOutcome.Completed : RunOutcome.Failed, result.Outcome);
        Assert.Single(session.Inputs, input => input.Rule == "mirror.settlement.use-modules");
        Assert.Equal(receipt && returned ? 1 : 0, saved.Count);
        if (saved.Count > 0) Assert.Equal(["B", "A"], saved[0].Select(team => team.Name));
    }

    [Fact]
    public async Task ATransientReceiptFailureResumesTheSubmittedSettlementWithoutPayingAgain()
    {
        var inner = new Session([
            Stage("mirror.settlement.use-modules", MirrorSettlementFlow.Clear, MirrorSettlementFlow.UseModules),
            Stage("mirror.settlement.acknowledge", Receipt),
            Stage(null, Entrance)]);
        var session = new FlakySession(inner, "mirror.settlement.acknowledge");
        var saved = new List<MirrorTeamOptions[]>();

        var result = await new MirrorRunner(session, new NoMapReader(),
            (queue, _) => { saved.Add(queue.ToArray()); return Task.CompletedTask; })
            .RunAsync(new() { ClaimRewards = true, Teams = Teams() }, default);

        Assert.Equal(RunOutcome.Completed, result.Outcome);
        Assert.Equal(1, session.Failures);
        Assert.Single(inner.Inputs, input => input.Rule == "mirror.settlement.use-modules");
        Assert.Single(inner.Inputs, input => input.Rule == "mirror.settlement.acknowledge");
        Assert.Contains(inner.Reports, item => item.Rule == "mirror.run.transient");
        Assert.Equal(["B", "A"], Assert.Single(saved).Select(team => team.Name));
    }

    [Fact]
    public async Task PersistentTransientFailuresStopWhenTheGameCannotBeRestarted()
    {
        var inner = new Session([
            Stage("mirror.settlement.use-modules", MirrorSettlementFlow.Clear, MirrorSettlementFlow.UseModules),
            Stage("mirror.settlement.acknowledge", Receipt),
            Stage(null, Entrance)]);
        var session = new FlakySession(inner, "mirror.settlement.acknowledge", int.MaxValue);
        var saved = new List<MirrorTeamOptions[]>();

        var result = await new MirrorRunner(session, new NoMapReader(),
            (queue, _) => { saved.Add(queue.ToArray()); return Task.CompletedTask; })
            .RunAsync(new() { ClaimRewards = true, Teams = Teams() }, default);

        Assert.Equal(RunOutcome.Failed, result.Outcome);
        Assert.Equal(11, session.Failures);
        Assert.Equal(1, inner.Restarts);
        Assert.Single(inner.Inputs, input => input.Rule == "mirror.settlement.use-modules");
        Assert.Empty(saved);
    }

    [Fact]
    public async Task AModuleSubmissionThatNeverChangesThePageCannotBeRepeated()
    {
        var session = new Session([
            Stage("mirror.settlement.use-modules", MirrorSettlementFlow.Clear, MirrorSettlementFlow.UseModules),
            Stage(null, MirrorSettlementFlow.Clear, MirrorSettlementFlow.UseModules)]);
        var saved = new List<MirrorTeamOptions[]>();

        var result = await Runner(session, saved).RunAsync(new() { ClaimRewards = true, Teams = Teams() }, default);

        Assert.Equal(RunOutcome.Failed, result.Outcome);
        Assert.Single(session.Inputs);
        Assert.Empty(saved);
    }

    [Fact]
    public async Task AWeeklyBonusThatRemainsSelectedStopsBeforeModulePayment()
    {
        var bonuses = new[] { Hit(MirrorSettlementFlow.Weekly, 900), Hit(MirrorSettlementFlow.Weekly, 1100), Hit(MirrorSettlementFlow.Weekly, 1300) };
        VisualTarget[] targets = [Hit(MirrorSettlementFlow.Clear), Hit(MirrorSettlementFlow.UseModules), .. bonuses];
        var session = new Session([new("mirror.settlement.weekly-bonus", targets), new(null, targets)]);

        var result = await MirrorSettlementFlow.RunAsync(session, new() { ClaimRewards = true, WeeklyBonus = MirrorWeeklyBonus.One }, default);

        Assert.True(result.Cleared);
        Assert.False(result.Claimed);
        Assert.Equal("周奖励选择未发生变化", result.Reason);
        Assert.Single(session.Inputs);
        Assert.Equal(new PixelPoint(1300, 350), session.Inputs[0].Target);
    }

    [Fact]
    public async Task WeeklyBonusSelectionMustBeObservedToDecreaseBeforePayingModules()
    {
        VisualTarget[] Bonuses(int count) => [Hit(MirrorSettlementFlow.Clear), Hit(MirrorSettlementFlow.UseModules),
            .. Enumerable.Range(0, count).Select(index => Hit(MirrorSettlementFlow.Weekly, 900 + index * 200))];
        var session = new Session([
            new("mirror.settlement.weekly-bonus", Bonuses(3)), new("mirror.settlement.weekly-bonus", Bonuses(2)),
            new("mirror.settlement.use-modules", Bonuses(1)), Stage("mirror.settlement.acknowledge", Receipt), Stage(null, Entrance)]);

        var result = await MirrorSettlementFlow.RunAsync(session, new() { ClaimRewards = true, WeeklyBonus = MirrorWeeklyBonus.One }, default);

        Assert.True(result.Claimed);
        Assert.Equal(["mirror.settlement.weekly-bonus", "mirror.settlement.weekly-bonus", "mirror.settlement.use-modules",
            "mirror.settlement.acknowledge"], session.Inputs.Select(input => input.Rule));
    }

    [Fact]
    public async Task OnlyEligibleTeamsRotateAndTheNextEligibleTeamRunsNext()
    {
        MirrorTeamOptions[] teams =
        [
            new() { Name = "普通队", Mode = MirrorTeamMode.Normal },
            new() { Name = "困难 A", Mode = MirrorTeamMode.Hard },
            new() { Name = "停用队", Enabled = false },
            new() { Name = "困难 B", Mode = MirrorTeamMode.Hard }
        ];
        var session = new Session([
            Stage("mirror.settlement.use-modules", MirrorSettlementFlow.Clear, MirrorSettlementFlow.UseModules),
            Stage("mirror.settlement.acknowledge", Receipt), Stage("mirror.entry.navigate", Entrance),
            Stage("mirror.settlement.use-modules", MirrorSettlementFlow.Clear, MirrorSettlementFlow.UseModules),
            Stage("mirror.settlement.acknowledge", Receipt), Stage(null, Entrance)]);
        var saved = new List<MirrorTeamOptions[]>();

        var result = await Runner(session, saved).RunAsync(new() { Mode = MirrorMode.Hard, Runs = 2, ClaimRewards = true, Teams = teams }, default);

        Assert.Equal(RunOutcome.Completed, result.Outcome);
        Assert.Equal(2, saved.Count);
        Assert.Equal(["普通队", "停用队", "困难 B", "困难 A"], saved[0].Select(team => team.Name));
        Assert.Equal(["普通队", "停用队", "困难 A", "困难 B"], saved[1].Select(team => team.Name));
        var beginnings = session.Reports.Where(item => item.Rule == "mirror.run.begin").Select(item => item.Message).ToArray();
        Assert.Equal(2, beginnings.Length);
        Assert.Contains("困难 A", beginnings[0]);
        Assert.Contains("困难 B", beginnings[1]);
        Assert.Equal(["普通队", "困难 A", "停用队", "困难 B"], teams.Select(team => team.Name));
    }

    [Theory]
    [InlineData("")]
    [InlineData("ff")]
    [InlineData("ON OFF")]
    [InlineData("ONLY")]
    [InlineData("OFFLINE")]
    public async Task AmbiguousInfiniteModeTextCannotToggleOrEnter(string text)
    {
        var session = new Session([InfiniteState(null, text)]);

        Assert.False(await MirrorEntryFlow.RunAsync(session, new(), default));
        Assert.Empty(session.Inputs);
        Assert.Contains(text.ToLowerInvariant(), session.Reports.Single(report => report.Rule == "mirror.entry.unknown-infinite").Message);
    }

    [Fact]
    public async Task InfiniteModeIsDisabledOnlyAfterOnAndEnteredOnlyAfterANewOffObservation()
    {
        var session = new Session([
            InfiniteState("mirror.entry.disable-infinite", "ON"), InfiniteState("mirror.entry.enter", "OFF"), Stage(null, Map)]);

        Assert.True(await MirrorEntryFlow.RunAsync(session, new(), default));
        Assert.Equal(["mirror.entry.disable-infinite", "mirror.entry.enter"], session.Inputs.Select(input => input.Rule));
        Assert.True(session.Inputs[0].Frame < session.Inputs[1].Frame);
    }

    [Fact]
    public async Task LockedInfiniteModeEntersWithoutOnOffText()
    {
        var session = new Session([Stage("mirror.entry.enter", Enter, "mirror/road_to_mir/infinity_mirror_locked.png"), Stage(null, Map)]);

        Assert.True(await MirrorEntryFlow.RunAsync(session, new(), default));

        Assert.Equal(["mirror.entry.enter"], session.Inputs.Select(input => input.Rule));
        Assert.Empty(session.Reports);
    }

    [Fact]
    public async Task ResumeDialogOverEnterButtonContinuesExistingRun()
    {
        var dialog = InfiniteState("mirror.entry.resume", "OFF");
        var session = new Session([InfiniteState("mirror.entry.enter", "OFF"),
            dialog with { Targets = [.. dialog.Targets, Hit("mirror/road_to_mir/resume_assets.png")] }, Stage(null, Map)]);

        Assert.True(await MirrorEntryFlow.RunAsync(session, new(), default));

        Assert.Equal(["mirror.entry.enter", "mirror.entry.resume"], session.Inputs.Select(input => input.Rule));
    }

    [Fact]
    public async Task InfiniteModeRetriesAMissedClickAfterHoverObscuresTheToggle()
    {
        var session = new Session([
            InfiniteState("mirror.entry.disable-infinite", "ON"), InfiniteState("mirror.entry.enter", "OFF"), Stage(null, Map)])
            { IgnoredInfiniteClicks = 1, HiddenInfiniteObservationsAfterClick = 2 };

        Assert.True(await MirrorEntryFlow.RunAsync(session, new(), default));

        Assert.Equal(["mirror.entry.disable-infinite", "mirror.entry.disable-infinite", "mirror.entry.enter"],
            session.Inputs.Select(input => input.Rule));
        Assert.True(session.Elapsed >= TimeSpan.FromSeconds(1));
        Assert.Contains(session.Reports, report => report.Rule == "mirror.entry.retry-infinite");
    }

    [Fact]
    public async Task InfiniteModeStopsAfterThreeUnsuccessfulTogglesWithoutEntering()
    {
        var session = new Session([InfiniteState("mirror.entry.disable-infinite", "ON"), Stage(null, Map)])
            { IgnoredInfiniteClicks = int.MaxValue };

        Assert.False(await MirrorEntryFlow.RunAsync(session, new(), default));

        Assert.Equal(3, session.Inputs.Count);
        Assert.All(session.Inputs, input => Assert.Equal("mirror.entry.disable-infinite", input.Rule));
    }

    [Theory]
    [InlineData("OFF", true)]
    [InlineData("ON", false)]
    [InlineData("", false)]
    public async Task MissingInfiniteToggleStillNeedsAnExplicitOffBeforeEntry(string text, bool enters)
    {
        var session = new Session([InfiniteState(enters ? "mirror.entry.enter" : null, text, false), Stage(null, Map)]);

        Assert.Equal(enters, await MirrorEntryFlow.RunAsync(session, new(), default));
        Assert.Equal(enters ? 1 : 0, session.Inputs.Count);
    }

    [Theory]
    [InlineData(720, false, 0)]
    [InlineData(1440, false, 0)]
    [InlineData(720, true, 0)]
    [InlineData(720, false, -1)]
    [InlineData(720, true, 1)]
    public async Task StarsWaitForEachSelectionAndCorrectConversionAfterSubmitting(int height, bool convert, int borderShift)
    {
        var session = new Session([
            StarPage("mirror.stars.select", height), StarPage("mirror.stars.select", height, 0),
            StarPage("mirror.stars.select", height, 0, 2), StarPage("mirror.stars.enter", height, 0, 2, 3),
            StarConfirmation("mirror.stars.convert", height, !convert, borderShift: borderShift),
            StarConfirmation("mirror.stars.confirm", height, convert, borderShift: borderShift),
            Stage(null, "mirror/road_to_mir/bleed_gift_assets.png", MirrorRewardFlow.GiftConfirm)], height * 16 / 9, height);

        Assert.True(await MirrorEntryFlow.RunAsync(session, StarTeam(convert), default));

        var factor = height / 720;
        Assert.Equal([new PixelPoint(230 * factor, 196 * factor), new(630 * factor, 196 * factor), new(830 * factor, 196 * factor)],
            session.Inputs.Where(input => input.Rule == "mirror.stars.select").Select(input => input.Target));
        Assert.Equal(["mirror.stars.select", "mirror.stars.select", "mirror.stars.select", "mirror.stars.enter",
            "mirror.stars.convert", "mirror.stars.confirm"], session.Inputs.Select(input => input.Rule));
        Assert.True(session.Elapsed >= TimeSpan.FromMilliseconds(6 * 900));
    }

    [Fact]
    public async Task StarlightNumbersNeverLimitTheConfiguredSelection()
    {
        var session = new Session([
            StarPage("mirror.stars.select", 720), StarPage("mirror.stars.select", 720, 0), StarPage("mirror.stars.select", 720, 0, 1),
            StarPage("mirror.stars.select", 720, 0, 1, 2), StarPage("mirror.stars.select", 720, 0, 1, 2, 3), StarPage("mirror.stars.select", 720, 0, 1, 2, 3, 4),
            StarPage("mirror.stars.select", 720, 0, 1, 2, 3, 4, 5), StarPage("mirror.stars.enter", 720, 0, 1, 2, 3, 4, 5, 6),
            StarConfirmation("mirror.stars.confirm", 720, false, 0), Stage(null, "mirror/road_to_mir/bleed_gift_assets.png", MirrorRewardFlow.GiftConfirm)], 1280, 720);
        var team = new MirrorTeamOptions { StarLevels = [1, 1, 1, 1, 1, 1, 1, 0, 0, 0] };

        Assert.True(await MirrorEntryFlow.RunAsync(session, team, default));

        Assert.Equal(7, session.Inputs.Count(input => input.Rule == "mirror.stars.select"));
        Assert.Equal("mirror.stars.confirm", session.Inputs[^1].Rule);
    }

    [Fact]
    public async Task StarsResumeAnExistingConfirmationByCancellingAndKeepingTheTwoAlreadySelectedCards()
    {
        var session = new Session([
            StarConfirmation("mirror.stars.cancel-existing", 720, true, 90),
            StarPage("mirror.stars.select", 720, 0, 2), StarPage("mirror.stars.enter", 720, 0, 2, 3),
            StarConfirmation("mirror.stars.confirm", 720, false), Stage(null, "mirror/road_to_mir/bleed_gift_assets.png", MirrorRewardFlow.GiftConfirm)], 1280, 720);

        Assert.True(await MirrorEntryFlow.RunAsync(session, StarTeam(), default));

        Assert.Equal(["mirror.stars.cancel-existing", "mirror.stars.select", "mirror.stars.enter", "mirror.stars.confirm"],
            session.Inputs.Select(input => input.Rule));
        Assert.Equal(new PixelPoint(830, 196), session.Inputs[1].Target);
        Assert.Contains(session.Reports, item => item.Rule == "mirror.stars.configured" && item.Message.Contains("3 项"));
    }

    [Fact]
    public void ChainPathKeepsSlotsOnTheUpperRowAndMovesThirdSkillsToTheLowerRow()
    {
        var frame = MirrorRewardTests.Frame(1) with { Targets = [MirrorRewardTests.Target("battle/gear_left.png", 266, 540),
            MirrorRewardTests.Target("battle/gear_right.png", 880, 540)] };
        // 第二个技能位上沿的愤怒色块（720p 下检测条位于 y=515..522）。
        for (var y = 515; y < 523; y++)
            for (var x = 313 + 130; x < 313 + 160; x++)
            {
                var offset = (y * 1280 + x) * 4;
                frame.Pixels.Bgra[offset + 2] = 140;
            }

        var path = BattleChain.Plan(frame)!;

        Assert.Equal([602, 665, 602, 602, 602, 602, 602], path.Skip(1).Take(7).Select(point => point.Y));
    }

    [Fact]
    public async Task AllBaseStarsUseTheSelectAllButton()
    {
        var all = Hit("mirror/road_to_mir/select_all_stars_assets.png", 1195, 508);
        int[] cards = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];
        var page = StarPage("mirror.stars.select-all", 720, 0, 2);
        var session = new Session([page with { Targets = [.. page.Targets, all] }, StarPage("mirror.stars.enter", 720, cards),
            StarConfirmation("mirror.stars.confirm", 720, false, 0), Stage(null, "mirror/road_to_mir/bleed_gift_assets.png", MirrorRewardFlow.GiftConfirm)], 1280, 720);

        Assert.True(await MirrorEntryFlow.SelectStarsAsync(session, new(), default));

        Assert.Equal(["mirror.stars.select-all", "mirror.stars.enter", "mirror.stars.confirm"], session.Inputs.Select(input => input.Rule));
    }

    [Fact]
    public async Task WithoutTheSelectAllButtonUniformStarsFallBackToTheCards()
    {
        var states = Enumerable.Range(0, 10).Select(count => StarPage("mirror.stars.select", 720, Enumerable.Range(0, count).ToArray())).ToList();
        states.AddRange([StarPage("mirror.stars.enter", 720, Enumerable.Range(0, 10).ToArray()), StarConfirmation("mirror.stars.confirm", 720, false, 0),
            Stage(null, "mirror/road_to_mir/bleed_gift_assets.png", MirrorRewardFlow.GiftConfirm)]);
        var session = new Session(states, 1280, 720);

        Assert.True(await MirrorEntryFlow.SelectStarsAsync(session, new(), default));

        Assert.Equal(10, session.Inputs.Count(input => input.Rule == "mirror.stars.select"));
    }

    [Fact]
    public async Task AMissedCardClickIsRetried()
    {
        var session = new Session([StarPage("mirror.stars.select", 720), StarPage("mirror.stars.select", 720),
            StarPage("mirror.stars.select", 720, 0), StarPage("mirror.stars.select", 720, 0, 2), StarPage("mirror.stars.enter", 720, 0, 2, 3),
            StarConfirmation("mirror.stars.confirm", 720, false), Stage(null, "mirror/road_to_mir/bleed_gift_assets.png", MirrorRewardFlow.GiftConfirm)], 1280, 720);

        Assert.True(await MirrorEntryFlow.SelectStarsAsync(session, StarTeam(), default));

        var clicks = session.Inputs.Where(input => input.Rule == "mirror.stars.select").Select(input => input.Target).ToArray();
        Assert.Equal([new PixelPoint(230, 196), new(230, 196), new(630, 196), new(830, 196)], clicks);
        Assert.DoesNotContain(session.Reports, item => item.Rule == "mirror.stars.unchanged");
    }

    [Fact]
    public async Task ACardStillNotSelectedAfterThreeClicksIsSkipped()
    {
        var session = new Session([StarPage("mirror.stars.select", 720), StarPage("mirror.stars.select", 720), StarPage("mirror.stars.select", 720),
            StarPage("mirror.stars.select", 720), StarPage("mirror.stars.select", 720, 2), StarPage("mirror.stars.enter", 720, 2, 3),
            StarConfirmation("mirror.stars.confirm", 720, false), Stage(null, "mirror/road_to_mir/bleed_gift_assets.png", MirrorRewardFlow.GiftConfirm)], 1280, 720);

        Assert.True(await MirrorEntryFlow.SelectStarsAsync(session, StarTeam(), default));

        Assert.Equal(5, session.Inputs.Count(input => input.Rule == "mirror.stars.select"));
        Assert.Contains(session.Reports, item => item.Rule == "mirror.stars.unchanged");
    }

    [Fact]
    public async Task StarsDoNotSubmitIfTheConversionToggleDidNotChangeAfterOneClick()
    {
        var session = new Session([StarPage("mirror.stars.enter", 720, 0, 2, 3),
            StarConfirmation("mirror.stars.convert", 720, true), StarConfirmation(null, 720, true)], 1280, 720);

        Assert.False(await MirrorEntryFlow.SelectStarsAsync(session, StarTeam(), default));

        Assert.Single(session.Inputs, input => input.Rule == "mirror.stars.convert");
        Assert.DoesNotContain(session.Inputs, input => input.Rule == "mirror.stars.confirm");
    }

    [Fact]
    public async Task AnUnrecognizedCheckboxCannotConfirmStarlightSpending()
    {
        var popup = StarConfirmation(null, 720, false) with { Bgra = new byte[1280 * 720 * 4] };
        var session = new Session([StarPage("mirror.stars.enter", 720, 0, 2, 3), popup], 1280, 720);

        Assert.False(await MirrorEntryFlow.SelectStarsAsync(session, StarTeam(), default));

        Assert.DoesNotContain(session.Inputs, input => input.Rule == "mirror.stars.confirm");
        Assert.Contains(session.Reports, item => item.Rule == "mirror.stars.unknown-conversion");
    }

    [Fact]
    public async Task AGenericDoneButtonWithoutTheStarPageLayoutCannotSelectOrSpendStarlight()
    {
        var session = new Session([Stage(null, "mirror/road_to_mir/dreaming_star/dreaming_star_enter_assets.png")]);

        Assert.False(await MirrorEntryFlow.SelectStarsAsync(session, new(), default));

        Assert.Empty(session.Inputs);
        Assert.Contains(session.Reports, item => item.Rule == "mirror.stars.unknown-layout");
    }

    private static MirrorTeamOptions StarTeam(bool convert = false) => new()
        { StarLevels = [1, 0, 1, 1, 0, 0, 0, 0, 0, 0], ConvertStarlight = convert };

    private static FrameState StarConfirmation(string? action, int height, bool convert, int remaining = 70, int borderShift = 0)
    {
        var factor = height / 720;
        var pixels = new byte[height * 16 / 9 * height * 4];
        // 确认框的方框边线与白色勾形状，独立于旧转换模板。
        PaintStarPixels(pixels, height, 738, 345 + borderShift, 27, 1, 140, 140, 140);
        PaintStarPixels(pixels, height, 738, 374 + borderShift, 27, 1, 140, 140, 140);
        PaintStarPixels(pixels, height, 738 + borderShift, 345, 1, 30, 140, 140, 140);
        PaintStarPixels(pixels, height, 764 + borderShift, 345, 1, 30, 140, 140, 140);
        if (convert)
            for (var x = 743; x <= 760; x++)
                PaintStarPixels(pixels, height, x, x <= 749 ? 356 + x - 743 : 362 - (x - 749), 1, 4, 185, 185, 185);
        return new(action, [Hit("mirror/road_to_mir/dreaming_star/select_star_confirm_assets.png", 713 * factor, 535 * factor)],
            [new(remaining.ToString(), .99, new(700 * factor, 305 * factor, 50 * factor, 25 * factor))], pixels);
    }

    private static FrameState StarPage(string? action, int height, params int[] selected)
    {
        var factor = height / 720;
        int[] prices = [10, 10, 20, 20, 30, 30, 40, 40, 50, 60];
        (string Name, int X, int Y, int Width, int Height)[] titles =
        [
            ("起始之星", 220, 185, 78, 26), ("层积星云", 418, 185, 80, 27), ("星际旅行", 617, 185, 79, 27),
            ("倾落的流星雨", 800, 185, 111, 26), ("双星商店", 1013, 184, 80, 29),
            ("卫星商店", 222, 426, 76, 23), ("星云的宠爱", 413, 425, 92, 24), ("星芒的引导", 610, 425, 93, 26),
            ("偶然的彗星", 809, 425, 93, 26), ("全面的可能性", 997, 425, 113, 26)
        ];
        var done = Hit("mirror/road_to_mir/dreaming_star/dreaming_star_enter_assets.png", 1195 * factor, 649 * factor);
        var pixels = new byte[height * 16 / 9 * height * 4];
        foreach (var index in selected)
            PaintStarPixels(pixels, height, 155 + index % 5 * 200, 338 + index / 5 * 240, 65, 16, 48, 50, 68);
        return new(action, [done], [new("西西弗的星之恩惠", .99, new(138 * factor, 32 * factor, 223 * factor, 31 * factor)),
            new(Math.Max(0, 120 - selected.Sum(index => prices[index])).ToString(), .99, new(990 * factor, 32 * factor, 45 * factor, 28 * factor)),
            .. titles.Select(item => new RecognizedText(item.Name, .99,
                new(item.X * factor, item.Y * factor, item.Width * factor, item.Height * factor))),
            .. selected.Select(index => new RecognizedText(prices[index].ToString(), .99,
                new((270 + index % 5 * 200) * factor, (158 + index / 5 * 240) * factor, 30 * factor, 22 * factor)))], pixels);
    }

    private static void PaintStarPixels(byte[] pixels, int height, int left, int top, int width, int rectangleHeight, byte r, byte g, byte b)
    {
        var factor = height / 720;
        var screenWidth = height * 16 / 9;
        for (var y = top * factor; y < (top + rectangleHeight) * factor; y++)
        for (var x = left * factor; x < (left + width) * factor; x++)
        {
            var offset = (y * screenWidth + x) * 4;
            pixels[offset] = b; pixels[offset + 1] = g; pixels[offset + 2] = r; pixels[offset + 3] = 255;
        }
    }

    [Theory]
    [InlineData(720)]
    [InlineData(1440)]
    public async Task InitialGiftsCancelTheRemainingChanceWarningAndKeepTheAlreadySelectedFirstGift(int height)
    {
        var factor = height / 720;
        var session = new Session([InitialGiftWarning(height), InitialGiftPage("mirror.initial.gift", height, 2, 1),
            InitialGiftPage("mirror.initial.submit", height, 2, 1, 2), Stage(null, "mirror/theme_pack/feature_theme_pack_assets.png")], height * 16 / 9, height);

        Assert.True(await MirrorEntryFlow.SelectInitialGiftsAsync(session, new(), default));

        Assert.Equal(["mirror.initial.cancel-warning", "mirror.initial.gift", "mirror.initial.submit"], session.Inputs.Select(input => input.Rule));
        Assert.Equal(new PixelPoint(826 * factor, 367 * factor), session.Inputs[1].Target);
        Assert.Contains(session.Reports, item => item.Rule == "mirror.initial.configured" && item.Message.Contains("2/2"));
    }

    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    public async Task InitialGiftsUseTheObservedSelectionLimit(int maximum)
    {
        var states = Enumerable.Range(0, maximum).Select(count => InitialGiftPage("mirror.initial.gift", 720, maximum,
            Enumerable.Range(1, count).ToArray())).ToList();
        states.Add(InitialGiftPage("mirror.initial.submit", 720, maximum, Enumerable.Range(1, maximum).ToArray()));
        states.Add(Stage(null, "mirror/theme_pack/feature_theme_pack_assets.png"));
        var session = new Session(states, 1280, 720);

        Assert.True(await MirrorEntryFlow.SelectInitialGiftsAsync(session, new(), default));

        Assert.Equal(maximum, session.Inputs.Count(input => input.Rule == "mirror.initial.gift"));
        Assert.Single(session.Inputs, input => input.Rule == "mirror.initial.submit");
    }

    [Fact]
    public async Task InitialGiftsReplaceAnUnwantedSelectionInTheConfiguredPriorityOrder()
    {
        var session = new Session([InitialGiftPage("mirror.initial.clear-gift", 720, 2, 1),
            InitialGiftPage("mirror.initial.gift", 720, 2), InitialGiftPage("mirror.initial.gift", 720, 2, 3),
            InitialGiftPage("mirror.initial.submit", 720, 2, 3, 2), Stage(null, "mirror/theme_pack/feature_theme_pack_assets.png")], 1280, 720);

        Assert.True(await MirrorEntryFlow.SelectInitialGiftsAsync(session, new() { InitialGifts = [3, 2, 1] }, default));

        Assert.Equal([new PixelPoint(829, 260), new(825, 474), new(826, 367)], session.Inputs.Take(3).Select(input => input.Target));
    }

    [Fact]
    public async Task InitialGiftsStopIfTheClickDoesNotChangeTheCountAndBorder()
    {
        var page = InitialGiftPage("mirror.initial.gift", 720, 2, 1);
        var session = new Session([page, page, page, InitialGiftPage(null, 720, 2, 1)], 1280, 720);

        Assert.False(await MirrorEntryFlow.SelectInitialGiftsAsync(session, new(), default));

        Assert.Equal(3, session.Inputs.Count);
        Assert.DoesNotContain(session.Inputs, input => input.Rule == "mirror.initial.submit");
        Assert.Contains(session.Reports, item => item.Rule == "mirror.initial.unchanged");
    }

    [Fact]
    public async Task AnInitialGiftClickSwallowedByThePageTransitionIsRetried()
    {
        var session = new Session([InitialGiftPage("mirror.initial.gift", 720, 2), InitialGiftPage("mirror.initial.gift", 720, 2),
            InitialGiftPage("mirror.initial.gift", 720, 2, 1), InitialGiftPage("mirror.initial.submit", 720, 2, 1, 2),
            Stage(null, "mirror/theme_pack/feature_theme_pack_assets.png")], 1280, 720);

        Assert.True(await MirrorEntryFlow.SelectInitialGiftsAsync(session, new(), default));

        Assert.Equal(3, session.Inputs.Count(input => input.Rule == "mirror.initial.gift"));
        Assert.Single(session.Inputs, input => input.Rule == "mirror.initial.submit");
    }

    [Fact]
    public async Task InitialGiftsCannotSubmitWhenTheCountAndBordersDisagree()
    {
        var page = InitialGiftPage(null, 720, 2, 1) with { Bgra = new byte[1280 * 720 * 4] };
        var session = new Session([page], 1280, 720);

        Assert.False(await MirrorEntryFlow.SelectInitialGiftsAsync(session, new(), default));

        Assert.Empty(session.Inputs);
        Assert.Contains(session.Reports, item => item.Rule == "mirror.initial.unknown-selection");
    }

    private static FrameState InitialGiftWarning(int height)
    {
        var factor = height / 720;
        return new("mirror.initial.cancel-warning", [],
            [new("仍有选择E.G.O饰品的机会。", .98354, new(520 * factor, 304 * factor, 229 * factor, 18 * factor)),
                new("要在不选择E.G.O饰品的情况下继续吗？", .98499, new(472 * factor, 328 * factor, 327 * factor, 17 * factor)),
                new("X取消", .80113, new(502 * factor, 454 * factor, 70 * factor, 24 * factor))]);
    }

    private static FrameState InitialGiftPage(string? action, int height, int maximum, params int[] selected)
    {
        var factor = height / 720;
        PixelPoint[] centers = [new(829, 260), new(826, 367), new(825, 474)];
        var targets = centers.Select((point, index) => Hit($"mirror/road_to_mir/select_init_gift/bleed_ego_gift_{index + 1}.png",
            point.X * factor, point.Y * factor)).ToList();
        targets.Add(Hit("mirror/road_to_mir/select_init_ego_gifts_confirm_assets.png", 1054 * factor, 586 * factor));
        var pixels = new byte[height * 16 / 9 * height * 4];
        foreach (var index in selected)
            PaintStarPixels(pixels, height, centers[index - 1].X + 60, centers[index - 1].Y - 48, 200, 4, 255, 170, 0);
        return new(action, targets.ToArray(),
            [new($"{selected.Length}/{maximum}", .95, new(1120 * factor, 567 * factor, 48 * factor, 37 * factor))], pixels);
    }

    [Theory]
    [InlineData(1440, 400, 790, 400, 290, 1750, 790)]
    [InlineData(720, 200, 395, 200, 145, 875, 395)]
    public async Task FormationUsesSinnerIdsAndScalesBothRowsWithTheFrame(int height,
        int x7, int y7, int x1, int y1, int x12, int y12)
    {
        var anchor = Hit(Identify, height == 1440 ? 2200 : 1100, height == 1440 ? 160 : 80);
        var session = new FormationSession(anchor, height * 16 / 9, height);

        Assert.True(await MirrorFormationFlow.RunAsync(session, [7, 1, 12], default));
        Assert.Equal([new PixelPoint(x7, y7), new(x1, y1), new(x12, y12)], session.Inputs.Select(input => input.Target));
        Assert.Equal(3, session.Inputs.Select(input => input.Frame).Distinct().Count());
        Assert.Equal(4, session.Observations);
        Assert.Equal(TimeSpan.FromMilliseconds(360), session.Elapsed);
        Assert.All(session.Delays, delay => Assert.InRange(delay.TotalMilliseconds, 100, 150));
    }

    [Fact]
    public async Task FormationReusesTheNewAnchorAfterClearingAndConfirmingPreviousSelections()
    {
        var session = new FormationSession(Hit(Identify, 2000, 100))
        {
            InitialSelections = 2,
            ClearedAnchor = Hit(Identify, 2200, 160)
        };

        Assert.True(await MirrorFormationFlow.RunAsync(session, [7, 1], default));

        var selections = session.Inputs.Where(input => input.Rule == "mirror.formation.sinner").ToArray();
        Assert.Equal([new PixelPoint(400, 790), new(400, 290)], selections.Select(input => input.Target));
        Assert.Equal([5L, 6L], selections.Select(input => input.Frame));
        Assert.Equal(7, session.Observations);
        Assert.Equal(["mirror.formation.clear", "mirror.formation.clear-confirm", "mirror.formation.sinner", "mirror.formation.sinner"],
            session.Inputs.Select(input => input.Rule));
    }

    [Fact]
    public async Task FormationStartsFromVerifiedEmptySelectionWithoutResetDialog()
    {
        var session = new FormationSession(Hit(Identify, 2200, 160)) { ResetPresentWhenEmpty = true };
        Assert.True(await MirrorFormationFlow.RunAsync(session, [4, 1], default));
        Assert.DoesNotContain(session.Inputs, input => input.Rule == "mirror.formation.clear");
        Assert.Equal(2, session.Inputs.Count(input => input.Rule == "mirror.formation.sinner"));
    }

    [Fact]
    public async Task FormationVerifiesEachOfTheTwelveSlotsBeforeSelectingTheNext()
    {
        var session = new FormationSession(Hit(Identify, 2200, 160));

        Assert.True(await MirrorFormationFlow.RunAsync(session, Enumerable.Range(1, 12).ToArray(), default));

        Assert.Equal(12, session.Inputs.Count);
        Assert.Equal(12, session.Delays.Count);
        Assert.All(session.Delays, delay => Assert.InRange(delay.TotalMilliseconds, 100, 150));
        Assert.Equal(TimeSpan.FromMilliseconds(1440), session.Elapsed);
        Assert.Equal(13, session.Observations);
        Assert.Equal(12, session.Inputs.Select(input => input.Frame).Distinct().Count());
        Assert.All(session.ObservationQueries.Skip(1), queries => Assert.Equal(
            [Identify, "teams/selected.png"], queries.Select(query => query.Asset)));
    }

    [Fact]
    public async Task FormationWaitsForTheResetDialogToAppearSettleAndCloseBeforeSelectingAnyone()
    {
        var session = new FormationSession(Hit(Identify, 2200, 160))
        {
            InitialSelections = 4,
            ConfirmationDelayObservations = 2,
            ConfirmationYPositions = [530, 498, 498],
            ClosingDialogObservations = 2
        };

        Assert.True(await MirrorFormationFlow.RunAsync(session, [1], default));

        Assert.Equal(["mirror.formation.clear", "mirror.formation.clear-confirm", "mirror.formation.sinner"],
            session.Inputs.Select(input => input.Rule));
        Assert.Equal(6, session.Inputs[1].Frame);
        Assert.Equal(498, session.Inputs[1].Target.Y);
        Assert.Equal(10, session.Inputs[2].Frame);
        Assert.Equal(11, session.Observations);
        Assert.All(session.ObservationQueries.SelectMany(queries => queries).Where(query => query.Asset == "teams/clear_selection_confirm_assets.png"),
            query => Assert.Equal(SearchMode.Normal, query.Search));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task FormationNeverTreatsTheDialogObscuringSelectionMarkersAsAnEmptyTeam(bool confirmationAppears)
    {
        var session = new FormationSession(Hit(Identify, 2200, 160))
        {
            InitialSelections = 4,
            NeverShowConfirmation = !confirmationAppears,
            ClosingDialogObservations = 100
        };

        Assert.False(await MirrorFormationFlow.RunAsync(session, [1, 6], default));

        Assert.DoesNotContain(session.Inputs, input => input.Rule == "mirror.formation.sinner");
        Assert.Equal(confirmationAppears ? 7 : 1, session.Inputs.Count);
        Assert.InRange(session.Observations, 1, 83);
        Assert.Contains("mirror.formation.not-cleared", session.Reports);
    }

    [Theory]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(true, true)]
    public async Task FormationRetriesIgnoredResetStepsOnlyAfterFreshUnchangedFeedback(bool openingIgnored, bool confirmationIgnored)
    {
        var session = new FormationSession(Hit(Identify, 2200, 160))
        {
            InitialSelections = 12,
            BackupSinners = [8, 9, 10, 11, 12],
            IgnoredResetClicks = openingIgnored ? 1 : 0,
            IgnoredConfirmationClicks = confirmationIgnored ? 1 : 0
        };

        Assert.True(await MirrorFormationFlow.RunAsync(session, Enumerable.Range(1, 12).ToArray(), default));

        var opening = session.Inputs.Where(input => input.Rule == "mirror.formation.clear").ToArray();
        var confirmation = session.Inputs.Where(input => input.Rule == "mirror.formation.clear-confirm").ToArray();
        Assert.Equal(openingIgnored ? 2 : 1, opening.Length);
        Assert.Equal(confirmationIgnored ? 2 : 1, confirmation.Length);
        if (openingIgnored) Assert.True(opening[1].Frame - opening[0].Frame >= 12);
        if (confirmationIgnored) Assert.True(confirmation[1].Frame - confirmation[0].Frame >= 12);
        Assert.Equal(12, session.Inputs.Count(input => input.Rule == "mirror.formation.sinner"));
        Assert.True(session.Inputs.First(input => input.Rule == "mirror.formation.sinner").Frame > confirmation[^1].Frame);
    }

    [Fact]
    public async Task FormationBoundsResetRetriesAcrossBothRecoveriesWhenTheOriginalTeamNeverChanges()
    {
        var session = new FormationSession(Hit(Identify, 2200, 160)) { InitialSelections = 12, IgnoredResetClicks = 10 };

        Assert.False(await MirrorFormationFlow.RunAsync(session, Enumerable.Range(1, 12).ToArray(), default));

        Assert.Equal(6, session.Inputs.Count);
        Assert.All(session.Inputs, input => Assert.Equal("mirror.formation.clear", input.Rule));
        Assert.Equal(77, session.Observations);
        Assert.Equal(2, session.Reports.Count(rule => rule == "mirror.formation.recover"));
        Assert.Contains("mirror.formation.not-cleared", session.Reports);
    }

    [Fact]
    public async Task CancellingTheFormationPausePreventsTheNextClickAndFinalObservation()
    {
        using var cancellation = new CancellationTokenSource();
        var session = new FormationSession(Hit(Identify, 2200, 160)) { OnDelay = _ => cancellation.Cancel() };

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => MirrorFormationFlow.RunAsync(session, [7, 1, 12], cancellation.Token));

        Assert.Single(session.Inputs);
        Assert.Single(session.Delays);
        Assert.Equal(1, session.Observations);
    }

    [Fact]
    public async Task FormationCannotSucceedIfFeedbackLeavesTheFormationPage()
    {
        var session = new FormationSession(Hit(Identify, 2200, 160)) { HideAnchorAfterSelection = true };

        Assert.False(await MirrorFormationFlow.RunAsync(session, [7, 1, 12], default));

        Assert.Single(session.Inputs);
        Assert.Equal(3, session.Observations);
        Assert.Contains("mirror.formation.unverified", session.Reports);
    }

    [Fact]
    public async Task FormationWaitsForDelayedFeedbackWithoutTogglingASelectedSinner()
    {
        var session = new FormationSession(Hit(Identify, 2200, 160)) { FeedbackDelayObservations = 2 };

        Assert.True(await MirrorFormationFlow.RunAsync(session, [1, 6, 3], default));

        Assert.Equal(3, session.Inputs.Count);
        Assert.Equal(10, session.Observations);
        Assert.Equal(9, session.Delays.Count);
        Assert.DoesNotContain("mirror.formation.retry", session.Reports);
    }

    [Fact]
    public async Task FormationRetriesAnIgnoredClickOnlyAfterRepeatedUnchangedFeedback()
    {
        var session = new FormationSession(Hit(Identify, 2200, 160)) { IgnoredSinnerClicks = 1 };

        Assert.True(await MirrorFormationFlow.RunAsync(session, [1, 6], default));

        Assert.Equal([new PixelPoint(400, 290), new(400, 290), new(1750, 290)], session.Inputs.Select(input => input.Target));
        Assert.Equal([1L, 7L, 8L], session.Inputs.Select(input => input.Frame));
        Assert.Single(session.Reports, rule => rule == "mirror.formation.retry");
    }

    [Fact]
    public async Task FormationStopsIfOnlyTheFirstFourConfiguredSinnersWereActuallySelected()
    {
        var session = new FormationSession(Hit(Identify, 2200, 160)) { SelectionLimit = 4 };

        Assert.False(await MirrorFormationFlow.RunAsync(session, [1, 6, 3, 4, 2, 5, 7, 11, 12, 10, 8, 9], default));

        Assert.Equal(6, session.Inputs.Count);
        Assert.Equal(18, session.Observations);
        Assert.Equal(4, session.Reports.Count(rule => rule == "mirror.formation.selected"));
        Assert.Equal(new PixelPoint(670, 290), session.Inputs[^1].Target);
        Assert.Equal(session.Inputs[^2].Target, session.Inputs[^1].Target);
        Assert.Contains("mirror.formation.unverified", session.Reports);
    }

    [Fact]
    public async Task FormationRejectsASelectionInTheWrongSlotEvenWhenTheCountIncreases()
    {
        var session = new FormationSession(Hit(Identify, 2200, 160)) { WrongSinner = 12 };

        Assert.False(await MirrorFormationFlow.RunAsync(session, [1, 6], default));

        Assert.Single(session.Inputs);
        Assert.Equal(3, session.Observations);
        Assert.Contains("mirror.formation.unverified", session.Reports);
        Assert.DoesNotContain("mirror.formation.retry", session.Reports);
        Assert.DoesNotContain("mirror.formation.recover", session.Reports);
    }

    [Fact]
    public async Task FormationWaitsForAnEarlierBackupBannerToRecoverWithoutClickingAgain()
    {
        var session = new FormationSession(Hit(Identify, 2200, 160))
        {
            BackupSinners = [8, 9, 10, 11, 12],
            HiddenBackupSinner = 11,
            HideBackupAfterSinnerClick = 10,
            HiddenBackupObservations = 2
        };

        Assert.True(await MirrorFormationFlow.RunAsync(session, [1, 6, 3, 4, 2, 5, 7, 11, 12, 10, 8, 9], default));

        Assert.Equal(12, session.Inputs.Count);
        Assert.Equal(15, session.Observations);
        Assert.Equal(12, session.Reports.Count(rule => rule == "mirror.formation.selected"));
        Assert.DoesNotContain("mirror.formation.retry", session.Reports);
    }

    [Fact]
    public async Task FormationStopsAfterSixIncompleteFramesWithoutRepeatingAnAlreadyAcceptedClick()
    {
        var session = new FormationSession(Hit(Identify, 2200, 160))
        {
            BackupSinners = [8, 9, 10, 11, 12],
            HiddenBackupSinner = 11,
            HideBackupAfterSinnerClick = 10,
            HiddenBackupObservations = 100
        };

        Assert.False(await MirrorFormationFlow.RunAsync(session, [1, 6, 3, 4, 2, 5, 7, 11, 12, 10, 8, 9], default));

        Assert.Equal(10, session.Inputs.Count);
        Assert.Equal(17, session.Observations);
        Assert.Equal(9, session.Reports.Count(rule => rule == "mirror.formation.selected"));
        Assert.DoesNotContain("mirror.formation.retry", session.Reports);
        Assert.Contains("mirror.formation.unverified", session.Reports);
    }

    [Fact]
    public async Task FormationRejectsAnExtraMemberEvenWhenTheExpectedMemberIsAlsoPresent()
    {
        var session = new FormationSession(Hit(Identify, 2200, 160)) { ExtraSinner = 12 };

        Assert.False(await MirrorFormationFlow.RunAsync(session, [1, 6], default));

        Assert.Single(session.Inputs);
        Assert.Equal(3, session.Observations);
        Assert.Contains("mirror.formation.unverified", session.Reports);
        Assert.DoesNotContain("mirror.formation.retry", session.Reports);
    }

    [Fact]
    public async Task FormationRebuildsTheConfiguredOrderAfterAnInitialMisclick()
    {
        var session = new FormationSession(Hit(Identify, 2200, 160))
        {
            WrongSinner = 12,
            WrongSinnerClicks = 1,
            ResetAvailableAfterSelection = true
        };
        int[] order = [1, 6, 3, 4, 2, 5, 7, 11, 12, 10, 8, 9];

        Assert.True(await MirrorFormationFlow.RunAsync(session, order, default));

        Assert.Equal(["mirror.formation.sinner", "mirror.formation.clear", "mirror.formation.clear-confirm"],
            session.Inputs.Take(3).Select(input => input.Rule));
        Assert.Equal(13, session.Inputs.Count(input => input.Rule == "mirror.formation.sinner"));
        Assert.Equal(order.Select(number => new PixelPoint(2200 + (-1800 + (number - 1) % 6 * 270), 160 + 130 + (number - 1) / 6 * 500)),
            session.Inputs.Skip(3).Select(input => input.Target));
        Assert.Single(session.Reports, rule => rule == "mirror.formation.recover");
        Assert.DoesNotContain("mirror.formation.failed", session.Reports);
    }

    [Fact]
    public async Task FormationStopsAfterTwoCompleteRecoveriesIfEveryFirstSelectionIsWrong()
    {
        var session = new FormationSession(Hit(Identify, 2200, 160)) { WrongSinner = 12, ResetAvailableAfterSelection = true };

        Assert.False(await MirrorFormationFlow.RunAsync(session, [1, 6], default));

        Assert.Equal(3, session.Inputs.Count(input => input.Rule == "mirror.formation.sinner"));
        Assert.Equal(2, session.Inputs.Count(input => input.Rule == "mirror.formation.clear"));
        Assert.Equal(2, session.Inputs.Count(input => input.Rule == "mirror.formation.clear-confirm"));
        Assert.Equal(2, session.Reports.Count(rule => rule == "mirror.formation.recover"));
        Assert.Contains("mirror.formation.failed", session.Reports);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task CancellationDuringFormationRecoveryPreventsAnyFurtherInput(bool duringReset)
    {
        using var cancellation = new CancellationTokenSource();
        FormationSession session = null!;
        session = new FormationSession(Hit(Identify, 2200, 160))
        {
            WrongSinner = 12,
            ResetAvailableAfterSelection = true,
            OnReport = rule => { if (!duringReset && rule == "mirror.formation.recover") cancellation.Cancel(); },
            OnDelay = _ => { if (duringReset && session.Reports.Contains("mirror.formation.recover")) cancellation.Cancel(); }
        };

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => MirrorFormationFlow.RunAsync(session, [1, 6], cancellation.Token));

        Assert.Equal(duringReset ? 2 : 1, session.Inputs.Count);
        Assert.Single(session.Inputs, input => input.Rule == "mirror.formation.sinner");
        Assert.DoesNotContain(session.Inputs, input => input.Rule == "mirror.formation.clear-confirm");
        Assert.DoesNotContain("mirror.formation.failed", session.Reports);
    }

    [Theory]
    [InlineData(720)]
    [InlineData(1440)]
    public async Task FormationVerifiesRedAndCyanSlotsBeforeCompletingAllTwelveSelections(int height)
    {
        var session = new FormationSession(Hit(Identify, 2200 * height / 1440, 160 * height / 1440), height * 16 / 9, height)
        {
            BackupSinners = [8, 9, 10, 11, 12]
        };

        Assert.True(await MirrorFormationFlow.RunAsync(session, Enumerable.Range(1, 12).ToArray(), default));

        Assert.Equal(12, session.Inputs.Count);
        Assert.Equal(13, session.Observations);
        Assert.Equal(12, session.Reports.Count(rule => rule == "mirror.formation.selected"));
    }

    [Theory]
    [InlineData(720)]
    [InlineData(1440)]
    public async Task FormationReusesTheCompleteObservedOrderIncludingBackupSlots(int height)
    {
        int[] order = [1, 6, 3, 4, 2, 5, 7, 11, 12, 10, 8, 9];
        var session = new FormationSession(Hit(Identify, 2200 * height / 1440, 160 * height / 1440), height * 16 / 9, height)
        {
            InitialOrder = order,
            BackupSinners = [8, 9, 10, 11, 12],
            BackupLabelGap = true
        };

        Assert.True(await MirrorFormationFlow.RunAsync(session, order, default));

        Assert.Empty(session.Inputs);
        Assert.Equal(1, session.Observations);
        Assert.Equal(12, session.OrderReads);
        Assert.Contains("mirror.formation.reused", session.Reports);
    }

    [Fact]
    public async Task FormationRebuildsWhenObservedMembersMatchButTheirOrderDiffers()
    {
        var session = new FormationSession(Hit(Identify, 2200, 160)) { InitialOrder = [1, 6, 3] };

        Assert.True(await MirrorFormationFlow.RunAsync(session, [6, 1, 3], default));

        Assert.Equal(["mirror.formation.clear", "mirror.formation.clear-confirm", "mirror.formation.sinner",
            "mirror.formation.sinner", "mirror.formation.sinner"], session.Inputs.Select(input => input.Rule));
        Assert.DoesNotContain("mirror.formation.reused", session.Reports);
    }

    [Theory]
    [InlineData(true, .99)]
    [InlineData(false, .6)]
    public async Task FormationRebuildsWhenTheCurrentOrderEvidenceIsIncomplete(bool missing, double confidence)
    {
        var session = new FormationSession(Hit(Identify, 2200, 160))
        {
            InitialOrder = [1, 6, 3], MissingOrderSinner = missing ? 3 : null, OrderConfidence = confidence
        };

        Assert.True(await MirrorFormationFlow.RunAsync(session, [1, 6, 3], default));

        Assert.Equal("mirror.formation.clear", session.Inputs[0].Rule);
        Assert.Equal(3, session.Inputs.Count(input => input.Rule == "mirror.formation.sinner"));
        Assert.DoesNotContain("mirror.formation.reused", session.Reports);
    }

    [Fact]
    public async Task FormationChecksTheScreenAgainAfterReusingAFormation()
    {
        var session = new FormationSession(Hit(Identify, 2200, 160)) { InitialOrder = [1, 6, 3] };
        Assert.True(await MirrorFormationFlow.RunAsync(session, [1, 6, 3], default));
        session.MissingOrderSinner = 3;

        Assert.True(await MirrorFormationFlow.RunAsync(session, [1, 6, 3], default));

        Assert.Single(session.Reports, rule => rule == "mirror.formation.reused");
        Assert.Equal("mirror.formation.clear", session.Inputs[0].Rule);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task EntrySelectsRequestedTeamBeforeTreatingTheSharedAnchorAsFormation(bool starsVisible)
    {
        VisualTarget[] targets = [Hit(Identify, 2400, 356), Hit("mirror/road_to_mir/select_team_confirm_assets.png"),
            .. starsVisible ? new[] { Hit("mirror/road_to_mir/select_team_stars_assets.png") } : []];
        var pixels = new byte[2560 * 1440 * 4];
        var session = new Session([
            new("team.dismiss-focus", targets, [Text("编队 #1", 250, 700)], pixels),
            new("team.choose-name", targets, [Text("编队 #2", 250, 700)], pixels),
            new("mirror.entry.confirm-team", targets, [Text("编队 #2", 250, 700)], pixels),
            Stage(null, Map)]);

        Assert.True(await MirrorEntryFlow.RunAsync(session, new() { GameTeamNumber = 2 }, default));
        Assert.Equal(["team.dismiss-focus", "team.choose-name", "mirror.entry.confirm-team"],
            session.Inputs.Select(input => input.Rule));
    }

    [Theory]
    [InlineData("编队 #1", true)]
    [InlineData("Team #2", true)]
    [InlineData("预设 #1", false)]
    [InlineData("要重置编队顺序吗？", false)]
    public void LeftTeamListIsDistinctFromDeploymentPreset(string text, bool expected) =>
        Assert.Equal(expected, MirrorEntryFlow.HasTeamList([Text(text, 250, 700)]));

    [Fact]
    public async Task EntryConfirmationTakesPriorityOverTheVisibleBackgroundTeamButton()
    {
        var confirm = Hit("mirror/road_to_mir/enter_mirror_confirm.png", 1482, 990);
        var session = new Session([
            new("mirror.entry.confirm-team", [Hit(Identify, 2400, 356), confirm,
                Hit("mirror/road_to_mir/select_team_stars_assets.png", 2300, 1076),
                Hit("mirror/road_to_mir/select_team_confirm_assets.png", 2294, 1172)], [Text("编队 #1", 250, 700)]),
            Stage(null, Map)]);
        Assert.True(await MirrorEntryFlow.RunAsync(session, new(), default));
        Assert.Equal(confirm.Center, Assert.Single(session.Inputs).Target);
    }

    [Fact]
    public async Task EntryResumesFromFormationWhenTheBattleButtonIsObscured()
    {
        var session = new Session([Stage(null, Identify)]);

        Assert.True(await MirrorEntryFlow.RunAsync(session, new(), default));

        Assert.Empty(session.Inputs);
    }

    [Theory]
    [InlineData("要重置编队顺序吗？", true)]
    [InlineData("Reset deployment order?", true)]
    [InlineData("要退出镜牢吗？", false)]
    [InlineData("", false)]
    public async Task FormationResumesOnlyARecognizedResetDialog(string message, bool succeeds)
    {
        var session = new FormationSession(Hit(Identify, 2200, 160))
            { StartsInResetDialog = true, ConfirmationText = message };

        Assert.Equal(succeeds, await MirrorFormationFlow.RunAsync(session, [1], default));

        if (succeeds)
            Assert.Equal(["mirror.formation.clear-confirm", "mirror.formation.sinner"], session.Inputs.Select(input => input.Rule));
        else
            Assert.Empty(session.Inputs);
    }

    private sealed class FormationSession(VisualTarget anchor, int width = 2560, int height = 1440) : IGameSession
    {
        private readonly HashSet<int> selected = [];
        private int? pendingSinner;
        private int pendingPolls;
        private int sinnerClicks;
        private bool clearing;
        private bool cleared;
        private int clearPolls;
        private int closingPolls;
        private int resetClicks;
        private int confirmationClicks;
        private int hiddenBackupObservations;
        public int InitialSelections { get; init; }
        public int[] InitialOrder { get; init; } = [];
        public int? MissingOrderSinner { get; set; }
        public double OrderConfidence { get; init; } = .99;
        public int OrderReads { get; private set; }
        public VisualTarget? ClearedAnchor { get; init; }
        public bool HideAnchorAfterSelection { get; init; }
        public int FeedbackDelayObservations { get; init; }
        public int IgnoredSinnerClicks { get; init; }
        public int SelectionLimit { get; init; } = 12;
        public int? WrongSinner { get; init; }
        public int WrongSinnerClicks { get; init; } = int.MaxValue;
        public int? ExtraSinner { get; init; }
        public int[] BackupSinners { get; init; } = [];
        public bool BackupLabelGap { get; init; }
        public int? HiddenBackupSinner { get; init; }
        public int HideBackupAfterSinnerClick { get; init; }
        public int HiddenBackupObservations { get; init; }
        public int ConfirmationDelayObservations { get; init; }
        public int[] ConfirmationYPositions { get; init; } = [350];
        public int ClosingDialogObservations { get; init; }
        public bool NeverShowConfirmation { get; init; }
        public bool StartsInResetDialog { get; init; }
        public string ConfirmationText { get; init; } = "要重置编队顺序吗？";
        public int IgnoredResetClicks { get; init; }
        public int IgnoredConfirmationClicks { get; init; }
        public bool ResetAvailableAfterSelection { get; init; }
        public bool ResetPresentWhenEmpty { get; init; }
        public Action<TimeSpan>? OnDelay { get; init; }
        public Action<string>? OnReport { get; init; }
        public TimeSpan Elapsed { get; private set; }
        public int Observations { get; private set; }
        public List<(string Rule, PixelPoint Target, long Frame)> Inputs { get; } = [];
        public List<TimeSpan> Delays { get; } = [];
        public List<string> Reports { get; } = [];
        public List<IReadOnlyList<ImageQuery>> ObservationQueries { get; } = [];
        public ValueTask<GameFrame> ObserveAsync(IReadOnlyList<ImageQuery> queries, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            ObservationQueries.Add(queries);
            if (Observations == 0 && StartsInResetDialog) clearing = true;
            if (pendingSinner is { } sinner && pendingPolls-- <= 0)
            {
                selected.Add(sinner);
                if (ExtraSinner is { } extra) selected.Add(extra);
                pendingSinner = null;
            }
            var targets = new List<VisualTarget>();
            var currentAnchor = cleared ? ClearedAnchor ?? anchor : anchor;
            var onPage = !HideAnchorAfterSelection || sinnerClicks == 0;
            if (onPage) targets.Add(currentAnchor);
            var dialogVisible = clearing && (!cleared || closingPolls++ < ClosingDialogObservations);
            if (clearing && cleared && !dialogVisible) clearing = false;
            if (!clearing && ((InitialSelections > 0 || InitialOrder.Length > 0) && !cleared || ResetAvailableAfterSelection && selected.Count > 0 || ResetPresentWhenEmpty && selected.Count == 0))
                targets.Add(Hit("teams/clear_selection_assets.png"));
            if (dialogVisible && !NeverShowConfirmation && clearPolls++ >= ConfirmationDelayObservations)
            {
                var y = ConfirmationYPositions[Math.Min(clearPolls - ConfirmationDelayObservations - 1, ConfirmationYPositions.Length - 1)];
                targets.Add(Hit("teams/clear_selection_confirm_assets.png", 740, y));
            }
            var visibleSinners = !cleared && InitialOrder.Length > 0 ? InitialOrder
                : cleared || InitialSelections == 0 ? selected.AsEnumerable() : Enumerable.Range(1, InitialSelections);
            if (onPage && !dialogVisible)
                targets.AddRange(visibleSinners
                    .Where(number => !BackupSinners.Contains(number))
                    .Select(number =>
                    {
                        var point = Slot(currentAnchor, number);
                        return Hit("teams/selected.png", point.X, point.Y);
                    }));
            var pixels = new byte[width * height * 4];
            var hideBackup = HiddenBackupSinner is not null && sinnerClicks >= HideBackupAfterSinnerClick
                && ++hiddenBackupObservations <= HiddenBackupObservations;
            if (onPage && !dialogVisible)
                foreach (var number in visibleSinners.Where(number => BackupSinners.Contains(number)
                    && !(hideBackup && HiddenBackupSinner == number)))
                {
                    var point = Slot(currentAnchor, number);
                    for (var y = point.Y - 20 * height / 1440; y < point.Y + 20 * height / 1440; y++)
                        for (var x = point.X - 100 * height / 1440; x < point.X + 100 * height / 1440; x++)
                        {
                            if (BackupLabelGap && Math.Abs(y - point.Y) <= 5 * height / 1440) continue;
                            var offset = (y * width + x) * 4;
                            pixels[offset] = 100; pixels[offset + 1] = 110;
                        }
                }
            return ValueTask.FromResult(new GameFrame(new(new(++Observations, width, height, 1, 0), pixels),
                targets.Where(target => queries.Any(query => query.Asset == target.Asset)).ToArray()));
        }
        public ValueTask ClickAsync(GameFrame frame, PixelPoint target, string rule, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            Assert.Equal(Observations, frame.Identity.Id);
            Assert.InRange(target.X, 0, width - 1);
            Assert.InRange(target.Y, 0, height - 1);
            Inputs.Add((rule, target, frame.Identity.Id));
            if (rule == "mirror.formation.clear")
            {
                if (++resetClicks > IgnoredResetClicks) { clearing = true; cleared = false; clearPolls = 0; closingPolls = 0; }
            }
            else if (rule == "mirror.formation.clear-confirm")
            {
                if (++confirmationClicks > IgnoredConfirmationClicks) { cleared = true; selected.Clear(); }
            }
            else if (rule == "mirror.formation.sinner")
            {
                sinnerClicks++;
                if (sinnerClicks > IgnoredSinnerClicks && selected.Count < SelectionLimit)
                {
                    pendingSinner = WrongSinner is { } wrong && sinnerClicks <= WrongSinnerClicks ? wrong
                        : Enumerable.Range(1, 12).Single(number => Slot(cleared ? ClearedAnchor ?? anchor : anchor, number) == target);
                    pendingPolls = FeedbackDelayObservations;
                }
            }
            return ValueTask.CompletedTask;
        }
        private PixelPoint Slot(VisualTarget currentAnchor, int number) => new(
            currentAnchor.Center.X + (int)((-1800 + (number - 1) % 6 * 270) * height / 1440.0),
            currentAnchor.Center.Y + (int)((130 + (number - 1) / 6 * 500) * height / 1440.0));
        public ValueTask DelayAsync(TimeSpan duration, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            Delays.Add(duration);
            OnDelay?.Invoke(duration);
            ct.ThrowIfCancellationRequested();
            Elapsed += duration;
            return ValueTask.CompletedTask;
        }
        public ValueTask<IReadOnlyList<RecognizedText>> ReadTextAsync(GameFrame frame, CancellationToken ct,
            PixelRect? region = null, int scale = 1, TextPreprocessing preprocessing = TextPreprocessing.None)
        {
            ct.ThrowIfCancellationRequested();
            if (preprocessing == TextPreprocessing.None)
                return ValueTask.FromResult<IReadOnlyList<RecognizedText>>([new(ConfirmationText, .99, region!.Value)]);
            OrderReads++;
            Assert.Equal(TextPreprocessing.FormationOrder, preprocessing);
            var area = region!.Value;
            var number = InitialOrder.SingleOrDefault(number =>
            {
                var point = Slot(anchor, number);
                return Math.Abs(area.X + area.Width / 2 - point.X) <= height / 1440.0
                    && Math.Abs(area.Y + (int)(115 * height / 1440.0) - point.Y) <= 2 * height / 1440.0;
            });
            if (number == 0 || number == MissingOrderSinner) return ValueTask.FromResult<IReadOnlyList<RecognizedText>>([]);
            return ValueTask.FromResult<IReadOnlyList<RecognizedText>>(
                [new((Array.IndexOf(InitialOrder, number) + 1).ToString(), OrderConfidence, area)]);
        }
        public ValueTask KeyAsync(GameFrame frame, GameKey key, string rule, CancellationToken ct) => throw new NotSupportedException();
        public ValueTask DragAsync(GameFrame frame, PixelPoint from, PixelPoint to, TimeSpan duration, string rule, CancellationToken ct) => throw new NotSupportedException();
        public void Report(string rule, string message) { Reports.Add(rule); OnReport?.Invoke(rule); }
    }

    [Theory]
    [InlineData(BattlePurpose.Luxcavation, 2)]
    [InlineData(BattlePurpose.Mirror, 3)]
    public async Task MirrorBattleContinuesAfterAVictoryConfirmationUntilAMirrorDestinationIsObserved(BattlePurpose purpose, int observations)
    {
        var session = new Session([
            new("battle.confirm-settlement", [], [Text("战斗胜利", 100, 100), Text("确认", 900, 650)]), Stage(null, Map)]);

        Assert.True(await BattleFlow.ContinueAsync(session, 1, false, default, purpose));
        Assert.Single(session.Inputs);
        Assert.Equal(observations, session.Observations);
        if (purpose == BattlePurpose.Mirror) Assert.Contains(session.Reports, item => item.Rule == "battle.mirror-exit");
    }

    [Theory]
    [InlineData(MirrorRewardFlow.GiftBox)]
    [InlineData(MirrorRewardFlow.GiftSelect)]
    [InlineData(MirrorSettlementFlow.Complete)]
    [InlineData(MirrorSettlementFlow.Clear)]
    public async Task MirrorBattleHandsGiftBoxesAndClearScreensBackWithoutAnotherBattleInput(string destination)
    {
        var session = new Session([Stage(null, destination)]);
        Assert.True(await BattleFlow.ContinueAsync(session, 1, true, default, BattlePurpose.Mirror));
        Assert.Empty(session.Inputs);
        Assert.Single(session.Reports, item => item.Rule == "battle.mirror-exit");
    }

    [Theory]
    [InlineData("battle/more_information_assets.png")]
    [InlineData("battle/turn_assets.png")]
    [InlineData("battle/pause_assets.png")]
    [InlineData("battle/dead_all.png")]
    [InlineData("battle/continue_assets.png")]
    [InlineData("battle/win_rate_assets.png")]
    public async Task MapWithIncidentalCombatMatchStillEntersTheSelectedNode(string combat)
    {
        using var stop = new CancellationTokenSource(TimeSpan.FromSeconds(2));
        var session = new Session([
            Stage("mirror.route.enter-node", Map, MirrorRouteFlow.Enter, combat),
            Stage(null, MirrorSettlementFlow.Clear)]);

        var result = await Runner(session, []).RunAsync(new() { Teams = Teams(), ClaimRewards = false }, stop.Token);

        Assert.Equal(RunOutcome.Completed, result.Outcome);
        Assert.Equal("mirror.route.enter-node", Assert.Single(session.Inputs).Rule);
        Assert.DoesNotContain(session.Reports, report => report.Rule == "battle.fight");
    }

    [Fact]
    public async Task TakingOverACombatPageIgnoresAnIncidentalObservationMatch()
    {
        using var stop = new CancellationTokenSource(TimeSpan.FromSeconds(2));
        var session = new Session([
            Stage("battle.win-rate", "battle/turn_assets.png", "battle/more_information_assets.png", MirrorRewardFlow.ObserveBurn),
            Stage(null, MirrorSettlementFlow.Clear)]);

        await Runner(session, []).RunAsync(new() { Teams = Teams(), ClaimRewards = false }, stop.Token);

        Assert.DoesNotContain(session.Reports, report => report.Rule.StartsWith("mirror.observe"));
        Assert.Contains(session.Reports, report => report.Rule == "battle.turn");
    }

    private static MirrorTeamOptions[] Teams() => [new() { Name = "A" }, new() { Name = "B" }];
    private static MirrorRunner Runner(Session session, List<MirrorTeamOptions[]> saved) => new(session, new NoMapReader(),
        (queue, _) => { saved.Add(queue.ToArray()); return Task.CompletedTask; });
    private static FrameState Stage(string? action, params string[] assets) => new(action, assets.Select(asset => Hit(asset)).ToArray());
    private static FrameState InfiniteState(string? action, string state, bool toggle = true) =>
        new(action, toggle ? [Hit(Enter), Hit(Infinite)] : [Hit(Enter)], [Text(state, 2200, 680)]);
    private static VisualTarget Hit(string asset, int x = 500, int y = 350) => asset == MirrorRouteFlow.Bus
        ? new(asset, new(80, 720), new(60, 710, 40, 20), 1)
        : new(asset, new(x, y), new(x - 20, y - 10, 40, 20), 1);
    private static RecognizedText Text(string text, int x, int y) => new(text, 1, new(x, y, 40, 20));
    private sealed record FrameState(string? Action, VisualTarget[] Targets, RecognizedText[]? Text = null, byte[]? Bgra = null);

    private sealed class NoMapReader : IMirrorMapReader
    {
        public MirrorMapSnapshot Read(PixelFrame frame, PixelPoint bus, CancellationToken cancellationToken) =>
            throw new InvalidOperationException("本测试路径不应进入地图寻路");
    }

    private sealed class ShopMapReader : IMirrorMapReader
    {
        public MirrorMapSnapshot Read(PixelFrame frame, PixelPoint bus, CancellationToken cancellationToken) => new(frame.Identity, bus,
            [new(0, MirrorNodeKind.Shop, new(900, 350), new(880, 330, 40, 40), .99)], [new(-1, 0)]);
    }

    private sealed class RemainingMapReader(int remaining) : IMirrorMapReader
    {
        public List<PixelPoint> Buses { get; } = [];
        public int NodeCount { get; private set; }
        public MirrorMapSnapshot Read(PixelFrame frame, PixelPoint bus, CancellationToken cancellationToken)
        {
            Buses.Add(bus);
            var nodes = Enumerable.Range(0, remaining).Select(index => new MirrorRouteNode(index,
                index == remaining - 1 ? MirrorNodeKind.BossBattle : MirrorNodeKind.Event,
                new(bus.X + 512 * (index + 1), bus.Y + 40), new(bus.X + 512 * (index + 1) - 20, bus.Y + 20, 40, 40), .99)).ToArray();
            NodeCount = nodes.Length;
            return new(frame.Identity, bus, nodes, Enumerable.Range(0, remaining).Select(index => new MirrorRouteConnection(index - 1, index)).ToArray());
        }
    }

    /// <summary>在指定规则的输入发送前抛出瞬时错误，模拟画面过期或窗口消息未确认；其余调用转交内部会话。</summary>
    private sealed class FlakySession(Session inner, string failingRule, int failures = 1) : IGameSession
    {
        public int Failures { get; private set; }
        public TimeSpan Elapsed => inner.Elapsed;
        public int Observations => inner.Observations;
        public ValueTask<GameFrame> ObserveAsync(IReadOnlyList<ImageQuery> queries, CancellationToken ct) => inner.ObserveAsync(queries, ct);
        public ValueTask<IReadOnlyList<RecognizedText>> ReadTextAsync(GameFrame frame, CancellationToken ct, PixelRect? region = null,
            int scale = 1, TextPreprocessing preprocessing = TextPreprocessing.None) => inner.ReadTextAsync(frame, ct, region, scale, preprocessing);
        public ValueTask ClickAsync(GameFrame frame, PixelPoint target, string rule, CancellationToken ct)
        {
            if (rule == failingRule && Failures < failures)
            {
                Failures++;
                throw new GameTransientException("测试模拟识别画面已过期");
            }
            return inner.ClickAsync(frame, target, rule, ct);
        }
        public ValueTask KeyAsync(GameFrame frame, GameKey key, string rule, CancellationToken ct) => inner.KeyAsync(frame, key, rule, ct);
        public ValueTask DragAsync(GameFrame frame, PixelPoint from, PixelPoint to, TimeSpan duration, string rule, CancellationToken ct) =>
            inner.DragAsync(frame, from, to, duration, rule, ct);
        public ValueTask DelayAsync(TimeSpan duration, CancellationToken ct) => inner.DelayAsync(duration, ct);
        public void Report(string rule, string message) => inner.Report(rule, message);
        public ValueTask<bool> RestartGameAsync(string reason, CancellationToken ct) => inner.RestartGameAsync(reason, ct);
    }

    private sealed class Session(IReadOnlyList<FrameState> states, int width = 2560, int height = 1440) : IGameSession
    {
        private int index;
        private int textReads;
        private int infiniteClicks;
        private int hiddenInfiniteObservations;
        public int IgnoredInfiniteClicks { get; init; }
        public int HiddenInfiniteObservationsAfterClick { get; init; }
        public int InitialEmptyTextReads { get; init; }
        public TimeSpan Elapsed { get; private set; }
        public int Observations { get; private set; }
        public int Restarts { get; private set; }
        public ValueTask<bool> RestartGameAsync(string reason, CancellationToken ct)
        {
            Restarts++;
            return ValueTask.FromResult(false);
        }
        public List<(string Rule, PixelPoint Target, long Frame)> Inputs { get; } = [];
        public List<(string Rule, string Message)> Reports { get; } = [];
        public ValueTask<GameFrame> ObserveAsync(IReadOnlyList<ImageQuery> queries, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            var targets = states[index].Targets.Where(hit => queries.Any(query => query.Asset == hit.Asset && query.Threshold <= hit.Score)).ToArray();
            if (hiddenInfiniteObservations > 0)
            {
                hiddenInfiniteObservations--;
                targets = targets.Where(hit => hit.Asset != Infinite).ToArray();
            }
            return ValueTask.FromResult(new GameFrame(new(new(++Observations, width, height, 1, 0), states[index].Bgra ?? []), targets));
        }
        public ValueTask<IReadOnlyList<RecognizedText>> ReadTextAsync(GameFrame frame, CancellationToken ct, PixelRect? region = null, int scale = 1, TextPreprocessing preprocessing = TextPreprocessing.None)
        {
            ct.ThrowIfCancellationRequested();
            if (++textReads <= InitialEmptyTextReads) return ValueTask.FromResult<IReadOnlyList<RecognizedText>>([]);
            var text = states[index].Text ?? [];
            return ValueTask.FromResult<IReadOnlyList<RecognizedText>>(text.Where(item => region is null
                || region.Value.Contains(item.Bounds.X + item.Bounds.Width / 2, item.Bounds.Y + item.Bounds.Height / 2)).ToArray());
        }
        public ValueTask ClickAsync(GameFrame frame, PixelPoint target, string rule, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            Assert.Equal(Observations, frame.Identity.Id);
            Assert.InRange(target.X, 0, width - 1);
            Assert.InRange(target.Y, 0, height - 1);
            Assert.Equal(states[index].Action, rule);
            Assert.True(index < states.Count - 1, "末状态不应发送额外输入");
            Inputs.Add((rule, target, frame.Identity.Id));
            if (rule == "mirror.entry.disable-infinite")
            {
                hiddenInfiniteObservations = HiddenInfiniteObservationsAfterClick;
                if (++infiniteClicks <= IgnoredInfiniteClicks) return ValueTask.CompletedTask;
            }
            index++;
            return ValueTask.CompletedTask;
        }
        public ValueTask KeyAsync(GameFrame frame, GameKey key, string rule, CancellationToken ct) => ClickAsync(frame, new(1, 1), rule, ct);
        public ValueTask DragAsync(GameFrame frame, PixelPoint from, PixelPoint to, TimeSpan duration, string rule, CancellationToken ct) => ClickAsync(frame, from, rule, ct);
        public ValueTask DelayAsync(TimeSpan duration, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            Elapsed += duration;
            return ValueTask.CompletedTask;
        }
        public void Report(string rule, string message) => Reports.Add((rule, message));
    }
}
