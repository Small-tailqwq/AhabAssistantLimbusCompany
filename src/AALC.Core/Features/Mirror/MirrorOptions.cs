namespace AALC.Core.Features.Mirror;

public enum MirrorMode { Normal, Hard }
public enum MirrorTeamMode { Both, Normal, Hard }
public enum MirrorWeeklyBonus { None, One, All }

public sealed record MirrorOptions
{
    public MirrorMode Mode { get; init; }
    public int Runs { get; init; } = 1;
    public bool ClaimRewards { get; init; }
    public MirrorWeeklyBonus WeeklyBonus { get; init; }
    public MirrorTeamOptions[] Teams { get; init; } = [new()];
}

public sealed record MirrorTeamOptions
{
    public string Name { get; init; } = "队伍 1";
    public bool Enabled { get; init; } = true;
    public MirrorTeamMode Mode { get; init; }
    public int GameTeamNumber { get; init; } = 1;
    public bool SelectTeamByOrder { get; init; }
    public int[] SinnerOrder { get; init; } = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
    public bool ReformEachFloor { get; init; }
    public bool AvoidSkill3 { get; init; }
    public bool DefenseForSolo { get; init; }
    public int DefenseForSoloTurns { get; init; } = 5;
    public bool ConvertStarlight { get; init; }
    public int[] StarLevels { get; init; } = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1];
    public int[] InitialGifts { get; init; } = [1, 2, 3];
    public MirrorThemeOptions Theme { get; init; } = new();
    public MirrorRewardOptions Rewards { get; init; } = new();
    public MirrorShopOptions Shop { get; init; } = new();
}

public static class MirrorPlan
{
    public static readonly string[] Keywords = ["burn", "bleed", "tremor", "rupture", "poise", "sinking", "charge", "slash", "pierce", "blunt"];
    public static readonly MirrorObservedGift SoloGift = new("general", 3, 4, 8);

    public static MirrorObservedGift[] ObservedGifts(MirrorTeamOptions team)
    {
        var configured = team.Rewards.ObservedGifts;
        if (!team.DefenseForSolo || configured.Contains(SoloGift)) return configured;
        if (configured.Length >= MirrorObservation.MaximumGifts)
            throw new ArgumentException("小指良单通需要一个观测位，请减少其他观测饰品。");
        return [SoloGift, .. configured];
    }

    public static bool Eligible(MirrorTeamOptions team, MirrorMode mode) => team.Enabled &&
        (team.Mode == MirrorTeamMode.Both || team.Mode == MirrorTeamMode.Normal && mode == MirrorMode.Normal
            || team.Mode == MirrorTeamMode.Hard && mode == MirrorMode.Hard);

    public static MirrorTeamOptions[] Rotate(IReadOnlyList<MirrorTeamOptions> teams, int completedIndex) =>
        teams.Where((_, index) => index != completedIndex).Append(teams[completedIndex]).ToArray();

    public static void Validate(MirrorOptions options)
    {
        ValidateConfiguration(options);
        if (!options.ClaimRewards && options.Runs != 1) throw new ArgumentException("保留结算奖励时只能运行一轮");
        if (!options.Teams.Any(team => Eligible(team, options.Mode))) throw new ArgumentException("没有适用于当前难度的镜牢队伍");
    }

    public static void ValidateConfiguration(MirrorOptions options)
    {
        if (!Enum.IsDefined(options.Mode) || !Enum.IsDefined(options.WeeklyBonus))
            throw new ArgumentException("镜牢难度或周奖励设置无效");
        if (options.Runs is < 1 or > 999) throw new ArgumentException("镜牢次数须为 1–999");
        if (options.Teams is null) throw new ArgumentException("缺少镜牢队伍配置");
        foreach (var team in options.Teams)
        {
            if (string.IsNullOrWhiteSpace(team.Name) || !Enum.IsDefined(team.Mode) || team.GameTeamNumber is < 1 or > 50)
                throw new ArgumentException("镜牢队伍名称、用途或游戏编号无效");
            if (team.SinnerOrder is null || team.SinnerOrder.Length is < 1 or > 12 || team.SinnerOrder.Distinct().Count() != team.SinnerOrder.Length
                || team.SinnerOrder.Any(value => value is < 1 or > 12)) throw new ArgumentException("出战顺序须为不重复的 1–12 罪人编号");
            if (team.DefenseForSoloTurns is < 1 or > 5) throw new ArgumentException("小指良防御回合须为 1–5");
            if (team.StarLevels is null || team.StarLevels.Length != 10 || team.StarLevels.Any(value => value is < 0 or > 3))
                throw new ArgumentException("十个星光增益的等级须为 0–3");
            if (team.InitialGifts is null || team.InitialGifts.Length != 3 || team.InitialGifts.Distinct().Count() != 3
                || team.InitialGifts.Any(value => value is < 1 or > 3)) throw new ArgumentException("初始饰品须为 1–3 的优先顺序");
            if (team.Rewards is null || !Keywords.Contains(team.Rewards.Keyword)
                || team.Rewards.SecondaryKeyword is { } second && !Keywords.Contains(second)) throw new ArgumentException("镜牢体系设置无效");
            if (!Enum.IsDefined(team.Rewards.CardPreference)) throw new ArgumentException("镜牢奖励卡优先级无效");
            if (team.Theme is null || team.Shop is null) throw new ArgumentException("缺少主题包或商店设置");
            if (team.Theme.RefreshLimit is < 0 or > 10) throw new ArgumentException("主题包刷新次数须为 0–10");
            if (team.Theme.Floor is < 1 or > 5) throw new ArgumentException("主题包楼层须为 1–5");
            if (team.Theme.PreferredThreshold is < -10 or > 10 || team.Theme.UnknownWeight is < -10 or > 10)
                throw new ArgumentException("主题包优选阈值和未知权重须为 -10–10");
            if (team.Theme.NormalWeights is null || team.Theme.HardWeights is null)
                throw new ArgumentException("缺少普通或困难主题包权重");
            foreach (var group in new[] { (Hard: false, Weights: team.Theme.NormalWeights), (Hard: true, Weights: team.Theme.HardWeights) })
                foreach (var pair in group.Weights)
                {
                    var pack = MirrorThemeCatalog.All.FirstOrDefault(pack => pack.Id.Equals(pair.Key, StringComparison.OrdinalIgnoreCase));
                    if (pack is null || !(group.Hard ? pack.InHard : pack.InNormal))
                        throw new ArgumentException($"当前模式的主题包 ID 无效：{pair.Key}");
                    if (pair.Value is < -10 or > 10) throw new ArgumentException($"主题包权重须为 -10–10：{pair.Key}");
                }
            MirrorShopRules.Validate(team.Shop, team.Rewards.Keyword, 1);
            MirrorObservation.Validate(team.Rewards.ObservedGifts);
            MirrorObservation.Validate(ObservedGifts(team));
        }
    }
}
