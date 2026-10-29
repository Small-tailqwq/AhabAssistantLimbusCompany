using AALC.Runtime;
using System.Runtime.InteropServices;
using AALC.Core.Features.Daily;
using AALC.Runtime.Daily;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;
using OpenCvSharp;

namespace AALC.Vision;

public sealed class GameObserver(IScreenCapture capture, TemplateMatcher matcher, string modelsDirectory,
    string? recordingDirectory = null) : IGameVision, IDisposable
{
    private readonly string? recordingPath = recordingDirectory is null ? null : EvidencePaths.RequireExternalPath(recordingDirectory);
    private readonly PageTextReader text = new(modelsDirectory);
    private readonly Dictionary<(long, PixelRect?, int, TextPreprocessing), IReadOnlyList<RecognizedText>> textCache = [];
    public event Action<PixelFrame>? FrameCaptured;

    public async ValueTask<GameFrame> ObserveAsync(IReadOnlyList<ImageQuery> queries, CancellationToken cancellationToken)
    {
        var frame = await capture.CaptureAsync(cancellationToken);
        cancellationToken.ThrowIfCancellationRequested();
        textCache.Clear();
        if (recordingPath is not null)
        {
            var directory = EvidencePaths.RequireExternalPath(recordingPath);
            Directory.CreateDirectory(directory);
            using var bgra = new Mat(frame.Identity.Height, frame.Identity.Width, MatType.CV_8UC4);
            Marshal.Copy(frame.Bgra, 0, bgra.Data, frame.Bgra.Length);
            using var bgr = new Mat();
            Cv2.CvtColor(bgra, bgr, ColorConversionCodes.BGRA2BGR);
            Cv2.ImWrite(EvidencePaths.RequireExternalPath(Path.Combine(directory, $"frame-{frame.Identity.Id:D6}.png")), bgr);
        }
        FrameCaptured?.Invoke(frame);
        using var gray = TemplateMatcher.Gray(frame);
        var hits = new List<VisualTarget>();
        foreach (var query in queries)
        {
            cancellationToken.ThrowIfCancellationRequested();
            hits.AddRange(matcher.Find(gray, query));
        }
        return new(frame, hits);
    }

    public ValueTask<IReadOnlyList<RecognizedText>> ReadTextAsync(GameFrame frame, CancellationToken cancellationToken,
        PixelRect? region = null, int scale = 1, TextPreprocessing preprocessing = TextPreprocessing.None)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var key = (frame.Identity.Id, region, scale, preprocessing);
        if (!textCache.TryGetValue(key, out var result))
        {
            result = text.Read(frame.Pixels, region, scale, cancellationToken, preprocessing);
            textCache[key] = result;
        }
        return ValueTask.FromResult(result);
    }

    public void Dispose() => text.Dispose();
}
