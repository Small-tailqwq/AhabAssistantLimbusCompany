using System.Text.RegularExpressions;
using AALC.Core.Automation;
using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;

namespace AALC.Runtime.Mirror;

public static class MirrorRewardFlow
{
    public const string Cards = "mirror/road_in_mir/select_encounter_reward_card_assets.png";
    public const string Gift = "mirror/road_in_mir/acquire_ego_gift_card.png";
    public const string GiftBox = "mirror/road_in_mir/acquire_ego_gift_box_assets.png";
    public const string BoxRefuse = "mirror/road_in_mir/acquire_ego_gift_refuse_assets.png";
    public const string GiftConfirm = "mirror/road_in_mir/ego_gift_get_confirm_assets.png";
    public const string GiftSelect = "mirror/road_in_mir/acquire_ego_gift_select_assets.png";
    public const string Refuse = "mirror/road_in_mir/refuse_gift_assets.png";
    public const string RefuseConfirm = "mirror/road_in_mir/refuse_gift_confirm_assets.png";
    public const string Claim = "mirror/get_reward_card/get_reward_card_confirm_assets.png";
    public const string Continue = "mirror/get_reward_card/continue_choosing_assets.png";
    public const string ObserveBurn = "mirror/road_to_mir/observe_ego_gift/observe_burn_assets.png";
    public const string ObserveBleed = "mirror/road_to_mir/observe_ego_gift/observe_bleed_assets.png";
    private static readonly string[] CardKinds = ["gain_starlight", "gain_ego", "gain_cost", "gain_cost_and_ego", "gain_ego_resource"];
    public static readonly ImageQuery[] Queries = [new(Cards), new(Gift, Multiple: true), new(GiftBox), new(BoxRefuse),
        new(GiftConfirm), new(GiftSelect, Search: SearchMode.Normal), new(Refuse), new(RefuseConfirm), new(Claim, .75), new(Continue),
        new(MirrorThemeFlow.Map), new("mirror/theme_pack/feature_theme_pack_assets.png"), new("mirror/shop/shop_coins_assets.png"),
        new("battle/turn_assets.png"), new("event/skip_assets.png"), new("event/choices_assets.png"),
        .. CardKinds.Select(kind => new ImageQuery($"mirror/get_reward_card/{kind}.png"))];

    public static IReadOnlyList<string> CardOrder(MirrorCardPreference preference) => preference switch
    {
        MirrorCardPreference.StarlightThenGift => ["gain_starlight", "gain_ego", "gain_cost", "gain_cost_and_ego", "gain_ego_resource"],
        MirrorCardPreference.StarlightThenCost => ["gain_starlight", "gain_cost", "gain_ego", "gain_cost_and_ego", "gain_ego_resource"],
        MirrorCardPreference.CostFirst => ["gain_cost", "gain_ego", "gain_cost_and_ego", "gain_ego_resource", "gain_starlight"],
        MirrorCardPreference.GiftFirst => ["gain_ego", "gain_cost", "gain_cost_and_ego", "gain_ego_resource", "gain_starlight"],
        _ => throw new ArgumentOutOfRangeException(nameof(preference))
    };

    public static async Task<(bool Handled, bool Failed)> HandleAsync(IGameSession s, GameFrame frame,
        MirrorRewardOptions options, CancellationToken ct)
    {
        if (!IsReward(frame)) return (false, false);
        var queries = Queries.Concat(new[] { options.Keyword, options.SecondaryKeyword }.Where(k => !string.IsNullOrWhiteSpace(k))
            .Distinct().Select(k => new ImageQuery($"mirror/road_in_mir/acquire_ego_gift/{k}.png", .85, true))).ToArray();
        var giftsChosen = false;
        var submitted = false;
        var refusing = false;
        var claimRetry = TimeSpan.Zero;
        var claimCount = 0;
        var cardSelectionAttempts = 0;
        var nextCardSelection = TimeSpan.Zero;
        var unreadableCardCount = 0;
        var unreadableGiftCount = 0;
        var selectionAttempts = 0;
        var previousSelectionCount = -1;
        var nextGiftInput = TimeSpan.Zero;
        var giftSubmitAttempts = 0;
        for (var attempt = 0; attempt < 45; attempt++)
        {
            ct.ThrowIfCancellationRequested();
            var previous = frame;
            frame = await s.ObserveAsync(queries, ct);
            // 背景地图可能被奖励层覆盖，先排除仍然可见的奖励控件。
            if (!IsReward(frame) && !(refusing && frame.Find(RefuseConfirm) is not null) && HasExit(frame)) return (true, false);
            if (frame.Find(GiftConfirm) is { } obtained)
            {
                s.Report("mirror.reward.obtained", "确认获得的镜牢饰品");
                await s.ClickAsync(frame, obtained.Center, "mirror.reward.confirm-obtained", ct);
                giftsChosen = false;
                submitted = true;
                cardSelectionAttempts = 0; claimCount = 0; claimRetry = TimeSpan.Zero;
                selectionAttempts = 0; previousSelectionCount = -1; giftSubmitAttempts = 0;
                nextGiftInput = TimeSpan.Zero;
            }
            else if (frame.Find(Continue) is { } more)
            {
                await s.ClickAsync(frame, more.Center, "mirror.reward.continue-choosing", ct);
                submitted = false; claimCount = 0; cardSelectionAttempts = 0;
            }
            else if (refusing && frame.Find(RefuseConfirm) is { } refusal)
            {
                await s.ClickAsync(frame, refusal.Center, "mirror.reward.confirm-refusal", ct);
                refusing = false; submitted = true;
            }
            else if (frame.Find(Cards) is not null)
            {
                giftsChosen = false;
                submitted = false;
                var count = SelectionCount(string.Concat((await s.ReadTextAsync(frame, ct,
                    frame.Region(1970, 210, 2120, 330), 2)).Select(text => text.Text)));
                if (count is null)
                {
                    if (++unreadableCardCount >= 8) return Fail(s, "无法确认奖励卡选择计数");
                }
                else if (count.Value.Selected == 0 && s.Elapsed >= nextCardSelection)
                {
                    unreadableCardCount = 0;
                    if (!CardsStable(previous, frame))
                    {
                        await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                        continue;
                    }
                    if (++cardSelectionAttempts > 3) return Fail(s, "奖励卡三次选择后计数仍未增加，未提交");
                    foreach (var kind in CardOrder(options.CardPreference))
                        if (frame.Find($"mirror/get_reward_card/{kind}.png") is { } card)
                        {
                            var name = kind switch { "gain_starlight" => "星光", "gain_ego" => "饰品", "gain_cost" => "经费",
                                "gain_cost_and_ego" => "经费与饰品", _ => "EGO 资源" };
                            s.Report(cardSelectionAttempts > 1 ? "mirror.reward.retry-card" : "mirror.reward.select-card",
                                $"选择奖励卡：{name}");
                            await s.ClickAsync(frame, card.Center, "mirror.reward.select-card", ct);
                            nextCardSelection = s.Elapsed + TimeSpan.FromSeconds(1);
                            break;
                        }
                }
                else if (count.Value.Selected == count.Value.Maximum && frame.Find(Claim) is { } claim
                    && s.Elapsed >= claimRetry)
                {
                    if (++claimCount > 3) return Fail(s, "奖励卡选中后三次确认仍未推进");
                    await s.ClickAsync(frame, claim.Center, "mirror.reward.claim-card", ct);
                    claimRetry = s.Elapsed + TimeSpan.FromSeconds(3);
                }
            }
            else if (frame.FindAll(Gift).Count > 0 && frame.Find(GiftSelect) is { } selection)
            {
                (int Selected, int Maximum)? count;
                {
                    // 只读按钮右侧计数，避免裁入半个“选择”文字。
                    var area = new PixelRect(selection.Center.X + (int)(78 * frame.Scale),
                        selection.Center.Y - (int)(58 * frame.Scale), (int)(120 * frame.Scale), (int)(120 * frame.Scale));
                    count = SelectionCount(string.Concat((await s.ReadTextAsync(frame, ct, area, 2)).Select(t => t.Text)));
                    // 多张候选先留出淡入时间，确认计数确实不存在。
                    if (count is null && frame.Find(Refuse) is not null && (frame.FindAll(Gift).Count == 1 || unreadableGiftCount >= 2))
                    {
                        // 只选一件的奖励按钮只有“选择”，没有多选页的数量分数。
                        var button = new PixelRect(selection.Center.X - (int)(100 * frame.Scale),
                            selection.Center.Y - (int)(50 * frame.Scale), (int)(300 * frame.Scale), (int)(100 * frame.Scale));
                        var label = string.Concat((await s.ReadTextAsync(frame, ct, button, 2)).Select(t => t.Text)).Trim();
                        if (label == "选择" || label.Equals("Select", StringComparison.OrdinalIgnoreCase))
                        {
                            count = (frame.FindAll(Gift).Count(gift => IsGiftSelected(frame, gift)), 1);
                        }
                    }
                }
                if (count is null)
                {
                    if (++unreadableGiftCount >= 8) return Fail(s, "无法识别饰品可选数量");
                    await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                    continue;
                }
                unreadableGiftCount = 0;
                if (s.Elapsed < nextGiftInput && (submitted || count.Value.Selected == previousSelectionCount))
                {
                    await s.DelayAsync(TimeSpan.FromMilliseconds(200), ct);
                    continue;
                }
                if (frame.FindAll(Gift).Count(gift => IsGiftSelected(frame, gift)) != count.Value.Selected)
                {
                    if (++selectionAttempts > 8) return Fail(s, "饰品选中边框与计数不一致，未继续选择");
                    await s.DelayAsync(TimeSpan.FromMilliseconds(200), ct);
                    continue;
                }
                if (count.Value.Selected == count.Value.Maximum)
                {
                    if (++giftSubmitAttempts > 3) return Fail(s, "饰品已选满，但三次提交后页面仍未退出");
                    await s.ClickAsync(frame, selection.Center, "mirror.reward.submit-gifts", ct);
                    submitted = true;
                    nextGiftInput = s.Elapsed + TimeSpan.FromSeconds(1);
                    await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                    continue;
                }
                submitted = false;
                if (previousSelectionCount != count.Value.Selected) selectionAttempts = 0;
                if (++selectionAttempts > 3) return Fail(s, "饰品选择三次后计数仍未增加，未提交");
                previousSelectionCount = count.Value.Selected;
                var candidates = new List<(VisualTarget Target, int Priority)>();
                var seenX = new List<int>();
                foreach (var gift in frame.FindAll(Gift).OrderBy(g => g.Center.X))
                {
                    if (seenX.Any(x => Math.Abs(gift.Center.X - x) < 50 * frame.Scale)) continue;
                    seenX.Add(gift.Center.X);
                    if (IsGiftSelected(frame, gift)) continue;
                    var area = new PixelRect(Math.Max(0, gift.Center.X - (int)(50 * frame.Scale)),
                        Math.Max(0, gift.Center.Y - (int)(300 * frame.Scale)), (int)(500 * frame.Scale), (int)(650 * frame.Scale));
                    if (options.AvoidWhiteGossypium)
                    {
                        var name = Normalize(string.Concat((await s.ReadTextAsync(frame, ct, area)).Select(t => t.Text)));
                        if (name.Contains("白棉花") || name.Contains("whitegossypium")) continue;
                    }
                    var priority = frame.FindAll($"mirror/road_in_mir/acquire_ego_gift/{options.Keyword}.png")
                        .Any(t => area.Contains(t.Center.X, t.Center.Y)) ? 2 : options.SecondaryKeyword is not null &&
                        frame.FindAll($"mirror/road_in_mir/acquire_ego_gift/{options.SecondaryKeyword}.png")
                        .Any(t => area.Contains(t.Center.X, t.Center.Y)) ? 1 : 0;
                    candidates.Add((gift, priority));
                }
                if (candidates.Count == 0)
                {
                    if (frame.Find(Refuse) is { } refuse)
                    {
                        await s.ClickAsync(frame, refuse.Center, "mirror.reward.refuse-gifts", ct);
                        refusing = true;
                    }
                    else return Fail(s, "可选饰品均被排除，未识别到拒绝按钮");
                }
                else
                {
                    if (candidates.Count < count.Value.Maximum - count.Value.Selected) return Fail(s, "可选饰品不足，未提交选择");
                    var chosen = candidates.OrderByDescending(g => g.Priority).First();
                    s.Report(selectionAttempts > 1 ? "mirror.reward.retry-gift" : "mirror.reward.select-gifts",
                        $"选择饰品，当前 {count.Value.Selected}/{count.Value.Maximum}");
                    await s.ClickAsync(frame, chosen.Target.Center, "mirror.reward.select-gift", ct);
                    nextGiftInput = s.Elapsed + TimeSpan.FromSeconds(1);
                    giftsChosen = true;
                }
            }
            else if (giftsChosen && !submitted && frame.Find(GiftSelect) is { } select)
            {
                await s.ClickAsync(frame, select.Center, "mirror.reward.submit-gifts", ct);
                submitted = true;
            }
            else if (!giftsChosen && frame.Find(GiftBox) is not null && frame.Find(BoxRefuse) is { } box)
            {
                submitted = false;
                await s.ClickAsync(frame, new(box.Center.X - (int)(500 * frame.Scale), box.Center.Y - (int)(500 * frame.Scale)), "mirror.reward.select-box-first", ct);
                frame = await s.ObserveControlsAsync(queries, ct);
                if (frame.Find(GiftBox) is null || frame.Find(BoxRefuse) is not { } nextBox) return Fail(s, "宝箱第二项选择页面未确认");
                await s.ClickAsync(frame, new(nextBox.Center.X, nextBox.Center.Y - (int)(500 * frame.Scale)), "mirror.reward.select-box-second", ct);
                giftsChosen = true;
            }
            await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
        }
        return Fail(s, "镜牢奖励页面未退出，停止重复操作");
    }

    public static (int Selected, int Maximum)? SelectionCount(string text)
    {
        var match = Regex.Match(text.Replace(" ", "").Replace('／', '/'), @"(?<!\d)([0-2])/([12])(?!\d)");
        if (!match.Success) return null;
        var selected = match.Groups[1].Value[0] - '0';
        var maximum = match.Groups[2].Value[0] - '0';
        return selected <= maximum ? (selected, maximum) : null;
    }

    private static string Normalize(string text) => Regex.Replace(text, @"\s+", "").ToLowerInvariant();

    private static bool CardsStable(GameFrame previous, GameFrame current)
    {
        if (previous.Find(Cards) is null) return false;
        var any = false;
        foreach (var kind in CardKinds)
        {
            var key = $"mirror/get_reward_card/{kind}.png";
            var before = previous.Find(key);
            var after = current.Find(key);
            if ((before is null) != (after is null)) return false;
            if (before is null || after is null) continue;
            if (Math.Abs(before.Center.X - after.Center.X) > 10 * current.Scale
                || Math.Abs(before.Center.Y - after.Center.Y) > 10 * current.Scale) return false;
            any = true;
        }
        return any;
    }

    public static bool IsGiftSelected(GameFrame frame, VisualTarget gift)
    {
        var left = gift.Center.X - (int)(64 * frame.Scale);
        var top = gift.Center.Y - (int)(200 * frame.Scale);
        var width = Math.Max(1, (int)(12 * frame.Scale));
        var height = Math.Max(1, (int)(300 * frame.Scale));
        if (left < 0 || top < 0 || left + width > frame.Identity.Width || top + height > frame.Identity.Height) return false;
        var gold = 0;
        for (var y = top; y < top + height; y++)
            for (var x = left; x < left + width; x++)
            {
                var offset = (y * frame.Identity.Width + x) * 4;
                var b = frame.Pixels.Bgra[offset]; var g = frame.Pixels.Bgra[offset + 1]; var r = frame.Pixels.Bgra[offset + 2];
                if (r >= 200 && g >= 100 && b < 100) gold++;
            }
        return gold > width * height * .15;
    }

    // 宝箱图标常驻；拒绝确认图标也用于编队等通用弹窗，只有本流程发起拒绝后才处理。
    public static bool IsReward(GameFrame frame) => frame.Targets.Any(t => t.Asset is Cards or Gift
        or BoxRefuse or GiftConfirm or GiftSelect or Refuse or Claim or Continue
        || CardKinds.Any(kind => t.Asset == $"mirror/get_reward_card/{kind}.png"));
    private static bool HasExit(GameFrame frame) => new[] { MirrorThemeFlow.Map, "mirror/theme_pack/feature_theme_pack_assets.png",
        "mirror/shop/shop_coins_assets.png", "battle/turn_assets.png", "event/skip_assets.png", "event/choices_assets.png" }
        .Any(asset => frame.Find(asset) is not null);
    private static (bool, bool) Fail(IGameSession s, string message)
    {
        s.Report("mirror.reward.failed", message);
        return (true, true);
    }

    private static (PixelPoint Anchor, int Step)? ObserveLayout(GameFrame frame)
    {
        var burn = frame.Find(ObserveBurn)?.Center;
        var bleed = frame.Find(ObserveBleed)?.Center;
        var step = burn is { } first && bleed is { } second
            && second.X - first.X >= 100 * frame.Scale && second.X - first.X <= 150 * frame.Scale
            ? second.X - first.X : (int)(124 * frame.Scale);
        var anchor = burn ?? (bleed is { } point ? new PixelPoint(point.X - step, point.Y) : (PixelPoint?)null);
        return anchor is { } value ? (value, step) : null;
    }

    private static bool ObserveFailed(IGameSession session, string message)
    {
        session.Report("mirror.observe.failed", message);
        return false;
    }

    public static async Task<bool> ObserveGiftsAsync(IGameSession s, IReadOnlyList<MirrorObservedGift> gifts, CancellationToken ct)
    {
        MirrorObservation.Validate(gifts);
        ImageQuery[] queries = [new(ObserveBurn), new(ObserveBleed), new(GiftConfirm), new("mirror/shop/leave_shop_confirm_assets.png"),
            new("mirror/theme_pack/feature_theme_pack_assets.png"), new(MirrorThemeFlow.Map),
            .. Enumerable.Range(1, 3).Select(i => new ImageQuery($"mirror/road_to_mir/observe_ego_gift/Level_{new string('I', i)}.png", Multiple: true))];
        var frame = await s.ObserveAsync(queries, ct);
        var chosen = 0;
        foreach (var gift in gifts)
        {
            var index = Array.FindIndex(MirrorObservation.Systems, system => system.Key == gift.Keyword);
            var layout = ObserveLayout(frame);
            if (layout is null) return ObserveFailed(s, "未识别到观测饰品页");
            var adjacent = index == MirrorObservation.Systems.Length - 1 ? index - 1 : index + 1;
            await s.ClickAsync(frame, new(layout.Value.Anchor.X + layout.Value.Step * adjacent, layout.Value.Anchor.Y), "mirror.observe.reset-category", ct);
            await s.DelayAsync(TimeSpan.FromMilliseconds(200), ct);
            frame = await s.ObserveAsync(queries, ct);
            layout = ObserveLayout(frame);
            if (layout is null) return ObserveFailed(s, "切换体系后观测页锚点消失");
            await s.ClickAsync(frame, new(layout.Value.Anchor.X + layout.Value.Step * index, layout.Value.Anchor.Y), "mirror.observe.category", ct);
            await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
            frame = await s.ObserveAsync(queries, ct);
            var area = frame.Region(158, 450, 1577, 1247);
            var levelKey = $"mirror/road_to_mir/observe_ego_gift/Level_{new string('I', gift.Level)}.png";
            VisualTarget? Level(GameFrame view) => view.FindAll(levelKey).FirstOrDefault(hit =>
                hit.Center.X < area.X + (int)(100 * view.Scale) && area.Contains(hit.Center.X, hit.Center.Y));
            var level = Level(frame);
            for (var attempt = 0; level is null && frame.Find("mirror/road_to_mir/observe_ego_gift/Level_III.png") is null && attempt < 12; attempt++)
            {
                await s.DragAsync(frame, new(area.Right - (int)(100 * frame.Scale), area.Y + (int)(100 * frame.Scale)),
                    new(area.Right - (int)(100 * frame.Scale), area.Bottom - (int)(100 * frame.Scale)),
                    TimeSpan.FromMilliseconds(750), "mirror.observe.scroll-top", ct);
                await s.DelayAsync(TimeSpan.FromMilliseconds(350), ct);
                var before = frame;
                frame = await s.ObserveAsync(queries, ct);
                level = Level(frame);
                if (before.Pixels.Bgra.AsSpan().SequenceEqual(frame.Pixels.Bgra)) break;
            }
            for (var attempt = 0; level is null && attempt < 12; attempt++)
            {
                await s.DragAsync(frame, new(area.Right - (int)(100 * frame.Scale), area.Bottom - (int)(100 * frame.Scale)),
                    new(area.Right - (int)(100 * frame.Scale), area.Y + (int)(100 * frame.Scale)),
                    TimeSpan.FromMilliseconds(750), "mirror.observe.scroll-level", ct);
                await s.DelayAsync(TimeSpan.FromMilliseconds(350), ct);
                var before = frame;
                frame = await s.ObserveAsync(queries, ct);
                level = Level(frame);
                if (before.Pixels.Bgra.AsSpan().SequenceEqual(frame.Pixels.Bgra)) break;
            }
            if (level is null) return ObserveFailed(s, "未找到观测饰品等级");
            var x = level.Center.X + (int)((gift.Column - 1) * 165 * frame.Scale);
            var y = level.Center.Y + (int)((80 + (gift.Row - 1) * 160) * frame.Scale);
            for (var attempt = 0; y > area.Bottom - (int)(100 * frame.Scale) && attempt < 12; attempt++)
            {
                var amount = Math.Min(y - area.Bottom + (int)(100 * frame.Scale), (int)(300 * frame.Scale));
                var before = frame;
                var from = new PixelPoint(area.Right - (int)(100 * frame.Scale), area.Bottom - (int)(100 * frame.Scale));
                await s.DragAsync(frame, from, new(from.X, from.Y - amount), TimeSpan.FromMilliseconds(750), "mirror.observe.scroll-gift", ct);
                await s.DelayAsync(TimeSpan.FromMilliseconds(350), ct);
                frame = await s.ObserveAsync(queries, ct);
                if (Level(frame) is { } observed)
                {
                    x = observed.Center.X + (int)((gift.Column - 1) * 165 * frame.Scale);
                    y = observed.Center.Y + (int)((80 + (gift.Row - 1) * 160) * frame.Scale);
                }
                else
                {
                    var moved = MirrorObservationScroll.MeasureUpward(before.Pixels, frame.Pixels, area, amount + (int)(120 * frame.Scale));
                    if (moved is null or 0) return ObserveFailed(s, "观测列表滚动后未能定位目标，未点击饰品");
                    y -= moved.Value;
                }
            }
            if (!area.Contains(x, y) || y > area.Bottom - (int)(100 * frame.Scale))
                return ObserveFailed(s, "观测饰品位置未进入可见区域");
            var countArea = frame.Region(2035, 1104, 2352, 1187);
            var countText = string.Concat((await s.ReadTextAsync(frame, ct, countArea, 2)).Select(item => item.Text));
            var count = MirrorObservation.SelectionCount(countText);
            var emptyCount = chosen == 0 && Regex.IsMatch(countText.Replace(" ", "").Replace('／', '/'), @"(?<!\d)0/(?!\d)");
            if (count is { } existingCount ? existingCount.Selected != chosen || chosen >= existingCount.Maximum : !emptyCount)
                return ObserveFailed(s, "未能核对观测饰品的选择数量，未继续选择");
            s.Report("mirror.observe.select", $"选择观测饰品：{MirrorObservation.Describe(gift)}");
            await s.ClickAsync(frame, new(x, y), "mirror.observe.gift", ct);
            var changed = false;
            for (var attempt = 0; attempt < 6; attempt++)
            {
                await s.DelayAsync(TimeSpan.FromMilliseconds(350), ct);
                frame = await s.ObserveAsync(queries, ct);
                count = MirrorObservation.SelectionCount(string.Concat((await s.ReadTextAsync(frame, ct, countArea, 2)).Select(item => item.Text)));
                if (count is { } value && value.Selected == chosen + 1) { changed = true; break; }
            }
            if (!changed) return ObserveFailed(s, "观测饰品点击后数量未增加，未提交");
            chosen++;
        }
        var selected = gifts.Count == 0;
        var requested = false;
        for (var attempt = 0; attempt < 20; attempt++)
        {
            frame = await s.ObserveAsync(queries, ct);
            if (frame.Find(ObserveBurn) is null && frame.Find(ObserveBleed) is null &&
                (frame.Find(MirrorThemeFlow.Map) is not null || frame.Find("mirror/theme_pack/feature_theme_pack_assets.png") is not null)) return true;
            if (frame.Find(GiftConfirm) is { } confirm)
            {
                await s.ClickAsync(frame, confirm.Center, "mirror.observe.confirm-gift", ct);
                selected = true; requested = false;
            }
            else if (frame.Find("mirror/shop/leave_shop_confirm_assets.png") is { } yes)
            {
                await s.ClickAsync(frame, yes.Center, "mirror.observe.confirm-selection", ct);
                selected = true; requested = false;
            }
            else if (!requested)
            {
                var area = selected ? frame.Region(1741, 1108, 1949, 1189) : frame.Region(2035, 1104, 2352, 1187);
                var text = string.Concat((await s.ReadTextAsync(frame, ct, area, 2)).Select(t => t.Text)).ToLowerInvariant();
                if (selected ? text.Contains("拒绝") || text.Contains("reject") : text.Contains("选择") || text.Contains("select"))
                {
                    await s.ClickAsync(frame, new(area.X + area.Width / 2, area.Y + area.Height / 2), selected ? "mirror.observe.reject-rest" : "mirror.observe.submit", ct);
                    requested = true;
                }
            }
            await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
        }
        s.Report("mirror.observe.failed", "观测饰品选择后未确认退出");
        return false;
    }
}
