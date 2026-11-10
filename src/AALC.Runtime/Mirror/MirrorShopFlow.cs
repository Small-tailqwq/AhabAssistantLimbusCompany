using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;
using System.Text.RegularExpressions;

namespace AALC.Runtime.Mirror;

public static partial class MirrorShopFlow
{
    private const string Coins = "mirror/shop/shop_coins_assets.png";
    private const string GiftPopup = "mirror/road_in_mir/ego_gift_get_confirm_assets.png";
    private const string Map = "mirror/road_in_mir/legend_assets.png";
    private const string Return = "mirror/shop/return_assets.png";
    private const string HealReturn = "mirror/shop/heal_sinner/heal_sinner_return_assets.png";
    private const string HealAll = "mirror/shop/heal_sinner/heal_all_sinner_assets.png";
    private const string Purchase = "mirror/shop/purchase_assets.png";
    private const string PowerUp = "mirror/shop/power_up_assets.png";
    private const string PowerUpConfirm = "mirror/shop/power_up_confirm_assets.png";
    private const string Confirm = "mirror/shop/enhance_and_fuse_and_sell_confirm_assets.png";
    private static readonly string[] PendingConfirmations = [PowerUpConfirm,
        "mirror/shop/refresh_keyword_confirm_assets.png", "mirror/shop/skill_replacement_confirm_assets.png"];
    private static readonly ImageQuery[] Common = [new(Coins), new(GiftPopup), new(Map), new(Return), new(HealReturn), new(HealAll),
        new(Purchase), new(PowerUp), new("mirror/shop/ID_skill_replace_search_return_assets.png"),
        new("mirror/shop/leave_assets.png"), new("mirror/shop/leave_shop_confirm_assets.png"),
        .. PendingConfirmations.Select(asset => new ImageQuery(asset))];

    public static Task<bool> RunAsync(IGameSession session, MirrorShopOptions options, string keyword, int floor,
        CancellationToken cancellationToken)
    {
        MirrorShopRules.Validate(options, keyword, floor);
        return new ShopRun(session, options, keyword, cancellationToken).RunAsync(floor);
    }

    public static async ValueTask<bool> IsHealingResultAsync(IGameSession session, GameFrame frame, CancellationToken ct)
    {
        if (frame.Find("mirror/shop/leave_assets.png") is null) return false;
        var text = await session.ReadTextAsync(frame, ct);
        return text.Any(item => item.Text.Contains("治疗罪人") && item.Bounds.Y < 200 * frame.Scale)
            && text.Any(item => item.Text.Contains("全体罪人") && item.Text.Contains("恢复"));
    }

    public static async ValueTask<bool> IsHealingChoicesAsync(IGameSession session, GameFrame frame, CancellationToken ct)
    {
        if (frame.Find(HealReturn) is null || frame.Find(HealAll) is null) return false;
        var text = await session.ReadTextAsync(frame, ct);
        return text.Any(item => item.Text.Contains("治疗罪人") && item.Bounds.Y < 200 * frame.Scale)
            && text.Any(item => item.Text.Contains("全体罪人") && item.Text.Contains("恢复"));
    }

    public static async ValueTask<PixelPoint?> EnhancementExitAsync(IGameSession session, GameFrame frame, CancellationToken ct)
    {
        var confirmation = frame.Find(PowerUpConfirm) is not null;
        if (!confirmation && frame.Find(PowerUp) is null) return null;
        var text = await session.ReadTextAsync(frame, ct);
        if (!text.Any(item => item.Text.Contains("强化") && item.Text.Contains("饰品"))) return null;
        var close = text.FirstOrDefault(item => item.Text.Contains(confirmation ? "取消" : "关闭") && item.Bounds.X < frame.Identity.Width / 2
            && item.Bounds.Y > frame.Identity.Height / 2);
        return close is null ? null : new(close.Bounds.X + close.Bounds.Width / 2, close.Bounds.Y + close.Bounds.Height / 2);
    }

    private sealed partial class ShopRun(IGameSession s, MirrorShopOptions options, string keyword, CancellationToken ct)
    {
        private readonly string[] keywords = new[] { keyword }.Concat(options.Keywords).Distinct().ToArray();
        private bool healed;

        public async Task<bool> RunAsync(int floor)
        {
            ct.ThrowIfCancellationRequested();
            s.Report("mirror.shop.begin", floor > 0 ? $"处理第 {floor} 层商店" : "处理镜牢商店");
            if (MirrorShopRules.SkipFloor(options, floor)) return await LeaveAsync();
            if (!await ReturnToShopAsync()) return false;
            if (options.Skill != MirrorShopSkill.None && !await ReplaceSkillsAsync()) return false;
            if (options.Heal && !healed && !await HealAsync()) return false;
            if (options.Inventory == MirrorShopInventory.SellListedKeywords && !await SellAsync()) return false;
            if (options.Purchases != MirrorShopPurchases.None && !await BuyAsync()) return false;
            if (options.Inventory == MirrorShopInventory.KeywordRecipes && !await FuseRecipesAsync()) return false;
            if (options.Enhance && !await EnhanceAsync()) return false;
            return await LeaveAsync();
        }

        private ValueTask<GameFrame> ObserveRawAsync(IEnumerable<ImageQuery>? extra = null) =>
            s.ObserveAsync(extra is null ? Common : Common.Concat(extra).Distinct().ToArray(), ct);

        private async Task<GameFrame?> ObserveAsync(IEnumerable<ImageQuery>? extra = null)
        {
            for (var attempt = 0; attempt < 8; attempt++)
            {
                ct.ThrowIfCancellationRequested();
                var frame = await ObserveRawAsync(extra);
                if (frame.Find(GiftPopup) is not { } popup) return frame;
                await s.ClickAsync(frame, popup.Center, "mirror.shop.dismiss-gift", ct);
                await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
            }
            s.Report("mirror.shop.popup-stalled", "获得饰品弹窗持续存在，停止商店操作");
            return null;
        }

        private async Task<int?> FundsAsync(GameFrame frame, bool healing = false)
        {
            if (frame.Find(GiftPopup) is not null) return null;
            var enhancement = frame.Find(PowerUp) is not null || frame.Find(PowerUpConfirm) is not null;
            var region = healing ? frame.Region(2232, 193, 2391, 277)
                : enhancement ? frame.Region(1880, 150, 2230, 258) : frame.Region(1142, 227, 1315, 321);
            foreach (var scale in new[] { 1, 2 })
            {
                var text = await s.ReadTextAsync(frame, ct, region, scale);
                if (enhancement && EnhancementAmounts(text).Skip(1).Any())
                    text = await s.ReadTextAsync(frame, ct, frame.Region(1880, 150, 2076, 258), scale);
                var funds = ReadFunds(text, enhancement);
                if (funds is not null) return funds;
            }
            // 小区域 OCR 偶尔把三位数拆开（治疗后 987 读成 8、87 与 9），全图 OCR 同帧仍正确；取中心落在余额框内的文字。
            var inside = (await s.ReadTextAsync(frame, ct)).Where(item =>
                item.Bounds.X + item.Bounds.Width / 2 is var x && x >= region.X && x < region.Right
                && item.Bounds.Y + item.Bounds.Height / 2 is var y && y >= region.Y && y < region.Bottom).ToArray();
            return ReadFunds(inside, enhancement);
        }

        private static int? ReadFunds(IReadOnlyList<RecognizedText> text, bool enhancement)
        {
            if (!enhancement) return MirrorShopRules.ReadFunds(text.Select(item => item.Text));
            var amount = EnhancementAmounts(text).FirstOrDefault();
            return amount is null ? null : MirrorShopRules.ReadFunds([amount]);
        }

        private static IEnumerable<string> EnhancementAmounts(IReadOnlyList<RecognizedText> text) =>
            text.OrderBy(item => item.Bounds.X)
                .Select(item => Regex.Match(item.Text, @"^\s*[0-9OoDQIlZSGh,]+").Value)
                .Where(value => value.Any(char.IsAsciiDigit));

        private async Task<bool> ReturnToShopAsync()
        {
            var subpageExitSent = false;
            var enhancementCancelSent = false;
            for (var attempt = 0; attempt < 10; attempt++)
            {
                var frame = await ObserveAsync();
                if (frame is null) return false;
                if (frame.Find(PowerUpConfirm) is not null && await EnhancementExitAsync(s, frame, ct) is { } cancel)
                {
                    healed = true;
                    if (!enhancementCancelSent)
                    {
                        await s.ClickAsync(frame, cancel, "mirror.shop.cancel-enhance", ct);
                        enhancementCancelSent = true;
                    }
                }
                else if (PendingConfirmations.Any(asset => frame.Find(asset) is not null))
                {
                    s.Report("mirror.shop.pending-confirmation", "商店仍有未完成确认，停止切换页面");
                    return false;
                }
                else if (await EnhancementExitAsync(s, frame, ct) is { } close)
                {
                    healed = true;
                    if (!subpageExitSent)
                    {
                        await s.ClickAsync(frame, close, "mirror.shop.close-enhance", ct);
                        subpageExitSent = true;
                    }
                }
                else if (await IsHealingResultAsync(s, frame, ct))
                {
                    healed = true;
                    if (!subpageExitSent)
                    {
                        await s.ClickAsync(frame, frame.Find("mirror/shop/leave_assets.png")!.Center, "mirror.shop.heal-return", ct);
                        subpageExitSent = true;
                    }
                }
                else if (await IsHealingChoicesAsync(s, frame, ct))
                {
                    healed = true;
                    if (!subpageExitSent)
                    {
                        await s.ClickAsync(frame, frame.Find(HealReturn)!.Center, "mirror.shop.return", ct);
                        subpageExitSent = true;
                    }
                }
                else if ((frame.Find(HealReturn) ?? frame.Find("mirror/shop/ID_skill_replace_search_return_assets.png") ?? frame.Find(Return)) is { } back)
                    await s.ClickAsync(frame, back.Center, "mirror.shop.return", ct);
                else if (frame.Find(Purchase) is not null)
                    await s.ClickAsync(frame, new(1, 1), "mirror.shop.close-detail", ct);
                else if (frame.Find(Coins) is not null) return true;
                else if (frame.Find(Map) is not null) return false;
                await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
            }
            s.Report("mirror.shop.return-failed", "未确认返回商店主页面");
            return false;
        }

        private async Task<bool> LeaveAsync()
        {
            var nextLeaveClick = TimeSpan.Zero;
            var nextConfirmClick = TimeSpan.Zero;
            for (var attempt = 0; attempt < 20; attempt++)
            {
                var frame = await ObserveAsync();
                if (frame is null) return false;
                if (PendingConfirmations.Any(asset => frame.Find(asset) is not null)) return false;
                if (frame.Find("mirror/shop/leave_shop_confirm_assets.png") is { } confirm)
                {
                    if (s.Elapsed >= nextConfirmClick)
                    {
                        await s.ClickAsync(frame, confirm.Center, "mirror.shop.leave-confirm", ct);
                        nextConfirmClick = s.Elapsed + TimeSpan.FromSeconds(3);
                        nextLeaveClick = nextConfirmClick;
                    }
                }
                else if (frame.Find(Map) is not null) { s.Report("mirror.shop.finished", "商店操作结束，已返回地图"); return true; }
                else if (s.Elapsed >= nextLeaveClick)
                {
                    if (frame.Find(HealReturn) is { } healBack)
                        await s.ClickAsync(frame, healBack.Center, "mirror.shop.heal-return", ct);
                    else if (frame.Find(Return) is { } back)
                        await s.ClickAsync(frame, back.Center, "mirror.shop.return", ct);
                    else if (frame.Find("mirror/shop/leave_assets.png") is { } leave)
                    {
                        await s.ClickAsync(frame, leave.Center, "mirror.shop.leave", ct);
                        nextLeaveClick = s.Elapsed + TimeSpan.FromSeconds(2);
                    }
                }
                await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
            }
            s.Report("mirror.shop.leave-failed", "未观察到商店退出后的地图");
            return false;
        }

        private async Task<bool> WaitForFundsChangeAsync(int before, bool increase, long committedFrame,
            string operation, bool healing = false)
        {
            int? observed = null;
            for (var attempt = 0; attempt < 12; attempt++)
            {
                await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                var frame = await ObserveAsync();
                if (frame is null) return false;
                if (frame.Identity.Id <= committedFrame) continue;
                var funds = await FundsAsync(frame, healing && frame.Find(Coins) is null);
                if (funds is { } after && (increase ? after > before : after < before) && (!healing || after == before - 100)
                    && !PendingConfirmations.Any(asset => frame.Find(asset) is not null))
                {
                    if (observed == after)
                    {
                        s.Report("mirror.shop.verified", $"{operation}已确认，经费 {before} → {after}");
                        return true;
                    }
                    observed = after;
                }
                else observed = null;
            }
            s.Report("mirror.shop.unverified", $"{operation}后未确认经费变化，停止重复确认");
            return false;
        }

        private async Task<bool> HealAsync()
        {
            const string entry = "mirror/shop/heal_sinner/heal_sinner_assets.png";
            const string all = HealAll;
            var frame = await ObserveAsync([new(entry), new(all)]);
            if (frame is null) return false;
            if (frame.Find(entry) is not { } button) return true;
            var money = await FundsAsync(frame);
            if (money is null || money < 100)
            {
                s.Report("mirror.shop.heal-skipped", "经费未知或不足 100，跳过治疗");
                return true;
            }
            await s.ClickAsync(frame, button.Center, "mirror.shop.heal-open", ct);
            for (var attempt = 0; attempt < 8; attempt++)
            {
                await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
                frame = await ObserveAsync([new(all)]);
                if (frame is null) return false;
                if (frame.Find(all) is not { } heal) continue;
                if (HealingUnavailable(frame, heal))
                {
                    s.Report("mirror.shop.heal-skipped", "全体治疗不可用，返回商店");
                    return await ReturnToShopAsync();
                }
                money = await FundsAsync(frame, true);
                if (money is null || money < 100)
                {
                    s.Report("mirror.shop.heal-skipped", "治疗页经费未知或不足，返回商店");
                    return await ReturnToShopAsync();
                }
                await s.ClickAsync(frame, heal.Center, "mirror.shop.heal-all", ct);
                return await WaitForFundsChangeAsync(money.Value, false, frame.Identity.Id, "全体治疗", true)
                    && await ReturnToShopAsync();
            }
            s.Report("mirror.shop.heal-unavailable", "未识别到全体治疗按钮，返回商店");
            return await ReturnToShopAsync();
        }

        private static bool HealingUnavailable(GameFrame frame, VisualTarget heal)
        {
            var left = heal.Center.X + (int)(55 * frame.Scale);
            var right = heal.Center.X + (int)(125 * frame.Scale);
            var top = heal.Center.Y - (int)(122 * frame.Scale);
            var bottom = heal.Center.Y - (int)(68 * frame.Scale);
            if (left < 0 || top < 0 || right > frame.Identity.Width || bottom > frame.Identity.Height
                || left >= right || top >= bottom || frame.Pixels.Bgra.Length != frame.Identity.Width * frame.Identity.Height * 4) return false;
            var red = 0;
            var orange = 0;
            for (var y = top; y < bottom; y++)
            for (var x = left; x < right; x++)
            {
                var offset = (y * frame.Identity.Width + x) * 4;
                var b = frame.Pixels.Bgra[offset]; var g = frame.Pixels.Bgra[offset + 1]; var r = frame.Pixels.Bgra[offset + 2];
                if (r > 100 && r > g * 2.2 && g < 85 && r > b * 1.8) red++;
                if (r > 120 && g > 65 && r > g * 1.2 && g > b * 1.6) orange++;
            }
            var area = (right - left) * (bottom - top);
            return red > area * .1 && orange < area * .01;
        }

        private async Task<bool> BuyAsync()
        {
            var gifts = new List<string>();
            if (options.Purchases == MirrorShopPurchases.EssentialsAndKeyword)
                gifts.AddRange(new[] { "carmilla", "homeward", "lithograph", "phlebotomy_pack", "piece_of_relationship" }
                    .Select(name => $"mirror/shop/must_purchase/{name}.png"));
            gifts.AddRange(keywords.Select(value => $"mirror/shop/enhance_gifts/shop_{value}.png"));
            ImageQuery[] queries = [.. gifts.Select(asset => new ImageQuery(asset, .85, true)), new(Purchase),
                new("mirror/shop/refresh_assets.png"), new("mirror/shop/refresh_keyword_assets.png"),
                new("mirror/shop/refresh_keyword_confirm_assets.png"),
                .. keywords.Select(value => new ImageQuery($"mirror/shop/keyword/keyword_{value}.png"))];
            var normal = 0;
            var targeted = 0;
            var blocked = new HashSet<string>();
            for (var transaction = 0; transaction < 50; transaction++)
            {
                var frame = await ObserveAsync(queries);
                if (frame is null) return false;
                var money = await FundsAsync(frame);
                if (money is null)
                {
                    s.Report("mirror.shop.funds-unknown", "无法确认经费，停止购买与刷新");
                    return true;
                }
                var gift = gifts.Where(asset => !blocked.Contains(asset))
                    .SelectMany(frame.FindAll).OrderBy(hit => gifts.IndexOf(hit.Asset))
                    .ThenBy(hit => hit.Center.Y).ThenBy(hit => hit.Center.X).FirstOrDefault();
                if (gift is not null && money > 0)
                {
                    await s.ClickAsync(frame, gift.Center, "mirror.shop.select-gift", ct);
                    await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
                    frame = await ObserveAsync(queries);
                    if (frame is null) return false;
                    var text = await s.ReadTextAsync(frame, ct);
                    if (keywords.Contains("bleed") && text.Any(item => item.Text.Contains("白棉花")
                        || item.Text.Contains("gossypium", StringComparison.OrdinalIgnoreCase)))
                    {
                        blocked.Add(gift.Asset);
                        if (!await ReturnToShopAsync()) return false;
                        continue;
                    }
                    if (frame.Find(Purchase) is not { } buy)
                    {
                        blocked.Add(gift.Asset);
                        if (!await ReturnToShopAsync()) return false;
                        continue;
                    }
                    var before = await FundsAsync(frame);
                    if (before is null) { s.Report("mirror.shop.funds-unknown", "商品确认前经费未知，停止购买"); return await ReturnToShopAsync(); }
                    await s.ClickAsync(frame, buy.Center, "mirror.shop.purchase", ct);
                    if (!await WaitForFundsChangeAsync(before.Value, false, frame.Identity.Id, "购买饰品")) return false;
                    if (!await ReturnToShopAsync()) return false;
                    continue;
                }
                if (targeted < options.KeywordRefreshLimit && MirrorShopRules.CanRefresh(money, 300, options.ReserveFunds)
                    && frame.Find("mirror/shop/refresh_keyword_assets.png") is { } refreshKeyword)
                {
                    await s.ClickAsync(frame, refreshKeyword.Center, "mirror.shop.refresh-keyword-open", ct);
                    var success = false;
                    var keywordChosen = false;
                    for (var attempt = 0; attempt < 8; attempt++)
                    {
                        await s.DelayAsync(TimeSpan.FromMilliseconds(300), ct);
                        frame = await ObserveAsync(queries);
                        if (frame is null) return false;
                        if (keywordChosen && frame.Find("mirror/shop/refresh_keyword_confirm_assets.png") is { } confirm)
                        {
                            var before = await FundsAsync(frame);
                            if (!MirrorShopRules.CanRefresh(before, 300, options.ReserveFunds)) return await ReturnToShopAsync();
                            await s.ClickAsync(frame, confirm.Center, "mirror.shop.refresh-keyword-confirm", ct);
                            if (!await WaitForFundsChangeAsync(before!.Value, false, frame.Identity.Id, "关键词刷新")) return false;
                            success = true;
                            break;
                        }
                        var selectedKeyword = keywords[targeted % keywords.Length];
                        if (!keywordChosen && frame.Find($"mirror/shop/keyword/keyword_{selectedKeyword}.png") is { } choice)
                        {
                            await s.ClickAsync(frame, choice.Center, "mirror.shop.refresh-keyword-select", ct);
                            keywordChosen = true;
                        }
                    }
                    if (!success) return false;
                    targeted++;
                    blocked.Clear();
                    continue;
                }
                if (normal < options.NormalRefreshLimit && MirrorShopRules.CanRefresh(money, 200, options.ReserveFunds)
                    && frame.Find("mirror/shop/refresh_assets.png") is { } refresh)
                {
                    await s.ClickAsync(frame, refresh.Center, "mirror.shop.refresh", ct);
                    if (!await WaitForFundsChangeAsync(money.Value, false, frame.Identity.Id, "普通刷新")) return false;
                    normal++;
                    blocked.Clear();
                    continue;
                }
                return true;
            }
            s.Report("mirror.shop.purchase-limit", "本次商店交易达到上限");
            return false;
        }

        private async Task<bool> EnhanceAsync()
        {
            const string entry = "mirror/shop/enhance_gifts_assets.png";
            const string power = "mirror/shop/power_up_assets.png";
            const string confirm = "mirror/shop/power_up_confirm_assets.png";
            var assets = keywords.SelectMany(value => new[] { $"mirror/shop/level_IV_gifts/{value}_level_IV.png",
                $"mirror/shop/enhance_gifts/big_{value}.png", $"mirror/shop/enhance_gifts/{value}.png" }).ToArray();
            ImageQuery[] queries = [new(entry), new(power), new(confirm), .. assets.Select(asset => new ImageQuery(asset, Multiple: true))];
            var frame = await ObserveAsync(queries);
            if (frame?.Find(entry) is not { } open) return frame is not null;
            await s.ClickAsync(frame, open.Center, "mirror.shop.enhance-open", ct);
            var finished = new HashSet<(int, int)>();
            var unknownFunds = 0;
            for (var item = 0; item < 30; item++)
            {
                await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
                frame = await ObserveAsync(queries);
                if (frame is null) return false;
                var target = assets.SelectMany(frame.FindAll).Where(hit =>
                        MirrorShopRules.InEnhanceGrid(hit.Center, frame.Identity.Width, frame.Identity.Height)
                        && !finished.Contains((hit.Center.X / 15, hit.Center.Y / 15)))
                    .OrderBy(hit => Array.IndexOf(assets, hit.Asset)).ThenBy(hit => hit.Center.Y).ThenBy(hit => hit.Center.X).FirstOrDefault();
                if (target is null) return await ReturnToShopAsync();
                var money = await FundsAsync(frame);
                if (money is null && unknownFunds++ < 2)
                {
                    await s.DelayAsync(TimeSpan.FromSeconds(1), ct);
                    continue;
                }
                if (money is null || money == 0)
                {
                    s.Report("mirror.shop.enhance-skipped", "经费未知或不足，跳过升级");
                    return await ReturnToShopAsync();
                }
                unknownFunds = 0;
                await s.ClickAsync(frame, target.Center, "mirror.shop.enhance-select", ct);
                for (var level = 0; level < 2; level++)
                {
                    await s.DelayAsync(TimeSpan.FromMilliseconds(300), ct);
                    frame = await ObserveAsync(queries);
                    if (frame is null) return false;
                    if (frame.Find(power) is not { } button) break;
                    await s.ClickAsync(frame, button.Center, "mirror.shop.enhance-level", ct);
                    await s.DelayAsync(TimeSpan.FromMilliseconds(300), ct);
                    frame = await ObserveAsync(queries);
                    if (frame is null) return false;
                    if (frame.Find(confirm) is not { } confirmation) break;
                    money = await FundsAsync(frame);
                    if (money is null || money == 0)
                    {
                        s.Report("mirror.shop.enhance-unverified", "升级确认页经费未知或不足，停止升级");
                        return false;
                    }
                    await s.ClickAsync(frame, confirmation.Center, "mirror.shop.enhance-confirm", ct);
                    if (!await WaitForFundsChangeAsync(money.Value, false, frame.Identity.Id, "升级饰品")) return false;
                }
                finished.Add((target.Center.X / 15, target.Center.Y / 15));
            }
            s.Report("mirror.shop.enhance-limit", "本次升级扫描达到上限");
            return false;
        }
    }
}
