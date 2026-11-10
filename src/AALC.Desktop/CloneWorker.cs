using System.Buffers;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading.Channels;
using AALC.Core.Features.Mirror;
using AALC.Platform.Windows.Tools;
using AALC.Runtime;
using AALC.Runtime.DesktopClone;
using AALC.Runtime.Mail;
using AALC.Vision;

namespace AALC.Desktop;

/// <summary>
/// 分身内的无窗口进程：Program 在初始化 Avalonia 之前进入这里。任务配置由主程序经文件交付，
/// 事件、预览和结果经管道回报；管道断开说明主程序已退出，此时停止任务并结束进程。
/// </summary>
internal sealed class CloneWorker
{
    private const int MaxForwardedDetail = 8 * 1024;
    private const int MaxPreviewBytes = 47 * 1024;
    private static readonly TimeSpan FrameInterval = TimeSpan.FromSeconds(1);
    private static readonly TimeSpan StopWait = TimeSpan.FromSeconds(3);
    private readonly Channel<string[]> outgoing = Channel.CreateBounded<string[]>(new BoundedChannelOptions(1024)
    {
        FullMode = BoundedChannelFullMode.DropOldest, SingleReader = true
    });
    private readonly string logPath;
    private CancellationTokenSource? cancellation;
    private Task running = Task.CompletedTask;
    private long lastFrame;

    private CloneWorker(string logPath) => this.logPath = logPath;

    public static int Run(string[] args)
    {
        string Argument(string key)
        {
            var index = Array.IndexOf(args, key);
            return index >= 0 && index + 1 < args.Length ? args[index + 1] : throw new ArgumentException($"缺少参数 {key}");
        }
        // 任务计划启动的进程不继承主程序的环境变量，数据根必须显式传入。
        Environment.SetEnvironmentVariable("AALC_DATA_ROOT", Argument("--data-root"));
        var logPath = EvidencePaths.RequireExternalPath(Path.Combine(EvidencePaths.ResolveRoot(), "clone", "logs", $"worker-{DateTime.Now:yyyyMMdd}.log"));
        var worker = new CloneWorker(logPath);
        try
        {
            var expected = int.Parse(Argument("--expected-session-id"), CultureInfo.InvariantCulture);
            var session = Process.GetCurrentProcess().SessionId;
            if (session != expected) throw new InvalidOperationException($"分身内进程运行在错误的会话：expected={expected}，actual={session}");
            return worker.RunAsync(Argument("--clone-pipe"), session).GetAwaiter().GetResult();
        }
        catch (Exception exception)
        {
            worker.Log(exception.ToString());
            return 1;
        }
    }

    private void Log(string message)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(logPath)!);
        File.AppendAllText(logPath, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} [{Environment.ProcessId}] {message}\n");
    }

    private async Task<int> RunAsync(string pipeName, int session)
    {
        using var pipe = new NamedPipeClientStream(".", pipeName, PipeDirection.InOut, PipeOptions.Asynchronous);
        await pipe.ConnectAsync(10_000);
        var writer = Task.Run(() => WriteAsync(pipe));
        Enqueue("hello", CloneProtocol.WorkerRole, CloneProtocol.Version);
        var (primed, detail) = CloneAudio.Prime();
        Enqueue("audio-prime", primed ? "ready" : "failed", CloneProtocol.Encode(detail));
        Enqueue("ready", session.ToString(CultureInfo.InvariantCulture));
        Log($"已连接主程序，会话 {session}");
        try { await ReadCommandsAsync(pipe); }
        catch (IOException exception) { Log($"管道读取结束：{exception.Message}"); }
        cancellation?.Cancel();
        try { await running.WaitAsync(StopWait); }
        catch (TimeoutException) { Log("任务未在收尾时限内结束"); }
        outgoing.Writer.TryComplete();
        try { await writer.WaitAsync(TimeSpan.FromSeconds(1)); }
        catch (Exception exception) when (exception is TimeoutException or IOException) { }
        return 0;
    }

    private async Task WriteAsync(PipeStream pipe)
    {
        await foreach (var message in outgoing.Reader.ReadAllAsync())
        {
            await pipe.WriteAsync(CloneProtocol.Serialize(message));
            await pipe.FlushAsync();
        }
    }

    private void Enqueue(params string[] message) => outgoing.Writer.TryWrite(message);

    private async Task ReadCommandsAsync(PipeStream pipe)
    {
        var buffer = new byte[4096];
        var pending = new ArrayBufferWriter<byte>();
        while (true)
        {
            var count = await pipe.ReadAsync(buffer);
            if (count == 0) return;
            foreach (var value in buffer.AsSpan(0, count))
            {
                if (value != (byte)'\n')
                {
                    pending.Write([value]);
                    if (pending.WrittenCount > CloneProtocol.MaxMessageBytes) throw new InvalidDataException("主程序消息超过长度上限");
                    continue;
                }
                var message = CloneProtocol.Parse(pending.WrittenSpan);
                pending.Clear();
                switch (message)
                {
                    case ["run", var path]: Start(CloneProtocol.Decode(path)); break;
                    case ["stop"]: cancellation?.Cancel(); break;
                    case ["shutdown"]: return;
                }
            }
        }
    }

    private void Start(string requestPath)
    {
        if (!running.IsCompleted)
        {
            Enqueue("error", CloneProtocol.Encode("分身任务已经在运行"));
            return;
        }
        cancellation = new();
        var token = cancellation.Token;
        running = Task.Run(() => ExecuteAsync(requestPath, token), CancellationToken.None);
    }

    private async Task ExecuteAsync(string requestPath, CancellationToken token)
    {
        RunResult result;
        try
        {
            var request = CloneTaskRequest.Load(requestPath);
            File.Delete(requestPath);
            var steam = SteamLocator.FindExecutable() ?? throw new FileNotFoundException("未找到 steam.exe");
            var context = new GameTaskContext(request.RepositoryRoot, request.OcrModelsDirectory, new(request.GameLanguage, request.GameTheme),
                null, steam, SteamLocator.LaunchArguments, Publish, PublishFrame);
            result = request.Kind switch
            {
                CloneTaskRequest.DailyKind => await GameTasks.RunDailyAsync(context, request.Daily ?? throw new InvalidDataException("请求缺少日常配置"), token),
                CloneTaskRequest.MirrorKind => await GameTasks.RunMirrorAsync(context, request.Mirror ?? throw new InvalidDataException("请求缺少镜牢配置"), SaveQueueAsync, token),
                CloneTaskRequest.LaunchKind => await GameTasks.RunLaunchAsync(context,
                    request.Launch ?? throw new InvalidDataException("请求缺少启动计划"),
                    request.Daily ?? throw new InvalidDataException("请求缺少日常配置"),
                    request.Mirror ?? throw new InvalidDataException("请求缺少镜牢配置"), SaveQueueAsync, token),
                _ => throw new InvalidDataException($"未知分身任务 {request.Kind}")
            };
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { result = new(RunOutcome.Cancelled, "已停止", 0, 0); }
        catch (Exception exception)
        {
            Log(exception.ToString());
            result = new(RunOutcome.Failed, exception.Message, 0, 0);
        }
        Log($"任务结束：{result.Outcome} {result.Reason}");
        Enqueue("result", result.Outcome.ToString(), CloneProtocol.Encode(result.Reason),
            result.Observations.ToString(CultureInfo.InvariantCulture), result.ElapsedMilliseconds.ToString(CultureInfo.InvariantCulture));
    }

    private void Publish(RunEvent item)
    {
        if (!RunEventDisplay.IsShown(item)) return;
        if (item.Detail is { Length: > MaxForwardedDetail } detail) item = item with { Detail = detail[..MaxForwardedDetail] + "…" };
        Enqueue("event", CloneProtocol.Encode(JsonSerializer.Serialize(item)));
    }

    private void PublishFrame(PixelFrame frame)
    {
        var now = Stopwatch.GetTimestamp();
        if (Stopwatch.GetElapsedTime(lastFrame, now) < FrameInterval) return;
        lastFrame = now;
        if (FramePreview.Encode(frame, MaxPreviewBytes) is { } encoded)
            Enqueue("frame", frame.Identity.Id.ToString(CultureInfo.InvariantCulture), Convert.ToBase64String(encoded));
    }

    /// <summary>队伍轮换写回配置是主程序的职责，这里只把新顺序交给它。</summary>
    private Task SaveQueueAsync(MirrorTeamOptions[] teams, CancellationToken token)
    {
        var path = EvidencePaths.RequireExternalPath(Path.Combine(EvidencePaths.ResolveRoot(), "clone", "requests", $"queue-{DateTime.Now:yyyyMMdd-HHmmss-fff}.json"));
        File.WriteAllText(path, JsonSerializer.Serialize(teams));
        Enqueue("mirror-queue", CloneProtocol.Encode(path));
        return Task.CompletedTask;
    }
}

/// <summary>RDP 的重定向音频端点是懒创建的；游戏只探测一次音频设备，要先用短静音把端点打开。</summary>
internal static class CloneAudio
{
    private const int SampleRate = 48_000;
    private const short Channels = 2;
    private const short SampleBytes = 2;
    private const int DurationMilliseconds = 200;
    private const uint SndMemory = 0x4;
    private const uint SndNoDefault = 0x2;

    public static (bool Primed, string Detail) Prime()
    {
        var wave = SilentWave();
        for (var attempt = 1; attempt <= 3; attempt++)
        {
            if (PlaySound(wave, 0, SndMemory | SndNoDefault)) return (true, $"attempt={attempt}");
            Thread.Sleep(200);
        }
        return (false, "attempts=3");
    }

    private static byte[] SilentWave()
    {
        var dataSize = SampleRate * DurationMilliseconds / 1000 * Channels * SampleBytes;
        using var stream = new MemoryStream(44 + dataSize);
        using var writer = new BinaryWriter(stream);
        writer.Write("RIFF"u8);
        writer.Write(36 + dataSize);
        writer.Write("WAVEfmt "u8);
        writer.Write(16);
        writer.Write((short)1);
        writer.Write(Channels);
        writer.Write(SampleRate);
        writer.Write(SampleRate * Channels * SampleBytes);
        writer.Write((short)(Channels * SampleBytes));
        writer.Write((short)(SampleBytes * 8));
        writer.Write("data"u8);
        writer.Write(dataSize);
        writer.Write(new byte[dataSize]);
        writer.Flush();
        return stream.ToArray();
    }

    [DllImport("winmm.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool PlaySound(byte[] sound, nint module, uint flags);
}
