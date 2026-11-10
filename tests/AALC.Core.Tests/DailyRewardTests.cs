using AALC.Core.Features.Daily;
using AALC.Core.Features.Mail;
using AALC.Runtime.Daily;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;
using Xunit;

namespace AALC.Core.Tests;

public sealed class DailyRewardTests
{
    private const string Cancel = "enkephalin/enkephalin_cancel_assets.png";
    private const string Disabled = "enkephalin/all_in_disabled_assets.png";
    private const string Confirm = "enkephalin/enkephalin_confirm_assets.png";
    private const string Use = "enkephalin/use_lunacy_assets.png";
    private const string All = "enkephalin/all_in_assets.png";
    private const string Missions = "pass/pass_missions_assets.png";
    private const string Weekly = "pass/weekly_assets.png";
    private const string RewardConfirm = "mail/get_mail_prize_confirm.png";

    [Theory]
    [InlineData("05:20", true)]
    [InlineData("O5:2O", true)]
    [InlineData("06:10", false)]
    [InlineData("05:60", false)]
    [InlineData("unknown", false)]
    public void GrandetRequiresParsedMinuteAndSecondFields(string text, bool ready) =>
        Assert.Equal(ready, DailyRewardRules.GrandetReady(text));

    [Theory]
    [InlineData(26, 1)]
    [InlineData(52, 2)]
    [InlineData(78, 3)]
    [InlineData(104, 4)]
    [InlineData(999, 0)]
    public void RefillConfigurationLimitsTheDailyPriceTier(int price, int tier) =>
        Assert.Equal(tier, DailyRewardRules.RefillTierForPrice(price));

    [Fact]
    public async Task DisabledModuleExchangeIsSuccessfulWithoutConfirming()
    {
        var session = new Session([Frame(1, false, Cancel, Disabled), Frame(2, false, Cancel, Disabled), Frame(3, false)]);
        Assert.True(await EnkephalinFlow.ConvertAsync(session, default));
        Assert.Equal(["daily.modules.close"], session.Clicks);
    }

    [Fact]
    public async Task ModuleConsumptionNeedsANewDisabledFrame()
    {
        var session = new Session([
            Frame(1, true, Cancel, All), Frame(2, true, Cancel, All, Confirm),
            Frame(3, false, Cancel, Disabled), Frame(4, false, Cancel, Disabled), Frame(5, false)]);
        Assert.True(await EnkephalinFlow.ConvertAsync(session, default));
        Assert.Equal(["daily.modules.select-all", "daily.modules.confirm", "daily.modules.close"], session.Clicks);
    }

    [Fact]
    public async Task OnePreselectedModuleConfirmsOnceAndRequiresTwentyStaminaDeduction()
    {
        var session = new Session([SingleModuleFrame(1, true), SingleModuleFrame(2, false),
            SingleModuleFrame(3, false), Frame(4, false)]);
        session.TextReader = (frame, region) => region?.Y == 310
            ? [new("1", .99, new(681, 318, 11, 24))]
            : [new(frame.Identity.Id == 1 ? "24/36" : "4/136", .99, new(575, 400, 114, 57))];
        Assert.True(await EnkephalinFlow.ConvertAsync(session, default));
        Assert.Equal(["daily.modules.confirm", "daily.modules.close"], session.Clicks);
        Assert.Contains("daily.modules.single-selected", session.Reports);
        Assert.Contains("daily.modules.converted", session.Reports);
    }

    [Theory]
    [InlineData("24/136")]
    [InlineData("14/136")]
    [InlineData("unreadable")]
    public async Task OneModuleDoesNotRepeatConfirmationWithoutTheExpectedDeduction(string after)
    {
        var session = new Session([SingleModuleFrame(1, true), SingleModuleFrame(2, false)]);
        session.TextReader = (frame, region) => region?.Y == 310
            ? [new("1", .99, new(681, 318, 11, 24))]
            : [new(frame.Identity.Id == 1 ? "24/136" : after, .99, new(575, 400, 114, 57))];
        Assert.False(await EnkephalinFlow.ConvertAsync(session, default));
        Assert.Single(session.Clicks);
        Assert.Equal("daily.modules.confirm", session.Clicks[0]);
        Assert.Contains("daily.modules.unverified", session.Reports);
    }

    [Fact]
    public async Task DisabledConfirmationCannotConsumeTheDefaultOneSelection()
    {
        var session = new Session([SingleModuleFrame(1, false), SingleModuleFrame(2, false), Frame(3, false)]);
        session.TextReader = (_, _) => throw new InvalidOperationException("灰态确认按钮不应进入数量识别");
        Assert.True(await EnkephalinFlow.ConvertAsync(session, default));
        Assert.Equal(["daily.modules.close"], session.Clicks);
        Assert.Contains("daily.modules.unavailable", session.Reports);
    }

    [Fact]
    public async Task UnchangedModulePanelCannotRepeatConsumptionConfirmation()
    {
        var session = new Session([Frame(1, true, Cancel, All), Frame(2, true, Cancel, All, Confirm)]);
        Assert.False(await EnkephalinFlow.ConvertAsync(session, default));
        Assert.Single(session.Clicks, rule => rule == "daily.modules.confirm");
        Assert.Contains("daily.modules.unverified", session.Reports);
    }

    [Fact]
    public async Task AlreadyPurchasedFirstTierOnlyAllowsOneMorePurchaseForTierTwo()
    {
        var p52 = "enkephalin/lunacy_spend_52_assets.png";
        var p78 = "enkephalin/lunacy_spend_78_assets.png";
        var session = new Session([
            Frame(1, false, Cancel, Disabled, Use), Frame(2, false, Cancel, Disabled, Use),
            Frame(3, false, Cancel, Confirm, p52), Frame(4, false, Cancel, Confirm, p78),
            Frame(5, false, Cancel, Confirm, p78), Frame(6, false),
            Frame(7, false, Cancel, Disabled), Frame(8, false, Cancel, Disabled), Frame(9, false)]);
        Assert.True(await EnkephalinFlow.RefillAsync(session, 2, false, default));
        Assert.Single(session.Clicks, rule => rule == "daily.refill.confirm");
    }

    [Fact]
    public async Task UnchangedPriceCannotRepeatLunacyConfirmation()
    {
        var session = new Session([
            Frame(1, false, Cancel, Disabled, Use), Frame(2, false, Cancel, Disabled, Use),
            Frame(3, false, Cancel, Confirm, "enkephalin/lunacy_spend_26_assets.png")]);
        Assert.False(await EnkephalinFlow.RefillAsync(session, 2, false, default));
        Assert.Single(session.Clicks, rule => rule == "daily.refill.confirm");
        Assert.Contains("daily.refill.unverified", session.Reports);
    }

    [Theory]
    [InlineData("104", true)]
    [InlineData("78", false)]
    [InlineData("unreadable", false)]
    public async Task ThirdTierRequiresObservedPriceAdvanceBeforeFinalModuleConversion(string nextPrice, bool completed)
    {
        var session = new Session([
            Frame(1, false, Cancel, Disabled, Use), Frame(2, false, Cancel, Disabled, Use),
            Frame(3, false, Cancel, Confirm, "enkephalin/lunacy_spend_78_assets.png"),
            Frame(4, false, Cancel, Confirm), Frame(5, false, Cancel, Confirm), Frame(6, false),
            Frame(7, false, Cancel, Disabled), Frame(8, false, Cancel, Disabled), Frame(9, false)]);
        session.TextReader = (_, region) =>
        {
            Assert.Equal(new PixelRect(565, 255, 95, 75), region);
            return [new(nextPrice, .994, new(590, 290, 30, 20))];
        };
        Assert.Equal(completed, await EnkephalinFlow.RefillAsync(session, 3, false, default));
        Assert.Single(session.Clicks, rule => rule == "daily.refill.confirm");
        Assert.Equal(completed ? 2 : 1, session.Reports.Count(rule => rule == "daily.modules.begin"));
        if (!completed) Assert.Contains("daily.refill.unverified", session.Reports);
    }

    [Fact]
    public async Task ZeroRefillTierDoesNotOpenOrConsumeAnything()
    {
        var session = new Session([]);
        Assert.True(await EnkephalinFlow.RefillAsync(session, 0, true, default));
        Assert.Empty(session.Clicks);
        Assert.Equal(0, session.Observations);
    }

    [Fact]
    public async Task NoMissionBadgesSkipOcrAndTabClicks()
    {
        var session = new Session([PassFrame(false, false)]);
        session.TextReader = (_, _) => throw new InvalidOperationException("没有领取提示时无需 OCR");
        Assert.True(await PassRewardFlow.RunAsync(session, true, false, false, default));
        Assert.DoesNotContain("daily.pass.claim-row", session.Clicks);
        Assert.Empty(session.Clicks);
    }

    [Fact]
    public async Task AClaimableRowMustChangeAfterOneClick()
    {
        var session = new Session([PassFrame(true, false)]);
        session.Text = [new("1/1", .99, new(670, 230, 20, 12))];
        Assert.False(await PassRewardFlow.RunAsync(session, true, false, false, default));
        Assert.Single(session.Clicks, rule => rule == "daily.pass.claim-row");
        Assert.Contains("daily.pass.claim-unverified", session.Reports);
    }

    [Fact]
    public async Task DisabledSeasonIsNotVisitedWhenItsBadgeIsPresent()
    {
        var session = new Session([PassFrame(false, true)]);
        session.TextReader = (_, _) => throw new InvalidOperationException("未开启赛季任务时无需读取其进度");
        Assert.True(await PassRewardFlow.RunAsync(session, true, false, false, default));
        Assert.DoesNotContain("daily.pass.claim-row", session.Clicks);
        Assert.Empty(session.Clicks);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task LevelRewardsConfirmAfterAnyEgoPresentation(bool hasPresentation)
    {
        var frames = new List<GameFrame> { LevelFrame(true) };
        if (hasPresentation) frames.Add(Frame(2, false));
        frames.Add(LevelFrame(false, RewardConfirm));
        frames.Add(LevelFrame(false));
        var session = new Session(frames);
        session.TextReader = (_, region) => region?.X == 770
            ? [new("全部领取", .99, new(800, 580, 100, 20))]
            : [new("SEASON 8", .98, new(896, 441, 90, 33)), new("WAW", .99, new(1113, 536, 84, 36))];
        Assert.True(await PassRewardFlow.RunAsync(session, false, true, false, default));
        Assert.Equal(hasPresentation
            ? ["daily.pass.claim-levels", "daily.pass.dismiss-ego", "daily.pass.confirm-levels"]
            : ["daily.pass.claim-levels", "daily.pass.confirm-levels"], session.Clicks);
        Assert.Contains("daily.pass.levels-claimed", session.Reports);
    }

    [Theory]
    [InlineData("SEASON 8")]
    [InlineData("WAW")]
    [InlineData("")]
    public async Task UnrecognizedRewardPageCannotReceivePresentationClicks(string label)
    {
        var session = new Session([LevelFrame(true), Frame(2, false)]);
        session.TextReader = (_, region) => [new(region?.X == 770 ? "全部领取" : label, .99, new(800, 580, 100, 20))];
        Assert.False(await PassRewardFlow.RunAsync(session, false, true, false, default));
        Assert.Equal(["daily.pass.claim-levels"], session.Clicks);
        Assert.Contains("daily.pass.levels-unverified", session.Reports);
    }

    [Fact]
    public async Task CancellationInterruptsTheFlowBeforeOpeningThePanel()
    {
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        var session = new Session([Frame(1, false)]);
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => EnkephalinFlow.ConvertAsync(session, cancellation.Token));
        Assert.Empty(session.Clicks);
    }

    private static GameFrame Frame(long id, bool orange, params string[] assets)
    {
        const int width = 1280, height = 720;
        var pixels = new byte[width * height * 4];
        if (orange)
            for (var offset = 0; offset < pixels.Length; offset += 4)
            {
                pixels[offset] = 30;
                pixels[offset + 1] = 100;
                pixels[offset + 2] = 180;
                pixels[offset + 3] = 255;
            }
        return new(new(new(id, width, height, 0, 0), pixels),
            assets.Select(a => new VisualTarget(a, new(700, 530), new(680, 510, 40, 40), .99)).ToArray());
    }

    private static GameFrame PassFrame(bool claimable, bool seasonBadge)
    {
        var frame = Frame(1, false, Missions, Weekly);
        void Paint(PixelRect bounds, byte r, byte g, byte b)
        {
            for (var y = bounds.Y; y < bounds.Bottom; y++)
            for (var x = bounds.X; x < bounds.Right; x++)
            {
                var offset = (y * frame.Identity.Width + x) * 4;
                frame.Pixels.Bgra[offset] = b;
                frame.Pixels.Bgra[offset + 1] = g;
                frame.Pixels.Bgra[offset + 2] = r;
            }
        }
        Paint(new(310, 72, 127, 6), 240, 160, 10);
        Paint(new(252, 220, 7, 75), 240, 160, 10);
        if (seasonBadge) Paint(new(266, 476, 34, 17), 180, 20, 10);
        if (claimable)
        {
            Paint(new(266, 190, 34, 17), 180, 20, 10);
            Paint(new(595, 221, 107, 30), 180, 100, 30);
        }
        return frame;
    }

    private static GameFrame SingleModuleFrame(long id, bool confirmEnabled)
    {
        var frame = Frame(id, false, Cancel, Disabled, All, Confirm);
        var confirmBounds = new PixelRect(716, 519, 39, 27);
        for (var y = confirmBounds.Y; y < confirmBounds.Bottom; y++)
            for (var x = confirmBounds.X; x < confirmBounds.Right; x++)
            {
                var offset = (y * frame.Identity.Width + x) * 4;
                for (var c = 0; c < 3; c++) frame.Pixels.Bgra[offset + c] = confirmEnabled ? (byte)184 : (byte)79;
            }
        return frame with { Targets = frame.Targets.Select(t => t.Asset == Confirm ? t with { Bounds = confirmBounds }
            : t.Asset == All || t.Asset == Disabled ? t with { Bounds = new(784, 308, 43, 45) } : t).ToArray() };
    }

    private static GameFrame LevelFrame(bool badge, params string[] assets)
    {
        var frame = Frame(1, false, [Missions, .. assets]);
        foreach (var (bounds, r, g, b) in new (PixelRect, byte, byte, byte)[]
            { (new(172, 72, 127, 6), 240, 160, 10), (new(269, 26, 31, 18), badge ? (byte)180 : (byte)0, 0, 0) })
        {
            for (var y = bounds.Y; y < bounds.Bottom; y++)
            for (var x = bounds.X; x < bounds.Right; x++)
            {
                var offset = (y * frame.Identity.Width + x) * 4;
                frame.Pixels.Bgra[offset] = b;
                frame.Pixels.Bgra[offset + 1] = g;
                frame.Pixels.Bgra[offset + 2] = r;
            }
        }
        return frame;
    }

    private sealed class Session(IReadOnlyList<GameFrame> frames) : IGameSession
    {
        public TimeSpan Elapsed { get; private set; }
        public int Observations { get; private set; }
        public List<string> Clicks { get; } = [];
        public List<string> Reports { get; } = [];
        public IReadOnlyList<RecognizedText> Text { get; set; } = [];
        public Func<GameFrame, PixelRect?, IReadOnlyList<RecognizedText>>? TextReader { get; set; }
        public ValueTask<GameFrame> ObserveAsync(IReadOnlyList<ImageQuery> queries, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            var source = frames[Math.Min(Observations, frames.Count - 1)];
            Observations++;
            return ValueTask.FromResult(source with { Pixels = source.Pixels with { Identity = source.Identity with { Id = Observations } } });
        }
        public ValueTask<IReadOnlyList<RecognizedText>> ReadTextAsync(GameFrame frame, CancellationToken ct, PixelRect? region = null, int scale = 1, TextPreprocessing preprocessing = TextPreprocessing.None)
        {
            ct.ThrowIfCancellationRequested();
            return ValueTask.FromResult(TextReader?.Invoke(frame, region) ?? Text);
        }
        public ValueTask ClickAsync(GameFrame frame, PixelPoint target, string rule, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested(); Clicks.Add(rule); return ValueTask.CompletedTask;
        }
        public ValueTask KeyAsync(GameFrame frame, GameKey key, string rule, CancellationToken ct) => throw new NotSupportedException();
        public ValueTask DragAsync(GameFrame frame, PixelPoint from, PixelPoint to, TimeSpan duration, string rule, CancellationToken ct) => throw new NotSupportedException();
        public ValueTask DelayAsync(TimeSpan duration, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested(); Elapsed += duration; return ValueTask.CompletedTask;
        }
        public void Report(string rule, string message) => Reports.Add(rule);
    }
}
