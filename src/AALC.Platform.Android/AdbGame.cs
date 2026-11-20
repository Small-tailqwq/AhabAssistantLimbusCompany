using System.Buffers.Binary;
using System.Diagnostics;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using AALC.Core.Automation;
using AALC.Core.Features.Mail;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;

namespace AALC.Platform.Android;

public sealed partial class AdbGame : IAttachedGame
{
    private readonly AdbClient adb;
    private readonly AdbDevice device;
    private readonly FileStream lease;
    private readonly object gate = new();
    private bool busy, disposed;
    private FrameIdentity? last;
    private string? window;
    private static long sequence;

    internal AdbGame(AdbClient adb, AdbDevice device)
    {
        this.adb = adb;
        this.device = device;
        var directory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AAALC", "adb-locks");
        Directory.CreateDirectory(directory);
        var name = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(device.Serial)));
        try { lease = new(Path.Combine(directory, name), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None); }
        catch (IOException e) { throw new IOException("无法独占模拟器，请先停止使用此设备的 AAALC 任务。", e); }
    }

    public async Task EnsureResolutionAsync(Action<string> report, CancellationToken cancellationToken)
    {
        var frame = (await CaptureAsync(cancellationToken)).Identity;
        if (GameResolution.IsTooSmall(frame.Width, frame.Height) || (long)frame.Width * 9 != (long)frame.Height * 16)
            throw new InvalidOperationException("请将模拟器设为 16:9 横屏（至少 1280×720），并全屏运行游戏。");
        report($"模拟器画面 {frame.Width}×{frame.Height}");
    }

    public async ValueTask<PixelFrame> CaptureAsync(CancellationToken cancellationToken)
    {
        using var operation = Enter();
        last = null;
        var focus = await ForegroundAsync(cancellationToken);
        var timestamp = Stopwatch.GetTimestamp();
        var raw = await ScreenshotAsync(cancellationToken);
        var (width, height, offset) = Dimensions(raw);
        if (await ForegroundAsync(cancellationToken) != focus) throw new GameTransientException("截图期间游戏窗口发生变化。");
        var pixels = raw.AsSpan(offset).ToArray();
        for (var i = 0; i < pixels.Length; i += 4)
        {
            (pixels[i], pixels[i + 2]) = (pixels[i + 2], pixels[i]);
            pixels[i + 3] = 255;
        }
        window = focus;
        last = new(Interlocked.Increment(ref sequence), width, height, device.TransportId, timestamp);
        return new(last, pixels);
    }

    public async ValueTask ClickAsync(TemplateHit target, FrameIdentity frame, CancellationToken cancellationToken)
    {
        using var operation = Enter();
        cancellationToken.ThrowIfCancellationRequested();
        if (frame != last || Stopwatch.GetElapsedTime(frame.CapturedAt) > TimeSpan.FromSeconds(5))
            throw new GameTransientException("输入依据的模拟器画面已失效。");
        last = null;
        var (x, y) = target.Center;
        if (x < 0 || y < 0 || x >= frame.Width || y >= frame.Height)
            throw new InvalidOperationException("点击超出模拟器画面。");
        var (width, height, _) = Dimensions(await ScreenshotAsync(cancellationToken));
        if (width != frame.Width || height != frame.Height || await ForegroundAsync(cancellationToken) != window
            || Stopwatch.GetElapsedTime(frame.CapturedAt) > TimeSpan.FromSeconds(5))
            throw new GameTransientException("输入前模拟器画面已变化或过期。");
        await adb.DeviceCommandAsync(device, ["shell", "input", "tap", x.ToString(CultureInfo.InvariantCulture),
            y.ToString(CultureInfo.InvariantCulture)], 65536, cancellationToken);
    }

    // screencap 的原始 RGBA 数据：旧版 12 字节头，新版另有 4 字节色彩空间。
    private Task<byte[]> ScreenshotAsync(CancellationToken token) =>
        adb.DeviceCommandAsync(device, ["exec-out", "screencap"], 64 * 1024 * 1024 + 16, token);

    private static (int Width, int Height, int Offset) Dimensions(byte[] raw)
    {
        if (raw.Length >= 12)
        {
            var w = BinaryPrimitives.ReadInt32LittleEndian(raw);
            var h = BinaryPrimitives.ReadInt32LittleEndian(raw.AsSpan(4));
            var format = BinaryPrimitives.ReadInt32LittleEndian(raw.AsSpan(8));
            if (w is > 0 and <= 8192 && h is > 0 and <= 8192 && format is 1 or 2 && raw.Length - 4 * w * h is 12 or 16)
                return (w, h, raw.Length - 4 * w * h);
        }
        throw new InvalidDataException("模拟器返回的截图尺寸或像素格式无效（需要 RGBA/RGBX 8888）。");
    }

    private async Task<string> ForegroundAsync(CancellationToken token)
    {
        var serial = Encoding.UTF8.GetString(await adb.DeviceCommandAsync(device, ["get-serialno"], 4096, token)).Trim();
        if (serial != device.Serial) throw new InvalidOperationException("模拟器连接已变化，请重新选择。");
        var dump = Encoding.UTF8.GetString(await adb.DeviceCommandAsync(device, ["shell", "dumpsys", "window"], 8 * 1024 * 1024, token));
        var matches = FocusedWindow().Matches(dump);
        if (matches.Count != 1 || !GameWindow().IsMatch(matches[0].Groups[1].Value))
            throw new InvalidOperationException("请将模拟器中的 Limbus Company 置于前台，并关闭系统弹窗。");
        return matches[0].Groups[1].Value;
    }

    [GeneratedRegex(@"(?m)^\s*mCurrentFocus=(.+?)\s*$")]
    private static partial Regex FocusedWindow();
    [GeneratedRegex(@"^Window\{\S+ u\d+ com\.ProjectMoon\.LimbusCompany/[^}]+\}$")]
    private static partial Regex GameWindow();

    private Operation Enter()
    {
        lock (gate)
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            if (busy) throw new GameTransientException("前一次模拟器操作尚未结束。");
            busy = true;
            return new(this);
        }
    }

    private readonly struct Operation(AdbGame game) : IDisposable
    {
        public void Dispose()
        {
            lock (game.gate)
            {
                game.busy = false;
                if (game.disposed) game.lease.Dispose();
            }
        }
    }

    public void Dispose()
    {
        lock (gate)
        {
            disposed = true;
            if (!busy) lease.Dispose();
        }
    }
}
