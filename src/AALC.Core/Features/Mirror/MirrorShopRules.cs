using System.Globalization;

namespace AALC.Core.Features.Mirror;

public static class MirrorShopRules
{
    public static IReadOnlyList<string> Keywords { get; } =
        Array.AsReadOnly(new[] { "burn", "bleed", "tremor", "rupture", "poise", "sinking", "charge", "slash", "pierce", "blunt" });

    public static void Validate(MirrorShopOptions options, string keyword, int floor)
    {
        ArgumentNullException.ThrowIfNull(options);
        if (!Keywords.Contains(keyword) || options.Keywords.Any(value => !Keywords.Contains(value))
            || options.SellKeywords.Any(value => !Keywords.Contains(value)))
            throw new ArgumentException("商店体系关键词无效");
        if (floor < 0 || options.SkipFloors.Any(value => value < 1)) throw new ArgumentException("商店楼层设置无效");
        if (floor == 0 && options.SkipFloors.Length > 0 && !SkipFloor(options, floor))
            throw new ArgumentException("无法确认当前楼层，不能应用跳过商店设置");
        if (!Enum.IsDefined(options.Purchases) || !Enum.IsDefined(options.Inventory) || !Enum.IsDefined(options.Skill))
            throw new ArgumentException("商店策略无效");
        if (options.NormalRefreshLimit is < 0 or > 10 || options.KeywordRefreshLimit is < 0 or > 10 || options.ReserveFunds < 0)
            throw new ArgumentException("商店刷新上限须为 0 到 10，预留经费不能为负数");
        if (options.SkillSinners.Any(value => value is < 1 or > 12)) throw new ArgumentException("技能替换罪人编号须为 1 到 12");
    }

    public static bool SkipFloor(MirrorShopOptions options, int floor) => options.SkipFloors.Contains(floor)
        || floor == 0 && Enumerable.Range(1, 5).All(options.SkipFloors.Contains);

    public static int? ReadFunds(IEnumerable<string> texts)
    {
        var values = new HashSet<int>();
        foreach (var source in texts)
        {
            var text = source.Trim().Replace(" ", "").Replace(",", "");
            var normalized = string.Concat(text.Select(character => character switch
            {
                'O' or 'o' or 'D' or 'Q' => '0', 'I' or 'l' => '1', 'Z' => '2',
                'S' => '5', 'G' => '6', 'B' => '8', 'h' => '4', _ => character
            }));
            if (normalized.Length > 0 && normalized.All(char.IsAsciiDigit)
                && int.TryParse(normalized, NumberStyles.None, CultureInfo.InvariantCulture, out var value)) values.Add(value);
        }
        return values.Count == 1 ? values.Single() : null;
    }

    public static bool CanRefresh(int? funds, int price, int reserve) =>
        funds is { } known && known >= price && known - price >= reserve;

    public static bool InEnhanceGrid(PixelPoint point, int width, int height) =>
        point.X >= width * .5151 && point.X <= width * .8844 && point.Y >= height * .3380 && point.Y <= height * .7130;

    public static IReadOnlyList<string> Recipes(string keyword)
    {
        var suffixes = keyword switch
        {
            "bleed" => new[] { "1", "2", "3", "hard_1", "hard_2", "hard_3" },
            "burn" => ["1", "2", "hard_1", "hard_2"],
            "charge" => ["1", "2", "hard_1"],
            "poise" => ["1", "2", "3", "4", "hard_1"],
            "rupture" => ["1", "2", "hard_1", "hard_2", "hard_3"],
            "sinking" or "tremor" => ["1", "2", "3", "hard_1"],
            _ => []
        };
        return suffixes.Select(suffix => $"mirror/shop/fusion_result/{keyword}_{suffix}.png").ToArray();
    }
}
