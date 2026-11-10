using System.IO.Pipes;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace AALC.Runtime.Agent;

public sealed record AgentRequest(string Operation, JsonElement Arguments);
public sealed record AgentResponse(JsonElement? Value = null, string? Error = null);
public sealed class AgentUnavailableException(string message) : InvalidOperationException(message);

/// <summary>每个 profile 一个当前用户管道；每次连接只处理一个有界请求。</summary>
public static class AgentPipe
{
    public const int MaxMessageBytes = 16 * 1024 * 1024;
    public static string Name(string profile) => "AAALC.Agent." + Convert.ToHexString(SHA256.HashData(
        Encoding.UTF8.GetBytes(Path.TrimEndingDirectorySeparator(Path.GetFullPath(profile)).ToUpperInvariant())))[..24];

    public static async Task WriteAsync<T>(Stream stream, T value, CancellationToken ct)
    {
        var bytes = JsonSerializer.SerializeToUtf8Bytes(value);
        if (bytes.Length > MaxMessageBytes) throw new InvalidDataException("Agent 消息超过大小上限");
        await stream.WriteAsync(BitConverter.GetBytes(bytes.Length), ct);
        await stream.WriteAsync(bytes, ct);
        await stream.FlushAsync(ct);
    }

    public static async Task<T> ReadAsync<T>(Stream stream, CancellationToken ct)
    {
        var header = new byte[4];
        await stream.ReadExactlyAsync(header, ct);
        var length = BitConverter.ToInt32(header);
        if (length is < 1 or > MaxMessageBytes) throw new InvalidDataException("Agent 消息长度无效");
        var bytes = new byte[length];
        await stream.ReadExactlyAsync(bytes, ct);
        return JsonSerializer.Deserialize<T>(bytes) ?? throw new InvalidDataException("Agent 消息为空");
    }

    public static async Task<JsonElement> CallAsync(string profile, string operation, object arguments, CancellationToken ct)
    {
        using var pipe = new NamedPipeClientStream(".", Name(profile), PipeDirection.InOut, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
        try { await pipe.ConnectAsync(3000, ct); }
        catch (TimeoutException) { throw new AgentUnavailableException("未连接到 AAALC，请先调用 aalc_open 或启动使用同一 profile 的桌面端"); }
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(TimeSpan.FromSeconds(45));
        await WriteAsync(pipe, new AgentRequest(operation, JsonSerializer.SerializeToElement(arguments)), timeout.Token);
        var response = await ReadAsync<AgentResponse>(pipe, timeout.Token);
        if (response.Error is { } error) throw new InvalidOperationException(error);
        return response.Value ?? throw new InvalidDataException("AAALC 返回了空响应");
    }
}

public sealed class AgentPipeServer : IDisposable
{
    private readonly CancellationTokenSource stopping = new();
    private readonly NamedPipeServerStream first;
    private readonly string name;
    private readonly Func<AgentRequest, CancellationToken, Task<object>> dispatch;
    public Task Completion { get; }

    public AgentPipeServer(string profile, Func<AgentRequest, CancellationToken, Task<object>> dispatch)
    {
        name = AgentPipe.Name(profile);
        this.dispatch = dispatch;
        // FirstPipeInstance 防止同一 profile 的多个桌面实例随机接收命令。
        first = Create(PipeOptions.FirstPipeInstance);
        Completion = ServeAsync();
    }

    private NamedPipeServerStream Create(PipeOptions extra = PipeOptions.None) => new(name, PipeDirection.InOut, 5,
        PipeTransmissionMode.Byte, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly | extra);

    private async Task ServeAsync()
    {
        var listener = first;
        var clients = new List<Task>();
        try
        {
            while (!stopping.IsCancellationRequested)
            {
                await listener.WaitForConnectionAsync(stopping.Token);
                var connected = listener;
                // 始终保留一个监听实例，截图等待期间仍能读取状态和请求停止。
                listener = Create();
                clients.RemoveAll(task => task.IsCompletedSuccessfully);
                clients.Add(HandleAsync(connected));
                if (clients.Count >= 4) await Task.WhenAny(clients).WaitAsync(stopping.Token);
            }
        }
        catch (OperationCanceledException) when (stopping.IsCancellationRequested) { }
        catch (ObjectDisposedException) when (stopping.IsCancellationRequested) { }
        finally
        {
            listener.Dispose();
            await Task.WhenAll(clients);
        }
    }

    private async Task HandleAsync(NamedPipeServerStream pipe)
    {
        using (pipe)
        using (var timeout = CancellationTokenSource.CreateLinkedTokenSource(stopping.Token))
        {
            timeout.CancelAfter(TimeSpan.FromSeconds(45));
            try
            {
                var request = await AgentPipe.ReadAsync<AgentRequest>(pipe, timeout.Token);
                AgentResponse response;
                try { response = new(JsonSerializer.SerializeToElement(await dispatch(request, timeout.Token))); }
                catch (Exception exception) { response = new(Error: exception.Message); }
                await AgentPipe.WriteAsync(pipe, response, timeout.Token);
            }
            catch (Exception exception) when (exception is IOException or OperationCanceledException or JsonException or InvalidDataException) { }
        }
    }

    public void Dispose() => stopping.Cancel();
}
