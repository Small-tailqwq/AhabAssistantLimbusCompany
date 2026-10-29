using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;

namespace AALC.Runtime.Mirror;

public static partial class MirrorShopFlow
{
    private sealed partial class ShopRun
    {
        private async Task<bool> SellAsync()
        {
            const string entry = "mirror/shop/sell_gift_assets.png";
            const string sellConfirm = "mirror/shop/sell_gift_confirm_assets.png";
            const string scroll = "mirror/shop/gifts_list_block.png";
            var assets = options.SellKeywords.Except(keywords).Distinct()
                .Select(value => $"mirror/shop/enhance_gifts/{value}.png").ToArray();
            if (assets.Length == 0) return true;
            var protectedAssets = keywords.Select(value => $"mirror/shop/level_IV_gifts/{value}_level_IV.png")
                .Append("mirror/shop/level_IV_gifts/lunar_memory.png").ToArray();
            ImageQuery[] queries = [new(entry), new(sellConfirm), new(Confirm), new(scroll),
                .. assets.Concat(protectedAssets).Select(asset => new ImageQuery(asset, Multiple: true))];
            var frame = await ObserveAsync(queries);
            if (frame?.Find(entry) is not { } open) return frame is not null;
            await s.ClickAsync(frame, open.Center, "mirror.shop.sell-open", ct);
            var modeConfirmed = false;
            var scrolled = false;
            for (var transaction = 0; transaction < 30; transaction++)
            {
                await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
                frame = await ObserveAsync(queries);
                if (frame is null) return false;
                if (!modeConfirmed && frame.Find(sellConfirm) is { } mode)
                {
                    await s.ClickAsync(frame, mode.Center, "mirror.shop.sell-mode-confirm", ct);
                    modeConfirmed = true;
                    continue;
                }
                var protectedTargets = protectedAssets.SelectMany(frame.FindAll).ToArray();
                var target = assets.SelectMany(frame.FindAll)
                    .Where(hit => !protectedTargets.Any(protect => Math.Abs(protect.Center.X - hit.Center.X) < 50 * frame.Scale
                        && Math.Abs(protect.Center.Y - hit.Center.Y) < 50 * frame.Scale))
                    .OrderBy(hit => hit.Center.Y).ThenBy(hit => hit.Center.X).FirstOrDefault();
                if (target is null)
                {
                    if (!scrolled && frame.Find(scroll) is { } bar)
                    {
                        await s.DragAsync(frame, bar.Center, new(bar.Center.X,
                            Math.Clamp(bar.Center.Y + (int)(500 * frame.Scale), 0, frame.Identity.Height - 1)),
                            TimeSpan.FromSeconds(1), "mirror.shop.sell-scroll", ct);
                        scrolled = true;
                        continue;
                    }
                    return await ReturnToShopAsync();
                }
                var before = await FundsAsync(frame);
                if (before is null) { s.Report("mirror.shop.sell-skipped", "经费未知，跳过出售"); return await ReturnToShopAsync(); }
                await s.ClickAsync(frame, target.Center, "mirror.shop.sell-select", ct);
                await s.DelayAsync(TimeSpan.FromMilliseconds(300), ct);
                frame = await ObserveAsync(queries);
                if (frame?.Find(Confirm) is not { } confirm) return false;
                await s.ClickAsync(frame, confirm.Center, "mirror.shop.sell-confirm", ct);
                var verified = false;
                var secondarySent = false;
                for (var attempt = 0; attempt < 12; attempt++)
                {
                    await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
                    frame = await ObserveAsync(queries);
                    if (frame is null) return false;
                    if (!secondarySent && frame.Find(sellConfirm) is { } secondary)
                    {
                        await s.ClickAsync(frame, secondary.Center, "mirror.shop.sell-payment-confirm", ct);
                        secondarySent = true;
                        continue;
                    }
                    var after = await FundsAsync(frame);
                    if (after > before)
                    {
                        s.Report("mirror.shop.sell-verified", $"出售已确认，经费 {before} → {after}");
                        verified = true;
                        break;
                    }
                }
                if (!verified) { s.Report("mirror.shop.sell-unverified", "出售后经费未增加，停止重复出售"); return false; }
            }
            return false;
        }

        private async Task<bool> FuseRecipesAsync()
        {
            const string entry = "mirror/shop/fuse_gift_assets.png";
            const string selectKeyword = "mirror/shop/fuse_to_select_keyword_assets.png";
            const string keywordConfirm = "mirror/shop/fuse_gift_confirm_assets.png";
            const string label = "mirror/shop/fuse_label.png";
            const string again = "mirror/shop/fuse_ego_gift_assets.png";
            foreach (var system in keywords)
            {
                var recipes = MirrorShopRules.Recipes(system);
                if (recipes.Count == 0) { s.Report("mirror.shop.recipe-unavailable", $"{system} 没有已知公式模板"); continue; }
                var keywordAsset = $"mirror/shop/keyword/keyword_{system}.png";
                ImageQuery[] queries = [new(entry), new(selectKeyword), new(keywordAsset), new(keywordConfirm),
                    new(label, .85, true), new(Confirm), new(again), .. recipes.Select(asset => new ImageQuery(asset))];
                if (!await ReturnToShopAsync()) return false;
                var opened = false;
                var keywordChosen = false;
                for (var attempt = 0; attempt < 12; attempt++)
                {
                    var frame = await ObserveAsync(queries);
                    if (frame is null) return false;
                    if (frame.FindAll(label).Count >= 2) { opened = true; break; }
                    if (keywordChosen && frame.Find(keywordConfirm) is { } confirm)
                        await s.ClickAsync(frame, confirm.Center, "mirror.shop.fuse-keyword-confirm", ct);
                    else if (!keywordChosen && frame.Find(keywordAsset) is { } choice)
                    {
                        await s.ClickAsync(frame, choice.Center, "mirror.shop.fuse-keyword", ct);
                        keywordChosen = true;
                    }
                    else if (frame.Find(selectKeyword) is { } select)
                        await s.ClickAsync(frame, select.Center, "mirror.shop.fuse-keyword-open", ct);
                    else if (frame.Find(entry) is { } open)
                        await s.ClickAsync(frame, open.Center, "mirror.shop.fuse-open", ct);
                    await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
                }
                if (!opened) return false;
                for (var transaction = 0; transaction < 15; transaction++)
                {
                    var frame = await ObserveAsync(queries);
                    if (frame is null) return false;
                    var labels = frame.FindAll(label).OrderBy(hit => hit.Center.Y).ToArray();
                    if (labels.Length < 2) return false;
                    var divider = labels[^1].Center.Y;
                    var recipe = recipes.Select(frame.Find).FirstOrDefault(hit => hit is not null && hit.Center.Y < divider);
                    if (recipe is null) break;
                    var funds = await FundsAsync(frame);
                    if (funds is null) { s.Report("mirror.shop.fuse-skipped", "经费未知，跳过公式合成"); break; }
                    await s.ClickAsync(frame, recipe.Center, "mirror.shop.recipe-select", ct);
                    await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
                    frame = await ObserveAsync(queries);
                    if (frame?.Find(Confirm) is not { } confirmation) return false;
                    funds = await FundsAsync(frame);
                    if (funds is null)
                    {
                        s.Report("mirror.shop.fuse-skipped", "合成确认页经费未知，停止合成");
                        return false;
                    }
                    var committed = frame.Identity.Id;
                    await s.ClickAsync(frame, confirmation.Center, "mirror.shop.recipe-confirm", ct);
                    var verified = false;
                    for (var attempt = 0; attempt < 12; attempt++)
                    {
                        await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                        frame = await ObserveRawAsync(queries);
                        if (frame.Identity.Id > committed && frame.Find(GiftPopup) is { } gift)
                        {
                            await s.ClickAsync(frame, gift.Center, "mirror.shop.recipe-received", ct);
                            s.Report("mirror.shop.recipe-verified", "已观察到公式合成结果");
                            verified = true;
                            break;
                        }
                    }
                    if (!verified) { s.Report("mirror.shop.recipe-unverified", "合成确认后未出现结果，停止重复确认"); return false; }
                    frame = await ObserveAsync(queries);
                    if (frame is null) return false;
                    if (frame.Find(again) is { } next)
                        await s.ClickAsync(frame, next.Center, "mirror.shop.recipe-again", ct);
                }
            }
            return await ReturnToShopAsync();
        }
    }
}
