using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;
using AALC.Runtime.Mirror;
using Xunit;
using static AALC.Core.Tests.MirrorRewardTests;

namespace AALC.Core.Tests;

public sealed class MirrorObservationTests
{
    [Theory]
    [InlineData("选择 2／3", 2, 3)]
    [InlineData("Select 3/3", 3, 3)]
    [InlineData("0/1", 0, 1)]
    public void CountsRecognizeAllObservationSlots(string text, int selected, int maximum) =>
        Assert.Equal((selected, maximum), MirrorObservation.SelectionCount(text));

    [Theory]
    [InlineData("3/2")]
    [InlineData("0/23")]
    [InlineData("unknown")]
    public void InvalidCountsStayUnknown(string text) => Assert.Null(MirrorObservation.SelectionCount(text));

    [Fact]
    public void DuplicateAndOverCapacitySelectionsAreRejected()
    {
        var gift = new MirrorObservedGift("general", 3, 4, 8);
        Assert.Throws<ArgumentException>(() => MirrorObservation.Validate([gift, gift]));
        Assert.Throws<ArgumentException>(() => MirrorObservation.Validate(Enumerable.Range(1, 4).Select(column => gift with { Column = column }).ToArray()));
    }

    [Fact]
    public async Task ClampedScrollReanchorsBeforeClickingTheGift()
    {
        var session = new MirrorTestSession([Observe(1), Observe(2), Observe(3, 550), Observe(4, 490), Observe(5, 453),
            Observe(6, 453), Frame(7, MirrorThemeFlow.Map)]);
        session.Reader = (_, region) => [new(session.Actions.Any(item => item.Rule == "mirror.observe.gift") ? "1/3" : "0/3", .99, region ?? new())];
        var result = await MirrorRewardFlow.ObserveGiftsAsync(session, [new("burn", 3, 2, 1)], default);
        Assert.True(result);
        Assert.Equal(2, session.Actions.Count(item => item.Rule == "mirror.observe.scroll-gift"));
        var selection = Assert.Single(session.Actions, item => item.Rule == "mirror.observe.gift");
        Assert.Equal(new PixelPoint(100, 573), selection.Point);
        Assert.Equal(5, selection.FrameId);
    }

    [Fact]
    public async Task ClickWithoutCountIncreaseDoesNotSubmitOrToggleAgain()
    {
        var session = new MirrorTestSession([Observe(1), Observe(2), Observe(3, 250)]);
        session.Reader = (_, region) => [new("0/3", .99, region ?? new())];
        Assert.False(await MirrorRewardFlow.ObserveGiftsAsync(session, [new("burn", 3, 1, 1)], default));
        Assert.Single(session.Actions, item => item.Rule == "mirror.observe.gift");
        Assert.DoesNotContain(session.Actions, item => item.Rule == "mirror.observe.submit");
    }

    [Fact]
    public async Task HiddenUpperTierIsSearchedUpwards()
    {
        var session = new MirrorTestSession([Observe(1), Observe(2), Observe(3), Observe(4, 250), Observe(5, 250), Frame(6, MirrorThemeFlow.Map)]);
        session.Reader = (_, region) => [new(session.Actions.Any(item => item.Rule == "mirror.observe.gift") ? "1/3" : "0/3", .99, region ?? new())];
        Assert.True(await MirrorRewardFlow.ObserveGiftsAsync(session, [new("burn", 3, 1, 1)], default));
        Assert.Single(session.Actions, item => item.Rule == "mirror.observe.scroll-top");
    }

    [Fact]
    public void ScrollDisplacementIsMeasuredFromPixels()
    {
        const int width = 300, height = 200;
        var before = new byte[width * height * 4];
        new Random(42).NextBytes(before);
        var after = new byte[before.Length];
        for (var y = 10; y < 173; y++)
            Array.Copy(before, ((y + 17) * width + 20) * 4, after, (y * width + 20) * 4, 260 * 4);
        var identity = new FrameIdentity(1, width, height, 0, 0);
        var pixels = new PixelFrame(identity, before);
        var area = new PixelRect(20, 10, 260, 180);
        Assert.Equal(17, MirrorObservationScroll.MeasureUpward(pixels, new(identity with { Id = 2 }, after), area, 60));
        Assert.Equal(0, MirrorObservationScroll.MeasureUpward(pixels, pixels, area, 60));
        Assert.Null(MirrorObservationScroll.MeasureUpward(new(identity, new byte[before.Length]), pixels, area, 60));
    }

    private static GameFrame Observe(long id, int? levelY = null)
    {
        var targets = new List<VisualTarget> { Target(MirrorRewardFlow.ObserveBurn, 100, 100) };
        if (levelY is { } y) targets.Add(Target("mirror/road_to_mir/observe_ego_gift/Level_III.png", 100, y));
        return new(new(new(id, 1280, 720, 0, 0), new byte[1280 * 720 * 4]), targets);
    }
}
