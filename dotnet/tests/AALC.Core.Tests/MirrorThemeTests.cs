using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;
using AALC.Runtime.Mirror;
using Xunit;

namespace AALC.Core.Tests;

public sealed class MirrorThemeTests
{
    [Fact]
    public void CatalogAliasesUseTheSameIdWhileModeOverridesRemainIndependent()
    {
        var options = new MirrorThemeOptions { NormalWeights = new() { ["sweep"] = 9, ["forgot"] = 7 } };
        Assert.Equal(9, options.WeightFor("深夜 清扫复刻"));
        Assert.Equal(9, options.WeightFor("Nocturnal Sweeping BokGak"));
        Assert.Equal(-5, options.WeightFor("not catalogued"));
        Assert.Equal(10, (options with { HardMode = true }).WeightFor("凤皇"));
        Assert.Equal(1, options.WeightFor("地狱鸡"));
        Assert.Equal(7, options.WeightFor("F O R G O T T E N"));
        Assert.Equal(0, (options with { HardMode = true }).WeightFor("Forgotten"));
        Assert.Equal(4, (options with { HardMode = true, HardWeights = new() { ["forgot"] = 4 } }).WeightFor("遗忘"));
        Assert.Equal(-3, new MirrorThemeOptions { HardMode = true,
            HardWeights = new() { ["unchanging"] = -3, ["time"] = 7 } }.WeightFor("The Unchanging Time"));
    }

    [Fact]
    public async Task SelectsTheBestThemeOnceAndVerifiesMapEntry()
    {
        var source = PackFrame(1);
        var session = new MirrorTestSession([source, MirrorRewardTests.Frame(2, MirrorThemeFlow.Map)]);
        session.Reader = (frame, region) => [new(frame.Find(MirrorThemeFlow.Map) is not null ? "第1层" : region?.X < 500 ? "清扫" : "地狱鸡", .99, region ?? new())];
        Assert.True(await MirrorThemeFlow.RunAsync(session, new() { NormalWeights = new() { ["sweep"] = -5, ["chick"] = 5 } }, default));
        var action = Assert.Single(session.Actions);
        Assert.Equal("mirror.theme.select-pack", action.Rule);
        Assert.Equal(800, action.Point.X);
    }

    [Fact]
    public async Task RefreshBudgetIsBoundedAndSelectionStillNeedsAnExit()
    {
        var source = PackFrame(1);
        var session = new MirrorTestSession([source]);
        Assert.False(await MirrorThemeFlow.RunAsync(session, new() { PreferredThreshold = 10, RefreshLimit = 2 }, default));
        Assert.Equal(2, session.Actions.Count(a => a.Rule == "mirror.theme.refresh"));
        Assert.Equal(3, session.Actions.Count(a => a.Rule == "mirror.theme.select-pack"));
        Assert.Contains("mirror.theme.stalled", session.Reports);
    }

    [Fact]
    public async Task FailedDragIsRetriedOnlyAfterThreeConfirmedPackObservationsUsingFreshCoordinates()
    {
        var moved = PackFrame(4) with { Targets = [MirrorRewardTests.Target(MirrorThemeFlow.Normal, 860, 45),
            MirrorRewardTests.Target(MirrorThemeFlow.Pack, 900, 250)] };
        var session = new MirrorTestSession([PackFrame(1), PackFrame(2), PackFrame(3), moved,
            MirrorRewardTests.Frame(5, MirrorThemeFlow.Map)]);
        session.Reader = (frame, region) => [new(frame.Find(MirrorThemeFlow.Map) is not null ? "第1层" : "地狱鸡", .99, region ?? new())];
        Assert.True(await MirrorThemeFlow.RunAsync(session, new(), default));
        Assert.Equal([1L, 4L], session.Actions.Select(action => action.FrameId));
        Assert.Equal(900, session.Actions[1].Point.X);
        Assert.Contains("mirror.theme.retry", session.Reports);
    }

    [Fact]
    public async Task UnknownAndLoadingFramesResetTheRemainingPackConfirmation()
    {
        var loading = PackFrame(7) with { Targets = [.. PackFrame(7).Targets,
            MirrorRewardTests.Target("base/waiting_assets.png", 700, 350)] };
        var session = new MirrorTestSession([PackFrame(1), PackFrame(2), PackFrame(3), MirrorRewardTests.Frame(4),
            PackFrame(5), PackFrame(6), loading, PackFrame(8), PackFrame(9), MirrorRewardTests.Frame(10, MirrorThemeFlow.Map)]);
        session.Reader = (frame, region) => [new(frame.Find(MirrorThemeFlow.Map) is not null ? "第1层" : "地狱鸡", .99, region ?? new())];
        Assert.True(await MirrorThemeFlow.RunAsync(session, new(), default));
        Assert.Single(session.Actions);
    }

    [Fact]
    public async Task ALoadingOverlayDoesNotAllowTheFirstPackDrag()
    {
        var source = PackFrame(1) with { Targets = [.. PackFrame(1).Targets,
            MirrorRewardTests.Target("base/waiting_assets.png", 700, 350)] };
        var session = new MirrorTestSession([source]);
        Assert.False(await MirrorThemeFlow.RunAsync(session, new(), default));
        Assert.Empty(session.Actions);
    }

    [Fact]
    public async Task FourthFloorEventPreferenceKeepsTheLeftmostPack()
    {
        var session = new MirrorTestSession([PackFrame(1), MirrorRewardTests.Frame(2, MirrorThemeFlow.Map)]);
        session.Reader = (frame, region) => [new(frame.Find(MirrorThemeFlow.Map) is not null ? "第4层" : "地狱鸡", .99, region ?? new())];
        Assert.True(await MirrorThemeFlow.RunAsync(session, new() { Floor = 4, PreferEventPack = true, SkipEventPack = true }, default));
        Assert.Equal(400, Assert.Single(session.Actions).Point.X);
    }

    [Fact]
    public async Task OldMapAndUnreadableTransitionsAreWaitedOutUntilTheSelectedFloorIsConfirmed()
    {
        var session = new MirrorTestSession([PackFrame(1), MirrorRewardTests.Frame(2, MirrorThemeFlow.Map),
            MirrorRewardTests.Frame(3), MirrorRewardTests.Frame(4, MirrorThemeFlow.Map), MirrorRewardTests.Frame(5, MirrorThemeFlow.Map)]);
        session.Reader = (frame, region) => frame.Identity.Id == 4 ? []
            : [new(frame.Identity.Id switch { 2 => "正在探索第3层", 5 => "正在探索第4层", _ => "地狱鸡" }, .99, region ?? new())];

        Assert.True(await MirrorThemeFlow.RunAsync(session, new() { Floor = 4, PreferEventPack = true }, default));

        Assert.Equal(5, session.Observations);
        Assert.Equal(1, Assert.Single(session.Actions).FrameId);
    }

    [Fact]
    public async Task AMapThatNeverShowsTheSelectedFloorCannotCompleteTheThemeSelection()
    {
        var session = new MirrorTestSession([PackFrame(1), MirrorRewardTests.Frame(2, MirrorThemeFlow.Map)]);
        session.Reader = (frame, region) => [new(frame.Find(MirrorThemeFlow.Map) is not null ? "正在探索第3层" : "地狱鸡", .99, region ?? new())];

        Assert.False(await MirrorThemeFlow.RunAsync(session, new() { Floor = 4, PreferEventPack = true }, default));

        Assert.Equal(35, session.Observations);
        Assert.Single(session.Actions);
        Assert.Contains("mirror.theme.timeout", session.Reports);
    }

    private static GameFrame PackFrame(long id) => MirrorRewardTests.Frame(id, MirrorThemeFlow.Normal, MirrorThemeFlow.Refresh)
        with { Targets = [MirrorRewardTests.Target(MirrorThemeFlow.Normal, 860, 45),
            MirrorRewardTests.Target(MirrorThemeFlow.Refresh, 1100, 550),
            MirrorRewardTests.Target(MirrorThemeFlow.Pack, 400, 200), MirrorRewardTests.Target(MirrorThemeFlow.Pack, 800, 200)] };
}
