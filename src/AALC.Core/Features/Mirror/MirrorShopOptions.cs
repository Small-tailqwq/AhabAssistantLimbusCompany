namespace AALC.Core.Features.Mirror;

public enum MirrorShopPurchases { None, Keyword, EssentialsAndKeyword }
public enum MirrorShopInventory { Keep, SellListedKeywords, KeywordRecipes }
public enum MirrorShopSkill { None, OneToThree, TwoToThree, OneToTwo }

public sealed record MirrorShopOptions
{
    public MirrorShopPurchases Purchases { get; init; } = MirrorShopPurchases.EssentialsAndKeyword;
    public bool Heal { get; init; } = true;
    public bool Enhance { get; init; } = true;
    public MirrorShopInventory Inventory { get; init; }
    public int NormalRefreshLimit { get; init; }
    public int KeywordRefreshLimit { get; init; }
    public int ReserveFunds { get; init; }
    public string[] Keywords { get; init; } = [];
    public string[] SellKeywords { get; init; } = [];
    public MirrorShopSkill Skill { get; init; }
    public int[] SkillSinners { get; init; } = [1];
    public int[] SkipFloors { get; init; } = [];
}
