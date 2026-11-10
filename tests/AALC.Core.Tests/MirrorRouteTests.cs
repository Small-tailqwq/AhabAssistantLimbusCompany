using AALC.Core.Automation;
using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;
using AALC.Runtime.Mirror;
using Xunit;

namespace AALC.Core.Tests;

public sealed class MirrorRouteTests
{
    private static MirrorRouteNode Node(int id, MirrorNodeKind kind, int x, int y = 350) =>
        new(id, kind, new(x, y), new(x - 30, y - 30, 60, 60), .9);
    private static MirrorMapSnapshot Map(FrameIdentity frame, MirrorRouteNode[]? nodes = null,
        MirrorRouteConnection[]? edges = null) => new(frame, new(40, 360),
            nodes ?? [Node(0, MirrorNodeKind.Event, 350)], edges ?? [new(-1, 0)]);

    [Fact]
    public void AVisibleNodeWithoutAConnectionIsNotConsideredReachable()
    {
        Assert.Null(MirrorRoutePlanner.Choose(Map(new(1, 1280, 720, 1, 0), edges: []), new()));
    }

    [Fact]
    public void RouteCostUsesTheVisibleConnectedPathRatherThanTheCheapestFirstNode()
    {
        var map = Map(new(1, 1280, 720, 1, 0),
            [Node(0, MirrorNodeKind.Event, 350, 200), Node(1, MirrorNodeKind.Battle, 350, 400),
                Node(2, MirrorNodeKind.EliteBattle, 600, 200), Node(3, MirrorNodeKind.Event, 600, 400),
                Node(4, MirrorNodeKind.BossBattle, 850)],
            [new(-1, 0), new(-1, 1), new(0, 2), new(1, 3), new(2, 4), new(3, 4)]);
        var plan = MirrorRoutePlanner.Choose(map, new());
        Assert.Equal([1, 3, 4], plan!.Nodes.Select(node => node.Id));
        Assert.Equal(228, plan.Cost);
    }

    [Fact]
    public void AnUnobservedShopOrBossIsNeverAddedToThePlan()
    {
        var plan = MirrorRoutePlanner.Choose(Map(new(1, 1280, 720, 1, 0)), new());
        Assert.Equal(MirrorNodeKind.Event, Assert.Single(plan!.Nodes).Kind);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void ABossWithAnObservedSuccessorKeepsThatSuccessorInThePlan(bool hardMode)
    {
        var map = Map(new(1, 1280, 720, 1, 0),
            [Node(0, MirrorNodeKind.BossBattle, 724, 124), Node(1, MirrorNodeKind.Event, 980, 335)],
            [new(-1, 0), new(0, 1)]);

        var plan = MirrorRoutePlanner.Choose(map, new(hardMode));

        Assert.Equal([0, 1], plan!.Nodes.Select(node => node.Id));
        Assert.Equal(148, plan.Cost);
    }

    [Fact]
    public void AConnectingBossDoesNotOverrideTheCheaperRouteToAnObservedTerminalBoss()
    {
        var map = Map(new(1, 1280, 720, 1, 0),
            [Node(0, MirrorNodeKind.BossBattle, 350, 200), Node(1, MirrorNodeKind.Event, 350, 400),
                Node(2, MirrorNodeKind.HardBattle, 600, 200), Node(3, MirrorNodeKind.Event, 600, 400),
                Node(4, MirrorNodeKind.BossBattle, 850)],
            [new(-1, 0), new(-1, 1), new(0, 2), new(1, 3), new(2, 4), new(3, 4)]);

        var plan = MirrorRoutePlanner.Choose(map, new());

        Assert.Equal([1, 3, 4], plan!.Nodes.Select(node => node.Id));
        Assert.Equal(166, plan.Cost);
    }

    [Fact]
    public void AnUnclassifiedNodeKeepsItsIdentityAndConservativeCost()
    {
        var plan = MirrorRoutePlanner.Choose(Map(new(1, 1280, 720, 1, 0),
            [Node(0, MirrorNodeKind.Unknown, 350)]), new());

        Assert.Equal(MirrorNodeKind.Unknown, Assert.Single(plan!.Nodes).Kind);
        Assert.Equal(999, plan.Cost);
    }

    [Fact]
    public void AKnownRouteIsPreferredToAnUnknownRouteInTheSameColumn()
    {
        var plan = MirrorRoutePlanner.Choose(Map(new(1, 1280, 720, 1, 0),
            [Node(0, MirrorNodeKind.Unknown, 350, 200), Node(1, MirrorNodeKind.Event, 350, 400)],
            [new(-1, 0), new(-1, 1)]), new());

        Assert.Equal(MirrorNodeKind.Event, Assert.Single(plan!.Nodes).Kind);
    }

    [Fact]
    public void HardModeLimitsTheVisibleLookaheadToTwoNodes()
    {
        var map = Map(new(1, 1280, 720, 1, 0),
            [Node(0, MirrorNodeKind.Event, 350, 200), Node(1, MirrorNodeKind.Battle, 350, 400),
                Node(2, MirrorNodeKind.Event, 600, 200), Node(3, MirrorNodeKind.Battle, 600, 400),
                Node(4, MirrorNodeKind.AbnormalityBattle, 850, 200), Node(5, MirrorNodeKind.Shop, 850, 400)],
            [new(-1, 0), new(-1, 1), new(0, 2), new(1, 3), new(2, 4), new(3, 5)]);
        Assert.Equal(1, MirrorRoutePlanner.Choose(map, new())!.Nodes[0].Id);
        Assert.Equal([0, 2], MirrorRoutePlanner.Choose(map, new(true))!.Nodes.Select(node => node.Id));
    }

    [Theory]
    [InlineData(MirrorNodeKind.Event)]
    [InlineData(MirrorNodeKind.Unknown)]
    public async Task NodeSelectionAndEntryRequireFreshFeedbackBeforeAConfirmedHandoff(MirrorNodeKind kind)
    {
        var phase = 0;
        var session = new FakeSession(() => phase switch
        {
            0 => [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus],
            1 => [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus, MirrorRouteFlow.Enter],
            _ => ["teams/identify_assets.png"]
        });
        session.Action = rule => phase = rule == "mirror.route.select-node" ? 1 : 2;
        var reader = new FakeReader(frame => Map(frame, [Node(0, kind, 350)]));
        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);
        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(kind, result.Node);
        Assert.Equal(["mirror.route.select-node", "mirror.route.enter-node"], session.Actions);
        Assert.Equal([3, 4], session.InputFrames);
        Assert.Equal(5, session.Observations);
        Assert.Equal([3], reader.Frames);
    }

    [Fact]
    public async Task ClickingWithoutAPageChangeFailsInsteadOfCompletingTheNode()
    {
        var session = new FakeSession(() => [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus]);
        var result = await new MirrorRouteFlow(session, new FakeReader(frame => Map(frame))).AdvanceAsync(new(), default);
        Assert.Equal(MirrorRouteOutcome.Failed, result.Outcome);
        Assert.Equal("destination-unconfirmed", result.Reason);
        Assert.Equal(["mirror.route.select-node", "mirror.route.select-node", "mirror.route.select-bus", "mirror.route.select-node"], session.Actions);
        Assert.InRange(session.Observations, 3, 25);
    }

    [Fact]
    public async Task AnInterruptedNodeIsReenteredThroughTheBus()
    {
        var entered = false;
        var opened = false;
        var session = new FakeSession(() => entered ? ["teams/identify_assets.png"]
            : opened ? [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus, MirrorRouteFlow.Enter] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus]);
        session.Action = rule =>
        {
            if (rule == "mirror.route.select-bus") opened = true;
            if (rule == "mirror.route.enter-node") entered = true;
        };

        var result = await new MirrorRouteFlow(session, new FakeReader(frame => Map(frame))).AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(["mirror.route.select-node", "mirror.route.select-node", "mirror.route.select-bus", "mirror.route.enter-node"], session.Actions);
    }

    [Fact]
    public async Task DisappearanceOfTheMapWithoutADestinationIsInsufficient()
    {
        var clicked = false;
        var session = new FakeSession(() => clicked ? [] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus]);
        session.Action = _ => clicked = true;
        var result = await new MirrorRouteFlow(session, new FakeReader(frame => Map(frame))).AdvanceAsync(new(), default);
        Assert.Equal(MirrorRouteOutcome.Failed, result.Outcome);
        Assert.Equal("destination-unconfirmed", result.Reason);
        Assert.Single(session.Actions);
    }

    [Fact]
    public async Task ExistingEntryConfirmationDoesNotRequireANewRouteSelection()
    {
        var entered = false;
        var session = new FakeSession(() => entered ? ["mirror/shop/shop_coins_assets.png"]
            : [MirrorRouteFlow.Enter]);
        session.Action = _ => entered = true;
        var reader = new FakeReader(_ => throw new InvalidOperationException("不应重新寻路"));
        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);
        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Null(result.Node);
        Assert.Equal(["mirror.route.enter-node"], session.Actions);
        Assert.Empty(reader.Frames);
    }

    [Theory]
    [InlineData("battle/normal_to_battle_assets.png")]
    [InlineData("battle/chaim_to_battle_assets.png")]
    [InlineData("mirror/theme_pack/feature_theme_pack_assets.png")]
    [InlineData("event/skip_assets.png")]
    [InlineData("event/select_to_gain_ego.png")]
    [InlineData(MirrorSettlementFlow.Clear)]
    [InlineData(MirrorSettlementFlow.Complete)]
    [InlineData(MirrorSettlementFlow.Claim)]
    [InlineData(MirrorRewardFlow.Cards)]
    [InlineData(MirrorRewardFlow.Gift)]
    [InlineData(MirrorRewardFlow.GiftBox)]
    public async Task KnownStartThemeAndSettlementPagesConfirmTheEntryHandoff(string destination)
    {
        var entered = false;
        var session = new FakeSession(() => entered ? [destination] : [MirrorRouteFlow.Enter]);
        session.Action = _ => entered = true;
        var result = await new MirrorRouteFlow(session, new FakeReader(_ => throw new InvalidOperationException()))
            .AdvanceAsync(new(), default);
        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Single(session.Actions);
    }

    [Fact]
    public async Task AForegroundDestinationTakesPriorityOverABackgroundMap()
    {
        var session = new FakeSession(() => [MirrorRouteFlow.Legend, "teams/identify_assets.png"]);
        var result = await new MirrorRouteFlow(session, new FakeReader(_ => throw new InvalidOperationException()))
            .AdvanceAsync(new(), default);
        Assert.Equal(MirrorRouteOutcome.NotMap, result.Outcome);
        Assert.Empty(session.Actions);
    }

    [Fact]
    public async Task RecognizedLoadingCanExceedTheUnknownPageBudget()
    {
        FakeSession session = null!;
        var entered = false;
        session = new FakeSession(() => !entered ? [MirrorRouteFlow.Enter]
            : session.Elapsed < TimeSpan.FromSeconds(6) ? ["base/waiting_assets.png"] : ["teams/identify_assets.png"]);
        session.Action = _ => entered = true;
        var result = await new MirrorRouteFlow(session, new FakeReader(_ => throw new InvalidOperationException()))
            .AdvanceAsync(new(), default);
        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.True(session.Elapsed >= TimeSpan.FromSeconds(6));
        Assert.Single(session.Actions);
    }

    [Fact]
    public async Task LoadingConfirmationStillHasAThirtySecondDeadline()
    {
        var entered = false;
        var session = new FakeSession(() => entered ? ["base/waiting_assets.png"] : [MirrorRouteFlow.Enter]);
        session.Action = _ => entered = true;
        var result = await new MirrorRouteFlow(session, new FakeReader(_ => throw new InvalidOperationException()))
            .AdvanceAsync(new(), default);
        Assert.Equal(MirrorRouteOutcome.Failed, result.Outcome);
        Assert.Equal(TimeSpan.FromSeconds(30), session.Elapsed);
        Assert.Single(session.Actions);
    }

    [Fact]
    public async Task EntryCanSucceedOnItsThirdAttemptWithFreshFramesAndSpacedClicks()
    {
        var clicks = 0;
        var session = new FakeSession(() => clicks >= 3 ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Enter]);
        session.Action = _ => clicks++;

        var result = await new MirrorRouteFlow(session, new FakeReader(_ => throw new InvalidOperationException()))
            .AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(3, session.Actions.Count);
        Assert.All(session.Actions, action => Assert.Equal("mirror.route.enter-node", action));
        Assert.Equal(3, session.InputFrames.Distinct().Count());
        Assert.All(session.InputTimes.Zip(session.InputTimes.Skip(1), (before, after) => after - before),
            interval => Assert.True(interval >= TimeSpan.FromMilliseconds(1250)));
    }

    [Fact]
    public async Task AVisibleEntryButtonUsesAtMostThreeClicksAndKeepsObservingUntilTheDeadline()
    {
        var session = new FakeSession(() => [MirrorRouteFlow.Enter]);

        var result = await new MirrorRouteFlow(session, new FakeReader(_ => throw new InvalidOperationException()))
            .AdvanceAsync(new(), default);

        Assert.Equal("destination-unconfirmed", result.Reason);
        Assert.Equal(TimeSpan.FromSeconds(30), session.Elapsed);
        Assert.Equal(3, session.Actions.Count);
        Assert.True(session.Observations > session.InputFrames[^1]);
        Assert.All(session.InputTimes.Zip(session.InputTimes.Skip(1), (before, after) => after - before),
            interval => Assert.True(interval >= TimeSpan.FromMilliseconds(1250)));
    }

    [Fact]
    public async Task ADisappearingEntryButtonIsNotClickedAgainOnAnUnknownPage()
    {
        var clicked = false;
        var session = new FakeSession(() => clicked ? [] : [MirrorRouteFlow.Enter]);
        session.Action = _ => clicked = true;

        var result = await new MirrorRouteFlow(session, new FakeReader(_ => throw new InvalidOperationException()))
            .AdvanceAsync(new(), default);

        Assert.Equal("destination-unconfirmed", result.Reason);
        Assert.Equal(["mirror.route.enter-node"], session.Actions);
    }

    [Fact]
    public async Task MissingBusStopsWithoutGuessingAPosition()
    {
        var session = new FakeSession(() => [MirrorRouteFlow.Legend]);
        var result = await new MirrorRouteFlow(session, new FakeReader(_ => throw new InvalidOperationException()))
            .AdvanceAsync(new(), default);
        Assert.Equal("bus-not-visible", result.Reason);
        Assert.Empty(session.Actions);
    }

    [Fact]
    public async Task CameraAdjustmentRebuildsTheMapFromTheNewFrame()
    {
        var bus = new PixelPoint(40, 360);
        var selected = false;
        var session = new FakeSession(() => selected ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        { BusPosition = _ => bus };
        session.Action = rule =>
        {
            if (rule == "mirror.route.align-camera") bus = new(bus.X, bus.Y + session.InputPoints[^1].Y - 360);
            else selected = true;
        };
        var reader = new FakeReader(frame => Map(frame, [Node(0, MirrorNodeKind.Event, 350, 72 + bus.Y - 360)],
            bus.Y == 360 ? [] : [new(-1, 0)]));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(["mirror.route.align-camera", "mirror.route.select-node"], session.Actions);
        Assert.Equal([3L, 6L], reader.Frames);
        Assert.Equal([new PixelPoint(640, 447), new(350, 159)], session.InputPoints);
    }

    [Fact]
    public async Task AVisibleRouteWithClippedGlyphsIsScannedBeforeItsFreshPlanIsSelected()
    {
        var bus = new PixelPoint(469, 264);
        var selected = false;
        var session = new FakeSession(() => selected ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        { BusPosition = _ => bus };
        session.Action = rule =>
        {
            if (rule == "mirror.route.align-camera")
                bus = new(bus.X + session.InputPoints[^1].X - 640, bus.Y + session.InputPoints[^1].Y - 360);
            else selected = true;
        };
        var reader = new FakeReader(frame => Map(frame,
            [Node(0, MirrorNodeKind.Event, bus.X + 256, bus.Y - 190),
                Node(1, MirrorNodeKind.Battle, bus.X + 256, bus.Y + 22),
                Node(2, MirrorNodeKind.Event, bus.X + 256, bus.Y + 234)], [new(-1, 1)]));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(["mirror.route.align-camera", "mirror.route.select-node"], session.Actions);
        Assert.Equal(new PixelPoint(469, 349), bus);
        Assert.Equal(new PixelPoint(725, 371), session.InputPoints[^1]);
        Assert.Equal(reader.Frames[^1], session.InputFrames[^1]);
        Assert.Equal([3L, 6L], reader.Frames);
        Assert.Single(session.Reports, report => report.Rule == "mirror.route.scan-complete");
    }

    [Fact]
    public async Task AUsableMapDoesNotDragBeforeSelection()
    {
        var selected = false;
        var session = new FakeSession(() => selected ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus]);
        session.Action = _ => selected = true;

        var result = await new MirrorRouteFlow(session, new FakeReader(frame => Map(frame))).AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(["mirror.route.select-node"], session.Actions);
        Assert.Equal([3L], session.InputFrames);
    }

    [Theory]
    [InlineData(720, 300, 310, 522, 0)]
    [InlineData(1440, 300, 310, 522, 0)]
    [InlineData(720, 350, 138, 350, 1)]
    [InlineData(1440, 350, 138, 350, 1)]
    [InlineData(720, 264, 286, 498, 0)]
    [InlineData(1440, 264, 286, 498, 0)]
    public async Task TwoUsableVisibleRowsNeedNoAdditionalCameraEvidence(int height, int busY, int upper, int lower, int connectedRow)
    {
        var factor = height / 720;
        var selected = false;
        var session = new FakeSession(() => selected ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus], height)
        { BusPosition = _ => new(469 * factor, busY * factor) };
        session.Action = _ => selected = true;
        var reader = new FakeReader(frame => Map(frame,
            [Node(0, MirrorNodeKind.Event, 725 * factor, upper * factor), Node(1, MirrorNodeKind.Event, 725 * factor, lower * factor)],
            [new(-1, connectedRow)]));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(["mirror.route.select-node"], session.Actions);
        Assert.Equal(new PixelPoint(725 * factor, (connectedRow == 0 ? upper : lower) * factor), session.InputPoints[^1]);
        Assert.Equal([3L], reader.Frames);
    }

    [Fact]
    public async Task AnIneffectivePanCannotSelectAnObscuredNode()
    {
        var session = new FakeSession(() => [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus]);
        var reader = new FakeReader(frame => Map(frame, [Node(0, MirrorNodeKind.Event, 350, 72)]));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal("camera-no-progress", result.Reason);
        Assert.Equal(["mirror.route.align-camera"], session.Actions);
        Assert.Equal([3L, 6L], reader.Frames);
    }

    [Fact]
    public async Task RepeatedOcclusionHasOneFourPanBudget()
    {
        var bus = new PixelPoint(469, 200);
        var session = new FakeSession(() => [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        { BusPosition = _ => bus };
        session.Action = _ => bus = bus with { Y = bus.Y + 3 };
        var reader = new FakeReader(frame => Map(frame, [Node(0, MirrorNodeKind.Event, 725, 72)], []));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal("no-confirmed-connection", result.Reason);
        Assert.Equal(4, session.Actions.Count);
        Assert.All(session.Actions, rule => Assert.Equal("mirror.route.align-camera", rule));
        Assert.Equal(5, reader.Frames.Count);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task AConfirmedBossOrShopBossPathUsesTheCurrentFrameWithoutDragging(bool shop)
    {
        var selected = false;
        var session = new FakeSession(() => selected ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        { BusPosition = _ => new(469, 264) };
        session.Action = _ => selected = true;
        var reader = new FakeReader(frame => Map(frame,
            shop ? [Node(0, MirrorNodeKind.Shop, 725, 286), Node(1, MirrorNodeKind.BossBattle, 981, 286), Node(2, MirrorNodeKind.Event, 1237, 72)]
                : [Node(0, MirrorNodeKind.BossBattle, 725, 286), Node(2, MirrorNodeKind.Event, 1237, 72)],
            shop ? [new(-1, 0), new(0, 1)] : [new(-1, 0)]));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(shop ? MirrorNodeKind.Shop : MirrorNodeKind.BossBattle, result.Node);
        Assert.Equal(["mirror.route.select-node"], session.Actions);
        Assert.Equal([new PixelPoint(725, 286)], session.InputPoints);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ABossWithAnObservedContinuationDoesNotEndScanningBeforeTheCurrentPathIsVisible(bool hardMode)
    {
        var selected = false;
        var bus = new PixelPoint(469, 264);
        var session = new FakeSession(() => selected ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        { BusPosition = _ => bus };
        session.Action = rule =>
        {
            if (rule == "mirror.route.align-camera") bus = new(179, 264);
            if (rule == "mirror.route.select-node") selected = true;
        };
        var reader = new FakeReader(frame => Map(frame,
            [Node(0, hardMode ? MirrorNodeKind.Event : MirrorNodeKind.BossBattle, bus.X + 256, bus.Y + 25),
                Node(1, hardMode ? MirrorNodeKind.BossBattle : MirrorNodeKind.Event, bus.X + 512, bus.Y + 238),
                Node(2, MirrorNodeKind.Battle, bus.X + 768, bus.Y + 25)],
            [new(-1, 0), new(0, 1), new(1, 2)]));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(hardMode), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(hardMode ? MirrorNodeKind.Event : MirrorNodeKind.BossBattle, result.Node);
        Assert.Equal(["mirror.route.align-camera", "mirror.route.select-node"], session.Actions);
        Assert.Equal(2, reader.Frames.Count);
        Assert.Equal(new PixelPoint(435, 289), session.InputPoints[^1]);
        Assert.Equal(reader.Frames[^1], session.InputFrames[^1]);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task AForegroundPageOrEntryButtonAfterDraggingTakesPriorityOverFurtherScanning(bool entry)
    {
        var phase = 0;
        var session = new FakeSession(() => phase == 0 ? [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus]
            : phase == 1 && entry ? [MirrorRouteFlow.Legend, MirrorRouteFlow.Enter] : ["teams/identify_assets.png"])
        { BusPosition = _ => new(469, 264) };
        session.Action = _ => phase++;

        var result = await new MirrorRouteFlow(session, new FakeReader(frame => Map(frame,
            [Node(0, MirrorNodeKind.Event, 725, 72)]))).AdvanceAsync(new(), default);

        Assert.Equal(entry ? MirrorRouteOutcome.Entered : MirrorRouteOutcome.NotMap, result.Outcome);
        Assert.Equal(entry ? ["mirror.route.align-camera", "mirror.route.enter-node"] : ["mirror.route.align-camera"], session.Actions);
    }

    [Fact]
    public async Task LosingTheMapAfterDraggingCannotUseTheOriginalPlan()
    {
        var dragged = false;
        var session = new FakeSession(() => dragged ? [] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        { BusPosition = _ => new(469, 264) };
        session.Action = _ => dragged = true;

        var result = await new MirrorRouteFlow(session, new FakeReader(frame => Map(frame,
            [Node(0, MirrorNodeKind.Event, 725, 72)]))).AdvanceAsync(new(), default);

        Assert.Equal("map-lost-after-camera", result.Reason);
        Assert.Equal(["mirror.route.align-camera"], session.Actions);
    }

    [Fact]
    public async Task CancellationAfterScanningPanPreventsAnyNodeInput()
    {
        using var stop = new CancellationTokenSource();
        var session = new FakeSession(() => [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        { BusPosition = _ => new(469, 264) };
        session.Action = _ => stop.Cancel();

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => new MirrorRouteFlow(session,
            new FakeReader(frame => Map(frame, [Node(0, MirrorNodeKind.Event, 725, 72)]))).AdvanceAsync(new(), stop.Token));

        Assert.Equal(["mirror.route.align-camera"], session.Actions);
    }

    [Fact]
    public async Task AutomaticMapCenteringMustSettleBeforeTheCurrentFrameIsPlannedAndClicked()
    {
        PixelPoint[] centers = [new(60, 264), new(56, 189), new(55, 172), new(55, 170), new(55, 169)];
        var selected = false;
        var session = new FakeSession(() => selected ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        {
            BusPosition = observation => centers[Math.Min(observation - 1, centers.Length - 1)]
        };
        session.Action = _ => selected = true;
        var reader = new FakeReader(frame => Map(frame, [Node(0, MirrorNodeKind.BossBattle, 724, 198)]));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal([5L], reader.Frames);
        Assert.Equal([new PixelPoint(55, 169)], reader.Buses);
        Assert.Equal([5L], session.InputFrames);
        Assert.Equal([new PixelPoint(724, 198)], session.InputPoints);
    }

    [Fact]
    public async Task AContinuouslyMovingMapCannotBePlannedOrClicked()
    {
        var session = new FakeSession(() => [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        {
            BusPosition = observation => new(500, 200 + observation * 5)
        };
        var reader = new FakeReader(_ => throw new InvalidOperationException("移动中的地图不应规划"));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal("map-moving", result.Reason);
        Assert.Empty(session.Actions);
        Assert.Empty(reader.Frames);
        Assert.Equal(13, session.Observations);
    }

    [Fact]
    public async Task ABriefBlackoutResetsStabilityAndWaitsForFreshMapFeedback()
    {
        FakeSession session = null!;
        var selected = false;
        session = new FakeSession(() => selected ? ["teams/identify_assets.png"] : session.Observations == 2
            ? [] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus]);
        session.Action = _ => selected = true;
        var reader = new FakeReader(frame => Map(frame));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal([6L], reader.Frames);
        Assert.Equal([6L], session.InputFrames);
    }

    [Fact]
    public async Task ABlackoutThatDoesNotClearHasABoundedWaitAndNoNodeInput()
    {
        FakeSession session = null!;
        session = new FakeSession(() => session.Observations == 0 ? [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus] : []);
        var reader = new FakeReader(_ => throw new InvalidOperationException("未知页面不应规划"));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Failed, result.Outcome);
        Assert.Equal(13, session.Observations);
        Assert.Empty(reader.Frames);
        Assert.Empty(session.Actions);
    }

    [Fact]
    public async Task AMissedSelectionRebuildsThePlanOnAFreshStableFrameInsteadOfRepeatingTheOldPoint()
    {
        var selected = 0;
        var entered = false;
        var session = new FakeSession(() => entered ? ["teams/identify_assets.png"] : selected >= 2
            ? [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus, MirrorRouteFlow.Enter] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        {
            BusPosition = observation => selected == 0 ? new(40, 360) : observation switch
            { 4 => new(300, 300), 5 => new(330, 270), _ => new(340, 260) }
        };
        session.Action = rule => { if (rule == "mirror.route.select-node") selected++; else entered = true; };
        var reads = 0;
        var reader = new FakeReader(frame => Map(frame,
            [++reads == 1 ? Node(0, MirrorNodeKind.BossBattle, 350) : Node(0, MirrorNodeKind.BossBattle, 650, 250)]));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(["mirror.route.select-node", "mirror.route.select-node", "mirror.route.enter-node"], session.Actions);
        Assert.Equal([3L, 8L], reader.Frames);
        Assert.Equal([3L, 8L, 9L], session.InputFrames);
        Assert.Equal([new PixelPoint(350, 350), new(650, 250)], session.InputPoints.Take(2));
    }

    [Fact]
    public async Task UnclearConnectionsWithoutAnOcclusionCueStopWithoutGuessingACameraDirection()
    {
        var session = new FakeSession(() => [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus]);
        var reader = new FakeReader(frame => Map(frame, edges: []));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal("no-confirmed-connection", result.Reason);
        Assert.Empty(session.Actions);
        Assert.Equal([3L], reader.Frames);
    }

    [Theory]
    [InlineData(72, 61)]
    [InlineData(648, -72)]
    public async Task AnObscuredGlyphUsesItsBoundsToMoveAndConfirmOnAFreshFrame(int y, int deltaY)
    {
        var bus = new PixelPoint(40, 360);
        var selected = false;
        var session = new FakeSession(() => selected ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        { BusPosition = _ => bus };
        session.Action = rule =>
        {
            if (rule == "mirror.route.align-camera") bus = new(bus.X, bus.Y + session.InputPoints[^1].Y - 360);
            else selected = true;
        };
        var reader = new FakeReader(frame => Map(frame, [new(0, MirrorNodeKind.HardBattle, new(725, y + bus.Y - 360),
            new(696, y + bus.Y - 360 - 17, 58, 35), .9407)]));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(["mirror.route.align-camera", "mirror.route.select-node"], session.Actions);
        Assert.Equal([new PixelPoint(640, 360 + deltaY + Math.Sign(deltaY) * 13), new(725, y + deltaY + Math.Sign(deltaY) * 13)], session.InputPoints);
        Assert.Equal([3L, 6L], reader.Frames);
        Assert.Equal([3L, 6L], session.InputFrames);
    }

    [Theory]
    [InlineData(720)]
    [InlineData(1440)]
    public async Task ATopEventFivePixelsOutsideTheCanvasUsesAnEffectivePanAndFreshConfirmation(int height)
    {
        var factor = height / 720;
        var bus = new PixelPoint(191 * factor, 313 * factor);
        var selected = false;
        var session = new FakeSession(() => selected ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus], height)
        { BusPosition = _ => bus };
        session.Action = rule =>
        {
            if (rule == "mirror.route.align-camera")
            {
                var delta = session.InputPoints[^1].Y - 360 * factor;
                if (Math.Abs(delta) >= 16 * factor) bus = bus with { Y = bus.Y + delta - Math.Sign(delta) * 10 * factor };
            }
            else selected = true;
        };
        var reader = new FakeReader(frame => Map(frame,
            [new(1, MirrorNodeKind.Event, new(445 * factor, 118 * factor + bus.Y - 313 * factor),
                new(423 * factor, 95 * factor + bus.Y - 313 * factor, 44 * factor, 45 * factor), .9167)], [new(-1, 1)]));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(["mirror.route.align-camera", "mirror.route.select-node"], session.Actions);
        Assert.Equal([new PixelPoint(640 * factor, 405 * factor), new(445 * factor, 153 * factor)], session.InputPoints);
        Assert.Equal([3L, 6L], reader.Frames);
        Assert.Equal([3L, 6L], session.InputFrames);
    }

    [Theory]
    [InlineData(72)]
    [InlineData(648)]
    public async Task AnObscuredNodeWithNoActualCameraMotionStopsAfterOnePan(int y)
    {
        var session = new FakeSession(() => [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus]);
        var reader = new FakeReader(frame => Map(frame, [Node(0, MirrorNodeKind.HardBattle, 725, y)]));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal("camera-no-progress", result.Reason);
        Assert.Equal(["mirror.route.align-camera"], session.Actions);
        Assert.Equal(2, reader.Frames.Count);
    }

    [Fact]
    public async Task ReplanningAfterAMissedClickSharesTheRemainingCameraBudget()
    {
        var bus = new PixelPoint(40, 360);
        var pans = 0;
        var selected = false;
        var session = new FakeSession(() => [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        { BusPosition = _ => bus };
        session.Action = rule =>
        {
            if (rule == "mirror.route.align-camera")
            {
                pans++;
                bus = bus with { Y = bus.Y + (selected ? 3 : session.InputPoints[^1].Y - 360) };
            }
            else selected = true;
        };
        var reader = new FakeReader(frame => Map(frame, [Node(0, MirrorNodeKind.HardBattle, 350,
            selected ? 72 + (pans - 1) * 3 : 72 + bus.Y - 360)]));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal("node-outside-map", result.Reason);
        Assert.Equal(4, session.Actions.Count(rule => rule == "mirror.route.align-camera"));
        Assert.Single(session.Actions, rule => rule == "mirror.route.select-node");
        Assert.Equal(new PixelPoint(350, 159), session.InputPoints[1]);
    }

    [Fact]
    public async Task CancellationAfterSelectionPreventsEntryInput()
    {
        using var cancellation = new CancellationTokenSource();
        var session = new FakeSession(() => [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus]);
        session.Action = _ => cancellation.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => new MirrorRouteFlow(session,
            new FakeReader(frame => Map(frame))).AdvanceAsync(new(), cancellation.Token));
        Assert.Equal(["mirror.route.select-node"], session.Actions);
    }

    [Fact]
    public async Task MapResultsFromAnotherFrameCannotBeUsedForInput()
    {
        var session = new FakeSession(() => [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus]);
        await Assert.ThrowsAsync<InvalidDataException>(() => new MirrorRouteFlow(session,
            new FakeReader(frame => Map(frame with { Id = frame.Id - 1 }))).AdvanceAsync(new(), default));
        Assert.Empty(session.Actions);
    }

    [Fact]
    public async Task AChineseNarrationEventWithoutTemplatesCanBeHandedBackToTheEventFlow()
    {
        var selected = false;
        var session = new FakeSession(() => selected ? [] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus]);
        session.Action = _ => selected = true;
        session.Text = [new("这是一段左侧事件叙述。", 1, new(100, 350, 220, 30)),
            new("SKIP", 1, new(1087, 618, 95, 60))];
        var result = await new MirrorRouteFlow(session, new FakeReader(frame => Map(frame))).AdvanceAsync(new(), default);
        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Single(session.Actions);
    }

    [Theory]
    [InlineData("event/very_high.png")]
    [InlineData("event/high.png")]
    public async Task AProbabilityLabelAloneCannotConfirmAnEventDestination(string probability)
    {
        var entered = false;
        var session = new FakeSession(() => entered ? [probability] : [MirrorRouteFlow.Enter]);
        session.Action = _ => entered = true;

        var result = await new MirrorRouteFlow(session, new FakeReader(frame => Map(frame))).AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Failed, result.Outcome);
        Assert.Single(session.Actions);
    }

    [Theory]
    [InlineData(720, -212, GameKey.Up)]
    [InlineData(1440, -212, GameKey.Up)]
    [InlineData(720, 0, GameKey.Right)]
    [InlineData(1440, 0, GameKey.Right)]
    [InlineData(720, 212, GameKey.Down)]
    [InlineData(1440, 212, GameKey.Down)]
    public async Task AConnectedCachedStepUsesRelativeGeometryAndKeyboardWithoutDragging(int height, int deltaY, GameKey direction)
    {
        var factor = height / 720;
        var phase = 0;
        var session = new FakeSession(() => phase is 0 or 3 or 4 ? [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus]
            : phase is 1 or 5 ? [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus, MirrorRouteFlow.Enter] : ["teams/identify_assets.png"], height)
        { BusPosition = _ => phase >= 3 ? new(500 * factor, 300 * factor) : new(40 * factor, 360 * factor) };
        session.Action = rule => phase = rule switch
        {
            "mirror.route.select-node" => 1,
            "mirror.route.select-direction" => 4,
            "mirror.route.confirm-selection" => 5,
            _ => phase == 1 ? 2 : 6
        };
        var reader = new FakeReader(frame => phase == 0 ? Map(frame,
            [Node(0, MirrorNodeKind.Event, 350 * factor, 360 * factor), Node(1, MirrorNodeKind.Shop, 606 * factor, (360 + deltaY) * factor),
                Node(2, MirrorNodeKind.Battle, 350 * factor, 148 * factor), Node(3, MirrorNodeKind.Battle, 350 * factor, 572 * factor)],
            [new(-1, 0), new(0, 1)]) : Map(frame,
            [Node(0, MirrorNodeKind.Shop, 756 * factor, (325 + deltaY) * factor),
                Node(1, MirrorNodeKind.Shop, 756 * factor, (deltaY == 0 ? 537 : 325) * factor)], [new(-1, 0), new(-1, 1)]));
        var flow = new MirrorRouteFlow(session, reader);
        Assert.Equal(MirrorRouteOutcome.Entered, (await flow.AdvanceAsync(new(), default)).Outcome);
        phase = 3;

        var result = await flow.AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(MirrorNodeKind.Shop, result.Node);
        Assert.Equal([direction, GameKey.Enter], session.Keys);
        Assert.Equal(["mirror.route.select-node", "mirror.route.enter-node", "mirror.route.select-direction",
            "mirror.route.confirm-selection", "mirror.route.enter-node"], session.Actions);
        Assert.Single(reader.Frames);
        Assert.Equal(session.InputFrames.Count, session.InputFrames.Distinct().Count());
        Assert.Single(session.Reports, report => report.Rule == "mirror.route.cache-hit");
    }

    [Fact]
    public async Task AnUnconfirmedSelectionDoesNotConsumeTheCachedStep()
    {
        var phase = 0;
        var session = new FakeSession(() => phase == 2 ? ["teams/identify_assets.png"] : phase == 1
            ? [MirrorRouteFlow.Legend, MirrorRouteFlow.Enter] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus]);
        session.Action = rule => { if (rule == "mirror.route.confirm-selection") phase = 1; else if (rule == "mirror.route.enter-node") phase = 2; };
        var reader = new FakeReader(frame => Map(frame,
            [Node(0, MirrorNodeKind.Event, 350, 360), Node(1, MirrorNodeKind.Shop, 606, 360)], [new(-1, 0), new(0, 1)]));
        var flow = new MirrorRouteFlow(session, reader);
        Assert.Equal(MirrorRouteOutcome.Failed, (await flow.AdvanceAsync(new(), default)).Outcome);

        var result = await flow.AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(MirrorNodeKind.Event, result.Node);
        Assert.Equal([GameKey.Right, GameKey.Enter], session.Keys);
        Assert.Single(session.Reports, report => report.Rule == "mirror.route.cache-hit");
    }

    [Fact]
    public async Task ANewFloorRequiresFreshScanningAndPlanning()
    {
        var bus = new PixelPoint(40, 360);
        var phase = 0;
        var session = new FakeSession(() => phase == 2 ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        { BusPosition = _ => bus };
        session.Action = rule =>
        {
            if (rule == "mirror.route.align-camera") bus = new(bus.X + session.InputPoints[^1].X - 640, bus.Y + session.InputPoints[^1].Y - 360);
            else phase = 2;
        };
        var reader = new FakeReader(frame =>
        {
            if (phase == 0) return Map(frame, [Node(0, MirrorNodeKind.Event, 350, 360), Node(1, MirrorNodeKind.Shop, 606, 360)],
                [new(-1, 0), new(0, 1)]);
            var nodes = new[] { Node(0, MirrorNodeKind.Shop, bus.X + 256, bus.Y + 25),
                Node(2, MirrorNodeKind.Event, bus.X + 887, bus.Y - 263) };
            var edges = new[] { new MirrorRouteConnection(-1, 0) };
            return Map(frame, nodes, edges);
        });
        var flow = new MirrorRouteFlow(session, reader);
        Assert.Equal(MirrorRouteOutcome.Entered, (await flow.AdvanceAsync(new(), default)).Outcome);
        phase = 3;
        bus = new(350, 335);
        flow.NotifyShopExited(); flow.ResetForFloor();

        var result = await flow.AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Contains("mirror.route.align-camera", session.Actions);
        Assert.Empty(session.Keys);
        Assert.DoesNotContain(session.Reports, report => report.Rule == "mirror.route.cache-hit");
        Assert.Equal(reader.Frames[^1], session.InputFrames[^1]);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    public async Task PostShopWUsesObservedEntryOrDestinationFeedback(int feedback)
    {
        var phase = 0;
        var session = new FakeSession(() => phase == 0 || phase == 1 && feedback == 1
            ? [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus]
            : phase == 3 || phase == 1 && feedback == 2 ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Enter]);
        session.Action = rule => phase = rule == "mirror.route.post-shop-next" ? 1 : rule == "mirror.route.confirm-selection" ? 2 : 3;
        var flow = new MirrorRouteFlow(session, new FakeReader(_ => throw new InvalidOperationException("已确认进入时不重新扫描")));
        flow.NotifyShopExited();

        var result = await flow.AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Null(result.Node);
        Assert.Equal(feedback == 1 ? [GameKey.W, GameKey.Enter] : [GameKey.W], session.Keys);
        Assert.DoesNotContain("mirror.route.select-node", session.Actions);
        Assert.DoesNotContain("mirror.route.align-camera", session.Actions);
        Assert.Equal(session.InputFrames.Count, session.InputFrames.Distinct().Count());
    }

    [Fact]
    public async Task PostShopWWithoutFeedbackFallsBackToTheCurrentMapOnce()
    {
        var selected = false;
        var session = new FakeSession(() => selected ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus]);
        session.Action = rule => { if (rule == "mirror.route.select-node") selected = true; };
        var reader = new FakeReader(frame => Map(frame));
        var flow = new MirrorRouteFlow(session, reader);
        flow.NotifyShopExited();

        var result = await flow.AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal([GameKey.W, GameKey.Enter], session.Keys);
        Assert.Equal(["mirror.route.post-shop-next", "mirror.route.confirm-selection", "mirror.route.select-node"], session.Actions);
        Assert.Equal(reader.Frames[^1], session.InputFrames[^1]);
        Assert.Single(session.Reports, report => report.Rule == "mirror.route.post-shop-miss");
    }

    [Fact]
    public async Task CancellationAfterWPreventsEnterAndMapSelection()
    {
        using var stop = new CancellationTokenSource();
        var session = new FakeSession(() => [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus]);
        session.Action = _ => stop.Cancel();
        var flow = new MirrorRouteFlow(session, new FakeReader(_ => throw new InvalidOperationException()));
        flow.NotifyShopExited();

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => flow.AdvanceAsync(new(), stop.Token));

        Assert.Equal([GameKey.W], session.Keys);
        Assert.Equal(["mirror.route.post-shop-next"], session.Actions);
    }

    [Fact]
    public async Task AnExhaustedCacheScansTheNextUsableMap()
    {
        var phase = 0;
        var bus = new PixelPoint(40, 360);
        var session = new FakeSession(() => phase == 1 ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        { BusPosition = _ => bus };
        session.Action = rule =>
        {
            if (rule == "mirror.route.align-camera") bus = new(bus.X + session.InputPoints[^1].X - 640, bus.Y + session.InputPoints[^1].Y - 360);
            else phase = 1;
        };
        var reader = new FakeReader(frame => Map(frame, [Node(0, MirrorNodeKind.Event, bus.X + 256, bus.Y + 25)]));
        var flow = new MirrorRouteFlow(session, reader);
        Assert.Equal(MirrorRouteOutcome.Entered, (await flow.AdvanceAsync(new(), default)).Outcome);
        phase = 2;
        bus = new(469, 264);

        var result = await flow.AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(["mirror.route.select-node", "mirror.route.select-node"], session.Actions);
        Assert.Equal(2, reader.Frames.Count);
        Assert.Empty(session.Keys);
        Assert.DoesNotContain(session.Reports, report => report.Rule == "mirror.route.cache-hit");
    }

    [Fact]
    public async Task CancellationAfterACachedDirectionPreventsEnterOnTheOldFrame()
    {
        using var stop = new CancellationTokenSource();
        var phase = 0;
        var session = new FakeSession(() => phase == 1 ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        { BusPosition = _ => phase == 2 ? new(350, 335) : new(40, 360) };
        session.Action = rule => { if (rule == "mirror.route.select-direction") stop.Cancel(); else phase = 1; };
        var reader = new FakeReader(frame => phase == 0 ? Map(frame,
            [Node(0, MirrorNodeKind.Event, 350, 360), Node(1, MirrorNodeKind.Shop, 606, 360)], [new(-1, 0), new(0, 1)])
            : Map(frame, [Node(0, MirrorNodeKind.Shop, 606, 360)]));
        var flow = new MirrorRouteFlow(session, reader);
        Assert.Equal(MirrorRouteOutcome.Entered, (await flow.AdvanceAsync(new(), default)).Outcome);
        phase = 2;

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => flow.AdvanceAsync(new(), stop.Token));

        Assert.Equal([GameKey.Right], session.Keys);
        Assert.Equal("mirror.route.select-direction", session.Actions[^1]);
        Assert.True(session.InputFrames[^1] > reader.Frames[^1]);
    }

    [Fact]
    public async Task AMissedCachedKeyInvalidatesTheCacheAndReplansOnFreshMapFeedback()
    {
        var phase = 0;
        var bus = new PixelPoint(40, 360);
        var session = new FakeSession(() => phase == 1 ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        { BusPosition = _ => bus };
        session.Action = rule =>
        {
            if (rule == "mirror.route.align-camera") bus = new(bus.X + session.InputPoints[^1].X - 640, bus.Y + session.InputPoints[^1].Y - 360);
            else if (rule == "mirror.route.select-node") phase = 1;
        };
        var reader = new FakeReader(frame => phase == 0 ? Map(frame,
            [Node(0, MirrorNodeKind.Event, 350, 360), Node(1, MirrorNodeKind.Shop, 606, 360)], [new(-1, 0), new(0, 1)])
            : Map(frame, [Node(0, MirrorNodeKind.Shop, bus.X + 256, bus.Y + 25)]));
        var flow = new MirrorRouteFlow(session, reader);
        Assert.Equal(MirrorRouteOutcome.Entered, (await flow.AdvanceAsync(new(), default)).Outcome);
        phase = 2;
        bus = new(350, 335);

        var result = await flow.AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(MirrorNodeKind.Shop, result.Node);
        Assert.Equal([GameKey.Right, GameKey.Enter], session.Keys);
        Assert.Single(session.Reports, report => report.Rule == "mirror.route.cache-hit");
        Assert.Single(session.Reports, report => report.Rule == "mirror.route.cache-miss");
        Assert.Equal(["mirror.route.select-node", "mirror.route.select-direction", "mirror.route.confirm-selection",
            "mirror.route.select-node"], session.Actions);
        Assert.Equal(2, session.Actions.Count(rule => rule == "mirror.route.select-node"));
        Assert.Equal(reader.Frames[^1], session.InputFrames[^1]);
        Assert.Equal(new(bus.X + 256, bus.Y + 25), session.InputPoints[^1]);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task LoadingOrAnUnknownPageAfterACachedKeyWaitsWithoutReplanning(bool loading)
    {
        var phase = 0;
        var loadingAt = TimeSpan.Zero;
        FakeSession session = null!;
        session = new FakeSession(() => phase == 1 || phase == 3 && session.Elapsed - loadingAt >= TimeSpan.FromSeconds(2)
            ? ["teams/identify_assets.png"] : phase == 3 ? loading ? ["base/waiting_assets.png"] : []
            : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        { BusPosition = _ => phase >= 2 ? new(350, 335) : new(40, 360) };
        session.Action = rule =>
        {
            if (rule == "mirror.route.select-node") phase = 1;
            else if (rule == "mirror.route.select-direction") { phase = 3; loadingAt = session.Elapsed; }
        };
        var reader = new FakeReader(frame => phase == 0 ? Map(frame,
            [Node(0, MirrorNodeKind.Event, 350, 360), Node(1, MirrorNodeKind.Shop, 606, 360)], [new(-1, 0), new(0, 1)])
            : Map(frame, [Node(0, MirrorNodeKind.Shop, 606, 360)]));
        var flow = new MirrorRouteFlow(session, reader);
        Assert.Equal(MirrorRouteOutcome.Entered, (await flow.AdvanceAsync(new(), default)).Outcome);
        phase = 2;

        var result = await flow.AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal([GameKey.Right], session.Keys);
        Assert.Single(reader.Frames);
        Assert.Equal(["mirror.route.select-node", "mirror.route.select-direction"], session.Actions);
        Assert.DoesNotContain(session.Reports, report => report.Rule == "mirror.route.cache-miss");
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task AMergedFirstStepMissingFromTheLatestFrameIsReobservedBeforeInput(bool remainsMissing)
    {
        var bus = new PixelPoint(469, 264);
        var selected = false;
        var reads = 0;
        var session = new FakeSession(() => selected ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        { BusPosition = _ => bus };
        session.Action = rule =>
        {
            if (rule == "mirror.route.align-camera") bus = new(bus.X, bus.Y + session.InputPoints[^1].Y - 360);
            else selected = true;
        };
        var reader = new FakeReader(frame => ++reads > 1 && (reads == 2 || remainsMissing)
            ? Map(frame, [Node(80, MirrorNodeKind.Battle, bus.X + 512, bus.Y + 22)], [])
            : Map(frame, [Node(40, MirrorNodeKind.Event, bus.X + 256, bus.Y - 192),
                Node(41, MirrorNodeKind.Battle, bus.X + 512, bus.Y + 22)], [new(-1, 40), new(40, 41)]));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal(remainsMissing ? MirrorRouteOutcome.Failed : MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(remainsMissing ? 2 : 1, session.Reports.Count(report => report.Rule == "mirror.route.scan-recheck"));
        Assert.Equal(remainsMissing ? [3L, 6L, 9L, 12L] : [3L, 6L, 9L], reader.Frames);
        if (remainsMissing)
        {
            Assert.Equal("first-step-unconfirmed", result.Reason);
            Assert.Equal(["mirror.route.align-camera"], session.Actions);
        }
        else
        {
            Assert.Equal(["mirror.route.align-camera", "mirror.route.select-node"], session.Actions);
            Assert.Equal([3L, 9L], session.InputFrames);
            Assert.Equal(new PixelPoint(725, 159), session.InputPoints[^1]);
        }
    }

    [Fact]
    public async Task ARightFrontierProbeWithNoNewInformationStopsUsingTheMeasuredCameraPosition()
    {
        var bus = new PixelPoint(469, 342);
        var selected = false;
        var session = new FakeSession(() => selected ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        { BusPosition = _ => bus };
        session.Action = rule => { if (rule == "mirror.route.align-camera") bus = bus with { X = bus.X - 100 }; else selected = true; };
        var reader = new FakeReader(frame => Map(frame,
            [Node(0, MirrorNodeKind.Event, bus.X + 256, bus.Y + 25), Node(1, MirrorNodeKind.Event, bus.X + 512, bus.Y + 25),
                Node(2, MirrorNodeKind.Event, bus.X + 768, bus.Y + 25)], [new(-1, 0), new(0, 1), new(1, 2)]));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(["mirror.route.align-camera", "mirror.route.select-node"], session.Actions);
        Assert.Equal(new PixelPoint(369, 342), bus);
        Assert.Equal(new PixelPoint(625, 367), session.InputPoints[^1]);
        Assert.Equal([3L, 6L], reader.Frames);
    }

    [Fact]
    public async Task ARightFrontierProbeReachesTheLeftAnchorInOneDrag()
    {
        var bus = new PixelPoint(469, 342);
        var selected = false;
        var reads = 0;
        var session = new FakeSession(() => selected ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        { BusPosition = _ => bus };
        session.Action = rule =>
        {
            if (rule == "mirror.route.align-camera") bus = new(bus.X + session.InputPoints[^1].X - 640, bus.Y);
            else selected = true;
        };
        var counts = new List<int>();
        var reader = new FakeReader(frame =>
        {
            var offset = ++reads * 10;
            var nodes = Enumerable.Range(0, 6).Select(index => Node(offset + index, MirrorNodeKind.Event,
                bus.X + 256 * (index + 1), bus.Y + 25)).Where(node => node.Bounds.Right <= 1280).ToArray();
            counts.Add(nodes.Length);
            return Map(frame, nodes, Enumerable.Range(0, nodes.Length)
                .Select(index => new MirrorRouteConnection(index == 0 ? -1 : offset + index - 1, offset + index)).ToArray());
        });

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal([3, 4], counts);
        Assert.Equal(["mirror.route.align-camera", "mirror.route.select-node"], session.Actions);
        Assert.Equal(new PixelPoint(bus.X + 256, bus.Y + 25), session.InputPoints[^1]);
        Assert.Equal(reader.Frames[^1], session.InputFrames[^1]);
    }

    [Fact]
    public async Task UnconfirmedKeyboardNavigationRebuildsTheScanAtTheNewBusPosition()
    {
        var phase = 0;
        var bus = new PixelPoint(40, 360);
        var session = new FakeSession(() => phase == 1 ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        { BusPosition = _ => bus };
        session.Action = rule =>
        {
            if (rule == "mirror.route.select-node") phase = 1;
            if (rule == "mirror.route.select-direction") { phase = 3; bus = new(606, 335); }
        };
        var reader = new FakeReader(frame => phase == 0 ? Map(frame,
            [Node(0, MirrorNodeKind.Event, 350, 360), Node(1, MirrorNodeKind.Shop, 606, 360)], [new(-1, 0), new(0, 1)])
            : Map(frame, [Node(0, phase == 2 ? MirrorNodeKind.Shop : MirrorNodeKind.Event, bus.X + 256, bus.Y + 25)]));
        var flow = new MirrorRouteFlow(session, reader);
        Assert.Equal(MirrorRouteOutcome.Entered, (await flow.AdvanceAsync(new(), default)).Outcome);
        phase = 2;
        bus = new(350, 335);

        var result = await flow.AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(MirrorNodeKind.Event, result.Node);
        Assert.Equal([GameKey.Right, GameKey.Enter], session.Keys);
        Assert.Equal(new PixelPoint(862, 360), session.InputPoints[^1]);
        Assert.Equal(reader.Frames[^1], session.InputFrames[^1]);
    }

    [Fact]
    public async Task AnUnconfirmedMouseSelectionStartsReplanningWithAFreshBusOrigin()
    {
        var selections = 0;
        var bus = new PixelPoint(40, 360);
        var session = new FakeSession(() => selections == 2 ? ["teams/identify_assets.png"] : [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus])
        { BusPosition = _ => bus };
        session.Action = rule => { if (rule == "mirror.route.select-node") { selections++; bus = new(350, 335); } };
        var reader = new FakeReader(frame => Map(frame,
            [selections == 0 ? Node(0, MirrorNodeKind.Event, 350, 360) : Node(0, MirrorNodeKind.Shop, 606, 360)]));

        var result = await new MirrorRouteFlow(session, reader).AdvanceAsync(new(), default);

        Assert.Equal(MirrorRouteOutcome.Entered, result.Outcome);
        Assert.Equal(MirrorNodeKind.Shop, result.Node);
        Assert.Equal(["mirror.route.select-node", "mirror.route.select-node"], session.Actions);
        Assert.Equal([new PixelPoint(350, 360), new(606, 360)], session.InputPoints);
        Assert.Equal(reader.Frames[^1], session.InputFrames[^1]);
    }

    private sealed class FakeReader(Func<FrameIdentity, MirrorMapSnapshot> read) : IMirrorMapReader
    {
        public List<long> Frames { get; } = [];
        public List<PixelPoint> Buses { get; } = [];
        public MirrorMapSnapshot Read(PixelFrame frame, PixelPoint bus, CancellationToken cancellationToken)
        { cancellationToken.ThrowIfCancellationRequested(); Frames.Add(frame.Identity.Id); Buses.Add(bus); return read(frame.Identity) with { Bus = bus }; }
    }

    private sealed class FakeSession(Func<string[]> observe, int height = 720) : IGameSession
    {
        public Action<string>? Action { get; set; }
        public List<string> Actions { get; } = [];
        public List<long> InputFrames { get; } = [];
        public List<TimeSpan> InputTimes { get; } = [];
        public List<PixelPoint> InputPoints { get; } = [];
        public List<GameKey> Keys { get; } = [];
        public List<(string Rule, string Message)> Reports { get; } = [];
        public Func<int, PixelPoint>? BusPosition { get; init; }
        public RecognizedText[] Text { get; set; } = [];
        public TimeSpan Elapsed { get; private set; }
        public int Observations { get; private set; }
        public ValueTask<GameFrame> ObserveAsync(IReadOnlyList<ImageQuery> queries, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            var targets = observe().Where(asset => queries.Any(query => query.Asset == asset))
                .Select(asset =>
                {
                    var center = asset == MirrorRouteFlow.Bus
                        ? BusPosition?.Invoke(Observations + 1) ?? new(40 * height / 720, 360 * height / 720) : new(500, 350);
                    var bounds = asset == MirrorRouteFlow.Bus
                        ? new PixelRect(center.X - 25 * height / 720, center.Y - 35 * height / 720, 50 * height / 720, 70 * height / 720)
                        : new(480, 330, 40, 40);
                    return new VisualTarget(asset, center, bounds, 1);
                }).ToArray();
            return ValueTask.FromResult(new GameFrame(new(new(++Observations, height * 16 / 9, height, 1, 0),
                new byte[height * 16 / 9 * height * 4]), targets));
        }
        public ValueTask<IReadOnlyList<RecognizedText>> ReadTextAsync(GameFrame frame, CancellationToken ct,
            PixelRect? region = null, int scale = 1, TextPreprocessing preprocessing = TextPreprocessing.None)
        { ct.ThrowIfCancellationRequested(); return ValueTask.FromResult<IReadOnlyList<RecognizedText>>(Text); }
        public ValueTask ClickAsync(GameFrame frame, PixelPoint target, string rule, CancellationToken ct)
        { Record(frame, target, rule, ct); return ValueTask.CompletedTask; }
        public ValueTask KeyAsync(GameFrame frame, GameKey key, string rule, CancellationToken ct)
        { Check(frame, new(1, 1), ct); Keys.Add(key); Record(frame, new(1, 1), rule, ct); return ValueTask.CompletedTask; }
        public ValueTask DragAsync(GameFrame frame, PixelPoint from, PixelPoint to, TimeSpan duration, string rule, CancellationToken ct)
        { Check(frame, from, ct); Record(frame, to, rule, ct); return ValueTask.CompletedTask; }
        public ValueTask DelayAsync(TimeSpan duration, CancellationToken ct)
        { ct.ThrowIfCancellationRequested(); Elapsed += duration; return ValueTask.CompletedTask; }
        public void Report(string rule, string message) => Reports.Add((rule, message));
        private void Record(GameFrame frame, PixelPoint point, string rule, CancellationToken ct)
        { Check(frame, point, ct); InputFrames.Add(frame.Identity.Id); InputTimes.Add(Elapsed); InputPoints.Add(point); Actions.Add(rule); Action?.Invoke(rule); }
        private void Check(GameFrame frame, PixelPoint point, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            Assert.Equal(Observations, frame.Identity.Id);
            Assert.InRange(point.X, 0, frame.Identity.Width - 1);
            Assert.InRange(point.Y, 0, frame.Identity.Height - 1);
        }
    }
}
