namespace AALC.Core.Features.Mirror;

public sealed record MirrorThemeOptions
{
    public bool HardMode { get; init; }
    public int Floor { get; init; } = 1;
    public int PreferredThreshold { get; init; }
    public int RefreshLimit { get; init; } = 3;
    public bool PreferEventPack { get; init; }
    public bool SkipEventPack { get; init; }
    public int UnknownWeight { get; init; } = -5;
    public Dictionary<string, int> NormalWeights { get; init => field = IgnoreCaseWeights(value); } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, int> HardWeights { get; init => field = IgnoreCaseWeights(value); } = new(StringComparer.OrdinalIgnoreCase);

    private static Dictionary<string, int> IgnoreCaseWeights(Dictionary<string, int> weights)
    {
        if (weights is null) return null!;
        var result = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        foreach (var pair in weights) result[pair.Key] = pair.Value;
        return result;
    }

    public int WeightFor(string title)
    {
        var pack = MirrorThemeCatalog.Match(title);
        if (pack is null || !(HardMode ? pack.InHard : pack.InNormal)) return UnknownWeight;
        return (HardMode ? HardWeights : NormalWeights).TryGetValue(pack.Id, out var weight) ? weight
            : HardMode ? pack.DefaultHardWeight : pack.DefaultNormalWeight;
    }
}
