using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;

namespace AALC.Runtime.Mirror;

public static partial class MirrorShopFlow
{
    private sealed partial class ShopRun
    {
        private async Task<bool> ReplaceSkillsAsync()
        {
            if (options.SkillSinners.Length == 0) return true;
            const string ordinary = "mirror/shop/skill_replacement_assets.png";
            const string first = "mirror/shop/super_shop_skill_replacement_1_assets.png";
            const string second = "mirror/shop/super_shop_skill_replacement_2_assets.png";
            const string search = "mirror/shop/ID_skill_search_assets.png";
            const string coins = "mirror/shop/skill_replacement_coins.png";
            const string confirm = "mirror/shop/skill_replacement_confirm_assets.png";
            const string searchReturn = "mirror/shop/ID_skill_replace_search_return_assets.png";
            string Purchased(int index) => $"mirror/shop/ID_skill_replace_{index}_purchased_assets.png";
            ImageQuery[] queries = [new(ordinary), new(first), new(second), new(search), new(coins, Multiple: true),
                new(confirm), new(searchReturn), new("mirror/shop/super_shop_assets.png"),
                new(Purchased(0)), new(Purchased(1)), new(Purchased(2))];
            string[] names = ["YiSang", "Faust", "DonQuixote", "Ryoshu", "Meursault", "HongLu", "Heathcliff", "Ishmael", "Rodion", "Sinclair", "Outis", "Gregor"];
            string[] chinese = ["李箱", "浮士", "堂吉", "良秀", "默尔", "鸿璐", "希斯", "以实", "罗佳", "辛克", "提斯", "格里"];
            var initial = await ObserveAsync(queries);
            if (initial is null) return false;
            var super = initial.Find("mirror/shop/super_shop_assets.png") is not null;
            var offers = super ? new[] { (first, 1), (second, 2) } : [(ordinary, 0)];
            foreach (var (asset, index) in offers)
            {
                var frame = await ObserveAsync(queries);
                if (frame is null) return false;
                if (frame.Find(Purchased(index)) is not null || frame.Find(asset) is not { } offer) continue;
                var region = new PixelRect(offer.Center.X - (int)(150 * frame.Scale), offer.Center.Y + (int)(20 * frame.Scale),
                    (int)(300 * frame.Scale), (int)(80 * frame.Scale));
                var text = await s.ReadTextAsync(frame, ct, region);
                if (!options.SkillSinners.Any(number => text.Any(item => item.Text.Contains(chinese[number - 1])
                    || item.Text.Replace(" ", "").Contains(names[number - 1], StringComparison.OrdinalIgnoreCase)))) continue;
                var funds = await FundsAsync(frame);
                if (funds is null || funds == 0) { s.Report("mirror.shop.skill-skipped", "经费未知或不足，跳过技能替换"); return true; }
                var target = new PixelPoint(offer.Center.X, offer.Center.Y - (int)(100 * frame.Scale));
                await s.ClickAsync(frame, target, "mirror.shop.skill-offer", ct);
                if (!await CompleteSkillAsync(queries, Purchased(index), coins, confirm)) return false;
                if (!await ReturnToShopAsync()) return false;
            }
            if (!super) return true;
            int[] positions = [198, 353, 510, 663, 818, 968, 1121, 1277, 1428, 1581, 1737, 1889];
            foreach (var sinner in options.SkillSinners.Distinct())
            {
                var frame = await ObserveAsync(queries);
                if (frame is null) return false;
                if (frame.Find(Purchased(0)) is not null || frame.Find(search) is not { } open) break;
                var funds = await FundsAsync(frame);
                if (funds is null || funds == 0)
                {
                    s.Report("mirror.shop.skill-skipped", "经费未知或不足，跳过指定罪人技能替换");
                    return true;
                }
                await s.ClickAsync(frame, open.Center, "mirror.shop.skill-search", ct);
                await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
                frame = await ObserveAsync(queries);
                if (frame?.Find(searchReturn) is null) return false;
                await s.ClickAsync(frame, frame.Point(positions[sinner - 1], 1299), "mirror.shop.skill-sinner", ct);
                await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
                frame = await ObserveAsync(queries);
                if (frame is null) return false;
                if (frame.FindAll(coins).Count != 3)
                {
                    if (frame.Find(searchReturn) is not { } back) return false;
                    await s.ClickAsync(frame, back.Center, "mirror.shop.skill-search-return", ct);
                    continue;
                }
                return await CompleteSkillAsync(queries, Purchased(0), coins, confirm) && await ReturnToShopAsync();
            }
            return await ReturnToShopAsync();
        }

        private async Task<bool> CompleteSkillAsync(ImageQuery[] queries, string purchasedAsset, string coinsAsset, string confirmAsset)
        {
            GameFrame? frame = null;
            VisualTarget[] choices = [];
            for (var attempt = 0; attempt < 8; attempt++)
            {
                await s.DelayAsync(TimeSpan.FromMilliseconds(300), ct);
                frame = await ObserveAsync(queries);
                if (frame is null) return false;
                choices = frame.FindAll(coinsAsset).OrderBy(hit => hit.Center.X).ToArray();
                if (choices.Length == 3) break;
            }
            if (frame is null || choices.Length != 3) { s.Report("mirror.shop.skill-unrecognized", "技能替换没有三个可确认选项"); return false; }
            var index = options.Skill switch { MirrorShopSkill.OneToThree => 2, MirrorShopSkill.TwoToThree => 1, _ => 0 };
            await s.ClickAsync(frame, choices[index].Center, "mirror.shop.skill-select", ct);
            await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
            frame = await ObserveAsync(queries);
            if (frame?.Find(confirmAsset) is not { } confirm) return false;
            var funds = await FundsAsync(frame);
            if (funds is null || funds == 0) return false;
            string Signature(IReadOnlyList<RecognizedText> text) => string.Join('|', text.Select(item => item.Text)
                .Where(value => value.Any(char.IsLetter) && !value.Any(char.IsAsciiDigit)).Order());
            var signature = Signature(await s.ReadTextAsync(frame, ct));
            var committed = frame.Identity.Id;
            await s.ClickAsync(frame, confirm.Center, "mirror.shop.skill-confirm", ct);
            var secondSent = false;
            for (var attempt = 0; attempt < 12; attempt++)
            {
                await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                frame = await ObserveAsync(queries);
                if (frame is null) return false;
                if (frame.Identity.Id <= committed) continue;
                var after = await FundsAsync(frame);
                var nextConfirm = frame.Find(confirmAsset);
                if (nextConfirm is null && (frame.Find(purchasedAsset) is not null || after < funds))
                {
                    s.Report("mirror.shop.skill-verified", "已确认技能替换结果");
                    return true;
                }
                if (!secondSent && nextConfirm is not null && after == funds && signature.Length > 0)
                {
                    var nextSignature = Signature(await s.ReadTextAsync(frame, ct));
                    if (nextSignature.Length > 0 && nextSignature != signature)
                    {
                        await s.ClickAsync(frame, nextConfirm.Center, "mirror.shop.skill-payment-confirm", ct);
                        secondSent = true;
                    }
                }
            }
            s.Report("mirror.shop.skill-unverified", "技能替换后未观察到购买标记或经费变化，停止重复确认");
            return false;
        }
    }
}
