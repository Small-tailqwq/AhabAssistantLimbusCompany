using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;
using AALC.Runtime.Mirror;
using Xunit;

namespace AALC.Core.Tests;

public sealed class MirrorShopTests
{
    private const string Coins = "mirror/shop/shop_coins_assets.png";
    private const string Leave = "mirror/shop/leave_assets.png";
    private const string Map = "mirror/road_in_mir/legend_assets.png";
    private const string Back = "mirror/shop/return_assets.png";
    private const string Popup = "mirror/road_in_mir/ego_gift_get_confirm_assets.png";
    private const string Gift = "mirror/shop/enhance_gifts/shop_burn.png";
    private const string Purchase = "mirror/shop/purchase_assets.png";
    private const string Confirm = "mirror/shop/enhance_and_fuse_and_sell_confirm_assets.png";
    private static MirrorShopOptions Options => new() { Purchases = MirrorShopPurchases.None, Heal = false, Enhance = false };

    [Fact]
    public async Task AllFloorsSkippedCanResumeInsideShopWithoutReadingFloor()
    {
        var session = new Session([Step(null, "mirror.shop.leave", Coins, Leave, Purchase), Exit()]);
        Assert.True(await MirrorShopFlow.RunAsync(session, new() { SkipFloors = [1, 2, 3, 4, 5] }, "burn", 0, default));
        Assert.Equal(["mirror.shop.leave"], session.Actions.Select(action => action.Rule));
    }

    [Fact]
    public void PartialFloorSkipStillRequiresKnownFloor()
    {
        Assert.Throws<ArgumentException>(() => MirrorShopRules.Validate(Options with { SkipFloors = [1, 2, 3, 4] }, "burn", 0));
    }

    [Theory]
    [InlineData("G10", 610)]
    [InlineData("1,250", 1250)]
    [InlineData("unknown", null)]
    public void FundsParserHandlesDocumentedOcrConfusions(string text, int? expected) =>
        Assert.Equal(expected, MirrorShopRules.ReadFunds([text]));

    [Fact]
    public void ConflictingAmountsAreUnknownAndCannotAuthorizeRefresh()
    {
        Assert.Null(MirrorShopRules.ReadFunds(["500", "600"]));
        Assert.False(MirrorShopRules.CanRefresh(null, 200, 0));
        Assert.False(MirrorShopRules.CanRefresh(799, 300, 500));
        Assert.True(MirrorShopRules.CanRefresh(800, 300, 500));
    }

    [Theory]
    [InlineData(1920, 1080, 1066, 570, true)]
    [InlineData(1920, 1080, 1825, 580, false)]
    [InlineData(2560, 1440, 1500, 700, true)]
    [InlineData(2560, 1440, 2433, 772, false)]
    public void UpgradeScanUsesTheCalibratedInventoryRegion(int width, int height, int x, int y, bool expected) =>
        Assert.Equal(expected, MirrorShopRules.InEnhanceGrid(new(x, y), width, height));

    [Fact]
    public async Task UnknownFundsCannotBuyOrRefresh()
    {
        var session = new Session([Step(null, "mirror.shop.leave", Coins, Leave, Gift, "mirror/shop/refresh_assets.png"), Exit()]);
        Assert.True(await MirrorShopFlow.RunAsync(session, Options with
            { Purchases = MirrorShopPurchases.Keyword, NormalRefreshLimit = 1 }, "burn", 1, default));
        Assert.Equal(["mirror.shop.leave"], session.Actions.Select(action => action.Rule));
        Assert.Contains("mirror.shop.funds-unknown", session.Reports);
    }

    [Fact]
    public async Task GiftPopupIsDismissedBeforeReadingFundsOrBuying()
    {
        var session = new Session([
            Step(500, "mirror.shop.dismiss-gift", Popup, Coins, Gift),
            Step(500, "mirror.shop.select-gift", Coins, Gift, Leave),
            Step(500, "mirror.shop.purchase", Coins, Purchase),
            Step(400, "mirror.shop.dismiss-gift", Popup, Coins),
            Step(400, "mirror.shop.leave", Coins, Leave), Exit()]);
        Assert.True(await MirrorShopFlow.RunAsync(session, Options with { Purchases = MirrorShopPurchases.Keyword }, "burn", 1, default));
        Assert.Equal("mirror.shop.dismiss-gift", session.Actions[0].Rule);
        Assert.Single(session.Actions, action => action.Rule == "mirror.shop.purchase");
        Assert.True(session.Complete);
    }

    [Fact]
    public async Task UnchangedPurchaseBalanceStopsWithoutSendingAnotherPayment()
    {
        var session = new Session([
            Step(500, "mirror.shop.select-gift", Coins, Gift, Leave),
            Step(500, "mirror.shop.purchase", Coins, Purchase), Step(500, null, Coins, Purchase)]);
        Assert.False(await MirrorShopFlow.RunAsync(session, Options with { Purchases = MirrorShopPurchases.Keyword }, "burn", 1, default));
        Assert.Single(session.Actions, action => action.Rule == "mirror.shop.purchase");
        Assert.DoesNotContain(session.Actions, action => action.Rule == "mirror.shop.leave");
    }

    [Fact]
    public async Task RefreshPreservesReservedFundsAndCannotBypassTheKeywordBudget()
    {
        var session = new Session([
            Step(799, "mirror.shop.refresh", Coins, Leave, "mirror/shop/refresh_assets.png", "mirror/shop/refresh_keyword_assets.png"),
            Step(599, "mirror.shop.leave", Coins, Leave, "mirror/shop/refresh_assets.png", "mirror/shop/refresh_keyword_assets.png"), Exit()]);
        Assert.True(await MirrorShopFlow.RunAsync(session, Options with { Purchases = MirrorShopPurchases.Keyword,
            NormalRefreshLimit = 1, KeywordRefreshLimit = 1, ReserveFunds = 500 }, "burn", 1, default));
        Assert.Equal(["mirror.shop.refresh", "mirror.shop.leave"], session.Actions.Select(action => action.Rule));
    }

    [Fact]
    public async Task KeywordIsSelectedBeforeItsConfirmationAndAStalledPaymentIsNotRepeated()
    {
        const string entry = "mirror/shop/refresh_keyword_assets.png";
        const string keyword = "mirror/shop/keyword/keyword_burn.png";
        const string confirm = "mirror/shop/refresh_keyword_confirm_assets.png";
        var session = new Session([
            Step(800, "mirror.shop.refresh-keyword-open", Coins, entry, Leave),
            Step(800, "mirror.shop.refresh-keyword-select", Coins, keyword, confirm),
            Step(800, "mirror.shop.refresh-keyword-confirm", Coins, keyword, confirm),
            Step(800, null, Coins, confirm)]);
        Assert.False(await MirrorShopFlow.RunAsync(session, Options with
            { Purchases = MirrorShopPurchases.Keyword, KeywordRefreshLimit = 1 }, "burn", 1, default));
        Assert.Single(session.Actions, action => action.Rule == "mirror.shop.refresh-keyword-confirm");
    }

    [Fact]
    public async Task HealingIsOnlyPaidOnceAndReturnsThroughTheHealingBackButton()
    {
        const string entry = "mirror/shop/heal_sinner/heal_sinner_assets.png";
        const string all = "mirror/shop/heal_sinner/heal_all_sinner_assets.png";
        const string back = "mirror/shop/heal_sinner/heal_sinner_return_assets.png";
        var session = new Session([
            Step(500, "mirror.shop.heal-open", Coins, Leave, entry),
            Step(500, "mirror.shop.heal-all", all, back),
            Step(400, "mirror.shop.return", back),
            Step(400, "mirror.shop.leave", Coins, Leave), Exit()]);
        Assert.True(await MirrorShopFlow.RunAsync(session, Options with { Heal = true }, "burn", 1, default));
        Assert.Single(session.Actions, action => action.Rule == "mirror.shop.heal-all");
        Assert.True(session.Complete);
    }

    [Fact]
    public async Task AKeywordGiftUpgradeRequiresANewLowerBalance()
    {
        const string entry = "mirror/shop/enhance_gifts_assets.png";
        const string badge = "mirror/shop/enhance_gifts/burn.png";
        const string power = "mirror/shop/power_up_assets.png";
        const string confirm = "mirror/shop/power_up_confirm_assets.png";
        var gift = Target(badge, 1500, 600);
        var session = new Session([
            Step(500, "mirror.shop.enhance-open", Coins, Leave, entry),
            new(500, "mirror.shop.enhance-select", [gift, Target(Back)]),
            Step(500, "mirror.shop.enhance-level", power, Back),
            Step(500, "mirror.shop.enhance-confirm", confirm),
            new(400, "mirror.shop.return", [gift, Target(Back)]),
            Step(400, "mirror.shop.leave", Coins, Leave), Exit()]);
        Assert.True(await MirrorShopFlow.RunAsync(session, Options with { Enhance = true }, "burn", 1, default));
        Assert.Single(session.Actions, action => action.Rule == "mirror.shop.enhance-confirm");
        Assert.True(session.Complete);
    }

    [Fact]
    public async Task SaleOnlyCommitsTheExplicitlyListedKeywordAndVerifiesTheIncome()
    {
        const string entry = "mirror/shop/sell_gift_assets.png";
        const string confirm = "mirror/shop/sell_gift_confirm_assets.png";
        var session = new Session([
            Step(500, "mirror.shop.sell-open", Coins, Leave, entry),
            Step(500, "mirror.shop.sell-select", "mirror/shop/enhance_gifts/charge.png", Back),
            Step(500, "mirror.shop.sell-confirm", Confirm),
            Step(500, "mirror.shop.sell-payment-confirm", confirm),
            Step(600, "mirror.shop.return", Back),
            Step(600, "mirror.shop.leave", Coins, Leave), Exit()]);
        Assert.True(await MirrorShopFlow.RunAsync(session, Options with
            { Inventory = MirrorShopInventory.SellListedKeywords, SellKeywords = ["charge", "burn"] }, "burn", 1, default));
        Assert.True(session.Complete);
        Assert.Single(session.Actions, action => action.Rule == "mirror.shop.sell-select");
    }

    [Fact]
    public async Task LunarMemoryCannotBeSelectedForSaleEvenIfAnotherBadgeMatchesIt()
    {
        const string entry = "mirror/shop/sell_gift_assets.png";
        var session = new Session([
            Step(500, "mirror.shop.sell-open", Coins, Leave, entry),
            Step(500, "mirror.shop.return", Back, "mirror/shop/enhance_gifts/charge.png", "mirror/shop/level_IV_gifts/lunar_memory.png"),
            Step(500, "mirror.shop.leave", Coins, Leave), Exit()]);
        Assert.True(await MirrorShopFlow.RunAsync(session, Options with
            { Inventory = MirrorShopInventory.SellListedKeywords, SellKeywords = ["charge"] }, "burn", 1, default));
        Assert.DoesNotContain(session.Actions, action => action.Rule == "mirror.shop.sell-select");
    }

    [Fact]
    public async Task AVisibleKnownRecipeNeedsAnObservedGiftResultBeforeAnotherFusion()
    {
        const string entry = "mirror/shop/fuse_gift_assets.png";
        const string keyword = "mirror/shop/keyword/keyword_burn.png";
        const string keywordConfirm = "mirror/shop/fuse_gift_confirm_assets.png";
        const string label = "mirror/shop/fuse_label.png";
        var labels = new[] { Target(label, 1400, 500), Target(label, 1400, 1000) };
        var session = new Session([
            Step(500, "mirror.shop.fuse-open", Coins, Leave, entry),
            Step(500, "mirror.shop.fuse-keyword", keyword),
            Step(500, "mirror.shop.fuse-keyword-confirm", keywordConfirm),
            new(500, "mirror.shop.recipe-select", [.. labels, Target("mirror/shop/fusion_result/burn_1.png", 1500, 600)]),
            Step(500, "mirror.shop.recipe-confirm", Confirm),
            Step(500, "mirror.shop.recipe-received", Popup),
            new(500, "mirror.shop.return", [.. labels, Target(Back)]),
            Step(500, "mirror.shop.leave", Coins, Leave), Exit()]);
        Assert.True(await MirrorShopFlow.RunAsync(session, Options with { Inventory = MirrorShopInventory.KeywordRecipes }, "burn", 1, default));
        Assert.Single(session.Actions, action => action.Rule == "mirror.shop.recipe-confirm");
        Assert.Contains("mirror.shop.recipe-verified", session.Reports);
    }

    [Theory]
    [InlineData(MirrorShopSkill.OneToThree, 1300)]
    [InlineData(MirrorShopSkill.TwoToThree, 1100)]
    [InlineData(MirrorShopSkill.OneToTwo, 900)]
    public async Task SkillReplacementSelectsTheRequestedConversionAndVerifiesPurchase(MirrorShopSkill conversion, int expectedX)
    {
        const string offer = "mirror/shop/skill_replacement_assets.png";
        const string coins = "mirror/shop/skill_replacement_coins.png";
        const string confirm = "mirror/shop/skill_replacement_confirm_assets.png";
        var session = new Session([
            new(500, "mirror.shop.skill-offer", [Target(Coins), Target(Leave), Target(offer)], ["李箱"]),
            new(500, "mirror.shop.skill-select", [Target(coins, 900), Target(coins, 1100), Target(coins, 1300)]),
            Step(500, "mirror.shop.skill-confirm", confirm),
            Step(400, "mirror.shop.leave", Coins, Leave, "mirror/shop/ID_skill_replace_0_purchased_assets.png"), Exit()]);
        Assert.True(await MirrorShopFlow.RunAsync(session, Options with { Skill = conversion }, "burn", 1, default));
        Assert.Equal(expectedX, session.Actions.Single(action => action.Rule == "mirror.shop.skill-select").Target.X);
        Assert.Single(session.Actions, action => action.Rule == "mirror.shop.skill-confirm");
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ASecondSkillConfirmationRequiresAnObservedDifferentDialog(bool changed)
    {
        const string offer = "mirror/shop/skill_replacement_assets.png";
        const string coins = "mirror/shop/skill_replacement_coins.png";
        const string confirm = "mirror/shop/skill_replacement_confirm_assets.png";
        var states = new List<State>
        {
            new(500, "mirror.shop.skill-offer", [Target(Coins), Target(Leave), Target(offer)], ["李箱"]),
            new(500, "mirror.shop.skill-select", [Target(coins, 900), Target(coins, 1100), Target(coins, 1300)]),
            new(500, "mirror.shop.skill-confirm", [Target(confirm)], ["选择替换技能"]),
            new(500, changed ? "mirror.shop.skill-payment-confirm" : null, [Target(confirm)],
                [changed ? "确认消费经费" : "选择替换技能"])
        };
        if (changed)
        {
            states.Add(Step(400, "mirror.shop.leave", Coins, Leave, "mirror/shop/ID_skill_replace_0_purchased_assets.png"));
            states.Add(Exit());
        }
        var session = new Session(states);
        Assert.Equal(changed, await MirrorShopFlow.RunAsync(session, Options with { Skill = MirrorShopSkill.OneToThree }, "burn", 1, default));
        Assert.Equal(changed ? 1 : 0, session.Actions.Count(action => action.Rule == "mirror.shop.skill-payment-confirm"));
        Assert.Single(session.Actions, action => action.Rule == "mirror.shop.skill-confirm");
    }

    [Fact]
    public async Task SuperShopSearchUsesTheExplicitSinnerNumberBeforeChoosingTheConversion()
    {
        const string search = "mirror/shop/ID_skill_search_assets.png";
        const string back = "mirror/shop/ID_skill_replace_search_return_assets.png";
        const string coins = "mirror/shop/skill_replacement_coins.png";
        const string confirm = "mirror/shop/skill_replacement_confirm_assets.png";
        var session = new Session([
            Step(500, "mirror.shop.skill-search", Coins, Leave, search, "mirror/shop/super_shop_assets.png"),
            Step(500, "mirror.shop.skill-sinner", back),
            new(500, "mirror.shop.skill-select", [Target(coins, 900), Target(coins, 1100), Target(coins, 1300)]),
            Step(500, "mirror.shop.skill-confirm", confirm),
            Step(400, "mirror.shop.leave", Coins, Leave, "mirror/shop/ID_skill_replace_0_purchased_assets.png"), Exit()]);
        Assert.True(await MirrorShopFlow.RunAsync(session, Options with
            { Skill = MirrorShopSkill.OneToThree, SkillSinners = [2] }, "burn", 1, default));
        Assert.Equal(new PixelPoint(353, 1299), session.Actions.Single(action => action.Rule == "mirror.shop.skill-sinner").Target);
        Assert.Contains("mirror.shop.skill-verified", session.Reports);
    }

    [Fact]
    public async Task CancellationBeforeEntryCannotSendAnyShopInput()
    {
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        var session = new Session([Step(500, null, Coins, Leave)]);
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => MirrorShopFlow.RunAsync(session, Options, "burn", 1, cancellation.Token));
        Assert.Empty(session.Actions);
    }

    private static VisualTarget Target(string asset, int x = 1000, int y = 600) => new(asset, new(x, y), new(x - 20, y - 10, 40, 20), 1);
    private static State Step(int? funds, string? action, params string[] assets) => new(funds, action, assets.Select(asset => Target(asset)).ToArray());
    private static State Exit() => Step(0, null, Map);
    private sealed record State(int? Funds, string? Action, VisualTarget[] Targets, string[]? Text = null);

    private sealed class Session(IReadOnlyList<State> states) : IGameSession
    {
        private int index;
        private long frameId;
        public TimeSpan Elapsed { get; private set; }
        public int Observations { get; private set; }
        public List<(string Rule, PixelPoint Target)> Actions { get; } = [];
        public List<string> Reports { get; } = [];
        public bool Complete => index == states.Count - 1;
        public ValueTask<GameFrame> ObserveAsync(IReadOnlyList<ImageQuery> queries, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            Observations++;
            var targets = states[index].Targets.Where(target => queries.Any(query => query.Asset == target.Asset)).ToArray();
            return ValueTask.FromResult(new GameFrame(new(new(++frameId, 2560, 1440, 1, 0), []), targets));
        }
        public ValueTask<IReadOnlyList<RecognizedText>> ReadTextAsync(GameFrame frame, CancellationToken ct, PixelRect? region = null, int scale = 1, TextPreprocessing preprocessing = TextPreprocessing.None)
        {
            ct.ThrowIfCancellationRequested();
            Assert.DoesNotContain(states[index].Targets, target => target.Asset == Popup);
            var isFunds = region is { } box && (box.X == 1142 || box.X == 1880 || box.X == 2232);
            string[] texts = isFunds ? states[index].Funds is { } value ? [value.ToString()] : [] : states[index].Text ?? [];
            return ValueTask.FromResult<IReadOnlyList<RecognizedText>>(texts.Select(text => new RecognizedText(text, 1, new(10, 10, 40, 20))).ToArray());
        }
        public ValueTask ClickAsync(GameFrame frame, PixelPoint target, string rule, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            Assert.Equal(frameId, frame.Identity.Id);
            Assert.Equal(states[index].Action, rule);
            Actions.Add((rule, target));
            Assert.True(index < states.Count - 1, "最后一帧不应再执行动作");
            index++;
            return ValueTask.CompletedTask;
        }
        public ValueTask KeyAsync(GameFrame frame, GameKey key, string rule, CancellationToken ct) => throw new NotSupportedException();
        public ValueTask DragAsync(GameFrame frame, PixelPoint from, PixelPoint to, TimeSpan duration, string rule, CancellationToken ct) =>
            throw new NotSupportedException();
        public ValueTask DelayAsync(TimeSpan duration, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            Elapsed += duration;
            return ValueTask.CompletedTask;
        }
        public void Report(string rule, string message) => Reports.Add(rule);
    }
}
