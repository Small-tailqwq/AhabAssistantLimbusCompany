using AALC.Core.Automation;

namespace AALC.Core.Features.Mirror;

public sealed record MirrorRouteOptions(bool HardMode = false);
public enum MirrorNodeKind { Battle, BossBattle, Event, HardBattle, EliteBattle, Shop, AbnormalityBattle, Unknown }
public sealed record MirrorRouteNode(int Id, MirrorNodeKind Kind, PixelPoint Center, PixelRect Bounds, double Score);
public sealed record MirrorRouteConnection(int From, int To);
public sealed record MirrorMapSnapshot(FrameIdentity Frame, PixelPoint Bus,
    IReadOnlyList<MirrorRouteNode> Nodes, IReadOnlyList<MirrorRouteConnection> Connections)
{
    public const int BusId = -1;
}
public sealed record MirrorRoutePlan(IReadOnlyList<MirrorRouteNode> Nodes, int Cost);

public static class MirrorRoutePlanner
{
    // 权重约等于节点实测秒数，见 docs/mirror-route.md。
    public static int Weight(MirrorNodeKind kind) => kind switch
    {
        MirrorNodeKind.Battle => 80,
        MirrorNodeKind.BossBattle => 130,
        MirrorNodeKind.Shop => 10,
        MirrorNodeKind.Event => 18,
        MirrorNodeKind.HardBattle => 110,
        MirrorNodeKind.EliteBattle => 140,
        MirrorNodeKind.Unknown => 999,
        _ => 999
    };

    public static MirrorRoutePlan? Choose(MirrorMapSnapshot map, MirrorRouteOptions options)
        => Choose(map.Nodes, map.Connections, map.Bus, 80 * map.Frame.Height / 1440.0, options);

    public static bool IsLocalBossCandidate(MirrorRouteNode node, IReadOnlyList<MirrorRouteConnection> connections)
        => node.Kind == MirrorNodeKind.BossBattle && !connections.Any(edge => edge.From == node.Id);

    public static MirrorRoutePlan? Choose(IReadOnlyList<MirrorRouteNode> graphNodes,
        IReadOnlyList<MirrorRouteConnection> connections, PixelPoint bus, double columnTolerance, MirrorRouteOptions options)
    {
        var nodes = graphNodes.ToDictionary(node => node.Id);
        var queue = new PriorityQueue<(int Id, MirrorRouteNode[] Path), int>();
        queue.Enqueue((MirrorMapSnapshot.BusId, []), 0);
        var costs = new Dictionary<int, int> { [MirrorMapSnapshot.BusId] = 0 };
        var reachable = new List<MirrorRoutePlan>();
        while (queue.TryDequeue(out var current, out var cost))
        {
            if (cost != costs[current.Id]) continue;
            if (current.Path.Length > 0) reachable.Add(new(current.Path, cost));
            if (options.HardMode && current.Path.Length >= 2) continue;
            var fromX = current.Id == MirrorMapSnapshot.BusId ? bus.X : nodes[current.Id].Center.X;
            foreach (var edge in connections.Where(edge => edge.From == current.Id))
            {
                if (!nodes.TryGetValue(edge.To, out var next) || next.Center.X <= fromX) continue;
                var nextCost = cost + Weight(next.Kind);
                if (costs.TryGetValue(next.Id, out var previous) && previous <= nextCost) continue;
                costs[next.Id] = nextCost;
                queue.Enqueue((next.Id, [.. current.Path, next]), nextCost);
            }
        }
        var bosses = reachable.Where(plan => IsLocalBossCandidate(plan.Nodes[^1], connections)).ToArray();
        if (bosses.Length > 0) return bosses.OrderBy(plan => plan.Cost).ThenBy(plan => plan.Nodes[0].Center.Y).First();
        if (reachable.Count == 0) return null;
        var furthest = reachable.Max(plan => plan.Nodes[^1].Center.X);
        return reachable.Where(plan => furthest - plan.Nodes[^1].Center.X <= columnTolerance)
            .OrderBy(plan => plan.Cost).ThenBy(plan => plan.Nodes[0].Center.Y).First();
    }
}
