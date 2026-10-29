using System.Buffers.Binary;
using System.Text.Json;
using System.Text.Json.Serialization;
using AALC.Core.Automation;
using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;
using AALC.Runtime.Mirror;

namespace AALC.Runtime.Replay;

public sealed record MirrorScenarioFrame(long Id, int Width, int Height, string ImagePath);
public sealed record MirrorScenario(MirrorOptions Options, RunResult ExpectedResult, RunEvent[] Events,
    MirrorScenarioFrame[] Frames)
{
    public static readonly JsonSerializerOptions Json = new()
    {
        PropertyNameCaseInsensitive = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        Converters = { new JsonStringEnumConverter() }
    };

    public static MirrorScenario LoadRun(string directory)
    {
        directory = Path.GetFullPath(directory);
        var options = JsonSerializer.Deserialize<MirrorOptions>(File.ReadAllText(Path.Combine(directory, "options.json")), Json)
            ?? throw new InvalidDataException("镜牢录制缺少配置");
        var result = JsonSerializer.Deserialize<RunResult>(File.ReadAllText(Path.Combine(directory, "result.json")), Json)
            ?? throw new InvalidDataException("镜牢录制缺少运行结果");
        var events = File.ReadLines(Path.Combine(directory, "events.jsonl")).Where(line => !string.IsNullOrWhiteSpace(line))
            .Select(line => JsonSerializer.Deserialize<RunEvent>(line, Json)
                ?? throw new InvalidDataException("镜牢录制包含空事件")).ToArray();
        var frames = events.Where(item => item.Rule == "automation.observe" && item.Action == "Observed")
            .Select(item => item.FrameId).Distinct().Select(id =>
            {
                var path = Path.Combine(directory, $"frame-{id:D6}.png");
                Span<byte> header = stackalloc byte[24];
                using var image = File.OpenRead(path);
                image.ReadExactly(header);
                if (!header[..8].SequenceEqual(new byte[] { 137, 80, 78, 71, 13, 10, 26, 10 }))
                    throw new InvalidDataException($"录制帧不是 PNG：{path}");
                var width = BinaryPrimitives.ReadInt32BigEndian(header[16..20]);
                var height = BinaryPrimitives.ReadInt32BigEndian(header[20..24]);
                if (width <= 0 || height <= 0) throw new InvalidDataException($"录制帧尺寸无效：{path}");
                return new MirrorScenarioFrame(id, width, height, path);
            }).ToArray();
        return new(options, result, events, frames);
    }
}

public interface IMirrorScenarioVision
{
    IReadOnlyList<VisualTarget> FindTargets(PixelFrame frame, IReadOnlyList<ImageQuery> queries, CancellationToken cancellationToken);
    IReadOnlyList<RecognizedText> ReadText(PixelFrame frame, PixelRect? region, int scale, CancellationToken cancellationToken,
        TextPreprocessing preprocessing = TextPreprocessing.None);
    MirrorMapSnapshot ReadMap(PixelFrame frame, PixelPoint bus, CancellationToken cancellationToken);
}

public sealed class MirrorScenarioReplay : IGameVision, IGameInput, IRunClock, IMirrorMapReader
{
    private sealed record Observation(ImageQuery[] Queries, VisualTarget[] Targets);
    private sealed record Ocr(PixelRect? Region, int Scale, RecognizedText[] Text, TextPreprocessing Preprocessing = TextPreprocessing.None);
    private readonly MirrorScenario scenario;
    private readonly RunEvent[] tape;
    private readonly Func<MirrorScenarioFrame, byte[]> pixels;
    private readonly Action<RunEvent>? publish;
    private readonly IMirrorScenarioVision? vision;
    private int cursor;
    private bool violation;
    private GameFrame? latest;
    private CancellationTokenSource? replayCancellation;

    public MirrorScenarioReplay(MirrorScenario scenario, Func<MirrorScenarioFrame, byte[]> pixels,
        Action<RunEvent>? publish = null, IMirrorScenarioVision? vision = null)
    {
        this.scenario = scenario;
        this.pixels = pixels;
        this.publish = publish;
        this.vision = vision;
        tape = scenario.Events.Where(item => item.Rule is "automation.observe" or "automation.ocr" or "mirror.route.map" or "mirror.run.cancelled"
            || item.Action is "Click" or "Key" or "Drag" or "Sent").ToArray();
    }

    public TimeSpan Elapsed { get; private set; }

    public GameSession CreateSession(TimeSpan timeout) => new(this, this, this, Publish, timeout, "Mirror");

    public async Task<RunResult> RunAsync(CancellationToken cancellationToken)
    {
        using var cancellation = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        replayCancellation = cancellation;
        return await new MirrorRunner(CreateSession(MirrorRunner.TimeoutFor(scenario.Options)), this)
            .RunAsync(scenario.Options, cancellation.Token);
    }

    public ScenarioAcceptance Evaluate(RunResult result)
    {
        var observed = !tape.Skip(cursor).Any(item => item.Rule == "automation.observe");
        var actions = !tape.Skip(cursor).Any(item => item.Action is "Click" or "Key" or "Drag" or "Sent");
        var reason = violation ? "scenario.contract-violation"
            : result.Outcome != scenario.ExpectedResult.Outcome ? "scenario.outcome-mismatch"
            : result.Reason != scenario.ExpectedResult.Reason ? "scenario.reason-mismatch"
            : cursor != tape.Length ? "scenario.unconsumed-events" : "scenario.accepted";
        return new(reason == "scenario.accepted", reason, observed, actions);
    }

    public ValueTask<GameFrame> ObserveAsync(IReadOnlyList<ImageQuery> queries, CancellationToken ct)
    {
        CheckCancellation(ct);
        var item = Take("automation.observe", "Observed");
        var observation = Read<Observation>(item);
        if (!queries.SequenceEqual(observation.Queries))
            throw ContractViolation("回放模板查询或顺序与录制不匹配");
        var frame = scenario.Frames.SingleOrDefault(frame => frame.Id == item.FrameId)
            ?? throw ContractViolation($"回放缺少帧 {item.FrameId}");
        var bgra = pixels(frame);
        if (bgra.Length != checked(frame.Width * frame.Height * 4)) throw ContractViolation("回放像素尺寸不匹配");
        var captured = new PixelFrame(new(item.FrameId, frame.Width, frame.Height, 0, Elapsed.Ticks), bgra);
        latest = new(captured, vision is null ? observation.Targets : vision.FindTargets(captured, queries, ct));
        return ValueTask.FromResult(latest);
    }

    public ValueTask<IReadOnlyList<RecognizedText>> ReadTextAsync(GameFrame frame, CancellationToken ct,
        PixelRect? region = null, int scale = 1, TextPreprocessing preprocessing = TextPreprocessing.None)
    {
        CheckFrame(frame.Identity, ct);
        var item = Take("automation.ocr", "Observed", frame.Identity.Id);
        var ocr = Read<Ocr>(item);
        if (ocr.Region != region || ocr.Scale != scale || ocr.Preprocessing != preprocessing)
            throw ContractViolation("回放 OCR 区域、倍率或预处理模式不匹配");
        return ValueTask.FromResult(vision is null ? (IReadOnlyList<RecognizedText>)ocr.Text : vision.ReadText(frame.Pixels, region, scale, ct, preprocessing));
    }

    public MirrorMapSnapshot Read(PixelFrame frame, PixelPoint bus, CancellationToken ct)
    {
        CheckFrame(frame.Identity, ct);
        var item = Take("mirror.route.map", "Progress", frame.Identity.Id);
        var map = Read<MirrorMapSnapshot>(item);
        if (map.Frame.Id != frame.Identity.Id || map.Frame.Width != frame.Identity.Width
            || map.Frame.Height != frame.Identity.Height || vision is null && map.Bus != bus)
            throw ContractViolation("回放图谱与当前帧或巴士坐标不匹配");
        if (vision is null) return map with { Frame = frame.Identity };
        var recognized = vision.ReadMap(frame, bus, ct);
        if (recognized.Frame != frame.Identity || recognized.Bus != bus)
            throw ContractViolation("重识别图谱与当前帧或巴士坐标不匹配");
        return recognized;
    }

    public ValueTask ClickAtAsync(PixelPoint target, FrameIdentity frame, CancellationToken ct) => Input(frame, ct);
    public ValueTask KeyPressAsync(GameKey key, FrameIdentity frame, CancellationToken ct) => Input(frame, ct);
    public ValueTask DragAsync(PixelPoint from, PixelPoint to, TimeSpan duration, FrameIdentity frame, CancellationToken ct) =>
        Input(frame, ct);
    public ValueTask DragPathAsync(IReadOnlyList<PixelPoint> path, TimeSpan duration, FrameIdentity frame, CancellationToken ct) =>
        Input(frame, ct);

    private ValueTask Input(FrameIdentity frame, CancellationToken ct)
    {
        CheckFrame(frame, ct);
        if (cursor >= tape.Length || tape[cursor].Action != "Sent")
        {
            if (cursor == tape.Length && scenario.ExpectedResult.Outcome == RunOutcome.Failed)
                throw new InvalidOperationException(scenario.ExpectedResult.Reason);
            throw ContractViolation("录制动作没有发送完成事件");
        }
        AdvanceClock(tape[cursor]);
        return ValueTask.CompletedTask;
    }

    public ValueTask DelayAsync(TimeSpan duration, CancellationToken ct)
    { CheckCancellation(ct); Elapsed += duration; return ValueTask.CompletedTask; }

    private void Publish(RunEvent item)
    {
        if (item.Rule == "mirror.run.cancelled" && cursor < tape.Length && tape[cursor].Rule == item.Rule)
            Take(item.Rule, item.Action, item.FrameId);
        if (item.Action is "Click" or "Key" or "Drag" or "Sent")
        {
            var expected = Take(item.Rule, item.Action, item.FrameId);
            if (expected.Target != item.Target) throw ContractViolation($"动作 {item.Rule} 的坐标或按键不匹配");
        }
        if (item.Rule is not ("mirror.route.map" or "mirror.route.scan")) publish?.Invoke(item);
    }

    private RunEvent Take(string rule, string action, long? frameId = null)
    {
        if (cursor >= tape.Length) throw ContractViolation($"录制事件已耗尽，仍请求 {rule}/{action}");
        var next = tape[cursor];
        if (next.Rule != rule || next.Action != action || frameId.HasValue && next.FrameId != frameId)
            throw ContractViolation($"录制预期 {next.Rule}/{next.Action}@{next.FrameId}，实际 {rule}/{action}@{frameId}");
        cursor++;
        AdvanceClock(next);
        return next;
    }

    private void AdvanceClock(RunEvent item) => Elapsed = TimeSpan.FromMilliseconds(Math.Max(Elapsed.TotalMilliseconds, item.ElapsedMilliseconds));
    private T Read<T>(RunEvent item)
    {
        try
        {
            return JsonSerializer.Deserialize<T>(item.Detail
                ?? throw ContractViolation($"录制事件 {item.Rule} 缺少详情"), MirrorScenario.Json)
                ?? throw ContractViolation($"录制事件 {item.Rule} 详情为空");
        }
        catch (JsonException) { violation = true; throw; }
    }
    private void CheckFrame(FrameIdentity frame, CancellationToken ct)
    {
        CheckCancellation(ct);
        if (latest?.Identity != frame) throw ContractViolation("回放操作使用了过期帧");
    }
    private void CheckCancellation(CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        if (cursor >= tape.Length || tape[cursor].Rule != "mirror.run.cancelled") return;
        if (replayCancellation is null) throw ContractViolation("取消录制须通过 MirrorScenarioReplay.RunAsync 回放");
        AdvanceClock(tape[cursor]);
        replayCancellation.Cancel();
        throw new OperationCanceledException(replayCancellation.Token);
    }
    private InvalidDataException ContractViolation(string message)
    { violation = true; return new(message); }
}
