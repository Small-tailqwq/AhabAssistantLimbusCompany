using System.ComponentModel;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using AALC.Runtime.DesktopClone;

namespace AALC.Platform.Windows.DesktopClone;

/// <summary>仅当前用户可连的命名管道。分身内进程以受限令牌连接，服务端以管理员运行，所以按用户 SID 授权。</summary>
public sealed class ClonePipeServer : ICloneTransport
{
    private readonly CancellationTokenSource stopping = new();
    private readonly List<PipeConnection> connections = [];
    private Action<ICloneConnection, string[]>? onMessage;
    private Action<ICloneConnection>? onDisconnect;
    private bool started;

    public ClonePipeServer(string? pipeName = null, Action<string>? log = null)
    {
        PipeName = pipeName ?? $"AAALC.v1.user-{WindowsIdentity.GetCurrent().User}.root";
        this.log = log ?? (_ => { });
    }

    private readonly Action<string> log;
    public string PipeName { get; }
    public int CurrentSessionId => Environment.ProcessId is var id && Native.ProcessIdToSessionId((uint)id, out var session) ? (int)session : -1;

    public void Start(Action<ICloneConnection, string[]> message, Action<ICloneConnection> disconnect)
    {
        if (started) return;
        started = true;
        onMessage = message;
        onDisconnect = disconnect;
        _ = Task.Run(AcceptAsync);
    }

    private static PipeSecurity Security()
    {
        var security = new PipeSecurity();
        security.SetAccessRuleProtection(true, false);
        security.AddAccessRule(new(new SecurityIdentifier(WellKnownSidType.NetworkSid, null), PipeAccessRights.FullControl, AccessControlType.Deny));
        security.AddAccessRule(new(WindowsIdentity.GetCurrent().User!, PipeAccessRights.FullControl, AccessControlType.Allow));
        return security;
    }

    private async Task AcceptAsync()
    {
        var token = stopping.Token;
        while (!token.IsCancellationRequested)
        {
            NamedPipeServerStream? pipe = null;
            try
            {
                pipe = NamedPipeServerStreamAcl.Create(PipeName, PipeDirection.InOut, NamedPipeServerStream.MaxAllowedServerInstances,
                    PipeTransmissionMode.Byte, PipeOptions.Asynchronous, CloneProtocol.MaxMessageBytes, CloneProtocol.MaxMessageBytes, Security());
                await pipe.WaitForConnectionAsync(token).ConfigureAwait(false);
                var connection = new PipeConnection(pipe);
                pipe = null;
                lock (connections) connections.Add(connection);
                _ = Task.Run(() => ReadAsync(connection, token), CancellationToken.None);
            }
            catch (OperationCanceledException) when (token.IsCancellationRequested) { pipe?.Dispose(); return; }
            catch (Exception exception)
            {
                pipe?.Dispose();
                log($"命名管道监听失败：{exception.Message}");
                // 持续失败（同名管道被占用）时退避，避免忙循环。
                try { await Task.Delay(1000, token).ConfigureAwait(false); }
                catch (OperationCanceledException) { return; }
            }
        }
    }

    private async Task ReadAsync(PipeConnection connection, CancellationToken token)
    {
        var buffer = new byte[4096];
        var pending = new List<byte>();
        try
        {
            while (true)
            {
                var count = await connection.ReadAsync(buffer, token).ConfigureAwait(false);
                if (count == 0) break;
                pending.AddRange(buffer.AsSpan(0, count));
                if (pending.Count > CloneProtocol.MaxMessageBytes) throw new InvalidDataException("桌面分身消息超过长度上限");
                int end;
                while ((end = pending.IndexOf((byte)'\n')) >= 0)
                {
                    var line = pending.GetRange(0, end).ToArray();
                    pending.RemoveRange(0, end + 1);
                    if (line.Length > 0) onMessage!(connection, CloneProtocol.Parse(line));
                }
            }
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { }
        catch (Exception exception) when (exception is IOException or ObjectDisposedException) { log($"读取管道结束：pid={connection.PeerProcessId} {exception.Message}"); }
        catch (Exception exception) { log($"处理管道消息失败：pid={connection.PeerProcessId} {exception}"); }
        finally
        {
            connection.Close();
            lock (connections) connections.Remove(connection);
            onDisconnect!(connection);
        }
    }

    public void Dispose()
    {
        stopping.Cancel();
        PipeConnection[] open;
        lock (connections) open = connections.ToArray();
        foreach (var connection in open) connection.Close();
    }

    private sealed class PipeConnection : ICloneConnection
    {
        private readonly NamedPipeServerStream pipe;
        private readonly SemaphoreSlim writing = new(1, 1);

        public PipeConnection(NamedPipeServerStream pipe)
        {
            this.pipe = pipe;
            if (!Native.GetNamedPipeClientProcessId(pipe.SafePipeHandle, out var processId)) throw new Win32Exception();
            PeerProcessId = (int)processId;
            PeerSessionId = Native.ProcessIdToSessionId(processId, out var session) ? (int)session : -1;
        }

        public string? Role { get; set; }
        public int PeerProcessId { get; }
        public int PeerSessionId { get; }

        public ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken token) => pipe.ReadAsync(buffer, token);

        public async ValueTask SendAsync(TimeSpan timeout, params string[] parts)
        {
            var payload = CloneProtocol.Serialize(parts);
            using var limit = new CancellationTokenSource(timeout);
            await writing.WaitAsync(limit.Token).ConfigureAwait(false);
            try
            {
                await pipe.WriteAsync(payload, limit.Token).ConfigureAwait(false);
                await pipe.FlushAsync(limit.Token).ConfigureAwait(false);
            }
            finally { writing.Release(); }
        }

        public void Close() => pipe.Dispose();
    }

    private static class Native
    {
        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool GetNamedPipeClientProcessId(Microsoft.Win32.SafeHandles.SafePipeHandle pipe, out uint clientProcessId);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool ProcessIdToSessionId(uint processId, out uint sessionId);
    }
}
