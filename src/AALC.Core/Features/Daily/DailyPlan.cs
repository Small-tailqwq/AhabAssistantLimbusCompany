namespace AALC.Core.Features.Daily;

public static class DailyPlan
{
    public static IReadOnlyList<int> Batches(int total, bool continuous, int maximum)
    {
        if (total < 0) throw new ArgumentException("采光次数不能为负数", nameof(total));
        if (continuous && maximum is < 1 or > 10)
            throw new ArgumentException("每批连战次数必须为 1 到 10", nameof(maximum));
        var batches = new List<int>();
        var size = continuous ? maximum : 1;
        while (total > 0)
        {
            var count = Math.Min(total, size);
            batches.Add(count);
            total -= count;
        }
        return batches;
    }

    public static int TeamFor(DailyOptions options, LuxcavationKind kind, DateTimeOffset now)
    {
        // 游戏日按首尔时间 06:00 切换，先减六小时再计算星期。
        var gameDate = now.ToOffset(TimeSpan.FromHours(9)).AddHours(-6);
        var day = gameDate.DayOfWeek == DayOfWeek.Sunday ? 7 : (int)gameDate.DayOfWeek;
        return kind switch
        {
            LuxcavationKind.Experience when options.ExpTeamByDay => options.ExpTeams[(day - 1) / 2],
            LuxcavationKind.Thread when options.ThreadTeamByDay => options.ThreadTeams[day - 1],
            _ => options.TeamNumber
        };
    }

    public static void Validate(DailyOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        if (options.ExpCount < 0 || options.ThreadCount < 0)
            throw new ArgumentException("经验本与纺锤本次数不能为负数");
        if (options.TeamNumber is < 1 or > 20)
            throw new ArgumentException("日常队伍编号必须为 1 到 20");
        if (options.MaxContinuousCombat is < 1 or > 10)
            throw new ArgumentException("每批连战次数必须为 1 到 10");
        if (options.ExpTeams is not { Length: 4 } || options.ExpTeams.Any(team => team is < 1 or > 20))
            throw new ArgumentException("经验本按日队伍需要四组 1 到 20 的队伍编号");
        if (options.ThreadTeams is not { Length: 7 } || options.ThreadTeams.Any(team => team is < 1 or > 20))
            throw new ArgumentException("纺锤本按日队伍需要七组 1 到 20 的队伍编号");
        if (options.RefillTier is < 0 or > 3)
            throw new ArgumentException("狂气补充档位必须为 0 到 3");
    }
}
