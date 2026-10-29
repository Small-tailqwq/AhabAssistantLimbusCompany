using System.Text.Json;
using AALC.Core.Automation;
using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;
using AALC.Runtime.Mirror;
using AALC.Runtime.Replay;
using Xunit;

namespace AALC.Core.Tests;

public sealed class MirrorReplayTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RecordedPreprocessingIsRequiredAndPassedToRecomputedVision(bool matches)
    {
        var source = await RecordAsync();
        var events = source.Events.ToArray();
        var index = Array.FindIndex(events, item => item.Rule == "automation.ocr");
        events[index] = events[index] with { Detail = JsonSerializer.Serialize(new
        {
            region = (PixelRect?)null, scale = 1, preprocessing = TextPreprocessing.FormationOrder,
            text = new[] { new RecognizedText("1", .99, new(10, 10, 10, 20)) }
        }) };
        var scenario = source with { Events = events };
        var vision = new SyntheticVision(scenario);
        var replay = new MirrorScenarioReplay(scenario, frame => new byte[frame.Width * frame.Height * 4], vision: vision);
        using var observation = JsonDocument.Parse(events.First(item => item.Rule == "automation.observe").Detail!);
        var queries = JsonSerializer.Deserialize<ImageQuery[]>(observation.RootElement.GetProperty("queries").GetRawText(), MirrorScenario.Json)!;
        var frame = await replay.ObserveAsync(queries, default);

        if (matches)
        {
            Assert.Empty(await replay.ReadTextAsync(frame, default, preprocessing: TextPreprocessing.FormationOrder));
            Assert.Equal(TextPreprocessing.FormationOrder, vision.LastPreprocessing);
        }
        else
        {
            await Assert.ThrowsAsync<InvalidDataException>(() => replay.ReadTextAsync(frame, default).AsTask());
            Assert.Equal(0, vision.TextReads);
        }
    }

    [Fact]
    public async Task RecomputedVisionRunsThroughTheSameProductionRunnerAndActionContract()
    {
        var scenario = await RecordAsync();
        var vision = new SyntheticVision(scenario);
        var replay = new MirrorScenarioReplay(scenario, frame => new byte[frame.Width * frame.Height * 4], vision: vision);

        var result = await replay.RunAsync(default);

        Assert.True(replay.Evaluate(result).Passed, result.Reason);
        Assert.True(vision.TargetReads > 0 && vision.TextReads > 0 && vision.MapReads > 0);
    }

    [Fact]
    public async Task EmptyRecomputedTargetsNeverFallBackToRecordedTargets()
    {
        var scenario = await RecordAsync();
        var vision = new SyntheticVision(scenario) { EmptyTargets = true };
        var replay = new MirrorScenarioReplay(scenario, frame => new byte[frame.Width * frame.Height * 4], vision: vision);

        var result = await replay.RunAsync(default);

        Assert.False(replay.Evaluate(result).Passed);
        Assert.Equal("scenario.contract-violation", replay.Evaluate(result).Reason);
        Assert.True(vision.TargetReads > 0);
    }

    [Fact]
    public async Task RecomputedMapConnectionsControlThePlanInsteadOfTheRecordedGraph()
    {
        var scenario = await RecordAsync();
        var vision = new SyntheticVision(scenario) { RemoveConnections = true };
        var replay = new MirrorScenarioReplay(scenario, frame => new byte[frame.Width * frame.Height * 4], vision: vision);

        var result = await replay.RunAsync(default);

        Assert.Equal(RunOutcome.Failed, result.Outcome);
        Assert.Equal("寻路未完成：no-confirmed-connection", result.Reason);
        Assert.False(replay.Evaluate(result).Passed);
        Assert.Equal("scenario.outcome-mismatch", replay.Evaluate(result).Reason);
        Assert.Equal(1, vision.MapReads);
    }

    [Fact]
    public async Task RecomputedCoordinatesMustStillMatchTheRecordedAction()
    {
        var scenario = await RecordAsync();
        var vision = new SyntheticVision(scenario) { MapPoint = new(351, 350) };
        var replay = new MirrorScenarioReplay(scenario, frame => new byte[frame.Width * frame.Height * 4], vision: vision);

        var result = await replay.RunAsync(default);

        Assert.Equal("scenario.contract-violation", replay.Evaluate(result).Reason);
        Assert.Contains("坐标或按键不匹配", result.Reason);
    }

    [Fact]
    public async Task RecomputedOcrStillRequiresTheRecordedRegionAndScale()
    {
        var source = await RecordAsync();
        var changed = false;
        var events = source.Events.Select(item =>
        {
            if (changed || item.Rule != "automation.ocr") return item;
            changed = true;
            return item with { Detail = JsonSerializer.Serialize(new { region = new PixelRect(1, 1, 1, 1), scale = 2,
                text = Array.Empty<RecognizedText>() }) };
        }).ToArray();
        var vision = new SyntheticVision(source);
        var replay = new MirrorScenarioReplay(source with { Events = events }, frame => new byte[frame.Width * frame.Height * 4], vision: vision);

        var result = await replay.RunAsync(default);

        Assert.Equal("scenario.contract-violation", replay.Evaluate(result).Reason);
        Assert.Equal(0, vision.TextReads);
    }

    [Fact]
    public async Task EmptyRecomputedOcrNeverFallsBackToRecordedText()
    {
        var source = await RecordAsync();
        var ocrIndex = Array.FindIndex(source.Events, item => item.Rule == "automation.ocr");
        var events = source.Events.ToArray();
        events[ocrIndex] = events[ocrIndex] with { Detail = JsonSerializer.Serialize(new { region = (PixelRect?)null, scale = 1,
            text = new[] { new RecognizedText("录制文字", 1, new(0, 0, 100, 20)) } }) };
        var scenario = source with { Events = events };
        var vision = new SyntheticVision(scenario);
        var replay = new MirrorScenarioReplay(scenario, frame => new byte[frame.Width * frame.Height * 4], vision: vision);
        using var observation = JsonDocument.Parse(events.First(item => item.Rule == "automation.observe").Detail!);
        var queries = JsonSerializer.Deserialize<ImageQuery[]>(observation.RootElement.GetProperty("queries").GetRawText(), MirrorScenario.Json)!;
        var frame = await replay.ObserveAsync(queries, default);

        Assert.Empty(await replay.ReadTextAsync(frame, default));
        Assert.Equal(1, vision.TextReads);
    }

    [Fact]
    public async Task RecomputedVisionCannotBypassTheRecordedQueryOrder()
    {
        var scenario = await RecordAsync();
        var vision = new SyntheticVision(scenario);
        var replay = new MirrorScenarioReplay(scenario, frame => new byte[frame.Width * frame.Height * 4], vision: vision);
        using var observation = JsonDocument.Parse(scenario.Events.First(item => item.Rule == "automation.observe").Detail!);
        var queries = JsonSerializer.Deserialize<ImageQuery[]>(observation.RootElement.GetProperty("queries").GetRawText(), MirrorScenario.Json)!;

        await Assert.ThrowsAsync<InvalidDataException>(() => replay.ObserveAsync(queries.Reverse().ToArray(), default).AsTask());
        Assert.Equal(0, vision.TargetReads);
    }

    [Fact]
    public async Task RecordedMapAndBattleAreReplayedThroughTheProductionSessionAndRunner()
    {
        var scenario = await RecordAsync();
        Assert.Equal(RunOutcome.Completed, scenario.ExpectedResult.Outcome);
        Assert.Contains(scenario.Events, item => item.Rule == "mirror.route.map");
        var replay = Replay(scenario);
        var result = await new MirrorRunner(replay.CreateSession(MirrorRunner.TimeoutFor(scenario.Options)), replay)
            .RunAsync(scenario.Options, default);
        Assert.True(replay.Evaluate(result).Passed, $"{result.Reason}: {replay.Evaluate(result).Reason}");
        Assert.Equal(scenario.ExpectedResult.Observations, result.Observations);
    }

    [Fact]
    public async Task AlteringTheRecordedGraphChangesProductionPlanningAndFailsTheExpectedOutcome()
    {
        var scenario = await RecordAsync();
        var events = scenario.Events.Select(item => item.Rule != "mirror.route.map" ? item : item with
        {
            Detail = JsonSerializer.Serialize(JsonSerializer.Deserialize<MirrorMapSnapshot>(item.Detail!)! with { Connections = [] })
        }).ToArray();
        var replay = Replay(scenario with { Events = events });
        var result = await new MirrorRunner(replay.CreateSession(MirrorRunner.TimeoutFor(scenario.Options)), replay)
            .RunAsync(scenario.Options, default);
        Assert.False(replay.Evaluate(result).Passed);
        Assert.Equal(RunOutcome.Failed, result.Outcome);
        Assert.Equal("寻路未完成：no-confirmed-connection", result.Reason);
        Assert.Equal("scenario.outcome-mismatch", replay.Evaluate(result).Reason);
    }

    [Fact]
    public async Task ARecordedSentCoordinateMustMatchTheActualAction()
    {
        var scenario = await RecordAsync();
        var events = scenario.Events.Select(item => item.Action == "Sent" && item.Rule == "mirror.route.select-node"
            ? item with { Target = "351,350" } : item).ToArray();
        var replay = Replay(scenario with { Events = events });
        var result = await new MirrorRunner(replay.CreateSession(MirrorRunner.TimeoutFor(scenario.Options)), replay)
            .RunAsync(scenario.Options, default);
        Assert.Equal("scenario.contract-violation", replay.Evaluate(result).Reason);
    }

    [Fact]
    public async Task TheFinalRecordedActionCannotBeLeftUnperformedEvenAfterCompletion()
    {
        var scenario = await RecordAsync();
        var last = scenario.Events.Last();
        scenario = scenario with { Events = [.. scenario.Events, last with { Rule = "mirror.extra", Action = "Sent", Target = "40,50" }] };
        var replay = Replay(scenario);
        var result = await new MirrorRunner(replay.CreateSession(MirrorRunner.TimeoutFor(scenario.Options)), replay)
            .RunAsync(scenario.Options, default);
        Assert.Equal(RunOutcome.Completed, result.Outcome);
        Assert.Equal("scenario.unconsumed-events", replay.Evaluate(result).Reason);
        Assert.False(replay.Evaluate(result).AllExpectedActionsPerformed);
    }

    [Fact]
    public async Task ReplayRequiresTheSpecificFinalReason()
    {
        var scenario = await RecordAsync();
        scenario = scenario with { ExpectedResult = scenario.ExpectedResult with { Reason = "另一种退出原因" } };
        var replay = Replay(scenario);
        var result = await new MirrorRunner(replay.CreateSession(MirrorRunner.TimeoutFor(scenario.Options)), replay)
            .RunAsync(scenario.Options, default);
        Assert.Equal("scenario.reason-mismatch", replay.Evaluate(result).Reason);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task MissingMapDataFailsInsteadOfCallingAModelOrInventingConnections(bool recompute)
    {
        var scenario = await RecordAsync();
        var vision = recompute ? new SyntheticVision(scenario) : null;
        var replay = new MirrorScenarioReplay(scenario with { Events = scenario.Events.Where(item => item.Rule != "mirror.route.map").ToArray() },
            frame => new byte[frame.Width * frame.Height * 4], vision: vision);
        var result = await new MirrorRunner(replay.CreateSession(MirrorRunner.TimeoutFor(scenario.Options)), replay)
            .RunAsync(scenario.Options, default);
        Assert.Equal("scenario.contract-violation", replay.Evaluate(result).Reason);
        if (vision is not null) Assert.Equal(0, vision.MapReads);
    }

    [Fact]
    public async Task OcrRegionAndScaleArePartOfTheRecordedContract()
    {
        var scenario = await RecordAsync();
        var changed = false;
        var events = scenario.Events.Select(item =>
        {
            if (changed || item.Rule != "automation.ocr") return item;
            changed = true;
            return item with { Detail = JsonSerializer.Serialize(new { region = new PixelRect(1, 1, 1, 1), scale = 2,
                text = Array.Empty<RecognizedText>() }) };
        }).ToArray();
        var replay = Replay(scenario with { Events = events });
        var result = await new MirrorRunner(replay.CreateSession(MirrorRunner.TimeoutFor(scenario.Options)), replay)
            .RunAsync(scenario.Options, default);
        Assert.Equal("scenario.contract-violation", replay.Evaluate(result).Reason);
    }

    [Fact]
    public async Task AnExplicitlyUnsentFailedInputReproducesItsRecordedFailure()
    {
        var source = await RecordAsync();
        var end = Array.FindIndex(source.Events, item => item.Rule == "mirror.route.select-node" && item.Action == "Click");
        var scenario = source with
        {
            Events = source.Events[..(end + 1)],
            ExpectedResult = new(RunOutcome.Failed, "窗口输入发送失败", 3, 0)
        };
        var replay = Replay(scenario);
        var result = await replay.RunAsync(default);
        Assert.Equal("窗口输入发送失败", result.Reason);
        Assert.True(replay.Evaluate(result).Passed);
    }

    [Fact]
    public async Task ARecordedCancellationIsPropagatedBeforeTheUnsentInput()
    {
        var source = await RecordAsync();
        var end = Array.FindIndex(source.Events, item => item.Rule == "mirror.route.select-node" && item.Action == "Click");
        var cancelled = source.Events[end] with { Rule = "mirror.run.cancelled", Action = "Progress", Target = null,
            Detail = "已停止镜牢任务" };
        var scenario = source with
        {
            Events = [.. source.Events[..(end + 1)], cancelled],
            ExpectedResult = new(RunOutcome.Cancelled, "已停止镜牢任务", 3, 0)
        };
        var replay = Replay(scenario);
        var result = await replay.RunAsync(default);
        Assert.Equal(RunOutcome.Cancelled, result.Outcome);
        Assert.True(replay.Evaluate(result).Passed, replay.Evaluate(result).Reason);
    }

    private static MirrorScenarioReplay Replay(MirrorScenario scenario) =>
        new(scenario, frame => new byte[frame.Width * frame.Height * 4]);

    private sealed class SyntheticVision(MirrorScenario scenario) : IMirrorScenarioVision
    {
        public bool EmptyTargets { get; init; }
        public bool RemoveConnections { get; init; }
        public PixelPoint MapPoint { get; init; } = new(350, 350);
        public int TargetReads { get; private set; }
        public int TextReads { get; private set; }
        public TextPreprocessing LastPreprocessing { get; private set; }
        public int MapReads { get; private set; }
        public IReadOnlyList<VisualTarget> FindTargets(PixelFrame frame, IReadOnlyList<ImageQuery> queries, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            TargetReads++;
            if (EmptyTargets) return [];
            using var observation = JsonDocument.Parse(scenario.Events.Single(item => item.Rule == "automation.observe" && item.FrameId == frame.Identity.Id).Detail!);
            return JsonSerializer.Deserialize<VisualTarget[]>(observation.RootElement.GetProperty("Targets").GetRawText(), MirrorScenario.Json)!;
        }
        public IReadOnlyList<RecognizedText> ReadText(PixelFrame frame, PixelRect? region, int scale, CancellationToken ct,
            TextPreprocessing preprocessing = TextPreprocessing.None)
        { ct.ThrowIfCancellationRequested(); TextReads++; LastPreprocessing = preprocessing; return []; }
        public MirrorMapSnapshot ReadMap(PixelFrame frame, PixelPoint bus, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            MapReads++;
            return new(frame.Identity, bus, [new(0, MirrorNodeKind.Battle, MapPoint, new(320, 320, 60, 60), .9)],
                RemoveConnections ? [] : [new(-1, 0)]);
        }
    }

    private static async Task<MirrorScenario> RecordAsync()
    {
        var world = new RecordedWorld();
        var events = new List<RunEvent>();
        var options = new MirrorOptions();
        var session = new GameSession(world, world, world, events.Add, MirrorRunner.TimeoutFor(options), "Mirror");
        var result = await new MirrorRunner(session, world).RunAsync(options, default);
        Assert.Equal(RunOutcome.Completed, result.Outcome);
        return new(options, result, events.ToArray(), world.Frames.ToArray());
    }

    private sealed class RecordedWorld : IGameVision, IGameInput, IRunClock, IMirrorMapReader
    {
        private int phase;
        public TimeSpan Elapsed { get; private set; }
        public List<MirrorScenarioFrame> Frames { get; } = [];
        public ValueTask<GameFrame> ObserveAsync(IReadOnlyList<ImageQuery> queries, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            string[] assets = phase switch
            {
                0 => [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus],
                1 => [MirrorRouteFlow.Legend, MirrorRouteFlow.Bus, MirrorRouteFlow.Enter],
                2 or 3 => ["battle/more_information_assets.png"],
                _ => [MirrorSettlementFlow.Clear, MirrorSettlementFlow.Claim]
            };
            var id = Frames.Count + 1;
            Frames.Add(new(id, 1280, 720, "synthetic-contract"));
            var targets = assets.Where(asset => queries.Any(query => query.Asset == asset)).Select(asset =>
                new VisualTarget(asset, asset == MirrorRouteFlow.Bus ? new(40, 360) : new(500, 350), new(480, 330, 40, 40), 1)).ToArray();
            return ValueTask.FromResult(new GameFrame(new(new(id, 1280, 720, 1, Elapsed.Ticks), new byte[1280 * 720 * 4]), targets));
        }
        public ValueTask<IReadOnlyList<RecognizedText>> ReadTextAsync(GameFrame frame, CancellationToken ct,
            PixelRect? region = null, int scale = 1, TextPreprocessing preprocessing = TextPreprocessing.None) => ValueTask.FromResult<IReadOnlyList<RecognizedText>>([]);
        public ValueTask ClickAtAsync(PixelPoint point, FrameIdentity frame, CancellationToken ct)
        { ct.ThrowIfCancellationRequested(); phase++; return ValueTask.CompletedTask; }
        public ValueTask KeyPressAsync(GameKey key, FrameIdentity frame, CancellationToken ct)
        { ct.ThrowIfCancellationRequested(); phase = key == GameKey.P ? 3 : 4; return ValueTask.CompletedTask; }
        public ValueTask DragAsync(PixelPoint from, PixelPoint to, TimeSpan duration, FrameIdentity frame, CancellationToken ct) =>
            throw new InvalidOperationException("该轨迹无需相机调整");
        public ValueTask DelayAsync(TimeSpan duration, CancellationToken ct)
        { ct.ThrowIfCancellationRequested(); Elapsed += duration; return ValueTask.CompletedTask; }
        public MirrorMapSnapshot Read(PixelFrame frame, PixelPoint bus, CancellationToken ct) => new(frame.Identity, bus,
            [new(0, MirrorNodeKind.Battle, new(350, 350), new(320, 320, 60, 60), .9)], [new(-1, 0)]);
    }
}
