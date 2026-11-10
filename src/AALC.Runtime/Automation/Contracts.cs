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
    /// <summary>关闭并重新启动游戏；不支持重启或次数已用完时返回 false。</summary>
    ValueTask<bool> RestartGameAsync(string reason, CancellationToken cancellationToken) => ValueTask.FromResult(false);
    bool CanRestartGame => false;
    /// <summary>为维护等待等计划外停留延长任务时限。</summary>
    void ExtendDeadline(TimeSpan duration) { }
}

/// <summary>观察中遇到不可恢复的游戏状态并已重启游戏；调用方应回到主界面后从未完成的步骤继续。</summary>
public sealed class GameRestartedException(string reason) : Exception(reason);

/// <summary>系统拒绝移动真实光标，输入未生效；通常在高权限窗口占据前台时出现，可稍后重试。</summary>
public sealed class GameInputBlockedException(string reason) : Exception(reason);

/// <summary>截图或输入的瞬时失败：画面过期、截图未返回、上一次截图或输入未结束、窗口消息未确认。
/// 游戏本身未必异常；输入抛出时不保证已生效，调用方应重新观察并按当前页面接续，不能假定动作已完成。</summary>
public sealed class GameTransientException(string reason, Exception? inner = null) : Exception(reason, inner);

public interface IGameRestarter
{
    /// <summary>返回时新游戏窗口已可截图和输入。</summary>
    ValueTask RestartAsync(CancellationToken cancellationToken);
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
