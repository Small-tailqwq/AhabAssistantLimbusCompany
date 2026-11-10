namespace AALC.Core.Features.Mirror;

public enum MirrorCardPreference { StarlightThenGift, StarlightThenCost, CostFirst, GiftFirst }
public sealed record MirrorObservedGift(string Keyword, int Level, int Row, int Column);

public sealed record MirrorRewardOptions
{
    public string Keyword { get; init; } = "bleed";
    public string? SecondaryKeyword { get; init; }
    public bool AvoidWhiteGossypium { get; init; } = true;
    public MirrorCardPreference CardPreference { get; init; }
    public MirrorObservedGift[] ObservedGifts { get; init; } = [];
}
