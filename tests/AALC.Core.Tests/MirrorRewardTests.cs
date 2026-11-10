using AALC.Core.Automation;
using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;
using AALC.Runtime.Mirror;
using Xunit;

namespace AALC.Core.Tests;

public sealed class MirrorRewardTests
{
    [Theory]
    [InlineData("teams/identify_assets.png")]
    [InlineData(MirrorThemeFlow.Map)]
    public async Task GenericConfirmationDoesNotCaptureAnUnrelatedPage(string page)
    {
        var frame = Frame(1, page, MirrorRewardFlow.RefuseConfirm);
        var session = new MirrorTestSession([frame]);
        Assert.False(MirrorRewardFlow.IsReward(frame));
        var result = await MirrorRewardFlow.HandleAsync(session, frame, new(), default);
        Assert.False(result.Handled);
        Assert.False(result.Failed);
        Assert.Empty(session.Actions);
        Assert.Equal(0, session.Observations);
    }

    [Fact]
    public void InvalidCardPreferenceIsRejectedBeforeStartingTheRun()
    {
        var options = new MirrorOptions { Teams = [new() { Rewards = new() { CardPreference = (MirrorCardPreference)999 } }] };
        Assert.Throws<ArgumentException>(() => MirrorPlan.ValidateConfiguration(options));
    }

    [Theory]
    [InlineData(MirrorCardPreference.StarlightThenGift, "gain_starlight", "gain_ego")]
    [InlineData(MirrorCardPreference.StarlightThenCost, "gain_starlight", "gain_cost")]
    [InlineData(MirrorCardPreference.CostFirst, "gain_cost", "gain_ego")]
    [InlineData(MirrorCardPreference.GiftFirst, "gain_ego", "gain_cost")]
    public void CardPreferencesHaveExplicitPriority(MirrorCardPreference preference, string first, string second) =>
        Assert.Equal([first, second], MirrorRewardFlow.CardOrder(preference).Take(2));

    [Theory]
    [InlineData("0/1", 0, 1)]
    [InlineData("0／2", 0, 2)]
    [InlineData("2 / 2", 2, 2)]
    [InlineData("0/23", null, null)]
    [InlineData("2/1", null, null)]
    [InlineData("unknown", null, null)]
    public void OnlyRecognizedSelectionCountsAreUsed(string text, int? selected, int? maximum) =>
        Assert.Equal(selected is { } count && maximum is { } limit ? (count, limit) : ((int, int)?)null,
            MirrorRewardFlow.SelectionCount(text));

    [Theory]
    [InlineData(MirrorThemeFlow.Map)]
    [InlineData("mirror/theme_pack/feature_theme_pack_assets.png")]
    public async Task InventoryBoxIconDoesNotCaptureTheMapOrThemePage(string page)
    {
        var frame = Frame(1, page, MirrorRewardFlow.GiftBox);
        var session = new MirrorTestSession([frame]);
        var result = await MirrorRewardFlow.HandleAsync(session, frame, new(), default);
        Assert.False(result.Handled);
        Assert.False(result.Failed);
        Assert.Empty(session.Actions);
    }

    [Fact]
    public async Task ClaimWaitingDoesNotToggleAnotherCardAndVerifiesConfirmationExit()
    {
        const string star = "mirror/get_reward_card/gain_starlight.png";
        const string cost = "mirror/get_reward_card/gain_cost.png";
        var session = new MirrorTestSession([
            Frame(2, MirrorRewardFlow.Cards, star), Frame(3, MirrorRewardFlow.Cards, star, cost),
            Frame(4, MirrorRewardFlow.Cards, star, cost), Frame(5, MirrorRewardFlow.Cards, MirrorRewardFlow.Claim),
            Frame(6, MirrorRewardFlow.Cards, cost, MirrorRewardFlow.Claim),
            Frame(7, MirrorRewardFlow.GiftConfirm), Frame(8, MirrorThemeFlow.Map)]);
        session.Reader = (frame, region) => [new(frame.Identity.Id <= 4 ? "0/1" : "1/1", .99, region ?? new())];
        var result = await MirrorRewardFlow.HandleAsync(session, Frame(1, MirrorRewardFlow.Cards), new(), default);
        Assert.True(result.Handled); Assert.False(result.Failed);
        Assert.Equal(["mirror.reward.select-card", "mirror.reward.claim-card", "mirror.reward.confirm-obtained"], session.Actions.Select(a => a.Rule));
        Assert.Equal(4, Assert.Single(session.Actions, action => action.Rule == "mirror.reward.select-card").FrameId);
        Assert.Equal(8, session.LastFrameId);
    }

    [Fact]
    public async Task GiftConfirmationCanBeFollowedByANewCardSelectionWithoutLeavingRewards()
    {
        const string cost = "mirror/get_reward_card/gain_cost.png";
        var session = new MirrorTestSession([Frame(1, MirrorRewardFlow.GiftConfirm),
            Frame(2, MirrorRewardFlow.Cards, cost, MirrorRewardFlow.Claim),
            Frame(3, MirrorRewardFlow.Cards, cost, MirrorRewardFlow.Claim),
            Frame(4, MirrorRewardFlow.Cards, cost, MirrorRewardFlow.Claim), Frame(5, MirrorThemeFlow.Map)]);
        session.Reader = (frame, region) => [new(frame.Identity.Id <= 3 ? "0/1" : "1/1", .99, region ?? new())];

        var result = await MirrorRewardFlow.HandleAsync(session, Frame(0, MirrorRewardFlow.GiftConfirm), new(), default);

        Assert.False(result.Failed);
        Assert.Equal(["mirror.reward.confirm-obtained", "mirror.reward.select-card", "mirror.reward.claim-card"],
            session.Actions.Select(action => action.Rule));
    }

    [Fact]
    public async Task TwoGiftsPreferTheConfiguredKeywordAndWaitForANewSubmitFrame()
    {
        var gifts = GiftFrame(1);
        var session = new MirrorTestSession([gifts, WithSelected(GiftFrame(2), 700), WithSelected(GiftFrame(3), 700, 250),
            Frame(4, MirrorRewardFlow.GiftConfirm), Frame(5, MirrorThemeFlow.Map)]);
        session.Reader = (frame, region) => region?.Width == 60 ? [new($"{frame.Identity.Id - 1}/2", .99, region.Value)] : [];
        var result = await MirrorRewardFlow.HandleAsync(session, gifts, new() { AvoidWhiteGossypium = false }, default);
        Assert.False(result.Failed);
        var clicks = session.Actions.Where(a => a.Rule == "mirror.reward.select-gift").ToArray();
        Assert.Equal(2, clicks.Length);
        Assert.Equal(700, clicks[0].Point.X);
        Assert.Equal([1L, 2L], clicks.Select(a => a.FrameId));
        Assert.Contains(session.Actions, a => a.Rule == "mirror.reward.submit-gifts" && a.FrameId == 3);
    }

    [Fact]
    public async Task LeavingTheGiftPageAfterTheFirstSelectionCannotClickASecondPosition()
    {
        var source = GiftFrame(1);
        var session = new MirrorTestSession([source, Frame(2, MirrorThemeFlow.Map)]);
        session.Reader = (_, region) => [new("0/2", .99, region ?? new())];
        var result = await MirrorRewardFlow.HandleAsync(session, source, new() { AvoidWhiteGossypium = false }, default);
        Assert.False(result.Failed);
        Assert.Equal("mirror.reward.select-gift", Assert.Single(session.Actions).Rule);
    }

    [Fact]
    public async Task LeavingTheBoxPageCannotClickItsSecondPosition()
    {
        var source = Frame(1, MirrorRewardFlow.GiftBox, MirrorRewardFlow.BoxRefuse);
        var session = new MirrorTestSession([source, Frame(2, MirrorThemeFlow.Map)]);
        var result = await MirrorRewardFlow.HandleAsync(session, source, new(), default);
        Assert.True(result.Failed);
        Assert.Equal("mirror.reward.select-box-first", Assert.Single(session.Actions).Rule);
    }

    [Fact]
    public async Task UnchangedSelectionCountRetriesWithoutSubmitting()
    {
        var source = GiftFrame(1, MirrorRewardFlow.GiftSelect);
        var session = new MirrorTestSession([source]);
        session.Reader = (_, region) => [new("0/1", .99, region ?? new())];
        var result = await MirrorRewardFlow.HandleAsync(session, source, new() { AvoidWhiteGossypium = false }, default);
        Assert.True(result.Failed);
        Assert.Equal(3, session.Actions.Count(a => a.Rule == "mirror.reward.select-gift"));
        Assert.DoesNotContain(session.Actions, a => a.Rule == "mirror.reward.submit-gifts");
    }

    [Fact]
    public async Task MissedGiftClickRecoversAfterCountFeedbackAndThenSubmits()
    {
        var frames = Enumerable.Range(1, 5).Select(id => GiftFrame(id)).ToList();
        frames.AddRange([WithSelected(GiftFrame(6), 700), Frame(7, MirrorRewardFlow.GiftConfirm), Frame(8, MirrorThemeFlow.Map)]);
        var session = new MirrorTestSession(frames);
        session.Reader = (frame, region) => region?.Width == 60
            ? [new(frame.Identity.Id < 6 ? "0/1" : "1/1", .99, region.Value)] : [];

        var result = await MirrorRewardFlow.HandleAsync(session, frames[0], new() { AvoidWhiteGossypium = false }, default);

        Assert.False(result.Failed);
        Assert.Equal(2, session.Actions.Count(action => action.Rule == "mirror.reward.select-gift"));
        Assert.Equal(6, Assert.Single(session.Actions, action => action.Rule == "mirror.reward.submit-gifts").FrameId);
    }

    [Fact]
    public async Task FullSelectionRetriesSubmissionWithoutTogglingAnyGift()
    {
        var source = WithSelected(GiftFrame(1), 700);
        var session = new MirrorTestSession([source]);
        session.Reader = (_, region) => region?.Width == 60 ? [new("1/1", .99, region.Value)] : [];

        var result = await MirrorRewardFlow.HandleAsync(session, source, new(), default);

        Assert.True(result.Failed);
        Assert.Equal(3, session.Actions.Count);
        Assert.All(session.Actions, action => Assert.Equal("mirror.reward.submit-gifts", action.Rule));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ExcludedGiftRequiresRefusalConfirmationAndObservedExit(bool mapVisible)
    {
        var source = Frame(1, MirrorRewardFlow.Gift, MirrorRewardFlow.Refuse, MirrorRewardFlow.GiftSelect);
        var confirmation = mapVisible ? Frame(2, MirrorRewardFlow.RefuseConfirm, MirrorThemeFlow.Map)
            : Frame(2, MirrorRewardFlow.RefuseConfirm);
        var session = new MirrorTestSession([source, confirmation, Frame(3, MirrorThemeFlow.Map)]);
        session.Reader = (_, region) => [new(region?.Width == 60 ? "0/1" : "白棉花", .99, region ?? new())];
        var result = await MirrorRewardFlow.HandleAsync(session, source, new(), default);
        Assert.False(result.Failed);
        Assert.Equal(["mirror.reward.refuse-gifts", "mirror.reward.confirm-refusal"], session.Actions.Select(a => a.Rule));
        Assert.Equal(3, session.LastFrameId);
    }

    [Fact]
    public async Task UnknownTransitionDoesNotBecomeSuccessfulRewardCompletion()
    {
        var session = new MirrorTestSession([Frame(2)]);
        var result = await MirrorRewardFlow.HandleAsync(session, Frame(1, MirrorRewardFlow.GiftConfirm), new(), default);
        Assert.True(result.Failed);
        Assert.Empty(session.Actions);
    }

    [Fact]
    public async Task GiftFadeInWaitsForReadableCountBeforeSelecting()
    {
        var source = GiftFrame(1);
        var session = new MirrorTestSession([source, GiftFrame(2), WithSelected(GiftFrame(3), 700),
            Frame(4, MirrorRewardFlow.GiftConfirm), Frame(5, MirrorThemeFlow.Map)]);
        session.Reader = (frame, region) => frame.Identity.Id == 1 ? [] : [new(frame.Identity.Id == 2 ? "0/1" : "1/1", .99, region ?? new())];

        var result = await MirrorRewardFlow.HandleAsync(session, source, new() { AvoidWhiteGossypium = false }, default);

        Assert.False(result.Failed);
        Assert.Equal(2, Assert.Single(session.Actions, a => a.Rule == "mirror.reward.select-gift").FrameId);
        Assert.DoesNotContain(session.Actions, a => a.FrameId == 1);
    }

    [Fact]
    public async Task UnreadableGiftCountStopsWithoutChoosing()
    {
        var source = GiftFrame(1);
        var session = new MirrorTestSession([source]);

        var result = await MirrorRewardFlow.HandleAsync(session, source, new() { AvoidWhiteGossypium = false }, default);

        Assert.True(result.Failed);
        Assert.Empty(session.Actions);
        Assert.Equal(8, session.Observations);
    }

    [Fact]
    public async Task NonRewardPageIsLeftToTheCaller()
    {
        var session = new MirrorTestSession([Frame(1, MirrorThemeFlow.Map)]);
        Assert.Equal((false, false), await MirrorRewardFlow.HandleAsync(session, Frame(1, MirrorThemeFlow.Map), new(), default));
        Assert.Equal(0, session.Observations);
    }

    [Theory]
    [InlineData("选择", false)]
    [InlineData("Select", false)]
    [InlineData("选择", true)]
    public async Task SingleGiftWithoutCounterUsesThePlainSelectButton(string label, bool excluded)
    {
        var source = SingleGiftFrame(1);
        var session = new MirrorTestSession(excluded
            ? [source, Frame(2, MirrorRewardFlow.RefuseConfirm), Frame(3, MirrorThemeFlow.Map)]
            : [source, WithSelected(SingleGiftFrame(2), 542), Frame(3, MirrorRewardFlow.GiftConfirm), Frame(4, MirrorThemeFlow.Map)]);
        session.Reader = (_, region) => region?.Width == 150 ? [new(label, .99, region.Value)]
            : region?.Width == 250 && excluded ? [new("白棉花", .99, region.Value)] : [];

        var result = await MirrorRewardFlow.HandleAsync(session, source, new(), default);

        Assert.False(result.Failed);
        Assert.Equal(excluded
            ? ["mirror.reward.refuse-gifts", "mirror.reward.confirm-refusal"]
            : new[] { "mirror.reward.select-gift", "mirror.reward.submit-gifts", "mirror.reward.confirm-obtained" },
            session.Actions.Select(action => action.Rule));
    }

    [Fact]
    public async Task SeveralGiftsWithoutCounterChooseOneAfterTheFadeIn()
    {
        GameFrame Page(long id, params int[] selected) => WithSelected(Frame(id) with
        {
            Targets = [Target(MirrorRewardFlow.Gift, 277, 360), Target(MirrorRewardFlow.Gift, 542, 360), Target(MirrorRewardFlow.Gift, 807, 360),
                Target(MirrorRewardFlow.GiftSelect, 1139, 579), Target(MirrorRewardFlow.Refuse, 949, 579)]
        }, selected);
        var source = Page(1);
        var session = new MirrorTestSession([source, Page(2), Page(3), Page(4), Page(5, 277), Page(6, 277), Page(7, 277), Frame(8, MirrorRewardFlow.GiftConfirm), Frame(9, MirrorThemeFlow.Map)]);
        session.Reader = (_, region) => region?.Width == 150 ? [new("选择", .99, region.Value)] : [];

        var result = await MirrorRewardFlow.HandleAsync(session, source, new(), default);

        Assert.False(result.Failed);
        Assert.Equal(["mirror.reward.select-gift", "mirror.reward.submit-gifts", "mirror.reward.confirm-obtained"],
            session.Actions.Select(action => action.Rule));
    }

    [Fact]
    public async Task OneDetectedCardWithUnreadableButtonDoesNotImplySingleSelection()
    {
        var source = SingleGiftFrame(1);
        var session = new MirrorTestSession([source]);

        var result = await MirrorRewardFlow.HandleAsync(session, source, new(), default);

        Assert.True(result.Failed);
        Assert.Empty(session.Actions);
    }

    private static GameFrame SingleGiftFrame(long id) => Frame(id) with
    {
        Targets = [Target(MirrorRewardFlow.Gift, 542, 360), Target(MirrorRewardFlow.GiftSelect, 1139, 579),
            Target(MirrorRewardFlow.Refuse, 949, 579)]
    };

    private static GameFrame WithSelected(GameFrame frame, params int[] centers)
    {
        foreach (var gift in frame.FindAll(MirrorRewardFlow.Gift).Where(gift => centers.Contains(gift.Center.X)))
            for (var y = gift.Center.Y - 100; y < gift.Center.Y + 50; y++)
                for (var x = gift.Center.X - 32; x < gift.Center.X - 26; x++)
                {
                    var offset = (y * frame.Identity.Width + x) * 4;
                    frame.Pixels.Bgra[offset + 1] = 170;
                    frame.Pixels.Bgra[offset + 2] = 255;
                }
        return frame;
    }

    private static GameFrame GiftFrame(long id, params string[] extra)
    {
        var frame = Frame(id, [MirrorRewardFlow.GiftSelect, .. extra]);
        return frame with { Targets = [.. frame.Targets,
            Target(MirrorRewardFlow.Gift, 250, 220), Target(MirrorRewardFlow.Gift, 450, 220), Target(MirrorRewardFlow.Gift, 700, 220),
            Target("mirror/road_in_mir/acquire_ego_gift/bleed.png", 750, 220)] };
    }

    internal static VisualTarget Target(string asset, int x, int y) => new(asset, new(x, y), new(x - 10, y - 10, 20, 20), .99);
    internal static GameFrame Frame(long id, params string[] assets) => new(new(new(id, 1280, 720, 0, 0), new byte[1280 * 720 * 4]),
        assets.Select(asset => Target(asset, 700, 530)).ToArray());
}

internal sealed class MirrorTestSession(IReadOnlyList<GameFrame> frames) : IGameSession
{
    public TimeSpan Elapsed { get; private set; }
    public int Observations { get; private set; }
    public long LastFrameId { get; private set; }
    public List<(string Rule, PixelPoint Point, long FrameId)> Actions { get; } = [];
    public List<string> Reports { get; } = [];
    public Func<GameFrame, PixelRect?, IReadOnlyList<RecognizedText>> Reader { get; set; } = (_, _) => [];
    public ValueTask<GameFrame> ObserveAsync(IReadOnlyList<ImageQuery> queries, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        var frame = frames[Math.Min(Observations++, frames.Count - 1)];
        LastFrameId = frame.Identity.Id;
        return ValueTask.FromResult(frame);
    }
    public ValueTask<IReadOnlyList<RecognizedText>> ReadTextAsync(GameFrame frame, CancellationToken ct, PixelRect? region = null, int scale = 1, TextPreprocessing preprocessing = TextPreprocessing.None)
    { ct.ThrowIfCancellationRequested(); return ValueTask.FromResult(Reader(frame, region)); }
    public ValueTask ClickAsync(GameFrame frame, PixelPoint point, string rule, CancellationToken ct)
    { ct.ThrowIfCancellationRequested(); Actions.Add((rule, point, frame.Identity.Id)); return ValueTask.CompletedTask; }
    public ValueTask KeyAsync(GameFrame frame, GameKey key, string rule, CancellationToken ct) => throw new NotSupportedException();
    public ValueTask DragAsync(GameFrame frame, PixelPoint from, PixelPoint to, TimeSpan duration, string rule, CancellationToken ct) =>
        ClickAsync(frame, from, rule, ct);
    public ValueTask DelayAsync(TimeSpan duration, CancellationToken ct)
    { ct.ThrowIfCancellationRequested(); Elapsed += duration; return ValueTask.CompletedTask; }
    public void Report(string rule, string message) => Reports.Add(rule);
}
