using AALC.Core.Features.Daily;
using AALC.Core.Features.Mail;
using AALC.Runtime.Daily;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;
using System.Text.Json;
using Xunit;

namespace AALC.Core.Tests;

public sealed class GameSessionTests
{
    [Theory]
    [InlineData(false, false, 720)]
    [InlineData(false, true, 720)]
    [InlineData(true, false, 720)]
    [InlineData(true, true, 720)]
    [InlineData(false, false, 1080)]
    [InlineData(true, true, 1080)]
    [InlineData(false, false, 1440)]
    [InlineData(true, true, 1440)]
    public async Task TutorialIsDismissedBeforeReturningCoveredControls(bool controlsOnly, bool backVisible, int height)
    {
        var clock = new Clock();
        var input = new Input(clock);
        var events = new List<RunEvent>();
        var target = new VisualTarget("teams/identify_assets.png", new(50, 50), new(40, 40, 20, 20), .99);
        var scale = height / 720.0;
        var prompt = new VisualTarget("home/first_prompt_assets.png", new((int)(1205 * scale), (int)(360 * scale)),
            new((int)(1182 * scale), (int)(332 * scale), (int)(46 * scale), (int)(56 * scale)), .99843);
        var back = new VisualTarget("home/back_assets.png", new(10, 10), new(5, 5, 10, 10), .99);
        var vision = new Vision(id => Frame(id, width: (int)(1280 * scale), height: height) with
        {
            Targets = id > 1 ? [target] : backVisible ? [target, prompt, back] : [target, prompt]
        });
        var session = new GameSession(vision, input, clock, events.Add, TimeSpan.FromMinutes(1));
        ImageQuery[] queries = [new(target.Asset)];

        var frame = controlsOnly ? await session.ObserveControlsAsync(queries, default)
            : await session.ObserveAsync(queries, default);

        Assert.Equal(2, frame.Identity.Id);
        Assert.Equal(backVisible ? "click" : "key", Assert.Single(input.Actions).Kind);
        var dismissal = Assert.Single(events, item => item.Action == "Sent");
        Assert.Equal("automation.tutorial.dismiss", dismissal.Rule);
        Assert.Equal(backVisible ? "10,10" : "Escape", dismissal.Target);
        Assert.Equal(1, dismissal.FrameId);
        Assert.Equal(controlsOnly ? 0 : 1, vision.Reads);
    }

    [Fact]
    public async Task PersistentTutorialStopsAfterThreeDismissals()
    {
        var clock = new Clock();
        var input = new Input(clock);
        var vision = new Vision(id => Frame(id, width: 1280, height: 720) with
        {
            Targets = [new("home/first_prompt_assets.png", new(1205, 360), new(1182, 332, 46, 56), .99843)]
        });
        var session = new GameSession(vision, input, clock, _ => { }, TimeSpan.FromMinutes(1));

        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => session.ObserveAsync([], default).AsTask());

        Assert.Contains("新手提示", error.Message);
        Assert.Equal(3, input.Actions.Count);
        Assert.Equal(TimeSpan.FromSeconds(3), clock.Elapsed);
        Assert.Equal(0, vision.Reads);
    }

    [Fact]
    public async Task BackButtonWithoutTutorialDoesNotNavigateAway()
    {
        var clock = new Clock();
        var input = new Input(clock);
        var vision = new Vision(id => Frame(id) with
        {
            Targets = [new("home/back_assets.png", new(10, 10), new(5, 5, 10, 10), .99)]
        });
        var session = new GameSession(vision, input, clock, _ => { }, TimeSpan.FromMinutes(1));

        await session.ObserveAsync([], default);

        Assert.Empty(input.Actions);
    }

    [Theory]
    [InlineData(720)]
    [InlineData(1080)]
    [InlineData(1440)]
    public async Task LuxcavationPageArrowDoesNotDismissThePage(int height)
    {
        var clock = new Clock();
        var input = new Input(clock);
        var scale = height / 720.0;
        var vision = new Vision(id => Frame(id, width: (int)(1280 * scale), height: height) with
        {
            Targets = [new("home/first_prompt_assets.png", new((int)(1235 * scale), (int)(358 * scale)),
                    new((int)(1212 * scale), (int)(330 * scale), (int)(46 * scale), (int)(56 * scale)), .9000),
                new("home/back_assets.png", new((int)(95 * scale), (int)(45 * scale)), new(0, 0, 10, 10), .99)]
        });
        var session = new GameSession(vision, input, clock, _ => { }, TimeSpan.FromMinutes(1));

        var frame = await session.ObserveControlsAsync([], default);

        Assert.Equal(1, frame.Identity.Id);
        Assert.Empty(input.Actions);
    }

    [Fact]
    public async Task BattleTurnControlsAvoidSlowOcrBeforeKeyboardInput()
    {
        var clock = new Clock();
        var events = new List<RunEvent>();
        var committed = false;
        var vision = new Vision(id =>
        {
            clock.Advance(TimeSpan.FromMilliseconds(940));
            var asset = committed ? "mirror/road_in_mir/legend_assets.png" : "battle/win_rate_assets.png";
            return Frame(id) with { Targets = committed
                ? [new(asset, new(90, 70), new(80, 60, 20, 20), .99)]
                : [new(asset, new(90, 70), new(80, 60, 20, 20), .99),
                    new("battle/turn_assets.png", new(20, 20), new(15, 15, 10, 10), .99)] };
        }) { OnRead = () => clock.Advance(TimeSpan.FromMilliseconds(4252)) };
        var session = new GameSession(vision, new Input(clock), clock, item =>
        {
            events.Add(item);
            if (item.Rule == "battle.commit-turn" && item.Action == "Sent") committed = true;
        }, TimeSpan.FromMinutes(1));

        Assert.True(await BattleFlow.ContinueAsync(session, 1, true, default, BattlePurpose.Mirror));

        Assert.Equal(0, vision.Reads);
        Assert.Equal(["battle.win-rate", "battle.commit-turn"], events.Where(item => item.Action == "Sent").Select(item => item.Rule));
        Assert.True(events.Single(item => item.Rule == "battle.commit-turn" && item.Action == "Sent").ElapsedMilliseconds < 5000);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ServerErrorBetweenPAndEnterIsRecoveredBeforeCommittingTheTurn(bool errorTemplate)
    {
        var clock = new Clock();
        var events = new List<RunEvent>();
        var phase = 0;
        var vision = new Vision(id => Frame(id, phase == 1) with
        {
            Targets = phase == 1 ? errorTemplate ? [new("base/try_again.png", new(63, 34), new(55, 30, 16, 8), .99)] : []
                : phase == 3 ? [new("mirror/road_in_mir/legend_assets.png", new(90, 70), new(80, 60, 20, 20), .99)]
                : [new("battle/win_rate_assets.png", new(90, 70), new(80, 60, 20, 20), .99),
                    new("battle/turn_assets.png", new(20, 20), new(15, 15, 10, 10), .99)]
        }) { Text = _ => phase == 1 ? ServerError() : [] };
        var session = new GameSession(vision, new Input(clock), clock, item =>
        {
            events.Add(item);
            if (item.Action != "Sent") return;
            if (item.Rule == "battle.win-rate" && phase == 0) phase = 1;
            else if (item.Rule == "daily.connection.retry-server") phase = 2;
            else if (item.Rule == "battle.commit-turn")
            {
                Assert.Equal(2, phase);
                phase = 3;
            }
        }, TimeSpan.FromMinutes(1));

        Assert.True(await BattleFlow.ContinueAsync(session, 1, true, default, BattlePurpose.Mirror));

        string[] expected = errorTemplate ? ["battle.win-rate", "daily.connection.retry-server", "battle.commit-turn"]
            : ["battle.win-rate", "daily.connection.retry-server", "battle.win-rate", "battle.commit-turn"];
        Assert.Equal(expected,
            events.Where(item => item.Action == "Sent").Select(item => item.Rule));
    }

    [Fact]
    public async Task FormationOrderPreprocessingIsPassedToVisionAndRecordedWithItsDuration()
    {
        var clock = new Clock();
        var vision = new Vision(id => Frame(id)) { OnRead = () => clock.Advance(TimeSpan.FromMilliseconds(40)) };
        var events = new List<RunEvent>();
        var session = new GameSession(vision, new Input(clock), clock, events.Add, TimeSpan.FromMinutes(1));
        var frame = await session.ObserveControlsAsync([], default);
        await session.ReadTextAsync(frame, default, new(10, 20, 30, 40), preprocessing: TextPreprocessing.FormationOrder);

        Assert.Equal([TextPreprocessing.FormationOrder], vision.PreprocessingModes);
        using var detail = JsonDocument.Parse(events.Single(item => item.Rule == "automation.ocr").Detail!);
        Assert.Equal((int)TextPreprocessing.FormationOrder, detail.RootElement.GetProperty("preprocessing").GetInt32());
        Assert.Equal(40, detail.RootElement.GetProperty("durationMilliseconds").GetDouble());
    }

    [Fact]
    public async Task TerminalGameErrorStopsWithoutRetryingTheDisabledButton()
    {
        var clock = new Clock();
        var input = new Input(clock);
        var vision = new Vision(id => Frame(id))
        {
            Text = _ => [new("游戏无法运行。", .99, new(570, 310, 135, 26)),
                new("即将关闭游戏。", .99, new(570, 338, 135, 26)),
                new("关闭", .99, new(510, 455, 60, 30)), new("重试", .99, new(710, 455, 60, 30))]
        };
        var session = new GameSession(vision, input, clock, _ => { }, TimeSpan.FromMinutes(3));

        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => session.ObserveAsync([], default).AsTask());

        Assert.Contains("需要重新进入游戏", error.Message);
        Assert.Empty(input.Actions);
        Assert.Equal(TimeSpan.Zero, clock.Elapsed);
    }

    [Fact]
    public async Task KnownControlsDoNotRunFullScreenOcrOnEveryObservation()
    {
        var clock = new Clock();
        var target = new VisualTarget("test/control.png", new(50, 50), new(40, 40, 20, 20), .99);
        var vision = new Vision(id => Frame(id) with { Targets = [target] });
        var session = new GameSession(vision, new Input(clock), clock, _ => { }, TimeSpan.FromMinutes(1));
        ImageQuery[] queries = [new(target.Asset)];
        await session.ObserveAsync(queries, default);
        for (var i = 0; i < 19; i++)
        {
            clock.Advance(TimeSpan.FromMilliseconds(100));
            await session.ObserveAsync(queries, default);
        }
        Assert.Equal(1, vision.Reads);
        clock.Advance(TimeSpan.FromMilliseconds(100));
        await session.ObserveAsync(queries, default);
        Assert.Equal(2, vision.Reads);
    }

    [Fact]
    public async Task UnknownPageInspectsServerDialogWithoutWaitingForTheNextInterval()
    {
        var clock = new Clock();
        var target = new VisualTarget("test/control.png", new(50, 50), new(40, 40, 20, 20), .99);
        var vision = new Vision(id => Frame(id) with { Targets = id == 1 ? [target] : [] });
        var session = new GameSession(vision, new Input(clock), clock, _ => { }, TimeSpan.FromMinutes(1));
        ImageQuery[] queries = [new(target.Asset)];
        await session.ObserveAsync(queries, default);
        clock.Advance(TimeSpan.FromMilliseconds(100));
        await session.ObserveAsync(queries, default);
        Assert.Equal(2, vision.Reads);
    }

    [Fact]
    public async Task ControlFeedbackOnlyReadsTheExplicitlyRequestedTextRegion()
    {
        var clock = new Clock();
        var vision = new Vision(id => Frame(id));
        var session = new GameSession(vision, new Input(clock), clock, _ => { }, TimeSpan.FromMinutes(1));
        for (var i = 0; i < 3; i++) await session.ObserveControlsAsync([], default);
        Assert.Empty(vision.TextRegions);
        var frame = await session.ObserveControlsAsync([], default);
        PixelRect row = new(10, 30, 70, 12);
        await session.ReadTextAsync(frame, default, row);
        Assert.Equal([row], vision.TextRegions);
    }

    [Theory]
    [InlineData("click")]
    [InlineData("key")]
    [InlineData("drag")]
    public async Task CancellationAfterObservationPreventsEveryInputKind(string action)
    {
        var clock = new Clock();
        var input = new Input(clock);
        var session = new GameSession(new Vision(id => Frame(id)), input, clock, _ => { }, TimeSpan.FromMinutes(1));
        var frame = await session.ObserveAsync([], default);
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => SendAsync(session, action, frame, cancellation.Token));

        Assert.Empty(input.Actions);
    }

    [Theory]
    [InlineData("click")]
    [InlineData("key")]
    [InlineData("drag")]
    public async Task AnotherObservationInvalidatesThePreviousInputFrame(string action)
    {
        var clock = new Clock();
        var input = new Input(clock);
        var session = new GameSession(new Vision(id => Frame(id)), input, clock, _ => { }, TimeSpan.FromMinutes(1));
        var previous = await session.ObserveAsync([], default);
        await session.ObserveAsync([], default);

        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => SendAsync(session, action, previous, default));

        Assert.Contains("过期观察帧", error.Message);
        Assert.Empty(input.Actions);
    }

    [Fact]
    public async Task OcrFinishingAtTheDeadlineCannotClickTheRecognizedRetryButton()
    {
        var clock = new Clock();
        var input = new Input(clock);
        var vision = new Vision(id => Frame(id, true))
        {
            Text = _ => ServerError(),
            OnRead = () => clock.Advance(TimeSpan.FromSeconds(10))
        };
        var session = new GameSession(vision, input, clock, _ => { }, TimeSpan.FromSeconds(10));

        var error = await Assert.ThrowsAsync<TimeoutException>(() => session.ObserveAsync([], default).AsTask());

        Assert.Contains("运行时限", error.Message);
        Assert.Equal(1, vision.Reads);
        Assert.Empty(input.Actions);
    }

    [Fact]
    public async Task PersistentChineseServerErrorRetriesAtMostOncePerFiveSeconds()
    {
        var clock = new Clock();
        var input = new Input(clock);
        var target = new VisualTarget("test/control.png", new(50, 50), new(40, 40, 20, 20), .99);
        var vision = new Vision(id => Frame(id, true) with { Targets = [target] })
        {
            Text = _ => clock.Elapsed < TimeSpan.FromSeconds(12) ? ServerError() : []
        };
        var session = new GameSession(vision, input, clock, _ => { }, TimeSpan.FromMinutes(1));

        await session.ObserveAsync([new(target.Asset)], default);

        Assert.Equal([TimeSpan.Zero, TimeSpan.FromSeconds(5), TimeSpan.FromSeconds(10)],
            input.Actions.Select(action => action.At));
        Assert.All(input.Actions, action => Assert.Equal("click", action.Kind));
        Assert.Equal(TimeSpan.FromSeconds(12), clock.Elapsed);
    }

    [Fact]
    public async Task ChineseServerErrorWithUnavailableRetryStopsAfterFifteenSeconds()
    {
        var clock = new Clock();
        var input = new Input(clock);
        var vision = new Vision(id => Frame(id)) { Text = _ => ServerError() };
        var session = new GameSession(vision, input, clock, _ => { }, TimeSpan.FromMinutes(1));

        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => session.ObserveAsync([], default).AsTask());

        Assert.Contains("重试按钮持续不可用", error.Message);
        Assert.Equal(TimeSpan.FromSeconds(15), clock.Elapsed);
        Assert.Empty(input.Actions);
    }

    private static Task SendAsync(GameSession session, string action, GameFrame frame, CancellationToken ct) => action switch
    {
        "click" => session.ClickAsync(frame, new(90, 66), "daily.test.click", ct).AsTask(),
        "key" => session.KeyAsync(frame, GameKey.Enter, "daily.test.key", ct).AsTask(),
        "drag" => session.DragAsync(frame, new(20, 20), new(20, 50), TimeSpan.FromMilliseconds(400), "daily.test.drag", ct).AsTask(),
        _ => throw new ArgumentOutOfRangeException(nameof(action))
    };

    private static GameFrame Frame(long id, bool retryAvailable = false, int width = 128, int height = 96)
    {
        var pixels = new byte[width * height * 4];
        if (retryAvailable)
            for (var y = 60; y < 72; y++)
            for (var x = 80; x < 104; x++)
            {
                var offset = (y * width + x) * 4;
                pixels[offset] = 30;
                pixels[offset + 1] = 100;
                pixels[offset + 2] = 180;
                pixels[offset + 3] = 255;
            }
        return new(new(new(id, width, height, 1, 0), pixels), []);
    }

    private static IReadOnlyList<RecognizedText> ServerError() =>
    [
        new("服务器发生错误", .99, new(10, 10, 70, 12)),
        new("请稍后再试", .99, new(10, 26, 70, 12)),
        new("关闭", .99, new(16, 60, 24, 12)),
        new("重试", .99, new(80, 60, 24, 12))
    ];

    private sealed class Clock : IRunClock
    {
        public TimeSpan Elapsed { get; private set; }
        public void Advance(TimeSpan duration) => Elapsed += duration;
        public ValueTask DelayAsync(TimeSpan delay, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            Advance(delay);
            return ValueTask.CompletedTask;
        }
    }

    private sealed class Vision(Func<long, GameFrame> frames) : IGameVision
    {
        private long sequence;
        public int Reads { get; private set; }
        public List<PixelRect?> TextRegions { get; } = [];
        public List<TextPreprocessing> PreprocessingModes { get; } = [];
        public Func<GameFrame, IReadOnlyList<RecognizedText>> Text { get; init; } = _ => [];
        public Action? OnRead { get; init; }
        public ValueTask<GameFrame> ObserveAsync(IReadOnlyList<ImageQuery> queries, CancellationToken ct) =>
            ValueTask.FromResult(frames(++sequence));
        public ValueTask<IReadOnlyList<RecognizedText>> ReadTextAsync(GameFrame frame, CancellationToken ct,
            PixelRect? region = null, int scale = 1, TextPreprocessing preprocessing = TextPreprocessing.None)
        {
            Reads++;
            TextRegions.Add(region);
            PreprocessingModes.Add(preprocessing);
            OnRead?.Invoke();
            return ValueTask.FromResult(Text(frame));
        }
    }

    private sealed class Input(Clock clock) : IGameInput
    {
        public List<(string Kind, TimeSpan At)> Actions { get; } = [];
        public ValueTask ClickAtAsync(PixelPoint target, FrameIdentity frame, CancellationToken ct)
        {
            Actions.Add(("click", clock.Elapsed));
            return ValueTask.CompletedTask;
        }
        public ValueTask KeyPressAsync(GameKey key, FrameIdentity frame, CancellationToken ct)
        {
            Actions.Add(("key", clock.Elapsed));
            return ValueTask.CompletedTask;
        }
        public ValueTask DragAsync(PixelPoint from, PixelPoint to, TimeSpan duration, FrameIdentity frame, CancellationToken ct)
        {
            Actions.Add(("drag", clock.Elapsed));
            return ValueTask.CompletedTask;
        }
    }
}
