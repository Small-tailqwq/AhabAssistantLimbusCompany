using AALC.Core.Automation;
using AALC.Core.Features.Mirror;
using Xunit;

namespace AALC.Core.Tests;

public sealed class MirrorMapScanTests
{
    private static MirrorRouteNode Node(int id, MirrorNodeKind kind, int x, int y) =>
        new(id, kind, new(x, y), new(x - 25, y - 20, 50, 40), .9);

    private static MirrorMapSnapshot Map(long id, PixelPoint bus, MirrorRouteNode[] nodes,
        MirrorRouteConnection[] edges, int height = 720) => new(new(id, height * 16 / 9, height, 1, id), bus, nodes, edges);

    [Fact]
    public void CameraTranslationsMergeActualVerticesAndEdgesWithTheirOriginalSources()
    {
        var first = Map(10, new(469, 264),
            [Node(7, MirrorNodeKind.Event, 725, 289), Node(9, MirrorNodeKind.Shop, 981, 289)], [new(-1, 7)]);
        var second = Map(20, new(100, 350),
            [Node(3, MirrorNodeKind.Event, 356, 375), Node(4, MirrorNodeKind.Shop, 612, 375)], [new(3, 4)]);
        var scan = new MirrorMapScan();

        Assert.Equal(3, scan.Add(first));
        Assert.Equal(1, scan.Add(second));

        Assert.Equal([new PixelPoint(512, 0), new(1024, 0)], scan.Nodes.Select(node => node.Center));
        Assert.Equal([first, second], scan.Observations);
        Assert.Equal([new MirrorMapNodeSource(first.Frame, 7), new(second.Frame, 3)], scan.Sources(0));
        Assert.Equal([new MirrorMapConnectionSource(first.Frame, -1, 7)], scan.Sources(new MirrorRouteConnection(-1, 0)));
        Assert.Equal([new MirrorMapConnectionSource(second.Frame, 3, 4)], scan.Sources(new MirrorRouteConnection(0, 1)));
        Assert.Equal([MirrorNodeKind.Event, MirrorNodeKind.Shop], scan.Choose(new())!.Nodes.Select(node => node.Kind));
        Assert.Null(scan.Confirm(scan.Nodes[0], second));
        var confirmed = second with { Connections = [new(-1, 3), new(3, 4)] };
        Assert.Same(second.Nodes[0], scan.Confirm(scan.Nodes[0], confirmed));
    }

    [Fact]
    public void DifferentResolutionsShareReferenceCoordinatesWithoutChangingOriginalFrames()
    {
        var scan = new MirrorMapScan();
        var low = Map(1, new(100, 350), [Node(0, MirrorNodeKind.Event, 356, 375)], [new(-1, 0)]);
        var high = Map(2, new(200, 700), [Node(15, MirrorNodeKind.Event, 712, 750)], [new(-1, 15)], 1440);
        scan.Add(low);

        Assert.Equal(0, scan.Add(high));
        Assert.Single(scan.Nodes);
        Assert.Equal([720, 1440], scan.Observations.Select(map => map.Frame.Height));
        Assert.Equal(2, scan.Sources(0).Count);
        Assert.Equal(0, scan.Add(high));
        Assert.Equal(2, scan.Observations.Count);
    }

    [Fact]
    public void SeeingAdjacentNodesDoesNotInventTheirConnection()
    {
        var scan = new MirrorMapScan();
        scan.Add(Map(1, new(100, 350), [Node(0, MirrorNodeKind.Event, 356, 375)], []));
        scan.Add(Map(2, new(100, 350), [Node(5, MirrorNodeKind.Shop, 612, 375)], []));

        Assert.Equal(2, scan.Nodes.Count);
        Assert.Empty(scan.Connections);
        Assert.Null(scan.Choose(new()));
    }

    [Fact]
    public void ConflictingClassesAtTheSamePositionRemainOneDisputedVertex()
    {
        var scan = new MirrorMapScan();
        scan.Add(Map(1, new(100, 350), [Node(0, MirrorNodeKind.HardBattle, 356, 375)], [new(-1, 0)]));
        scan.Add(Map(2, new(100, 350), [Node(4, MirrorNodeKind.EliteBattle, 358, 374)], [new(-1, 4)]));

        Assert.Single(scan.Nodes);
        Assert.Equal([0], scan.Disputed);
        Assert.Equal(2, scan.Sources(0).Count);
        Assert.Null(scan.Choose(new()));
    }

    [Fact]
    public void AWarningRingCandidateCanGainItsKnownClassFromASubsequentObservation()
    {
        var scan = new MirrorMapScan();
        var warning = Map(1, new(100, 350),
            [new(0, MirrorNodeKind.Unknown, new(356, 375), new(316, 335, 80, 80), .5)], [new(-1, 0)]);
        var recognized = Map(2, new(200, 400), [Node(8, MirrorNodeKind.Battle, 456, 425)], [new(-1, 8)]);
        scan.Add(warning);

        Assert.Equal(1, scan.Add(recognized));

        Assert.Equal(MirrorNodeKind.Battle, Assert.Single(scan.Nodes).Kind);
        Assert.Equal(100, scan.Nodes[0].Bounds.Width);
        Assert.Empty(scan.Disputed);
        Assert.Equal(2, scan.Sources(0).Count);
        Assert.Equal(MirrorNodeKind.Unknown, scan.Observations[0].Nodes[0].Kind);
        Assert.Equal(MirrorNodeKind.Battle, Assert.Single(scan.Choose(new())!.Nodes).Kind);
        Assert.Same(recognized.Nodes[0], scan.Confirm(scan.Nodes[0], recognized));
    }

    [Fact]
    public void AWarningRingObservationDoesNotDowngradeAPreviouslyKnownClass()
    {
        var scan = new MirrorMapScan();
        scan.Add(Map(1, new(100, 350), [Node(0, MirrorNodeKind.Battle, 356, 375)], [new(-1, 0)]));
        scan.Add(Map(2, new(200, 400), [Node(8, MirrorNodeKind.Unknown, 456, 425)], [new(-1, 8)]));

        Assert.Equal(MirrorNodeKind.Battle, Assert.Single(scan.Nodes).Kind);
        Assert.Empty(scan.Disputed);
        Assert.Equal(2, scan.Sources(0).Count);
        Assert.Equal(MirrorNodeKind.Battle, Assert.Single(scan.Choose(new())!.Nodes).Kind);
    }

    [Theory]
    [InlineData(720)]
    [InlineData(1440)]
    public void ActualThreeRowGlyphBoundsFitWithoutMovingTheBusToAnAnchor(int height)
    {
        var factor = height / 720;
        var map = Map(1, new(106 * factor, 342 * factor),
            [Node(0, MirrorNodeKind.Event, 362 * factor, 147 * factor), Node(1, MirrorNodeKind.Event, 362 * factor, 360 * factor),
                Node(2, MirrorNodeKind.Event, 362 * factor, 579 * factor)], [new(-1, 0)], height);

        Assert.All(map.Nodes, node => Assert.True(MirrorMapViewport.Contains(map.Frame, node.Bounds)));
        Assert.Null(MirrorMapViewport.Shift(map, new(74 * factor, 312 * factor, 64 * factor, 60 * factor)));
    }

    [Theory]
    [InlineData(5)]
    [InlineData(35)]
    public void CameraShiftKeepsTheActualBusBoundsInsideTheFrame(int busLeft)
    {
        var map = Map(1, new(35, 342), [Node(0, MirrorNodeKind.Event, 1237, 367)], [new(-1, 0)]);
        var busBounds = new PixelRect(busLeft, 312, 60, 60);

        var shift = MirrorMapViewport.Shift(map, busBounds, probeRight: true);

        if (busLeft == 5) Assert.Null(shift);
        else
        {
            Assert.Equal(new PixelPoint(-33, 0), shift);
            Assert.Equal(2, busBounds.X + shift!.Value.X);
        }
    }

    [Fact]
    public void AVisibleRightFrontierCanUseABoundedProbeWithoutAnAnchor()
    {
        var map = Map(1, new(469, 342), [Node(0, MirrorNodeKind.Event, 1160, 367)], [new(-1, 0)]);

        Assert.Null(MirrorMapViewport.Shift(map, new(439, 312, 60, 60)));
        Assert.Equal(new PixelPoint(-290, 0), MirrorMapViewport.Shift(map, new(439, 312, 60, 60), probeRight: true));
    }

    [Fact]
    public void VisibilityUsesTheGlyphBoundsAndNotOnlyItsCenter()
    {
        var map = Map(1, new(469, 264), [Node(0, MirrorNodeKind.Event, 725, 111)], [new(-1, 0)]);

        Assert.False(MirrorMapViewport.Contains(map.Frame, map.Nodes[0].Bounds));
        Assert.Equal(new PixelPoint(0, 16), MirrorMapViewport.Shift(map, new(439, 234, 60, 60), map.Nodes[0].Bounds));
    }

    [Theory]
    [InlineData(1185, 300, 20, 40, -16, 0)]
    [InlineData(35, 300, 20, 40, 16, 0)]
    [InlineData(423, 95, 44, 45, 0, 16)]
    [InlineData(423, 575, 44, 40, 0, -16)]
    public void AFivePixelVisibilityCorrectionUsesAnEffectiveMinimumOnItsRequiredAxis(int x, int y,
        int width, int height, int dx, int dy)
    {
        var glyph = new PixelRect(x, y, width, height);
        var map = Map(59, new(191, 313),
            [new(1, MirrorNodeKind.Event, new(x + width / 2, y + height / 2), glyph, .9167)], [new(-1, 1)]);

        Assert.Equal(new PixelPoint(dx, dy), MirrorMapViewport.Shift(map, new(161, 283, 60, 60), glyph));
    }
}
