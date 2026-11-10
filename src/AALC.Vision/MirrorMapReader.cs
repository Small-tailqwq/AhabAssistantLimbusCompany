using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using AALC.Core.Automation;
using AALC.Core.Features.Mirror;
using AALC.Runtime.Mail;
using AALC.Runtime.Mirror;
using AALC.Runtime;
using Microsoft.ML.OnnxRuntime;
using Microsoft.ML.OnnxRuntime.Tensors;
using OpenCvSharp;

namespace AALC.Vision;

public sealed class MirrorMapReader : IMirrorMapReader, IDisposable
{
    private readonly InferenceSession model;
    private readonly string? learningDirectory;
    private readonly string? recordingDirectory;
    private readonly string modelSource;
    private readonly string modelSha256;
    private MapLearningSample? pendingSample;
    private string? firstSampleSha256;

    private sealed record MapLearningSample(byte[] Image, string Sha256, MirrorMapSnapshot Prediction, string[] Reasons);

    public MirrorMapReader(string modelPath, string? learningDirectory = null, string? recordingDirectory = null)
    {
        modelSource = Path.GetFullPath(modelPath);
        var bytes = File.ReadAllBytes(modelSource);
        modelSha256 = Convert.ToHexStringLower(SHA256.HashData(bytes));
        this.learningDirectory = learningDirectory is null ? null : EvidencePaths.RequireExternalPath(learningDirectory);
        this.recordingDirectory = recordingDirectory is null ? null : EvidencePaths.RequireExternalPath(recordingDirectory);
        model = new(bytes);
        if (this.recordingDirectory is not null)
        {
            Directory.CreateDirectory(this.recordingDirectory);
            using var identity = new FileStream(Path.Combine(this.recordingDirectory, "map-model.json"), FileMode.CreateNew);
            JsonSerializer.Serialize(identity, new { modelSha256, modelSource, modelIdentitySource = "runtime-model-bytes" });
        }
    }

    public MirrorMapSnapshot Read(PixelFrame frame, PixelPoint bus, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (frame.Bgra.Length != checked(frame.Identity.Width * frame.Identity.Height * 4))
            throw new InvalidDataException("地图帧缓冲区尺寸不匹配");
        using var bgra = new Mat(frame.Identity.Height, frame.Identity.Width, MatType.CV_8UC4);
        Marshal.Copy(frame.Bgra, 0, bgra.Data, frame.Bgra.Length);
        using var bgr = new Mat();
        Cv2.CvtColor(bgra, bgr, ColorConversionCodes.BGRA2BGR);
        var nodes = DetectNodes(bgr, bus, frame.Identity.Height / 1440.0, cancellationToken);
        using var gray = TemplateMatcher.Gray(frame);
        using var detector = LineSegmentDetector.Create(LineSegmentDetectorModes.RefineNone);
        detector.Detect(gray, out Vec4f[] lines, out _, out _, out _);
        cancellationToken.ThrowIfCancellationRequested();
        var scale = frame.Identity.Height / 1440.0;
        var connections = Connect(nodes, bus, lines, scale, cancellationToken);
        if (!connections.Any(edge => edge.From == MirrorMapSnapshot.BusId))
        {
            var source = new PixelPoint(bus.X, bus.Y + (int)(50 * scale));
            var unknown = WarningRingCandidates(bgr, bus, nodes, scale, cancellationToken)
                .Where(node => Connected(source, node.Center, lines, scale)).Take(2).ToArray();
            if (unknown.Length == 1)
            {
                var node = unknown[0] with { Id = nodes.Count };
                nodes = [.. nodes, node];
                connections = [.. connections, new(MirrorMapSnapshot.BusId, node.Id)];
            }
        }
        var snapshot = new MirrorMapSnapshot(frame.Identity, bus, nodes, connections);
        CollectLearningSample(bgr, snapshot);
        return snapshot;
    }

    private void CollectLearningSample(Mat bgr, MirrorMapSnapshot snapshot)
    {
        if (learningDirectory is null) return;
        var reasons = new List<string>();
        if (!snapshot.Connections.Any(edge => edge.From == MirrorMapSnapshot.BusId)) reasons.Add("no-bus-connection");
        if (snapshot.Nodes.Any(node => node.Kind == MirrorNodeKind.Unknown)) reasons.Add("unknown-node");
        if (reasons.Count == 0)
        {
            CompleteLearningSegment();
            return;
        }
        Cv2.ImEncode(".png", bgr, out var png);
        var sample = new MapLearningSample(png, Convert.ToHexStringLower(SHA256.HashData(png)), snapshot, reasons.ToArray());
        if (firstSampleSha256 is null)
        {
            SaveLearningSample(sample);
            firstSampleSha256 = sample.Sha256;
        }
        pendingSample = sample;
    }

    public void CompleteLearningSegment()
    {
        if (pendingSample is { } sample && sample.Sha256 != firstSampleSha256) SaveLearningSample(sample);
        pendingSample = null;
        firstSampleSha256 = null;
    }

    private void SaveLearningSample(MapLearningSample sample)
    {
        var directory = EvidencePaths.RequireExternalPath(learningDirectory!);
        Directory.CreateDirectory(directory);
        var imageName = sample.Sha256 + ".png";
        var imagePath = Path.Combine(directory, imageName);
        if (File.Exists(imagePath))
        {
            if (Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(imagePath))) != sample.Sha256)
                throw new InvalidDataException("地图学习样本图片与SHA256文件名不符");
        }
        else
        {
            using var image = new FileStream(imagePath, FileMode.CreateNew);
            image.Write(sample.Image);
        }
        var metadataPath = Path.Combine(directory, sample.Sha256 + ".json");
        var metadata = File.Exists(metadataPath) ? JsonNode.Parse(File.ReadAllText(metadataPath))!.AsObject()
            : new JsonObject { ["imageSha256"] = sample.Sha256, ["image"] = imageName,
                ["annotationStatus"] = "pending", ["observations"] = new JsonArray() };
        var observations = metadata["observations"]!.AsArray();
        var observation = JsonSerializer.SerializeToNode(new
        {
            frameId = sample.Prediction.Frame.Id,
            source = recordingDirectory is null ? "runtime:MirrorMapReader" : Path.Combine(recordingDirectory, "events.jsonl"),
            sourceImage = recordingDirectory is null ? null : Path.Combine(recordingDirectory, $"frame-{sample.Prediction.Frame.Id:D6}.png"),
            prediction = sample.Prediction, predictionStatus = "pending", triggerReasons = sample.Reasons,
            modelSha256, modelSource, modelIdentitySource = "runtime-model-bytes"
        });
        if (observations.Any(existing => JsonNode.DeepEquals(existing, observation))) return;
        observations.Add(observation);
        var temporary = metadataPath + "." + Guid.NewGuid().ToString("N") + ".tmp";
        using (var file = new FileStream(temporary, FileMode.CreateNew))
            JsonSerializer.Serialize(file, metadata, new JsonSerializerOptions { WriteIndented = true });
        File.Move(temporary, metadataPath, true);
    }

    private static IReadOnlyList<MirrorRouteNode> WarningRingCandidates(Mat bgr, PixelPoint bus,
        IReadOnlyList<MirrorRouteNode> known, double scale, CancellationToken ct)
    {
        using var hsv = new Mat();
        Cv2.CvtColor(bgr, hsv, ColorConversionCodes.BGR2HSV);
        using var colored = new Mat();
        Cv2.InRange(hsv, new Scalar(0, 100, 110), new Scalar(35, 255, 255), colored);
        using var mask = new Mat();
        colored.ConvertTo(mask, MatType.CV_32FC1, 1.0 / 255);
        var rx = Math.Max(1, (int)Math.Round(164 * scale));
        var ry = Math.Max(1, (int)Math.Round(110 * scale));
        using var annulus = new Mat(ry * 2 + 1, rx * 2 + 1, MatType.CV_32FC1, Scalar.All(0));
        using var core = new Mat(annulus.Size(), MatType.CV_32FC1, Scalar.All(0));
        var ringPixels = 0; var corePixels = 0;
        for (var y = -ry; y <= ry; y++)
            for (var x = -rx; x <= rx; x++)
            {
                var radius = Math.Pow(x / (136 * scale), 2) + Math.Pow(y / (90 * scale), 2);
                if (radius >= .82 * .82 && radius <= 1.12 * 1.12) { annulus.Set(y + ry, x + rx, 1f); ringPixels++; }
                if (radius <= .6 * .6) { core.Set(y + ry, x + rx, 1f); corePixels++; }
            }
        annulus.ConvertTo(annulus, MatType.CV_32FC1, 1.0 / ringPixels);
        core.ConvertTo(core, MatType.CV_32FC1, 1.0 / corePixels);
        using var ringResponse = new Mat();
        using var coreResponse = new Mat();
        Cv2.Filter2D(mask, ringResponse, MatType.CV_32FC1, annulus);
        Cv2.Filter2D(mask, coreResponse, MatType.CV_32FC1, core);
        using var scores = new Mat();
        Cv2.Subtract(ringResponse, coreResponse, scores);
        var left = Math.Clamp(Math.Max(rx, bus.X + (int)(90 * scale)), 0, bgr.Width);
        var right = Math.Clamp(bgr.Width - rx, left, bgr.Width);
        var top = Math.Clamp((int)(300 * scale), 0, bgr.Height);
        var bottom = Math.Clamp((int)(1160 * scale), top, bgr.Height);
        if (left == right || top == bottom) return [];
        using (var region = new Mat(scores, new Rect(0, 0, bgr.Width, top))) region.SetTo(Scalar.All(0));
        using (var region = new Mat(scores, new Rect(0, bottom, bgr.Width, bgr.Height - bottom))) region.SetTo(Scalar.All(0));
        using (var region = new Mat(scores, new Rect(0, top, left, bottom - top))) region.SetTo(Scalar.All(0));
        using (var region = new Mat(scores, new Rect(right, top, bgr.Width - right, bottom - top))) region.SetTo(Scalar.All(0));
        var candidates = new List<MirrorRouteNode>();
        while (true)
        {
            ct.ThrowIfCancellationRequested();
            Cv2.MinMaxLoc(scores, out _, out var score, out _, out var point);
            if (score < .16) break;
            var x1 = Math.Max(0, point.X - (int)(140 * scale));
            var y1 = Math.Max(0, point.Y - (int)(90 * scale));
            using (var suppressed = new Mat(scores, new Rect(x1, y1,
                Math.Min(bgr.Width, point.X + (int)(140 * scale) + 1) - x1,
                Math.Min(bgr.Height, point.Y + (int)(90 * scale) + 1) - y1))) suppressed.SetTo(Scalar.All(0));
            if (coreResponse.At<float>(point.Y, point.X) > .2 || known.Any(node =>
                Math.Abs(node.Center.X - point.X) < 100 * scale && Math.Abs(node.Center.Y - point.Y) < 75 * scale)) continue;
            var coloredCounts = new int[4];
            var counts = new int[4];
            for (var y = -ry; y <= ry; y++)
                for (var x = -rx; x <= rx; x++)
                {
                    if (annulus.At<float>(y + ry, x + rx) == 0) continue;
                    var horizontal = x < 0 ? 0 : 1;
                    var vertical = y < 0 ? 2 : 3;
                    counts[horizontal]++; counts[vertical]++;
                    if (colored.At<byte>(point.Y + y, point.X + x) == 0) continue;
                    coloredCounts[horizontal]++; coloredCounts[vertical]++;
                }
            if (Enumerable.Range(0, 4).Any(index => coloredCounts[index] < counts[index] * .1)) continue;
            // WARNING 环只确认这种节点外观；节点类别仍未知，是否可达由原有线段覆盖判断。
            candidates.Add(new(0, MirrorNodeKind.Unknown, new(point.X, point.Y),
                new(point.X - (int)(136 * scale), point.Y - (int)(90 * scale), (int)(272 * scale), (int)(180 * scale)), score));
        }
        return candidates;
    }

    private IReadOnlyList<MirrorRouteNode> DetectNodes(Mat bgr, PixelPoint bus, double scale, CancellationToken ct)
    {
        var length = Math.Max(bgr.Width, bgr.Height);
        using var square = new Mat(length, length, MatType.CV_8UC3, Scalar.All(0));
        using (var area = new Mat(square, new Rect(0, 0, bgr.Width, bgr.Height))) bgr.CopyTo(area);
        using var resized = new Mat();
        Cv2.Resize(square, resized, new Size(640, 640));
        var tensor = new DenseTensor<float>(new[] { 1, 3, 640, 640 });
        var data = tensor.Buffer.Span;
        var row = new byte[640 * 3];
        for (var y = 0; y < 640; y++)
        {
            ct.ThrowIfCancellationRequested();
            Marshal.Copy(resized.Ptr(y), row, 0, row.Length);
            for (var x = 0; x < 640; x++)
                for (var channel = 0; channel < 3; channel++)
                    // Python 的 PIL RGB 截图经过 swapRB 后实际输入 BGR。
                    data[channel * 640 * 640 + y * 640 + x] = row[x * 3 + channel] * (1f / 255f);
        }
        using var run = new RunOptions();
        using var cancellation = ct.Register(() => run.Terminate = true);
        IDisposableReadOnlyCollection<DisposableNamedOnnxValue> inference;
        try
        {
            inference = model.Run([NamedOnnxValue.CreateFromTensor(model.InputMetadata.Keys.First(), tensor)],
                model.OutputMetadata.Keys.ToArray(), run);
        }
        catch (OnnxRuntimeException) when (ct.IsCancellationRequested)
        {
            throw new OperationCanceledException(ct);
        }
        using var outputs = inference;
        ct.ThrowIfCancellationRequested();
        var predictions = outputs.First().AsTensor<float>();
        if (predictions.Rank != 3 || predictions.Dimensions[0] != 1 || predictions.Dimensions[1] != 11)
            throw new InvalidDataException("地图模型输出必须为 [1,11,N] 的七类节点");
        var candidates = new List<MirrorRouteNode>();
        var ratio = length / 640.0;
        for (var index = 0; index < predictions.Dimensions[2]; index++)
        {
            var kind = 0;
            for (var candidate = 1; candidate < 7; candidate++)
                if (predictions[0, candidate + 4, index] > predictions[0, kind + 4, index]) kind = candidate;
            var score = predictions[0, kind + 4, index];
            if (!float.IsFinite(score) || score < .25) continue;
            var x = predictions[0, 0, index] * ratio;
            var y = predictions[0, 1, index] * ratio;
            var width = predictions[0, 2, index] * ratio;
            var height = predictions[0, 3, index] * ratio;
            if (!double.IsFinite(x + y + width + height) || width <= 0 || height <= 0) continue;
            var center = new PixelPoint((int)x, (int)y);
            if (center.X < 0 || center.X >= bgr.Width || center.Y < 0 || center.Y >= bgr.Height) continue;
            candidates.Add(new(0, (MirrorNodeKind)kind, center,
                new((int)(x - width / 2), (int)(y - height / 2), (int)width, (int)height), score));
        }
        var kept = new List<MirrorRouteNode>();
        foreach (var candidate in candidates.OrderByDescending(candidate => candidate.Score))
            if (!kept.Any(node => Overlap(node.Bounds, candidate.Bounds) > .4)) kept.Add(candidate);
        return kept.Where(node => node.Center.X >= bus.X + 50 * scale).OrderBy(node => node.Center.X)
            .ThenBy(node => node.Center.Y).Select((node, index) => node with { Id = index }).ToArray();
    }

    private static double Overlap(PixelRect a, PixelRect b)
    {
        var intersection = (double)Math.Max(0, Math.Min(a.Right, b.Right) - Math.Max(a.X, b.X))
            * Math.Max(0, Math.Min(a.Bottom, b.Bottom) - Math.Max(a.Y, b.Y));
        return intersection / ((double)a.Width * a.Height + (double)b.Width * b.Height - intersection);
    }

    private static IReadOnlyList<MirrorRouteConnection> Connect(IReadOnlyList<MirrorRouteNode> nodes,
        PixelPoint bus, IReadOnlyList<Vec4f> lines, double scale, CancellationToken ct)
    {
        var columns = new List<List<MirrorRouteNode>>();
        foreach (var node in nodes.OrderBy(node => node.Center.X))
        {
            if (columns.Count == 0 || node.Center.X - columns[^1].Average(value => value.Center.X) > 80 * scale)
                columns.Add([]);
            columns[^1].Add(node);
        }
        // 巴士模板中心高于所在车道，实际连接从其下方延伸。
        var source = new[] { new MirrorRouteNode(MirrorMapSnapshot.BusId, MirrorNodeKind.Battle,
            new(bus.X, bus.Y + (int)(50 * scale)), new(), 1) };
        var edges = new List<MirrorRouteConnection>();
        foreach (var column in columns)
        {
            ct.ThrowIfCancellationRequested();
            foreach (var from in source)
                foreach (var to in column)
                    if (Connected(from.Center, to.Center, lines, scale)) edges.Add(new(from.Id, to.Id));
            source = column.ToArray();
        }
        return edges;
    }

    private static bool Connected(PixelPoint from, PixelPoint to, IReadOnlyList<Vec4f> lines, double scale)
    {
        var dx = (double)to.X - from.X; var dy = (double)to.Y - from.Y;
        var distance = Math.Sqrt(dx * dx + dy * dy);
        // 默认缩放列距约为512*scale，只连邻近列，避免中间节点漏检时沿直线跨列。
        if (dx <= 80 * scale || dx > 640 * scale || distance == 0) return false;
        var ux = dx / distance; var uy = dy / distance;
        var intervals = new List<(double Start, double End)>();
        foreach (var line in lines)
        {
            var lx = line.Item2 - line.Item0; var ly = line.Item3 - line.Item1;
            var lineLength = Math.Sqrt(lx * lx + ly * ly);
            // 路径上的双箭头会把可见直线切成短段，仍按共线覆盖长度核验。
            if (lineLength < 20 * scale || Math.Abs(lx * ux + ly * uy) / lineLength < .98) continue;
            var perpendicularA = Math.Abs((line.Item0 - from.X) * uy - (line.Item1 - from.Y) * ux);
            var perpendicularB = Math.Abs((line.Item2 - from.X) * uy - (line.Item3 - from.Y) * ux);
            if (Math.Max(perpendicularA, perpendicularB) > 22 * scale) continue;
            var a = (line.Item0 - from.X) * ux + (line.Item1 - from.Y) * uy;
            var b = (line.Item2 - from.X) * ux + (line.Item3 - from.Y) * uy;
            var start = Math.Max(distance * .12, Math.Min(a, b));
            var end = Math.Min(distance * .88, Math.Max(a, b));
            if (end > start) intervals.Add((start, end));
        }
        var coverage = 0.0; var lastEnd = 0.0;
        foreach (var interval in intervals.OrderBy(interval => interval.Start))
        {
            coverage += Math.Max(0, interval.End - Math.Max(lastEnd, interval.Start));
            lastEnd = Math.Max(lastEnd, interval.End);
        }
        return coverage >= distance * .35;
    }

    public void Dispose()
    {
        try { CompleteLearningSegment(); }
        finally { model.Dispose(); }
    }
}
