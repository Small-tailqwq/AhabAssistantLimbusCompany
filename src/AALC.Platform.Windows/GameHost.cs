using System.Diagnostics;
using AALC.Core.Features.Daily;
using AALC.Core.Features.Mail;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;

namespace AALC.Platform.Windows;

/// <summary>
/// 持有当前游戏窗口，负责在任务前拉起游戏，以及运行中关闭并重启游戏后接回新窗口。
/// 启动与关闭方式与旧版 AALC 一致：优先本地 exe，否则 Steam 协议；先请求正常退出，超时再结束进程。
/// </summary>
public sealed class GameHost : IScreenCapture, IMailInput, IGameInput, IGameRestarter, IDisposable
{
    private const string SteamUrl = "steam://rungameid/1973530";
    private static readonly TimeSpan CloseTimeout = TimeSpan.FromSeconds(30);
    private static readonly TimeSpan LaunchTimeout = TimeSpan.FromMinutes(3);
    private static readonly TimeSpan StableWindow = TimeSpan.FromSeconds(3);
    private readonly string executable;
    private readonly string arguments;
    private readonly Action<string> report;
    private GameWindow window;

    private GameHost(GameWindow window, string executable, string arguments, Action<string> report, bool launched)
    {
        this.window = window;
        this.executable = executable;
        this.arguments = arguments;
        this.report = report;
        Launched = launched;
    }

    public GameWindowInfo Info => window.Info;
    /// <summary>游戏由本次打开时启动，任务需要先从标题页进入主界面。</summary>
    public bool Launched { get; }

    /// <summary>使用已选窗口；窗口不存在时先启动游戏。</summary>
    /// <param name="arguments">启动参数；分身内用 steam.exe 的 -applaunch 启动，以复用 Steam 登录态。</param>
    public static async Task<GameHost> OpenAsync(GameWindowInfo? selected, string executable, Action<string> report,
        CancellationToken cancellationToken, string arguments = "")
    {
        var current = selected is not null && GameWindow.Find().Contains(selected) ? selected : GameWindow.Find().FirstOrDefault();
        var launched = current is null;
        if (current is null)
        {
            Launch(executable, arguments, report);
            current = await WaitForWindowAsync(cancellationToken);
        }
        return new(new GameWindow(current), executable, arguments, report, launched);
    }

    public async ValueTask RestartAsync(CancellationToken cancellationToken)
    {
        var previous = window;
        var lastFrame = previous.LastFrame;
        var processId = previous.Info.ProcessId;
        previous.RequestClose();
        previous.Dispose();
        await CloseAsync(processId, cancellationToken);
        Launch(executable, arguments, report);
        window = new GameWindow(await WaitForWindowAsync(cancellationToken), lastFrame);
        await EnsureResolutionAsync(cancellationToken);
    }

    public Task EnsureResolutionAsync(CancellationToken cancellationToken) => window.EnsureResolutionAsync(report, cancellationToken);

    public static async Task CloseAsync(GameWindowInfo selected, Action<string> report, CancellationToken cancellationToken)
    {
        using var host = new GameHost(new GameWindow(selected), "", "", report, false);
        host.window.RequestClose();
        await host.CloseAsync(selected.ProcessId, cancellationToken);
    }

    private async Task CloseAsync(int processId, CancellationToken cancellationToken)
    {
        Process process;
        try { process = Process.GetProcessById(processId); }
        catch (ArgumentException) { return; }
        using (process)
        {
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeout.CancelAfter(CloseTimeout);
            try { await process.WaitForExitAsync(timeout.Token); }
            catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
            {
                report("等待游戏正常退出超时，结束游戏进程");
                process.Kill();
                await process.WaitForExitAsync(cancellationToken);
            }
        }
    }

    private static void Launch(string executable, string arguments, Action<string> report)
    {
        if (!string.IsNullOrWhiteSpace(executable) && File.Exists(executable))
        {
            Process.Start(new ProcessStartInfo(executable, arguments) { UseShellExecute = true, WorkingDirectory = Path.GetDirectoryName(executable)! })?.Dispose();
            report(arguments.Length == 0 ? "使用本地路径启动游戏" : $"使用 {Path.GetFileName(executable)} 启动游戏");
        }
        else
        {
            Process.Start(new ProcessStartInfo(SteamUrl) { UseShellExecute = true })?.Dispose();
            report("使用 Steam 启动游戏");
        }
    }

    private static async Task<GameWindowInfo> WaitForWindowAsync(CancellationToken cancellationToken)
    {
        var deadline = Stopwatch.GetTimestamp() + (long)(LaunchTimeout.TotalSeconds * Stopwatch.Frequency);
        GameWindowInfo? candidate = null;
        var seen = 0L;
        while (Stopwatch.GetTimestamp() < deadline)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var found = GameWindow.Find().FirstOrDefault();
            if (found is null || found != candidate) { candidate = found; seen = Stopwatch.GetTimestamp(); }
            else if (Stopwatch.GetElapsedTime(seen) >= StableWindow) return found;
            await Task.Delay(500, cancellationToken);
        }
        throw new TimeoutException("启动游戏后三分钟内未出现游戏窗口");
    }

    public ValueTask<PixelFrame> CaptureAsync(CancellationToken cancellationToken) => window.CaptureAsync(cancellationToken);
    public ValueTask ClickAsync(TemplateHit target, FrameIdentity frame, CancellationToken cancellationToken) =>
        window.ClickAsync(target, frame, cancellationToken);
    public ValueTask ClickAtAsync(PixelPoint target, FrameIdentity frame, CancellationToken cancellationToken) =>
        window.ClickAtAsync(target, frame, cancellationToken);
    public ValueTask KeyPressAsync(GameKey key, FrameIdentity frame, CancellationToken cancellationToken) =>
        window.KeyPressAsync(key, frame, cancellationToken);
    public ValueTask DragAsync(PixelPoint from, PixelPoint to, TimeSpan duration, FrameIdentity frame,
        CancellationToken cancellationToken) => window.DragAsync(from, to, duration, frame, cancellationToken);
    public ValueTask DragPathAsync(IReadOnlyList<PixelPoint> path, TimeSpan duration, FrameIdentity frame,
        CancellationToken cancellationToken) => window.DragPathAsync(path, duration, frame, cancellationToken);

    public void Dispose() => window.Dispose();
}
