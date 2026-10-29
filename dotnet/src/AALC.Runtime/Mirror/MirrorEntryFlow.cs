using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;

namespace AALC.Runtime.Mirror;

public static class MirrorEntryFlow
{
    private const string Entry = "mirror/road_to_mir/";
    private const string Stars = Entry + "dreaming_star/";
    private static readonly string[] Inside = [MirrorThemeFlow.Map, "mirror/theme_pack/feature_theme_pack_assets.png",
        "mirror/shop/shop_coins_assets.png", MirrorRewardFlow.Cards, MirrorRewardFlow.Gift,
        MirrorRewardFlow.GiftBox, MirrorRewardFlow.GiftConfirm, MirrorRewardFlow.GiftSelect, MirrorRewardFlow.Claim,
        "battle/more_information_assets.png", "battle/turn_assets.png", "battle/pause_assets.png",
        "battle/normal_to_battle_assets.png", "battle/chaim_to_battle_assets.png", "event/skip_assets.png",
        "mirror/claim_reward/claim_rewards_assets.png", "mirror/claim_reward/clear_assets.png"];
    public static readonly ImageQuery[] Queries = [.. Inside.Select(asset => new ImageQuery(asset)),
        new("home/drive_assets.png"), new("home/window_assets.png"), new("home/inferno_bus_assets.png"),
        new("mirror/shop/leave_assets.png"), new("mirror/shop/power_up_assets.png"), new("mirror/shop/power_up_confirm_assets.png"),
        new("mirror/shop/heal_sinner/heal_sinner_return_assets.png"), new("mirror/shop/heal_sinner/heal_all_sinner_assets.png"),
        new("home/mirror_dungeons_assets.png", .65), new("home/first_prompt_assets.png"), new("home/back_assets.png"),
        new(Entry + "resume_assets.png"), new(Entry + "enter_mirror_assets.png", .78), new(Entry + "enter_assets.png"),
        new(Entry + "infinity_mirror_enter_assets.png"), new(Entry + "select_team_stars_assets.png"),
        new(Entry + "select_team_confirm_assets.png"), new(Entry + "level_confirm_assets.png"), new(Entry + "enter_mirror_confirm.png"),
        new(Stars + "coins_assets.png", .9), new(Stars + "dreaming_star_enter_assets.png"), new(Stars + "select_star_confirm_assets.png"), new(Entry + "activate_gift_search_on_assets.png"),
        new(Entry + "activate_gift_search_off_assets.png"), new(MirrorRewardFlow.ObserveBurn), new(MirrorRewardFlow.ObserveBleed)];

    public static async Task<bool> RunAsync(IGameSession s, MirrorTeamOptions team, CancellationToken ct)
    {
        var selectedTeam = false;
        var infiniteChecks = 0;
        var infiniteClicks = 0;
        var nextInfiniteClick = TimeSpan.Zero;
        var nextEnterClick = TimeSpan.Zero;
        var nextEntryConfirmClick = TimeSpan.Zero;
        for (var attempt = 0; attempt < 100; attempt++)
        {
            var frame = await s.ObserveAsync(Queries, ct);
            if (Inside.Any(asset => frame.Find(asset) is not null) || await MirrorShopFlow.IsHealingResultAsync(s, frame, ct)
                || await MirrorShopFlow.IsHealingChoicesAsync(s, frame, ct)
                || await MirrorShopFlow.EnhancementExitAsync(s, frame, ct) is not null) return true;
            if (frame.Find("home/first_prompt_assets.png") is not null && frame.Find("home/back_assets.png") is { } back)
                await s.ClickAsync(frame, back.Center, "mirror.entry.dismiss-prompt", ct);
            else if (frame.Find(Entry + "select_team_stars_assets.png") is not null)
            {
                if (!selectedTeam)
                {
                    if (!await TeamSelection.RunAsync(s, team.GameTeamNumber, team.SelectTeamByOrder, ct)) return false;
                    selectedTeam = true;
                    continue;
                }
                if (!await ClickFirstAsync(s, frame, [Entry + "level_confirm_assets.png", Entry + "select_team_confirm_assets.png",
                    Entry + "enter_mirror_confirm.png"], "mirror.entry.confirm-team", ct))
                    await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
            }
            else if (frame.Find(Entry + "level_confirm_assets.png") is not null || frame.Find(Entry + "enter_mirror_confirm.png") is not null)
            {
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
                if (!await MirrorRewardFlow.ObserveGiftsAsync(s, team.Rewards.ObservedGifts, ct)) return false;
            }
            else if (frame.Find(Entry + "activate_gift_search_on_assets.png") is not null || frame.Find(Entry + "activate_gift_search_off_assets.png") is not null)
            {
                if (!await SelectInitialGiftsAsync(s, team, ct)) return false;
            }
            else if (frame.Find(Entry + "enter_assets.png") is { } enter)
            {
                if (s.Elapsed < nextEnterClick)
                {
                    await s.DelayAsync(TimeSpan.FromMilliseconds(250), ct);
                    continue;
                }
                // 留出检测高度，避免单行直识把状态词旁的斜线装饰一起识别。
                var state = string.Concat((await s.ReadTextAsync(frame, ct, frame.Region(2167, 640, 2337, 740), 2))
                    .Select(t => t.Text)).Trim().ToLowerInvariant();
                if (state != "off")
                {
                    if (++infiniteChecks > 12 || infiniteClicks >= 3 && s.Elapsed >= nextInfiniteClick)
                    {
                        s.Report("mirror.entry.unknown-infinite", "多次观察后仍无法确认无尽镜牢已关闭");
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
            else if (!await ClickFirstAsync(s, frame, [Entry + "resume_assets.png", Entry + "enter_mirror_assets.png",
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

    public static async Task<bool> SelectStarsAsync(IGameSession s, MirrorTeamOptions team, CancellationToken ct)
    {
        ImageQuery[] queries = [new(Stars + "select_star_confirm_assets.png"), new(Stars + "dreaming_star_enter_assets.png"),
            new(Entry + "bleed_gift_assets.png")];
        int? remaining = null;
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
                var amount = await ReadStarNumberAsync(s, frame, new(confirm.Center.X - (int)(72 * frame.Scale),
                    confirm.Center.Y - (int)(480 * frame.Scale), (int)(192 * frame.Scale), (int)(100 * frame.Scale)), ct);
                if (amount != remaining)
                {
                    s.Report("mirror.stars.preview-mismatch", $"星光确认框剩余数值未匹配配置：应为 {remaining}，识别为 {amount}");
                    return false;
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
            if (remaining is null && frame.Find(Stars + "dreaming_star_enter_assets.png") is not null)
            {
                remaining = await ConfigureStarsAsync(s, team.StarLevels, queries, ct);
                if (remaining is null) return false;
                continue;
            }
            if (remaining is not null && !submitted && frame.Find(Stars + "dreaming_star_enter_assets.png") is { } start)
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

    private static async Task<int?> ConfigureStarsAsync(IGameSession s, int[] requested, ImageQuery[] queries, CancellationToken ct)
    {
        // 已选卡的发光填充和点击动画需要稳定后再读取。
        await s.DelayAsync(TimeSpan.FromMilliseconds(900), ct);
        var frame = await s.ObserveControlsAsync(queries, ct);
        if (frame.Find(Stars + "dreaming_star_enter_assets.png") is not { } done) return null;
        if (!HasStarGrid(frame, StarGridOrigin(frame, done), await s.ReadTextAsync(frame, ct)))
        {
            s.Report("mirror.stars.unknown-layout", "未确认星光标题及十项恩惠布局");
            return null;
        }
        var current = await ReadStarGridAsync(s, frame, done, ct);
        if (current is null)
        {
            s.Report("mirror.stars.unknown-selection", "未确认当前十项星光的选中状态及成本");
            return null;
        }
        var (levels, available) = current.Value;
        var budget = available + levels.Select((level, index) => level * StarPrices[index]).Sum();
        var cost = requested.Select((level, index) => level * StarPrices[index]).Sum();
        if (cost > budget)
        {
            s.Report("mirror.stars.insufficient", $"星光配置需要 {cost}，本次可用额度为 {budget}");
            return null;
        }
        // 先取消不符合配置的已选项，让额度恢复后再选择。
        for (var index = 0; index < levels.Length; index++)
        {
            if (levels[index] == 0 || levels[index] == requested[index]) continue;
            var after = available + levels[index] * StarPrices[index];
            if (!await ChangeStarAsync(s, queries, index, 0, available, after, ct)) return null;
            available = after;
            levels[index] = 0;
        }
        for (var index = 0; index < levels.Length; index++)
        {
            if (levels[index] == requested[index]) continue;
            var after = available - StarPrices[index];
            if (!await ChangeStarAsync(s, queries, index, 1, available, after, ct)) return null;
            available = after;
            if (requested[index] > 1)
            {
                after = available - (requested[index] - 1) * StarPrices[index];
                if (!await ChangeStarAsync(s, queries, index, requested[index], available, after, ct)) return null;
                available = after;
            }
        }
        frame = await s.ObserveControlsAsync(queries, ct);
        if (frame.Find(Stars + "dreaming_star_enter_assets.png") is not { } finalDone) return null;
        var final = await ReadStarGridAsync(s, frame, finalDone, ct);
        if (final is null || !final.Value.Levels.SequenceEqual(requested) || final.Value.Available != budget - cost)
        {
            s.Report("mirror.stars.selection-mismatch", "星光网格最终选择或剩余数值未匹配配置，不提交");
            return null;
        }
        s.Report("mirror.stars.configured", $"星光选择已核对：{requested.Count(level => level > 0)} 项，消耗 {cost}，剩余 {available}");
        return available;
    }

    private static async Task<bool> ChangeStarAsync(IGameSession s, ImageQuery[] queries, int index, int level,
        int before, int after, CancellationToken ct)
    {
        var frame = await s.ObserveControlsAsync(queries, ct);
        if (frame.Find(Stars + "dreaming_star_enter_assets.png") is not { } done
            || await ReadAvailableStarsAsync(s, frame, ct) != before) return false;
        var origin = StarGridOrigin(frame, done);
        var point = new PixelPoint(origin.X + (int)(index % 5 * 400 * frame.Scale), origin.Y + (int)(index / 5 * 480 * frame.Scale));
        if (level > 1) point = new(point.X + (int)((level == 2 ? -80 : 80) * frame.Scale), point.Y + (int)(304 * frame.Scale));
        await s.ClickAsync(frame, point, level > 1 ? "mirror.stars.level" : level == 0 ? "mirror.stars.clear" : "mirror.stars.select", ct);
        for (var attempt = 0; attempt < 4; attempt++)
        {
            await s.DelayAsync(TimeSpan.FromMilliseconds(attempt == 0 ? 900 : 300), ct);
            frame = await s.ObserveControlsAsync(queries, ct);
            if (frame.Find(Stars + "dreaming_star_enter_assets.png") is not { } observedDone) continue;
            if (await ReadAvailableStarsAsync(s, frame, ct) == after
                && StarSelected(frame, StarGridOrigin(frame, observedDone), index) == (level > 0)) return true;
        }
        s.Report("mirror.stars.unchanged", $"第 {index + 1} 项星光点击后未观察到所需变化，不继续选择或提交");
        return false;
    }

    private static async Task<(int[] Levels, int Available)?> ReadStarGridAsync(IGameSession s, GameFrame frame, VisualTarget done, CancellationToken ct)
    {
        var available = await ReadAvailableStarsAsync(s, frame, ct);
        if (available is null) return null;
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
        return (levels, available.Value);
    }

    private static async ValueTask<int?> ReadAvailableStarsAsync(IGameSession s, GameFrame frame, CancellationToken ct)
    {
        var region = frame.Region(2010, 48, 2144, 132);
        return await ReadStarNumberAsync(s, frame, region, ct) ?? await ReadStarNumberAsync(s, frame, region, ct, 1);
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
        if (edges.Any(edge => StarPixelRatio(frame, edge, (r, g, b) => Math.Min(r, Math.Min(g, b)) >= 95
            && Math.Max(r, Math.Max(g, b)) - Math.Min(r, Math.Min(g, b)) <= 30) is not >= .6)) return null;
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
        static string Normalize(string value) => string.Concat(value.Where(char.IsLetterOrDigit)).ToLowerInvariant();
        if (!text.Any(item => Normalize(item.Text).Contains("graceofthesisypheanstar"))) return false;
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
            else if (frame.Find(Entry + (team.Rewards.ObservedGifts.Length == 0 ? "activate_gift_search_on_assets.png" : "activate_gift_search_off_assets.png")) is { } observe)
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
        await s.ClickAsync(frame, frame.Find(key)!.Center, select ? "mirror.initial.gift" : "mirror.initial.clear-gift", ct);
        for (var attempt = 0; attempt < 4; attempt++)
        {
            await s.DelayAsync(TimeSpan.FromMilliseconds(attempt == 0 ? 900 : 300), ct);
            frame = await s.ObserveControlsAsync(queries, ct);
            if (frame.Find(Entry + "select_init_ego_gifts_confirm_assets.png") is not { } confirm || frame.Find(key) is not { } gift) continue;
            var observed = await InitialGiftCountAsync(s, frame, confirm, ct);
            if (observed == (count + (select ? 1 : -1), maximum) && InitialGiftSelected(frame, gift) == select) return true;
        }
        s.Report("mirror.initial.unchanged", "初始饰品点击后未观察到计数和选中状态变化，不提交");
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
