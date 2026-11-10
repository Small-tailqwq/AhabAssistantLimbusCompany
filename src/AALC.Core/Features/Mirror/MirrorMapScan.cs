using AALC.Core.Automation;

namespace AALC.Core.Features.Mirror;

public sealed record MirrorMapNodeSource(FrameIdentity Frame, int NodeId);
public sealed record MirrorMapConnectionSource(FrameIdentity Frame, int From, int To);

public sealed class MirrorMapScan
{
    private readonly List<MirrorRouteNode> nodes = [];
    private readonly List<MirrorRouteConnection> connections = [];
    private readonly Dictionary<int, List<MirrorMapNodeSource>> nodeSources = [];
    private readonly Dictionary<MirrorRouteConnection, List<MirrorMapConnectionSource>> connectionSources = [];
    private readonly List<MirrorMapSnapshot> observations = [];
    private readonly HashSet<int> disputed = [];

    // Vertices are relative reference coordinates, never current screen detections.
    public IReadOnlyList<MirrorRouteNode> Nodes => nodes;
    public IReadOnlyList<MirrorRouteConnection> Connections => connections;
    public IReadOnlyList<MirrorMapSnapshot> Observations => observations;
    public IReadOnlySet<int> Disputed => disputed;
    public IReadOnlyList<MirrorMapNodeSource> Sources(int nodeId) => nodeSources[nodeId];
    public IReadOnlyList<MirrorMapConnectionSource> Sources(MirrorRouteConnection connection) => connectionSources[connection];

    public int Add(MirrorMapSnapshot observation)
    {
        if (observations.Any(previous => previous.Frame == observation.Frame)) return 0;
        observations.Add(observation);
        var scale = observation.Frame.Height / 1440.0;
        var ids = new Dictionary<int, int> { [MirrorMapSnapshot.BusId] = MirrorMapSnapshot.BusId };
        var added = 0;
        foreach (var detected in observation.Nodes)
        {
            var point = Relative(detected.Center, observation.Bus, scale);
            var bounds = detected.Bounds;
            var relativeBounds = new PixelRect((int)Math.Round((bounds.X - observation.Bus.X) / scale),
                (int)Math.Round((bounds.Y - observation.Bus.Y) / scale - 50),
                (int)Math.Round(bounds.Width / scale), (int)Math.Round(bounds.Height / scale));
            var nearby = nodes.Where(node => Near(node.Center, point)).ToArray();
            if (nearby.Length > 1)
            {
                foreach (var ambiguous in nearby) if (disputed.Add(ambiguous.Id)) added++;
                continue;
            }
            var known = nearby.SingleOrDefault();
            if (known is null)
            {
                var id = nodes.Count;
                known = new(id, detected.Kind, point, relativeBounds, detected.Score);
                nodes.Add(known);
                nodeSources.Add(id, []);
                added++;
            }
            else if (known.Kind == MirrorNodeKind.Unknown && detected.Kind != MirrorNodeKind.Unknown)
            {
                known = known with { Kind = detected.Kind, Center = point, Bounds = relativeBounds, Score = detected.Score };
                nodes[known.Id] = known;
                added++;
            }
            else if (detected.Kind != MirrorNodeKind.Unknown && known.Kind != detected.Kind && disputed.Add(known.Id)) added++;
            ids[detected.Id] = known.Id;
            nodeSources[known.Id].Add(new(observation.Frame, detected.Id));
        }
        foreach (var edge in observation.Connections)
        {
            if (!ids.TryGetValue(edge.From, out var from) || !ids.TryGetValue(edge.To, out var to)) continue;
            var mapped = new MirrorRouteConnection(from, to);
            if (!connectionSources.TryGetValue(mapped, out var sources))
            {
                connections.Add(mapped);
                connectionSources.Add(mapped, sources = []);
                added++;
            }
            sources.Add(new(observation.Frame, edge.From, edge.To));
        }
        return added;
    }

    public MirrorRoutePlan? Choose(MirrorRouteOptions options) =>
        MirrorRoutePlanner.Choose(nodes.Where(node => !disputed.Contains(node.Id)).ToArray(), connections,
            new(0, 0), 80, options);

    public MirrorRouteNode? Confirm(MirrorRouteNode vertex, MirrorMapSnapshot current)
    {
        if (disputed.Contains(vertex.Id)) return null;
        var scale = current.Frame.Height / 1440.0;
        var matches = current.Nodes.Where(node => node.Kind == vertex.Kind
            && Near(vertex.Center, Relative(node.Center, current.Bus, scale))
            && current.Connections.Any(edge => edge.From == MirrorMapSnapshot.BusId && edge.To == node.Id)).ToArray();
        return matches.Length == 1 ? matches[0] : null;
    }

    private static PixelPoint Relative(PixelPoint point, PixelPoint bus, double scale) =>
        new((int)Math.Round((point.X - bus.X) / scale), (int)Math.Round((point.Y - bus.Y) / scale - 50));

    private static bool Near(PixelPoint left, PixelPoint right) =>
        Math.Abs(left.X - right.X) <= 16 && Math.Abs(left.Y - right.Y) <= 16;
}
