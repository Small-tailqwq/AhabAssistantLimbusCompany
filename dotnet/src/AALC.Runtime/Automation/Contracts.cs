using AALC.Core.Features.Daily;
using AALC.Core.Features.Mail;
using AALC.Runtime.Mail;

namespace AALC.Runtime.Automation;

public sealed record ImageQuery(string Asset, double Threshold = 0.8, bool Multiple = false,
    SearchMode Search = SearchMode.Clam);
public sealed record VisualTarget(string Asset, PixelPoint Center, PixelRect Bounds, double Score);
public sealed record RecognizedText(string Text, double Confidence, PixelRect Bounds);
public enum TextPreprocessing { None, FormationOrder }
public sealed record GameFrame(PixelFrame Pixels, IReadOnlyList<VisualTarget> Targets)
{
    public FrameIdentity Identity => Pixels.Identity;
    public double Scale => Identity.Height / 1440.0;
    public VisualTarget? Find(string asset) => Targets.FirstOrDefault(hit => hit.Asset == asset);
    public IReadOnlyList<VisualTarget> FindAll(string asset) => Targets.Where(hit => hit.Asset == asset).ToArray();
    public PixelPoint Point(int x, int y) => new((int)(x * Scale), (int)(y * Scale));
    public PixelRect Region(int left, int top, int right, int bottom) =>
        new((int)(left * Scale), (int)(top * Scale), (int)((right - left) * Scale), (int)((bottom - top) * Scale));
}

public interface IGameSession
{
    TimeSpan Elapsed { get; }
    int Observations { get; }
    ValueTask<GameFrame> ObserveAsync(IReadOnlyList<ImageQuery> queries, CancellationToken cancellationToken);
    ValueTask<GameFrame> ObserveControlsAsync(IReadOnlyList<ImageQuery> queries, CancellationToken cancellationToken) =>
        ObserveAsync(queries, cancellationToken);
    ValueTask<IReadOnlyList<RecognizedText>> ReadTextAsync(GameFrame frame, CancellationToken cancellationToken,
        PixelRect? region = null, int scale = 1, TextPreprocessing preprocessing = TextPreprocessing.None);
    ValueTask ClickAsync(GameFrame frame, PixelPoint target, string rule, CancellationToken cancellationToken);
    ValueTask KeyAsync(GameFrame frame, GameKey key, string rule, CancellationToken cancellationToken);
    ValueTask DragAsync(GameFrame frame, PixelPoint from, PixelPoint to, TimeSpan duration,
        string rule, CancellationToken cancellationToken);
    ValueTask DragPathAsync(GameFrame frame, IReadOnlyList<PixelPoint> path, TimeSpan duration,
        string rule, CancellationToken cancellationToken) => throw new NotSupportedException();
    ValueTask DelayAsync(TimeSpan duration, CancellationToken cancellationToken);
    void Report(string rule, string message);
}

public interface IGameVision
{
    ValueTask<GameFrame> ObserveAsync(IReadOnlyList<ImageQuery> queries, CancellationToken cancellationToken);
    ValueTask<IReadOnlyList<RecognizedText>> ReadTextAsync(GameFrame frame, CancellationToken cancellationToken,
        PixelRect? region = null, int scale = 1, TextPreprocessing preprocessing = TextPreprocessing.None);
}

public interface IGameInput
{
    ValueTask ClickAtAsync(PixelPoint target, FrameIdentity frame, CancellationToken cancellationToken);
    ValueTask KeyPressAsync(GameKey key, FrameIdentity frame, CancellationToken cancellationToken);
    ValueTask DragAsync(PixelPoint from, PixelPoint to, TimeSpan duration, FrameIdentity frame,
        CancellationToken cancellationToken);
    ValueTask DragPathAsync(IReadOnlyList<PixelPoint> path, TimeSpan duration, FrameIdentity frame,
        CancellationToken cancellationToken) => throw new NotSupportedException();
}
