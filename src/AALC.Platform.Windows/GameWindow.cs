using System.ComponentModel;
using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using AALC.Core.Features.Mail;
using AALC.Runtime.Mail;
using AALC.Core.Features.Daily;
using AALC.Runtime.Daily;
using AALC.Runtime.Automation;

namespace AALC.Platform.Windows;

public sealed record GameWindowInfo(int ProcessId, long Handle, string Title)
{
    public override string ToString() => $"{Title}  ({ProcessId})";
}

public sealed class GameWindow : IScreenCapture, IMailInput, IGameInput, IDisposable
{
    private readonly GameWindowInfo info;
    private readonly Semaphore lease;
    private readonly Socket legacyListener;
    private readonly CancellationTokenSource legacyStopping = new();
    private readonly object gate = new();
    private Task<PixelFrame>? capturing;
    private Task? clicking;
    private long sequence;
    private bool disposed;
    private long lastFrame;

    public static IReadOnlyList<GameWindowInfo> Find()
    {
        var windows = new List<GameWindowInfo>();
        foreach (var process in Process.GetProcessesByName("LimbusCompany"))
        {
            using (process)
                if (process.MainWindowHandle != 0)
                    windows.Add(new(process.Id, process.MainWindowHandle, process.MainWindowTitle));
        }
        return windows;
    }

    /// <param name="firstFrame">重启游戏后沿用上一窗口的帧序号，避免录制帧文件重名。</param>
    public GameWindow(GameWindowInfo selected, long firstFrame = 0)
    {
        info = selected;
        sequence = firstFrame;
        lease = new Semaphore(1, 1, $@"Local\AALC.Next.Game.{info.ProcessId}");
        if (!lease.WaitOne(0))
        {
            lease.Dispose();
            throw new InvalidOperationException("该游戏窗口已有任务运行");
        }
        legacyListener = new(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp);
        try
        {
            ValidateWindow();
            legacyListener.ExclusiveAddressUse = true;
            legacyListener.Bind(new IPEndPoint(IPAddress.Loopback, 62333));
            legacyListener.Listen(5);
            _ = AcceptLegacyInstancesAsync();
        }
        catch (SocketException exception)
        {
            Release();
            throw new InvalidOperationException("旧版 AALC 或其他程序正在使用单实例端口 62333，请先退出后再运行", exception);
        }
        catch { Release(); throw; }
    }

    private async Task AcceptLegacyInstancesAsync()
    {
        var stopping = legacyStopping.Token;
        try
        {
            while (!stopping.IsCancellationRequested)
            {
                using var connection = await legacyListener.AcceptAsync(stopping).ConfigureAwait(false);
                using var receiveTimeout = CancellationTokenSource.CreateLinkedTokenSource(stopping);
                receiveTimeout.CancelAfter(TimeSpan.FromSeconds(1));
                try
                {
                    // 旧 main.py 以 connect/send 成功判断已有实例；消费探测，不执行传入参数。
                    await connection.ReceiveAsync(new byte[1024], SocketFlags.None, receiveTimeout.Token).ConfigureAwait(false);
                }
                catch (OperationCanceledException) when (receiveTimeout.IsCancellationRequested) { }
                catch (SocketException exception) when (exception.SocketErrorCode is SocketError.ConnectionReset or SocketError.ConnectionAborted) { }
            }
        }
        catch (OperationCanceledException) when (stopping.IsCancellationRequested) { }
        catch (ObjectDisposedException) when (stopping.IsCancellationRequested) { }
    }

    public GameWindowInfo Info => info;
    public long LastFrame => Interlocked.Read(ref sequence);

    /// <summary>请求游戏正常退出，与旧版 AALC 一致发送 WM_CLOSE。</summary>
    public void RequestClose() => Native.PostMessage((nint)info.Handle, 0x0010, 0, 0);

    private Native.Rect ValidateWindow()
    {
        var handle = (nint)info.Handle;
        Native.GetWindowThreadProcessId(handle, out var processId);
        if (disposed || processId != info.ProcessId || !Native.IsWindow(handle))
            throw new InvalidOperationException("游戏窗口已失效");
        if (Native.IsIconic(handle)) throw new InvalidOperationException("请先恢复游戏窗口");
        if (!Native.GetClientRect(handle, out var rect)) throw new Win32Exception();
        if (rect.Right <= 0 || rect.Bottom <= 0) throw new InvalidOperationException("游戏窗口尺寸无效");
        return rect;
    }

    /// <summary>模板按帧高缩放，低于 720p 时小图标分数会掉到阈值以下，运行前把窗口调到 720p；更大的窗口保持原样。</summary>
    public async Task EnsureResolutionAsync(Action<string> report, CancellationToken cancellationToken)
    {
        var rect = ValidateWindow();
        if (!GameResolution.IsTooSmall(rect.Right, rect.Bottom)) return;
        report($"游戏窗口 {rect.Right}x{rect.Bottom} 过小，调整为 {GameResolution.DefaultWidth}x{GameResolution.DefaultHeight}");
        var handle = (nint)info.Handle;
        if (Native.IsZoomed(handle)) Native.ShowWindow(handle, 9);
        for (var attempt = 0; attempt < 20; attempt++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Resize(handle, rect);
            await Task.Delay(500, cancellationToken);
            rect = ValidateWindow();
            if (!GameResolution.IsTooSmall(rect.Right, rect.Bottom)) return;
        }
        throw new InvalidOperationException($"无法把游戏窗口调整为 {GameResolution.DefaultWidth}x{GameResolution.DefaultHeight}（当前 {rect.Right}x{rect.Bottom}），请退出全屏后重试");
    }

    private static void Resize(nint handle, Native.Rect client)
    {
        if (!Native.GetWindowRect(handle, out var outer)) throw new Win32Exception();
        var width = outer.Right - outer.Left - client.Right + GameResolution.DefaultWidth;
        var height = outer.Bottom - outer.Top - client.Bottom + GameResolution.DefaultHeight;
        var monitor = new Native.MonitorInfo { Size = 40 };
        if (!Native.GetMonitorInfo(Native.MonitorFromWindow(handle, 2), ref monitor)) throw new Win32Exception();
        // 光标点击要求客户区留在屏幕内；异步提交避免游戏无响应时卡住停止路径。
        var x = Math.Max(monitor.Work.Left, Math.Min(outer.Left, monitor.Work.Right - width));
        var y = Math.Max(monitor.Work.Top, Math.Min(outer.Top, monitor.Work.Bottom - height));
        if (!Native.SetWindowPos(handle, 0, x, y, width, height, 0x4014)) throw new Win32Exception();
    }

    public async ValueTask<PixelFrame> CaptureAsync(CancellationToken cancellationToken)
    {
        Task<PixelFrame> pending;
        lock (gate)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (capturing is { IsCompleted: false }) throw new GameTransientException("前一次截图尚未结束");
            var rect = ValidateWindow();
            var id = Interlocked.Increment(ref sequence);
            pending = capturing = Task.Run(() => Capture(rect, id), CancellationToken.None);
        }
        PixelFrame frame;
        try { frame = await pending.WaitAsync(TimeSpan.FromSeconds(15), cancellationToken); }
        catch (TimeoutException exception) { throw new GameTransientException("等待游戏截图超过 15 秒", exception); }
        lastFrame = frame.Identity.Id;
        return frame;
    }

    private PixelFrame Capture(Native.Rect rect, long id)
    {
        var handle = (nint)info.Handle;
        var dc = Native.GetDC(handle);
        if (dc == 0) throw new Win32Exception();
        nint memory = 0, bitmap = 0, previous = 0;
        try
        {
            memory = Native.CreateCompatibleDC(dc);
            if (memory == 0) throw new Win32Exception();
            var header = new Native.BitmapInfo
            {
                Size = 40, Width = rect.Right, Height = -rect.Bottom, Planes = 1, BitCount = 32
            };
            bitmap = Native.CreateDIBSection(dc, ref header, 0, out var bits, 0, 0);
            if (bitmap == 0) throw new Win32Exception();
            previous = Native.SelectObject(memory, bitmap);
            if (!Native.PrintWindow(handle, memory, 3)) throw new InvalidOperationException("游戏截图失败");
            var bytes = new byte[checked(rect.Right * rect.Bottom * 4)];
            Marshal.Copy(bits, bytes, 0, bytes.Length);
            return new(new(id, rect.Right, rect.Bottom, info.Handle, Stopwatch.GetTimestamp()), bytes);
        }
        finally
        {
            if (previous != 0) Native.SelectObject(memory, previous);
            if (bitmap != 0) Native.DeleteObject(bitmap);
            if (memory != 0) Native.DeleteDC(memory);
            Native.ReleaseDC(handle, dc);
        }
    }

    public ValueTask ClickAsync(TemplateHit target, FrameIdentity frame, CancellationToken cancellationToken) =>
        ClickAtAsync(target.Center, frame, cancellationToken);

    public ValueTask ClickAtAsync(PixelPoint target, FrameIdentity frame, CancellationToken cancellationToken) =>
        RunInput(() => ClickCoreAsync(target, frame, cancellationToken));

    public ValueTask KeyPressAsync(GameKey key, FrameIdentity frame, CancellationToken cancellationToken) =>
        RunInput(() => KeyCoreAsync(key, frame, cancellationToken));

    public ValueTask DragAsync(PixelPoint from, PixelPoint to, TimeSpan duration, FrameIdentity frame,
        CancellationToken cancellationToken) => RunInput(() => DragCoreAsync([from, to], duration, frame, cancellationToken));

    public ValueTask DragPathAsync(IReadOnlyList<PixelPoint> path, TimeSpan duration, FrameIdentity frame,
        CancellationToken cancellationToken) => RunInput(() => DragCoreAsync(path, duration, frame, cancellationToken));

    private ValueTask RunInput(Func<Task> operation)
    {
        lock (gate)
        {
            if (clicking is { IsCompleted: false }) throw new GameTransientException("前一次输入尚未结束");
            clicking = operation();
            return new(clicking);
        }
    }

    private Native.Rect ValidateFrame(FrameIdentity frame, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var rect = ValidateWindow();
        if (frame.Window != info.Handle || frame.Id != lastFrame || frame.Width != rect.Right || frame.Height != rect.Bottom)
            throw new GameTransientException("输入依据的画面已失效");
        if (Stopwatch.GetElapsedTime(frame.CapturedAt) > TimeSpan.FromSeconds(5))
            throw new GameTransientException("识别画面已过期");
        return rect;
    }

    private static void ValidatePoint(PixelPoint point, Native.Rect rect)
    {
        if (point.X < 0 || point.X >= rect.Right || point.Y < 0 || point.Y >= rect.Bottom)
            throw new InvalidOperationException("输入超出游戏客户区");
    }

    private async Task ClickCoreAsync(PixelPoint point, FrameIdentity frame, CancellationToken cancellationToken)
    {
        var rect = ValidateFrame(frame, cancellationToken);
        ValidatePoint(point, rect);
        var position = (nint)((point.Y << 16) | (point.X & 0xffff));
        if (!Native.GetCursorPos(out var original)) throw new Win32Exception();
        var screenPoint = new Native.Point { X = point.X, Y = point.Y };
        if (!Native.ClientToScreen((nint)info.Handle, ref screenPoint)) throw new Win32Exception();
        try
        {
            // BackgroundInput 同时设置真实光标，窗口消息中的坐标不足以替代这个契约。
            MoveCursor(screenPoint.X, screenPoint.Y);
            Send(0x0006, 1, 0);
            cancellationToken.ThrowIfCancellationRequested();
            try
            {
                Send(0x0201, 0, position);
                await Task.Delay(40, cancellationToken);
            }
            finally
            {
                Send(0x0202, 0, position);
                // BackgroundInput 同步分支抬起后仍停留 10 ms，再恢复光标。
                await Task.Delay(10, CancellationToken.None);
            }
        }
        finally
        {
            RestoreCursor(original, new Native.Point { X = screenPoint.X - point.X, Y = screenPoint.Y - point.Y }, rect);
        }
    }

    private async Task KeyCoreAsync(GameKey key, FrameIdentity frame, CancellationToken cancellationToken)
    {
        ValidateFrame(frame, cancellationToken);
        uint code = key switch { GameKey.Escape => 0x1B, GameKey.Enter => 0x0D, GameKey.P => 0x50, GameKey.Space => 0x20,
            GameKey.Up => 0x26, GameKey.Down => 0x28, GameKey.Right => 0x27, GameKey.W => 0x57,
            _ => throw new ArgumentOutOfRangeException(nameof(key)) };
        var parameter = 1u | ((Native.MapVirtualKey(code, 0) & 0xff) << 16);
        if (key is GameKey.Up or GameKey.Down or GameKey.Right) parameter |= 0x01000000;
        Send(0x0006, 1, 0);
        cancellationToken.ThrowIfCancellationRequested();
        try
        {
            Send(0x0100, code, (nint)parameter);
            await Task.Delay(15, cancellationToken);
        }
        finally { Send(0x0101, code, unchecked((nint)(int)(parameter | 0xC0000000u))); }
    }

    private async Task DragCoreAsync(IReadOnlyList<PixelPoint> path, TimeSpan duration, FrameIdentity frame,
        CancellationToken cancellationToken)
    {
        var rect = ValidateFrame(frame, cancellationToken);
        if (path.Count < 2) throw new ArgumentException("拖动路径至少需要两个点", nameof(path));
        foreach (var point in path) ValidatePoint(point, rect);
        if (duration <= TimeSpan.Zero || duration > TimeSpan.FromSeconds(5))
            throw new ArgumentOutOfRangeException(nameof(duration));
        if (!Native.GetCursorPos(out var original)) throw new Win32Exception();
        var origin = new Native.Point();
        if (!Native.ClientToScreen((nint)info.Handle, ref origin)) throw new Win32Exception();
        var current = path[0];
        nint position() => (nint)((current.Y << 16) | (current.X & 0xffff));
        try
        {
            MoveCursor(origin.X + current.X, origin.Y + current.Y);
            Send(0x0006, 1, 0);
            cancellationToken.ThrowIfCancellationRequested();
            try
            {
                Send(0x0201, 0, position());
                await Task.Delay(10, cancellationToken);
                var steps = Math.Max(1, (int)(duration.TotalMilliseconds / (10 * (path.Count - 1))));
                for (var segment = 1; segment < path.Count; segment++)
                {
                    var from = path[segment - 1]; var to = path[segment];
                    for (var step = 1; step <= steps; step++)
                    {
                        cancellationToken.ThrowIfCancellationRequested();
                        current = new(from.X + (to.X - from.X) * step / steps, from.Y + (to.Y - from.Y) * step / steps);
                        MoveCursor(origin.X + current.X, origin.Y + current.Y);
                        await Task.Delay(10, cancellationToken);
                    }
                }
                await Task.Delay(TimeSpan.FromMilliseconds(Math.Max(500, duration.TotalMilliseconds * 0.3)), cancellationToken);
            }
            finally
            {
                Send(0x0202, 0, position());
                await Task.Delay(10, CancellationToken.None);
            }
        }
        finally
        {
            RestoreCursor(original, origin, rect);
        }
    }

    private void RestoreCursor(Native.Point original, Native.Point origin, Native.Rect client)
    {
        // 恢复到卡片上会再次触发真实光标悬停，遮住选择反馈；游戏内光标停到左上空白处。
        if (original.X >= origin.X && original.X < origin.X + client.Right
            && original.Y >= origin.Y && original.Y < origin.Y + client.Bottom)
            original = new Native.Point { X = origin.X + 1, Y = origin.Y + 1 };
        // 恢复失败不影响已发送的输入，也不能盖掉 finally 外正在传播的原始异常。
        // 点击已经送达，这里的消息未确认不能让调用方以为点击失败而重做。
        Native.SetCursorPos(original.X, original.Y);
        Native.SendMessageTimeout((nint)info.Handle, 0x0200, 0, 0, 3, 1500, out _);
    }

    private static void MoveCursor(int x, int y)
    {
        if (!Native.SetCursorPos(x, y)) throw new GameInputBlockedException("系统拒绝移动光标，前台可能是管理员权限窗口");
    }

    private void Send(uint message, nuint wParam, nint lParam)
    {
        // 换页后画面已推进，消息确认仍可能超过 250 ms；这里等待原消息，不重复发送点击。
        if (Native.SendMessageTimeout((nint)info.Handle, message, wParam, lParam, 3, 1500, out _) == 0)
        {
            var error = Marshal.GetLastWin32Error();
            throw new GameTransientException($"游戏窗口输入未确认：消息 0x{message:X4}，错误 {error}，等待上限 1500 ms",
                new Win32Exception(error));
        }
    }

    public void Dispose()
    {
        lock (gate)
        {
            if (disposed) return;
            disposed = true;
            // 原生截图和点击清理完成前保留两种租约，禁止其他运行器接管。
            var pending = new Task?[] { capturing, clicking }.OfType<Task>().Where(task => !task.IsCompleted).ToArray();
            if (pending.Length > 0)
                _ = Task.WhenAll(pending).ContinueWith(completed =>
                {
                    _ = completed.Exception;
                    Release();
                }, TaskScheduler.Default);
            else Release();
        }
    }

    private void Release()
    {
        legacyStopping.Cancel();
        legacyListener.Dispose();
        lease.Release();
        lease.Dispose();
    }

    private static class Native
    {
        [StructLayout(LayoutKind.Sequential)] internal struct Rect { public int Left, Top, Right, Bottom; }
        [StructLayout(LayoutKind.Sequential)] internal struct Point { public int X, Y; }
        [StructLayout(LayoutKind.Sequential)] internal struct MonitorInfo { public uint Size; public Rect Monitor, Work; public uint Flags; }
        [StructLayout(LayoutKind.Sequential)] internal struct BitmapInfo
        {
            public uint Size; public int Width, Height; public ushort Planes, BitCount;
            public uint Compression, SizeImage; public int XPelsPerMeter, YPelsPerMeter;
            public uint ClrUsed, ClrImportant, Colors;
        }
        [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool IsWindow(nint window);
        [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool IsIconic(nint window);
        [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool IsZoomed(nint window);
        [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool ShowWindow(nint window, int command);
        [DllImport("user32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool GetClientRect(nint window, out Rect rect);
        [DllImport("user32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool GetWindowRect(nint window, out Rect rect);
        [DllImport("user32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool SetWindowPos(nint window, nint after, int x, int y, int width, int height, uint flags);
        [DllImport("user32.dll")] internal static extern nint MonitorFromWindow(nint window, uint flags);
        [DllImport("user32.dll", EntryPoint = "GetMonitorInfoW", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool GetMonitorInfo(nint monitor, ref MonitorInfo info);
        [DllImport("user32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool GetCursorPos(out Point point);
        [DllImport("user32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool ClientToScreen(nint window, ref Point point);
        [DllImport("user32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool SetCursorPos(int x, int y);
        [DllImport("user32.dll")] internal static extern uint GetWindowThreadProcessId(nint window, out uint processId);
        [DllImport("user32.dll", SetLastError = true)] internal static extern nint GetDC(nint window);
        [DllImport("user32.dll")] internal static extern int ReleaseDC(nint window, nint dc);
        [DllImport("user32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool PrintWindow(nint window, nint dc, uint flags);
        [DllImport("gdi32.dll", SetLastError = true)] internal static extern nint CreateCompatibleDC(nint dc);
        [DllImport("gdi32.dll", SetLastError = true)] internal static extern nint CreateDIBSection(nint dc, ref BitmapInfo info, uint usage, out nint bits, nint section, uint offset);
        [DllImport("gdi32.dll")] internal static extern nint SelectObject(nint dc, nint value);
        [DllImport("gdi32.dll")] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool DeleteObject(nint value);
        [DllImport("gdi32.dll")] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool DeleteDC(nint dc);
        [DllImport("user32.dll", SetLastError = true)] internal static extern nint SendMessageTimeout(nint window, uint message, nuint wParam, nint lParam, uint flags, uint timeout, out nuint result);
        [DllImport("user32.dll")] internal static extern uint MapVirtualKey(uint code, uint mapType);
        [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool PostMessage(nint window, uint message, nuint wParam, nint lParam);
    }
}

