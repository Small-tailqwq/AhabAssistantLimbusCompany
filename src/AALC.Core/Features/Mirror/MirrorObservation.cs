using System.Text.RegularExpressions;

namespace AALC.Core.Features.Mirror;

public sealed record MirrorObserveSystem(string Key, string Name);

public static class MirrorObservation
{
    public const int MaximumGifts = 3;
    public const int Columns = 8;
    public const int MaximumRows = 10;
    public static readonly MirrorObserveSystem[] Systems =
    [
        new("burn", "烧伤"), new("bleed", "流血"), new("tremor", "震颤"), new("rupture", "破裂"),
        new("sinking", "沉沦"), new("poise", "呼吸"), new("charge", "充能"),
        new("slash", "斩击"), new("pierce", "突刺"), new("blunt", "打击"), new("general", "泛用")
    ];

    public static void Validate(IReadOnlyList<MirrorObservedGift> gifts)
    {
        if (gifts.Count > MaximumGifts) throw new ArgumentException("最多观测 3 件饰品。");
        if (gifts.Distinct().Count() != gifts.Count) throw new ArgumentException("观测饰品不能重复选择。");
        if (gifts.Any(gift => !Systems.Any(system => system.Key == gift.Keyword) || gift.Level is < 1 or > 3
            || gift.Row is < 1 or > MaximumRows || gift.Column is < 1 or > Columns))
            throw new ArgumentException("观测饰品的位置无效。");
    }

    public static string Describe(MirrorObservedGift gift) =>
        $"{Systems.Single(system => system.Key == gift.Keyword).Name} · {new string('I', gift.Level)} · 第{gift.Row}排第{gift.Column}列";

    public static (int Selected, int Maximum)? SelectionCount(string text)
    {
        var match = Regex.Match(text.Replace(" ", "").Replace('／', '/'), @"(?<!\d)([0-3])/([1-3])(?!\d)");
        if (!match.Success) return null;
        var selected = match.Groups[1].Value[0] - '0';
        var maximum = match.Groups[2].Value[0] - '0';
        return selected <= maximum ? (selected, maximum) : null;
    }
}
