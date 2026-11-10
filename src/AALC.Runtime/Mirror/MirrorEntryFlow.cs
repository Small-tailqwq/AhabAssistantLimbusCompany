using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;
using AALC.Runtime.Daily;

namespace AALC.Runtime.Mirror;

public static class MirrorEntryFlow
{
    private const string Entry = "mirror/road_to_mir/";
    private const string Stars = Entry + "dreaming_star/";
    private const string SelectAllStars = Entry + "select_all_stars_assets.png";
    private const string Forfeit = "mirror/claim_reward/claim_forfeit_assets.png";
    private static readonly string[] AllStarLevels = [Stars + "level_one_bonus_assets.png", Stars + "level_two_bonus_assets.png"];
    private static readonly string[] Inside = [MirrorThemeFlow.Map, "mirror/theme_pack/feature_theme_pack_assets.png",
        "mirror/shop/shop_coins_assets.png", MirrorRewardFlow.Cards, MirrorRewardFlow.Gift,
        MirrorRewardFlow.GiftBox, MirrorRewardFlow.GiftConfirm, MirrorRewardFlow.GiftSelect, MirrorRewardFlow.Claim,
        "battle/more_information_assets.png", "battle/turn_assets.png", "battle/pause_assets.png",
        "battle/normal_to_battle_assets.png", "battle/chaim_to_battle_assets.png", "teams/identify_assets.png", "event/skip_assets.png",
        "mirror/claim_reward/claim_rewards_assets.png", "mirror/claim_reward/clear_assets.png"];
    public static readonly ImageQuery[] Queries = [.. Inside.Select(asset => new ImageQuery(asset)),
        new("home/drive_assets.png"), new("home/window_assets.png"), new("home/inferno_bus_assets.png"),
        new("base/clear_all_caches_assets.png"),
        new("mirror/shop/leave_assets.png"), new("mirror/shop/power_up_assets.png"), new("mirror/shop/power_up_confirm_assets.png"),
        new("mirror/shop/heal_sinner/heal_sinner_return_assets.png"), new("mirror/shop/heal_sinner/heal_all_sinner_assets.png"),
        new("home/mirror_dungeons_assets.png", .65),
        new(Entry + "resume_assets.png"), new(Entry + "enter_mirror_assets.png", .78), new(Entry + "enter_assets.png"),
        new(Entry + "infinity_mirror_enter_assets.png"), new(Entry + "infinity_mirror_locked.png"), new(Entry + "select_team_stars_assets.png"),
        new(Entry + "select_team_confirm_assets.png"), new(Entry + "level_confirm_assets.png"), new(Entry + "enter_mirror_confirm.png"),
        new(Stars + "coins_assets.png", .9), new(Stars + "dreaming_star_enter_assets.png"), new(Stars + "select_star_confirm_assets.png"), new(Entry + "activate_gift_search_on_assets.png"),
        new(Entry + "activate_gift_search_off_assets.png"), new(MirrorRewardFlow.ObserveBurn), new(MirrorRewardFlow.ObserveBleed)];

    public static async Task<bool> RunAsync(IGameSession s, MirrorTeamOptions team, CancellationToken ct)
    {
        var selectedTeam = false;
        var resuming = false;
        var infiniteChecks = 0;
        var infiniteClicks = 0;
        var nextInfiniteClick = TimeSpan.Zero;
        var nextEnterClick = TimeSpan.Zero;
        var nextEntryConfirmClick = TimeSpan.Zero;
        for (var attempt = 0; attempt < 100; attempt++)
        {
            var frame = await s.ObserveAsync(Queries, ct);
            if (frame.Find("base/clear_all_caches_assets.png") is not null)
            {
                if (!await DailyNavigation.ReturnHomeAsync(s, ct)) return false;
                continue;
            }
            if (frame.Find(Entry + "level_confirm_assets.png") is not null || frame.Find(Entry + "enter_mirror_confirm.png") is not null)
            {
                var notice = string.Concat((await s.ReadTextAsync(frame, ct, frame.Region(900, 570, 1700, 800)))
                    .Select(item => item.Text));
                if (notice.Contains("当前进度已过期") && notice.Contains("领取") && notice.Contains("奖励"))
                {
                    if (!await ClearExpiredProgressAsync(s, frame, ct)) return false;
                    selectedTeam = false;
                    resuming = false;
                    nextEnterClick = nextEntryConfirmClick = TimeSpan.Zero;
                    continue;
                }
            }
            // 选队页左侧有“编队 #N”列表，战前出战页只有预设；两页共用人格锚点。
            var selectingTeam = frame.Find(Entry + "select_team_stars_assets.png") is not null
                || frame.Find("teams/identify_assets.png") is not null && HasTeamList(await s.ReadTextAsync(frame, ct,
                    frame.Region(80, 500, 400, 1120), 2));
            if (!selectingTeam
                && (Inside.Any(asset => frame.Find(asset) is not null) || await MirrorShopFlow.IsHealingResultAsync(s, frame, ct)
                || await MirrorShopFlow.IsHealingChoicesAsync(s, frame, ct)
                || await MirrorShopFlow.EnhancementExitAsync(s, frame, ct) is not null)) return true;
            if (selectingTeam)
            {
                var confirmation = frame.Find(Entry + "level_confirm_assets.png") is not null
                    || frame.Find(Entry + "enter_mirror_confirm.png") is not null;
                if (!selectedTeam && !confirmation)
                {
                    if (!await TeamSelection.RunAsync(s, team.GameTeamNumber, team.SelectTeamByOrder, ct)) return false;
                    selectedTeam = true;
                    continue;
                }
                if (s.Elapsed >= nextEntryConfirmClick)
                {
                    await ClickFirstAsync(s, frame, [Entry + "level_confirm_assets.png", Entry + "enter_mirror_confirm.png",
                        Entry + "select_team_confirm_assets.png"], "mirror.entry.confirm-team", ct);
                    nextEntryConfirmClick = s.Elapsed + TimeSpan.FromSeconds(3);
                }
            }
            else if (frame.Find(Entry + "level_confirm_assets.png") is not null || frame.Find(Entry + "enter_mirror_confirm.png") is not null)
            {
                if (resuming)
                    throw new InvalidOperationException("继续镜牢后出现未预期的确认框，已停止以保留当前进度");
                if (s.Elapsed >= nextEntryConfirmClick)
                {
                    await ClickFirstAsync(s, frame, [Entry + "level_confirm_assets.png", Entry + "enter_mirror_confirm.png"], "mirror.entry.confirm-level", ct);
                    nextEntryConfirmClick = s.Elapsed + TimeSpan.FromSeconds(3);
                    nextEnterClick = s.Elapsed + TimeSpan.FromSeconds(15);
                }
            }
            else if (frame.Find(Stars + "coins_assets.png") is not null || frame.Find(Stars + "dreaming_star_enter_assets.png") is not null
                || frame.Find(Stars + "select_star_confirm_assets.png") is not null)
            {
                if (!await SelectStarsAsync(s, team, ct)) return false;
            }
            else if (frame.Find(MirrorRewardFlow.ObserveBurn) is not null || frame.Find(MirrorRewardFlow.ObserveBleed) is not null)
            {
                if (!await MirrorRewardFlow.ObserveGiftsAsync(s, MirrorPlan.ObservedGifts(team), ct)) return false;
            }
            else if (frame.Find(Entry + "activate_gift_search_on_assets.png") is not null || frame.Find(Entry + "activate_gift_search_off_assets.png") is not null)
            {
                if (!await SelectInitialGiftsAsync(s, team, ct)) return false;
            }
            // 继续弹窗只调暗背景，背后的进入按钮仍能匹配；点进入会落在弹窗外并把它关掉。
            else if (frame.Find(Entry + "resume_assets.png") is { } resume)
            {
                await s.ClickAsync(frame, resume.Center, "mirror.entry.resume", ct);
                resuming = true;
            }
            else if (frame.Find(Entry + "enter_assets.png") is { } enter)
            {
                if (s.Elapsed < nextEnterClick)
                {
                    await s.DelayAsync(TimeSpan.FromMilliseconds(250), ct);
                    continue;
                }
                // 未解锁时面板只有锁和解锁条件，没有 ON/OFF，等同关闭。
                // 留出检测高度，避免单行直识把状态词旁的斜线装饰一起识别。
                var state = frame.Find(Entry + "infinity_mirror_locked.png") is not null ? "off"
                    : string.Concat((await s.ReadTextAsync(frame, ct, frame.Region(2167, 640, 2337, 740), 2))
                        .Select(t => t.Text)).Trim().ToLowerInvariant();
                if (state != "off")
                {
                    if (++infiniteChecks > 12 || infiniteClicks >= 3 && s.Elapsed >= nextInfiniteClick)
                    {
                        s.Report("mirror.entry.unknown-infinite", $"多次观察后仍无法确认无尽镜牢已关闭（识别结果：{(state.Length > 0 ? state : "空")}）");
                        return false;
                    }
                    if (state == "on" && s.Elapsed >= nextInfiniteClick
                        && frame.Find(Entry + "infinity_mirror_enter_assets.png") is { } infinite)
                    {
                        if (infiniteClicks > 0) s.Report("mirror.entry.retry-infinite", "无尽模式仍为 ON，重新关闭");
                        await s.ClickAsync(frame, infinite.Center, "mirror.entry.disable-infinite", ct);
                        infiniteClicks++;
                        nextInfiniteClick = s.Elapsed + TimeSpan.FromSeconds(1);
                    }
                    await s.DelayAsync(TimeSpan.FromMilliseconds(250), ct);
                    continue;
                }
                await s.ClickAsync(frame, enter.Center, "mirror.entry.enter", ct);
                nextEnterClick = s.Elapsed + TimeSpan.FromSeconds(2);
            }
            else if (!await ClickFirstAsync(s, frame, [Entry + "enter_mirror_assets.png",
                "home/mirror_dungeons_assets.png", "home/drive_assets.png", "home/window_assets.png"], "mirror.entry.navigate", ct))
            {
                if (BattleEvents.HasNarration(frame, await s.ReadTextAsync(frame, ct))) return true;
                await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
            }
            await s.DelayAsync(TimeSpan.FromMilliseconds(250), ct);
        }
        s.Report("mirror.entry.timeout", "镜牢入口未能推进");
        return false;
    }

    public static bool HasTeamList(IReadOnlyList<RecognizedText> text) => text.Any(item => item.Confidence >= .7
        && System.Text.RegularExpressions.Regex.IsMatch(item.Text, @"(?:编队|Team)\s*#?\s*\d+",
            System.Text.RegularExpressions.RegexOptions.IgnoreCase));

    private static async Task<bool> ClearExpiredProgressAsync(IGameSession s, GameFrame notice, CancellationToken ct)
    {
        s.Report("mirror.entry.expired", "当前镜牢进度已过期，清理旧奖励后重新进入");
        await ClickFirstAsync(s, notice, [Entry + "level_confirm_assets.png", Entry + "enter_mirror_confirm.png"],
            "mirror.entry.expired-open", ct);
        ImageQuery[] queries = [.. Queries, new(Forfeit, Search: SearchMode.Normal), new(MirrorSettlementFlow.UseModules)];
        var opened = false;
        var forfeited = false;
        var confirmed = false;
        for (var attempt = 0; attempt < 30; attempt++)
        {
            await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
            var frame = await s.ObserveAsync(queries, ct);
            if (!forfeited && frame.Find(Forfeit) is { } forfeit && frame.Find(MirrorSettlementFlow.UseModules) is not null)
            {
                if (!await HasOnlyZeroExpiredRewardsAsync(s, frame, ct))
                    throw new InvalidOperationException("过期进度的奖励未确认全部为零，已保留当前页面，请人工检查奖励");
                await s.ClickAsync(frame, forfeit.Center, "mirror.entry.expired-forfeit", ct);
                forfeited = true;
                continue;
            }
            if (forfeited)
            {
                var text = await s.ReadTextAsync(frame, ct, frame.Region(700, 400, 1900, 1100));
                var message = string.Concat(text.Select(item => item.Text));
                var confirm = text.FirstOrDefault(item => item.Text.Trim() == "确认");
                if (!confirmed && message.Contains("放弃") && message.Contains("奖励") && confirm is not null)
                {
                    await s.ClickAsync(frame, new(confirm.Bounds.X + confirm.Bounds.Width / 2,
                        confirm.Bounds.Y + confirm.Bounds.Height / 2), "mirror.entry.expired-confirm", ct);
                    confirmed = true;
                    continue;
                }
                if (frame.Find(Forfeit) is null && frame.Find(MirrorSettlementFlow.Clear) is null
                    && frame.Find(MirrorSettlementFlow.UseModules) is null
                    && confirm is null
                    && frame.Find(Entry + "level_confirm_assets.png") is null && frame.Find(Entry + "enter_mirror_confirm.png") is null
                    && (frame.Find(Entry + "enter_assets.png") is not null || frame.Find(Entry + "enter_mirror_assets.png") is not null))
                {
                    s.Report("mirror.entry.expired-cleared", "旧进度已清理，继续本轮镜牢");
                    return true;
                }
            }
            else if (!opened && frame.Find(MirrorSettlementFlow.Claim) is { } claim)
            {
                await s.ClickAsync(frame, claim.Center, "mirror.entry.expired-rewards", ct);
                opened = true;
            }
        }
        s.Report("mirror.entry.expired-incomplete", "过期进度清理未完成，已保留当前页面");
        throw new InvalidOperationException("过期进度清理未完成，已保留当前页面，请人工检查");
    }

    private static async Task<bool> HasOnlyZeroExpiredRewardsAsync(IGameSession s, GameFrame frame, CancellationToken ct)
    {
        // 读取完整数值字段，不能只取末位，否则 10、100 等奖励也会被当成零。
        PixelRect[] fields = [frame.Region(860, 904, 1120, 980), frame.Region(1760, 766, 1980, 830),
            frame.Region(1760, 846, 1980, 910), frame.Region(1760, 932, 1980, 996)];
        foreach (var field in fields)
        {
            var text = await s.ReadTextAsync(frame, ct, field, 2);
            if (text.Count != 1 || text[0].Confidence < .9) return false;
            var value = text[0].Text.Trim();
            if (value.StartsWith("EXP", StringComparison.OrdinalIgnoreCase)) value = value[3..].Trim();
            else if (value.StartsWith('x') || value.StartsWith('X') || value.StartsWith('×')) value = value[1..].Trim();
            if (value != "0") return false;
        }
        return true;
    }

    public static async Task<bool> SelectStarsAsync(IGameSession s, MirrorTeamOptions team, CancellationToken ct)
    {
        ImageQuery[] queries = [new(Stars + "select_star_confirm_assets.png"), new(Stars + "dreaming_star_enter_assets.png"),
            new(Entry + "bleed_gift_assets.png"), new(SelectAllStars), .. AllStarLevels.Select(asset => new ImageQuery(asset))];
        var configured = false;
        var submitted = false;
        var cancelledExisting = false;
        var conversionSent = false;
        var confirmed = false;
        for (var attempt = 0; attempt < 35; attempt++)
        {
            var frame = await s.ObserveControlsAsync(queries, ct);
            if (frame.Find(Entry + "bleed_gift_assets.png") is not null) return true;
            if (frame.Find(Stars + "select_star_confirm_assets.png") is { } confirm)
            {
                if (!submitted)
                {
                    if (!cancelledExisting)
                    {
                        await s.ClickAsync(frame, new(confirm.Center.X - (int)(340 * frame.Scale), confirm.Center.Y),
                            "mirror.stars.cancel-existing", ct);
                        cancelledExisting = true;
                    }
                    await s.DelayAsync(TimeSpan.FromMilliseconds(900), ct);
                    continue;
                }
                if (confirmed)
                {
                    await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
                    continue;
                }
                var conversion = StarConversionState(frame, confirm);
                if (conversion is null)
                {
                    s.Report("mirror.stars.unknown-conversion", "未确认星光转换复选框的边线及勾选状态");
                    return false;
                }
                if (conversion != team.ConvertStarlight)
                {
                    if (conversionSent)
                    {
                        s.Report("mirror.stars.conversion-unchanged", "星光转换开关点击后未改变，不提交");
                        return false;
                    }
                    await s.ClickAsync(frame, StarConversionPoint(frame, confirm), "mirror.stars.convert", ct);
                    conversionSent = true;
                }
                else
                {
                    await s.ClickAsync(frame, confirm.Center, "mirror.stars.confirm", ct);
                    confirmed = true;
                }
                await s.DelayAsync(TimeSpan.FromMilliseconds(900), ct);
                continue;
            }
            if (!configured && frame.Find(Stars + "dreaming_star_enter_assets.png") is not null)
            {
                if (!await ConfigureStarsAsync(s, team.StarLevels, queries, ct)) return false;
                configured = true;
                continue;
            }
            if (configured && !submitted && frame.Find(Stars + "dreaming_star_enter_assets.png") is { } start)
            {
                await s.ClickAsync(frame, start.Center, "mirror.stars.enter", ct);
                submitted = true;
            }
            await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
        }
        s.Report("mirror.stars.unverified", "星光选择或确认页面未能推进");
        return false;
    }

    private static readonly int[] StarPrices = MirrorStarBonusCatalog.All.Select(item => item.Cost).ToArray();

    private static async Task<bool> ConfigureStarsAsync(IGameSession s, int[] requested, ImageQuery[] queries, CancellationToken ct)
    {
        // 已选卡的发光填充和点击动画需要稳定后再读取。
        await s.DelayAsync(TimeSpan.FromMilliseconds(900), ct);
        var frame = await s.ObserveControlsAsync(queries, ct);
        if (frame.Find(Stars + "dreaming_star_enter_assets.png") is not { } done) return false;
        if (!HasStarGrid(frame, StarGridOrigin(frame, done), await s.ReadTextAsync(frame, ct)))
        {
            s.Report("mirror.stars.unknown-layout", "未确认星光标题及十项恩惠布局");
            return false;
        }
        if (await ReadStarLevelsAsync(s, frame, done, ct) is not { } levels)
        {
            s.Report("mirror.stars.unknown-selection", "未确认当前十项星光的选中状态及成本");
            return false;
        }
        // 与旧版一致，星光数字不作为选择条件：可用星光之外由账户星光支付，游戏自己结算。
        for (var index = 0; index < levels.Length; index++)
            if (levels[index] != 0 && levels[index] != requested[index])
                if (await ChangeStarAsync(s, queries, index, 0, ct)) levels[index] = 0;

        var uniform = requested[0] > 0 && requested.All(level => level == requested[0]);
        if (!uniform || levels.SequenceEqual(requested) || !await SelectAllStarsAsync(s, queries, levels, requested[0], ct))
            for (var index = 0; index < levels.Length; index++)
            {
                if (levels[index] == requested[index] || requested[index] == 0) continue;
                if (await ChangeStarAsync(s, queries, index, 1, ct) && requested[index] > 1)
                    await ChangeStarAsync(s, queries, index, requested[index], ct);
            }
        s.Report("mirror.stars.configured", $"星光选择完成：配置 {requested.Count(level => level > 0)} 项");
        return true;
    }

    // 与旧版一致：全部同级时用页面右侧的全选和全部强化，失败时回到逐卡选择。
    private static async Task<bool> SelectAllStarsAsync(IGameSession s, ImageQuery[] queries, int[] levels, int level, CancellationToken ct)
    {
        if (levels.Any(value => value == 0))
        {
            var selected = false;
            for (var click = 0; click < 3 && !selected; click++)
            {
                var frame = await s.ObserveControlsAsync(queries, ct);
                if (frame.Find(SelectAllStars) is not { } all) return false;
                await s.ClickAsync(frame, all.Center, "mirror.stars.select-all", ct);
                for (var attempt = 0; attempt < 4 && !selected; attempt++)
                {
                    await s.DelayAsync(TimeSpan.FromMilliseconds(attempt == 0 ? 900 : 300), ct);
                    frame = await s.ObserveControlsAsync(queries, ct);
                    if (frame.Find(Stars + "dreaming_star_enter_assets.png") is { } done)
                        selected = Enumerable.Range(0, 10).All(index => StarSelected(frame, StarGridOrigin(frame, done), index) == true);
                }
            }
            if (!selected) return false;
        }
        if (level == 1) return true;
        for (var click = 0; click < 3; click++)
        {
            var frame = await s.ObserveControlsAsync(queries, ct);
            if (frame.Find(Stars + "dreaming_star_enter_assets.png") is not { } done || frame.Find(AllStarLevels[level - 2]) is not { } upgrade) return false;
            if (await ReadStarLevelsAsync(s, frame, done, ct) is not { } current) return false;
            if (current.All(value => value == level)) return true;
            await s.ClickAsync(frame, upgrade.Center, "mirror.stars.level-all", ct);
            await s.DelayAsync(TimeSpan.FromMilliseconds(900), ct);
        }
        s.Report("mirror.stars.unchanged", "全部强化点击 3 次仍未确认等级，继续进入");
        return true;
    }

    private static async Task<bool> ChangeStarAsync(IGameSession s, ImageQuery[] queries, int index, int level, CancellationToken ct)
    {
        for (var click = 0; click < 3; click++)
        {
            var frame = await s.ObserveControlsAsync(queries, ct);
            if (frame.Find(Stars + "dreaming_star_enter_assets.png") is not { } done) return false;
            var origin = StarGridOrigin(frame, done);
            // 重点前再看一眼：响应慢的点击可能已生效，再点会把卡取消。
            if ((click > 0 || level == 1) && StarSelected(frame, origin, index) == (level > 0)) return true;
            var point = new PixelPoint(origin.X + (int)(index % 5 * 400 * frame.Scale), origin.Y + (int)(index / 5 * 480 * frame.Scale));
            if (level > 1) point = new(point.X + (int)((level == 2 ? -80 : 80) * frame.Scale), point.Y + (int)(304 * frame.Scale));
            await s.ClickAsync(frame, point, level > 1 ? "mirror.stars.level" : level == 0 ? "mirror.stars.clear" : "mirror.stars.select", ct);
            for (var attempt = 0; attempt < 4; attempt++)
            {
                await s.DelayAsync(TimeSpan.FromMilliseconds(attempt == 0 ? 900 : 300), ct);
                frame = await s.ObserveControlsAsync(queries, ct);
                if (frame.Find(Stars + "dreaming_star_enter_assets.png") is not { } observedDone) continue;
                if (StarSelected(frame, StarGridOrigin(frame, observedDone), index) == (level > 0)) return true;
            }
        }
        s.Report("mirror.stars.unchanged", $"第 {index + 1} 项星光点击 3 次仍未生效，跳过");
        return false;
    }

    private static async Task<int[]?> ReadStarLevelsAsync(IGameSession s, GameFrame frame, VisualTarget done, CancellationToken ct)
    {
        var origin = StarGridOrigin(frame, done);
        var levels = new int[10];
        for (var index = 0; index < levels.Length; index++)
        {
            var selected = StarSelected(frame, origin, index);
            if (selected is null) return null;
            if (!selected.Value) continue;
            var price = await ReadStarNumberAsync(s, frame, new(origin.X + (int)((index % 5 * 400 + 90) * frame.Scale),
                origin.Y + (int)((index / 5 * 480 - 96) * frame.Scale), (int)(70 * frame.Scale), (int)(72 * frame.Scale)), ct);
            if (price is null || price % StarPrices[index] != 0 || price / StarPrices[index] is < 1 or > 3) return null;
            levels[index] = price.Value / StarPrices[index];
        }
        return levels;
    }

    private static async ValueTask<int?> ReadStarNumberAsync(IGameSession s, GameFrame frame, PixelRect region, CancellationToken ct, int scale = 2)
    {
        var numbers = (await s.ReadTextAsync(frame, ct, region, scale)).Where(item => item.Confidence >= .6)
            .Select(item => string.Concat(item.Text.Where(char.IsAsciiDigit)))
            .Where(value => value.Length > 0).Select(value => int.TryParse(value, out var number) ? (int?)number : null)
            .Where(value => value is not null).Distinct().ToArray();
        return numbers.Length == 1 ? numbers[0] : null;
    }

    private static bool? StarSelected(GameFrame frame, PixelPoint origin, int index)
    {
        var region = new PixelRect(origin.X + (int)((index % 5 * 400 - 144) * frame.Scale),
            origin.Y + (int)((index / 5 * 480 + 288) * frame.Scale), (int)(112 * frame.Scale), (int)(24 * frame.Scale));
        var blue = StarPixelRatio(frame, region, (r, g, b) => b >= 45 && b - r >= 12);
        var border = StarPixelRatio(frame, new(origin.X + (int)((index % 5 * 400 - 160) * frame.Scale),
            origin.Y + (int)((index / 5 * 480 - 64) * frame.Scale), (int)(320 * frame.Scale), (int)(6 * frame.Scale)),
            (r, g, b) => b >= 45 && b - r >= 12);
        return blue >= .45 || border >= .10 ? true : blue <= .15 && border <= .06 ? false : null;
    }

    private static PixelPoint StarConversionPoint(GameFrame frame, VisualTarget confirm) =>
        new(confirm.Center.X + (int)(76 * frame.Scale), confirm.Center.Y - (int)(350 * frame.Scale));

    private static bool? StarConversionState(GameFrame frame, VisualTarget confirm)
    {
        var point = StarConversionPoint(frame, confirm);
        var left = point.X - (int)(26 * frame.Scale);
        var right = point.X + (int)(26 * frame.Scale);
        var top = point.Y - (int)(30 * frame.Scale);
        var bottom = point.Y + (int)(28 * frame.Scale);
        var thickness = Math.Max(1, (int)(2 * frame.Scale));
        PixelRect[] edges = [new(left, top, right - left + 1, thickness), new(left, bottom, right - left + 1, thickness),
            new(left, top, thickness, bottom - top + 1), new(right, top, thickness, bottom - top + 1)];
        // 模板中心与细边线独立取整，非整数缩放时允许边线在相邻像素上。
        var tolerance = (int)Math.Ceiling(2 * frame.Scale);
        if (edges.Any(edge => !Enumerable.Range(-tolerance, 2 * tolerance + 1).Any(offset =>
            StarPixelRatio(frame, edge.Width > edge.Height ? edge with { Y = edge.Y + offset } : edge with { X = edge.X + offset },
                (r, g, b) => Math.Min(r, Math.Min(g, b)) >= 95
                    && Math.Max(r, Math.Max(g, b)) - Math.Min(r, Math.Min(g, b)) <= 30) is >= .6))) return null;
        var inset = Math.Max(2, (int)(6 * frame.Scale));
        var white = StarPixelRatio(frame, new(left + inset, top + inset, right - left - 2 * inset, bottom - top - 2 * inset),
            (r, g, b) => Math.Min(r, Math.Min(g, b)) >= 160 && Math.Max(r, Math.Max(g, b)) - Math.Min(r, Math.Min(g, b)) <= 25);
        return white is >= .15 and <= .55 ? true : white <= .025 ? false : null;
    }

    private static double? StarPixelRatio(GameFrame frame, PixelRect region, Func<int, int, int, bool> predicate)
    {
        if (region.Width <= 0 || region.Height <= 0 || region.X < 0 || region.Y < 0 || region.Right > frame.Identity.Width
            || region.Bottom > frame.Identity.Height || frame.Pixels.Bgra.Length != frame.Identity.Width * frame.Identity.Height * 4) return null;
        var matched = 0;
        for (var y = region.Y; y < region.Bottom; y++)
        for (var x = region.X; x < region.Right; x++)
        {
            var offset = (y * frame.Identity.Width + x) * 4;
            if (predicate(frame.Pixels.Bgra[offset + 2], frame.Pixels.Bgra[offset + 1], frame.Pixels.Bgra[offset])) matched++;
        }
        return matched / (double)(region.Width * region.Height);
    }

    private static PixelPoint StarGridOrigin(GameFrame frame, VisualTarget done) =>
        // 既有完成按钮 bbox 中心与 Python 十卡网格的基准偏移。
        new(done.Center.X - (int)(1930 * frame.Scale), done.Center.Y - (int)(906 * frame.Scale));

    private static bool HasStarGrid(GameFrame frame, PixelPoint origin, IReadOnlyList<RecognizedText> text)
    {
        // 页面标题随汉化版本变化，十项名称及其网格位置才是稳定依据。
        static string Normalize(string value) => string.Concat(value.Where(char.IsLetterOrDigit)).ToLowerInvariant();
        string[][] names = [["起始之星", "Star of the Beginning"], ["层积星云", "Cumulating Starcloud"],
            ["星际旅行", "Interstellar Travel"], ["倾落的流星雨", "Star-shower"], ["双星商店", "Binary Star-shop"],
            ["卫星商店", "Moon Star-shop"], ["星云的宠爱", "Favor of the Nebulae"], ["星芒的引导", "Starlight Guidance"],
            ["偶然的彗星", "Chance Comet"], ["全面的可能性", "Perfected Possibility"]];
        return names.Select((aliases, index) => (aliases, index)).All(value => text.Any(item =>
            value.aliases.Any(alias => Normalize(item.Text).Contains(Normalize(alias)))
            && Math.Abs(item.Bounds.X + item.Bounds.Width / 2 - origin.X - value.index % 5 * 400 * frame.Scale) <= 180 * frame.Scale
            && Math.Abs(item.Bounds.Y + item.Bounds.Height / 2 - origin.Y - value.index / 5 * 480 * frame.Scale) <= 60 * frame.Scale));
    }

    public static async Task<bool> SelectInitialGiftsAsync(IGameSession s, MirrorTeamOptions team, CancellationToken ct)
    {
        var keyword = team.Rewards.Keyword;
        var giftKeys = team.InitialGifts.Select(index => Entry + $"select_init_gift/{keyword}_ego_gift_{index}.png").ToArray();
        ImageQuery[] queries = [new(Entry + keyword + "_gift_assets.png"), new(Entry + "slash_gift_1.png"),
            new(Entry + "activate_gift_search_on_assets.png"), new(Entry + "activate_gift_search_off_assets.png"),
            new(Entry + "select_init_ego_gifts_confirm_assets.png"), new(MirrorRewardFlow.GiftConfirm),
            new(MirrorRewardFlow.ObserveBurn), new(MirrorRewardFlow.ObserveBleed),
            new("mirror/theme_pack/feature_theme_pack_assets.png"), .. giftKeys.Select(key => new ImageQuery(key))];
        var selectedSystem = false;
        var cancelledWarning = false;
        var submitted = false;
        for (var attempt = 0; attempt < 35; attempt++)
        {
            var frame = await s.ObserveControlsAsync(queries, ct);
            if (frame.Find("mirror/theme_pack/feature_theme_pack_assets.png") is not null
                || frame.Find(MirrorRewardFlow.ObserveBurn) is not null || frame.Find(MirrorRewardFlow.ObserveBleed) is not null) return true;
            var dialogText = await s.ReadTextAsync(frame, ct, frame.Region(680, 580, 1870, 1000), 2);
            var warning = string.Concat(dialogText.Select(item => item.Text));
            if (warning.Contains("仍有选择") && warning.Contains("饰品") && warning.Contains("继续"))
            {
                var cancel = dialogText.FirstOrDefault(item => item.Text.Contains("取消"));
                if (cancelledWarning || cancel is null)
                {
                    s.Report("mirror.initial.warning", "未能取消初始饰品的剩余选择机会提示");
                    return false;
                }
                await s.ClickAsync(frame, new(cancel.Bounds.X + cancel.Bounds.Width / 2, cancel.Bounds.Y + cancel.Bounds.Height / 2),
                    "mirror.initial.cancel-warning", ct);
                cancelledWarning = true;
                submitted = false;
                await s.DelayAsync(TimeSpan.FromMilliseconds(900), ct);
                continue;
            }
            if (frame.Find(MirrorRewardFlow.GiftConfirm) is { } giftConfirm)
                await s.ClickAsync(frame, giftConfirm.Center, "mirror.initial.confirm-gift", ct);
            else if (frame.Find(Entry + (MirrorPlan.ObservedGifts(team).Length == 0 ? "activate_gift_search_on_assets.png" : "activate_gift_search_off_assets.png")) is { } observe)
                await s.ClickAsync(frame, observe.Center, "mirror.initial.observe-toggle", ct);
            else
            {
                // 同一体系的三件图标已出现时保留当前选择，不重复切换体系。
                if (giftKeys.All(key => frame.Find(key) is not null)) selectedSystem = true;
                if (!selectedSystem && frame.Find(Entry + keyword + "_gift_assets.png") is { } system)
                {
                    await s.ClickAsync(frame, system.Center, "mirror.initial.keyword", ct);
                    selectedSystem = true;
                }
                else if (!selectedSystem && keyword is "slash" or "pierce" or "blunt" && frame.Find(Entry + "slash_gift_1.png") is { } scroll)
                    await s.DragAsync(frame, scroll.Center, new(scroll.Center.X, scroll.Center.Y - (int)(400 * frame.Scale)),
                        TimeSpan.FromMilliseconds(250), "mirror.initial.scroll", ct);
                else if (selectedSystem && !submitted && frame.Find(Entry + "select_init_ego_gifts_confirm_assets.png") is { } confirm
                    && giftKeys.All(key => frame.Find(key) is not null))
                {
                    var count = await InitialGiftCountAsync(s, frame, confirm, ct);
                    var selected = giftKeys.Select(key => InitialGiftSelected(frame, frame.Find(key)!)).ToArray();
                    if (count is null || selected.Any(value => value is null) || count.Value.Maximum is < 1 or > 3
                        || count.Value.Selected != selected.Count(value => value == true))
                    {
                        s.Report("mirror.initial.unknown-selection", "未能核对初始饰品的选择数量及选中边框");
                        return false;
                    }
                    var wanted = giftKeys.Take(count.Value.Maximum).ToArray();
                    var clear = giftKeys.FirstOrDefault(key => !wanted.Contains(key) && InitialGiftSelected(frame, frame.Find(key)!) == true);
                    var choose = wanted.FirstOrDefault(key => InitialGiftSelected(frame, frame.Find(key)!) == false);
                    if (clear is not null || choose is not null)
                    {
                        if (!await ChangeInitialGiftAsync(s, frame, queries, clear ?? choose!, count.Value.Selected,
                            count.Value.Maximum, clear is null, ct)) return false;
                        continue;
                    }
                    if (count.Value.Selected == count.Value.Maximum)
                    {
                        s.Report("mirror.initial.configured", $"初始饰品已核对：{count.Value.Selected}/{count.Value.Maximum}");
                        await s.ClickAsync(frame, confirm.Center, "mirror.initial.submit", ct);
                        submitted = true;
                    }
                }
            }
            await s.DelayAsync(TimeSpan.FromMilliseconds(900), ct);
        }
        s.Report("mirror.initial.unverified", "初始饰品页面未能推进");
        return false;
    }

    private static async Task<bool> ChangeInitialGiftAsync(IGameSession s, GameFrame frame, ImageQuery[] queries,
        string key, int count, int maximum, bool select, CancellationToken ct)
    {
        // 页面切换后的第一下点击可能被吞，确认未生效才重点，避免把已选中的点掉。
        for (var click = 0; click < 3; click++)
        {
            if (frame.Find(key) is not { } target) break;
            await s.ClickAsync(frame, target.Center, select ? "mirror.initial.gift" : "mirror.initial.clear-gift", ct);
            for (var attempt = 0; attempt < 4; attempt++)
            {
                await s.DelayAsync(TimeSpan.FromMilliseconds(attempt == 0 ? 900 : 300), ct);
                frame = await s.ObserveControlsAsync(queries, ct);
                if (frame.Find(Entry + "select_init_ego_gifts_confirm_assets.png") is not { } confirm || frame.Find(key) is not { } gift) continue;
                var observed = await InitialGiftCountAsync(s, frame, confirm, ct);
                if (observed == (count + (select ? 1 : -1), maximum) && InitialGiftSelected(frame, gift) == select) return true;
            }
        }
        s.Report("mirror.initial.unchanged", "初始饰品点击 3 次后未观察到计数和选中状态变化，不提交");
        return false;
    }

    private static async ValueTask<(int Selected, int Maximum)?> InitialGiftCountAsync(IGameSession s, GameFrame frame,
        VisualTarget confirm, CancellationToken ct)
    {
        var text = await s.ReadTextAsync(frame, ct, new(confirm.Center.X + (int)(92 * frame.Scale),
            confirm.Center.Y - (int)(62 * frame.Scale), (int)(156 * frame.Scale), (int)(130 * frame.Scale)), 2);
        var value = string.Concat(text.OrderBy(item => item.Bounds.X).Select(item => item.Text)).Replace('／', '/').Split('/');
        if (value.Length != 2 || !int.TryParse(value[0].Trim(), out var selected) || !int.TryParse(value[1].Trim(), out var maximum)
            || selected < 0 || selected > maximum) return null;
        return (selected, maximum);
    }

    private static bool? InitialGiftSelected(GameFrame frame, VisualTarget gift)
    {
        var gold = StarPixelRatio(frame, new(gift.Center.X + (int)(120 * frame.Scale), gift.Center.Y - (int)(96 * frame.Scale),
            (int)(400 * frame.Scale), (int)(8 * frame.Scale)), (r, g, b) => r >= 200 && g >= 110 && b <= 100);
        return gold >= .15 ? true : gold <= .02 ? false : null;
    }

    internal static async Task<bool> ClickFirstAsync(IGameSession s, GameFrame frame, IEnumerable<string> assets, string rule, CancellationToken ct)
    {
        foreach (var asset in assets)
            if (frame.Find(asset) is { } target)
            {
                await s.ClickAsync(frame, target.Center, rule, ct);
                return true;
            }
        return false;
    }
}
