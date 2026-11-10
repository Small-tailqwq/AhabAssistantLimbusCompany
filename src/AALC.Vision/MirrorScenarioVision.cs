using System.Runtime.InteropServices;
using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;
using AALC.Runtime.Replay;
using OpenCvSharp;

namespace AALC.Vision;

public sealed class MirrorScenarioVision : IMirrorScenarioVision, IDisposable
{
    private readonly TemplateMatcher matcher;
    private readonly PageTextReader text;
    private readonly string mapModel;
    private readonly Dictionary<(PixelRect?, int, TextPreprocessing), IReadOnlyList<RecognizedText>> textCache = [];
    private PixelFrame? cachedTextFrame;
    private MirrorMapReader? maps;

    public MirrorScenarioVision(string repositoryRoot, string? modelsDirectory = null, TemplateOptions? options = null)
    {
        matcher = new(repositoryRoot, options ?? new());
        text = new(modelsDirectory ?? Path.Combine(repositoryRoot, "assets", "models", "ocr"));
        mapModel = Path.Combine(repositoryRoot, "assets", "model", "best.onnx");
    }

    public IReadOnlyList<VisualTarget> FindTargets(PixelFrame frame, IReadOnlyList<ImageQuery> queries, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        using var gray = TemplateMatcher.Gray(frame);
        var targets = new List<VisualTarget>();
        foreach (var query in queries)
        {
            cancellationToken.ThrowIfCancellationRequested();
            targets.AddRange(matcher.Find(gray, query));
        }
        cancellationToken.ThrowIfCancellationRequested();
        return targets;
    }

    public IReadOnlyList<RecognizedText> ReadText(PixelFrame frame, PixelRect? region, int scale, CancellationToken cancellationToken,
        TextPreprocessing preprocessing = TextPreprocessing.None)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (!ReferenceEquals(cachedTextFrame, frame))
        {
            textCache.Clear();
            cachedTextFrame = frame;
        }
        var key = (region, scale, preprocessing);
        if (!textCache.TryGetValue(key, out var result))
        {
            result = text.Read(frame, region, scale, cancellationToken, preprocessing);
            textCache[key] = result;
        }
        return result;
    }

    public MirrorMapSnapshot ReadMap(PixelFrame frame, PixelPoint bus, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        maps ??= new(mapModel);
        return maps.Read(frame, bus, cancellationToken);
    }

    public static byte[] ReadPixels(MirrorScenarioFrame frame)
    {
        using var bgr = Cv2.ImRead(frame.ImagePath);
        if (bgr.Empty() || bgr.Width != frame.Width || bgr.Height != frame.Height)
            throw new InvalidDataException($"录制帧读取失败或尺寸改变：{frame.ImagePath}");
        using var bgra = new Mat();
        Cv2.CvtColor(bgr, bgra, ColorConversionCodes.BGR2BGRA);
        var bytes = new byte[checked(frame.Width * frame.Height * 4)];
        Marshal.Copy(bgra.Data, bytes, 0, bytes.Length);
        return bytes;
    }

    public void Dispose()
    {
        maps?.Dispose();
        text.Dispose();
        matcher.Dispose();
    }
}
