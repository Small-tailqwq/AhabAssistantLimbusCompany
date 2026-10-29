using AALC.Runtime.Mirror;
using AALC.Runtime.Automation;
using Xunit;

namespace AALC.Core.Tests;

public sealed class MirrorEventTests
{
    [Theory]
    [InlineData("event/very_high.png")]
    [InlineData("event/high.png")]
    [InlineData("event/normal.png")]
    [InlineData("event/low.png")]
    [InlineData("event/very_low.png")]
    public async Task ProbabilityFragmentsDoNotClaimTheMapPage(string probability)
    {
        var frame = MirrorRewardTests.Frame(1, MirrorThemeFlow.Map, probability);
        var session = new MirrorTestSession([frame]);
        Assert.False(MirrorEventFlow.HasEventPageEvidence(frame));
        Assert.True(await MirrorEventFlow.RunAsync(session, default));
        Assert.Empty(session.Actions);
    }

    [Theory]
    [InlineData("Choices")]
    [InlineData("CHOICES")]
    public async Task EnglishChoiceOcrWorksWhenTheFirstOptionTemplateIsBelowThreshold(string header)
    {
        var frame = new GameFrame(new(new(1, 1920, 1080, 0, 0), new byte[1920 * 1080 * 4]),
            [MirrorRewardTests.Target("event/choices_assets.png", 1135, 199)]);
        var session = new MirrorTestSession([frame]);
        RecognizedText[] entries = [new(header, .99507, new(1053, 169, 167, 47)),
            new("Tell the truth.", .99519, new(1096, 298, 194, 34)),
            new("Say that you don't know.", .99579, new(1098, 508, 339, 32))];
        var result = await new BattleEvents().HandleAsync(session, frame, entries, default);
        Assert.True(result.Handled); Assert.False(result.Failed);
        var action = Assert.Single(session.Actions);
        Assert.Equal("battle.event.first-choice-ocr", action.Rule);
        Assert.Equal(1193, action.Point.X); Assert.Equal(315, action.Point.Y);
    }

    [Theory]
    [InlineData(MirrorThemeFlow.Map)]
    [InlineData("battle/turn_assets.png")]
    [InlineData(MirrorRewardFlow.Gift)]
    public async Task FreshKnownSuccessorsAreHandedToTheirOwner(string successor)
    {
        var session = new MirrorTestSession([MirrorRewardTests.Frame(1, "event/commence_battle_assets.png"),
            MirrorRewardTests.Frame(2, successor)]);
        Assert.True(await MirrorEventFlow.RunAsync(session, default));
        Assert.Equal("mirror.event.commence-battle", Assert.Single(session.Actions).Rule);
        Assert.Equal(2, session.LastFrameId);
    }

    [Fact]
    public async Task ExplicitGiftSelectionIsHandedOffEvenWhenTheEventRemainsBehindIt()
    {
        var session = new MirrorTestSession([MirrorRewardTests.Frame(1, MirrorRewardFlow.Gift,
            MirrorRewardFlow.GiftSelect, "event/skip_assets.png")]);
        Assert.True(await MirrorEventFlow.RunAsync(session, default));
        Assert.Empty(session.Actions);
    }

    [Fact]
    public async Task ClickingAProgressButtonIsNotAnExitProof()
    {
        var session = new MirrorTestSession([MirrorRewardTests.Frame(1, "event/commence_battle_assets.png"), MirrorRewardTests.Frame(2)]);
        Assert.False(await MirrorEventFlow.RunAsync(session, default));
        Assert.Single(session.Actions);
        Assert.Contains("mirror.event.unknown", session.Reports);
    }

    [Fact]
    public async Task EventOverlayBlocksBackgroundMapCompletion()
    {
        var session = new MirrorTestSession([MirrorRewardTests.Frame(1, "event/unknown_event.png", MirrorThemeFlow.Map)]);
        Assert.False(await MirrorEventFlow.RunAsync(session, default));
        Assert.DoesNotContain("mirror.event.exited", session.Reports);
    }

    [Fact]
    public async Task CancelledEventCannotSendInput()
    {
        var session = new MirrorTestSession([MirrorRewardTests.Frame(1, "event/unknown_event.png")]);
        using var cts = new CancellationTokenSource(); cts.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => MirrorEventFlow.RunAsync(session, cts.Token));
        Assert.Empty(session.Actions);
    }
}
