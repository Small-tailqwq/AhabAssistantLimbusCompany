using System.Collections.Concurrent;
using System.IO.Pipes;
using System.Text;
using System.Text.Json;
using AALC.Platform.Windows.DesktopClone;
using AALC.Runtime.DesktopClone;
using AALC.Runtime.Mail;
using AALC.Vision;
using Xunit;

namespace AALC.Core.Tests;

public sealed class CloneProtocolTests
{
    [Fact]
    public void MessagesRoundTrip()
    {
        var payload = CloneProtocol.Serialize("event", CloneProtocol.Encode("镜牢\t第一层\n"));
        var parsed = CloneProtocol.Parse(payload);
        Assert.Equal("event", parsed[0]);
        Assert.Equal("镜牢\t第一层\n", CloneProtocol.Decode(parsed[1]));
    }

    [Theory]
    [InlineData("a\tb")]
    [InlineData("a\nb")]
    [InlineData("a\rb")]
    public void FieldsCannotContainSeparators(string field) =>
        Assert.Throws<ArgumentException>(() => CloneProtocol.Serialize("event", field));

    [Fact]
    public void OversizedMessagesAreRejected() =>
        Assert.Throws<ArgumentException>(() => CloneProtocol.Serialize("event", new string('x', CloneProtocol.MaxMessageBytes)));

    [Fact]
    public void UndecodableTextDoesNotThrow() => Assert.Equal("无法解码远端消息", CloneProtocol.Decode("不是Base64"));
}

public sealed class FramePreviewTests
{
    [Fact]
    public void PreviewFitsTheMessageLimitAndDecodes()
    {
        var pixels = new byte[1280 * 720 * 4];
        new Random(7).NextBytes(pixels);
        var frame = new PixelFrame(new(9, 1280, 720, 0, 0), pixels);
        var encoded = FramePreview.Encode(frame, 2_000_000)!;
        var decoded = FramePreview.Decode(9, encoded);
        Assert.Equal(800, decoded.Identity.Width);
        Assert.Equal(450, decoded.Identity.Height);
        Assert.Null(FramePreview.Encode(frame, 10));
    }
}

public sealed class ClonePipeServerTests
{
    [Fact]
    public async Task ClientsExchangeLinesAndReportTheirIdentity()
    {
        var received = new ConcurrentQueue<string[]>();
        var connected = new TaskCompletionSource<ICloneConnection>(TaskCreationOptions.RunContinuationsAsynchronously);
        var disconnected = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using var server = new ClonePipeServer($"AAALC.test.{Guid.NewGuid():N}");
        server.Start((connection, message) => { received.Enqueue(message); connected.TrySetResult(connection); }, _ => disconnected.TrySetResult());

        using (var client = new NamedPipeClientStream(".", server.PipeName, PipeDirection.InOut, PipeOptions.Asynchronous))
        {
            await client.ConnectAsync(5000);
            // 一次写入两条消息，第二条跨越读缓冲。
            var large = CloneProtocol.Encode(new string('x', 6000));
            await client.WriteAsync(Encoding.UTF8.GetBytes($"hello\trdp-host\t1\nlog\t{large}\n"));
            var connection = await connected.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Equal(Environment.ProcessId, connection.PeerProcessId);
            Assert.Equal(server.CurrentSessionId, connection.PeerSessionId);
            await connection.SendAsync(TimeSpan.FromSeconds(1), "show");
            var buffer = new byte[16];
            var count = await client.ReadAsync(buffer);
            Assert.Equal("show\n", Encoding.UTF8.GetString(buffer, 0, count));
            while (received.Count < 2) await Task.Delay(10);
        }
        await disconnected.Task.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.Equal(["hello", "rdp-host", "1"], received.First());
        Assert.Equal(6000, CloneProtocol.Decode(received.Last()[1]).Length);
    }
}

public sealed class DesktopCloneControllerTests
{
    private const int MainSession = 1;
    private const int ChildSession = 7;
    private static readonly CloneTimings Fast = new()
    {
        Connection = TimeSpan.FromMinutes(1), AutorunRestore = TimeSpan.FromMinutes(1), RunStop = TimeSpan.FromSeconds(.2),
        SessionStop = TimeSpan.FromSeconds(.1), WorkerExit = TimeSpan.FromSeconds(.1), HostLogoff = TimeSpan.FromSeconds(.1),
        Poll = TimeSpan.FromMilliseconds(5)
    };

    private sealed class FakeConnection(int session) : ICloneConnection
    {
        public string? Role { get; set; }
        public int PeerProcessId => 100 + session;
        public int PeerSessionId => session;
        private readonly List<string[]> sent = [];
        public bool Closed { get; private set; }
        public Action<string[]>? OnSend { get; set; }
        public ValueTask SendAsync(TimeSpan timeout, params string[] parts)
        {
            lock (sent) sent.Add(parts);
            OnSend?.Invoke(parts);
            return ValueTask.CompletedTask;
        }
        public void Close() => Closed = true;
        public bool Received(string command)
        {
            lock (sent) return sent.Any(parts => parts[0] == command);
        }
        public string[] Commands()
        {
            lock (sent) return sent.Select(parts => parts[0]).ToArray();
        }
        public string[] Find(string command)
        {
            lock (sent) return sent.Single(parts => parts[0] == command);
        }
    }

    private sealed class FakeProcess : ICloneHostProcess
    {
        private readonly TaskCompletionSource exit = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public bool HasExited => exit.Task.IsCompleted;
        public int ExitCode { get; private set; }
        public bool Terminated { get; private set; }
        public Task WaitForExitAsync(CancellationToken cancellationToken) => exit.Task.WaitAsync(cancellationToken);
        public void Terminate() { Terminated = true; Exit(-1); }
        public void Exit(int code) { ExitCode = code; exit.TrySetResult(); }
        public void Dispose() { }
    }

    private sealed class FakeSystem : ICloneSystem
    {
        private readonly List<string> calls = [];
        // 清理在后台线程继续写入，断言读取副本。
        public string[] Calls { get { lock (calls) return calls.ToArray(); } }
        public void ClearCalls() { lock (calls) calls.Clear(); }
        private void Record(string call) { lock (calls) calls.Add(call); }
        public FakeProcess? Host { get; private set; }
        public CloneCompatibility Compatibility { get; set; } = new([]);
        public ChildSessionProbe Probe { get; set; } = new(null);
        public string? Conflict { get; set; }
        public bool Enabled { get; set; } = true;
        public bool LogoffClears { get; set; } = true;
        public TaskCompletionSource WorkerLaunched { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public string HostCrashLogPath => "crash.txt";
        public CloneCompatibility CheckCompatibility(int? ownedSessionId) => Compatibility;
        public ChildSessionProbe ProbeChildSession() => Probe;
        public bool ChildSessionsEnabled => Enabled;
        public void EnableChildSessions() => Record("enable-child-sessions");
        public void EnableRemoteDesktop(CancellationToken cancellationToken) => Record("enable-rdp");
        public int RdpPort => 3389;
        public IReadOnlyList<string> SuppressAutoruns()
        {
            Record("suppress");
            return [];
        }
        public void RestoreAutoruns() => Record("restore");
        public void LogoffChildSession(int sessionId)
        {
            Record($"logoff {sessionId}");
            if (LogoffClears) Probe = new(null);
        }
        public ICloneHostProcess StartHost(CloneHostStart start)
        {
            Record("start-host");
            return Host = new();
        }
        public void LaunchWorker(CloneWorkerStart start, CancellationToken cancellationToken)
        {
            Record($"launch-worker {start.SessionId}");
            WorkerLaunched.TrySetResult();
        }
        public string? FindGameConflict(int? childSessionId) => Conflict;
    }

    private sealed class FakeTransport : ICloneTransport
    {
        private Action<ICloneConnection, string[]>? message;
        private Action<ICloneConnection>? disconnect;
        private readonly TaskCompletionSource started = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public string PipeName => "pipe";
        public int CurrentSessionId => MainSession;
        public void Start(Action<ICloneConnection, string[]> onMessage, Action<ICloneConnection> onDisconnect)
        {
            message = onMessage;
            disconnect = onDisconnect;
            started.TrySetResult();
        }
        public async Task Deliver(ICloneConnection connection, params string[] parts)
        {
            await started.Task.WaitAsync(TimeSpan.FromSeconds(5));
            message!(connection, parts);
        }
        public void Disconnect(ICloneConnection connection) => disconnect!(connection);
        public void Dispose() { }
    }

    private sealed class Observer : ICloneRunObserver
    {
        public List<RunEvent> Events { get; } = [];
        public List<long> Frames { get; } = [];
        public List<string> Queues { get; } = [];
        public void OnEvent(RunEvent item) => Events.Add(item);
        public void OnFrame(long id, byte[] jpeg) => Frames.Add(id);
        public void OnMirrorQueue(string path) => Queues.Add(path);
    }

    private sealed class Harness : IDisposable
    {
        public FakeSystem System { get; } = new();
        public FakeTransport Transport { get; } = new();
        public FakeConnection Host { get; } = new(MainSession);
        public FakeConnection Worker { get; } = new(ChildSession);
        public DesktopCloneController Controller { get; }
        public List<string> Log { get; } = [];

        public Harness(CloneTimings? timings = null) =>
            Controller = new(System, Transport, message => { lock (Log) Log.Add(message); }, timings ?? Fast);

        public async Task WaitForStartedHost()
        {
            for (var i = 0; i < 500 && System.Host is null; i++) await Task.Delay(2);
            Assert.NotNull(System.Host);
        }

        public async Task ConnectHost()
        {
            await WaitForStartedHost();
            await Transport.Deliver(Host, "hello", CloneProtocol.HostRole, CloneProtocol.Version);
            System.Probe = new(ChildSession);
            await Transport.Deliver(Host, "rdp-connected", ChildSession.ToString());
            await System.WorkerLaunched.Task.WaitAsync(TimeSpan.FromSeconds(5));
        }

        public async Task StartReady()
        {
            var start = Controller.StartAsync(new(), CancellationToken.None);
            await ConnectHost();
            await Transport.Deliver(Worker, "hello", CloneProtocol.WorkerRole, CloneProtocol.Version);
            await Transport.Deliver(Worker, "ready", ChildSession.ToString());
            await start.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Equal(CloneState.Ready, Controller.Snapshot.State);
            Assert.Equal(ChildSession, Controller.Snapshot.SessionId);
        }

        public void Dispose() => Controller.Dispose();
    }

    private static Task WaitUntil(Func<bool> condition) => Task.Run(async () =>
    {
        for (var i = 0; i < 1000; i++)
        {
            if (condition()) return;
            await Task.Delay(5);
        }
        Assert.Fail("条件未在时限内满足");
    });

    [Fact]
    public async Task HealsLeftoverAutorunSuppressionOnCreation()
    {
        using var harness = new Harness();
        Assert.Contains("restore", harness.System.Calls);
    }

    [Fact]
    public async Task StartSuppressesAutorunsBeforeTheHostAndBecomesReady()
    {
        using var harness = new Harness();
        harness.System.ClearCalls();
        await harness.StartReady();
        Assert.Equal(["suppress", "start-host", $"launch-worker {ChildSession}"], harness.System.Calls);
        Assert.True(harness.Controller.Snapshot.IsActive);
    }

    [Fact]
    public async Task AutorunsAreRestoredAfterTheLogonWindow()
    {
        using var harness = new Harness(Fast with { AutorunRestore = TimeSpan.FromMilliseconds(20) });
        harness.System.ClearCalls();
        await harness.StartReady();
        await WaitUntil(() => harness.System.Calls.Contains("restore"));
    }

    [Fact]
    public async Task UnsupportedEnvironmentFailsBeforeAnyHostStarts()
    {
        using var harness = new Harness();
        harness.System.Compatibility = new([new("管理员权限", CloneCheckStatus.Failed, "需要管理员权限")], NeedsElevation: true);
        var error = await Assert.ThrowsAsync<CloneException>(() => harness.Controller.StartAsync(new(), CancellationToken.None));
        Assert.Contains("需要管理员权限", error.Message);
        Assert.Null(harness.System.Host);
        Assert.DoesNotContain("suppress", harness.System.Calls);
        Assert.Equal(CloneState.Error, harness.Controller.Snapshot.State);
    }

    [Fact]
    public async Task FirstEnableAsksForRelogonInsteadOfConnecting()
    {
        using var harness = new Harness();
        harness.System.Enabled = false;
        var error = await Assert.ThrowsAsync<CloneException>(() => harness.Controller.StartAsync(new(), CancellationToken.None));
        Assert.Contains("重新登录", error.Message);
        Assert.Contains("enable-child-sessions", harness.System.Calls);
        Assert.Null(harness.System.Host);
    }

    [Fact]
    public async Task EnablesRemoteDesktopOnlyWhenAsked()
    {
        using var harness = new Harness();
        var start = harness.Controller.StartAsync(new(EnableRemoteDesktop: true), CancellationToken.None);
        await harness.WaitForStartedHost();
        Assert.Contains("enable-rdp", harness.System.Calls);
        await harness.Controller.ShutdownAsync(TimeSpan.FromSeconds(1));
        await Assert.ThrowsAnyAsync<Exception>(() => start.WaitAsync(TimeSpan.Zero));
    }

    [Theory]
    [InlineData("rdp-host", 2)]
    [InlineData("child-session", MainSession)]
    [InlineData("unknown", MainSession)]
    public async Task HelloFromTheWrongSessionIsRejected(string role, int session)
    {
        using var harness = new Harness();
        var start = harness.Controller.StartAsync(new(), CancellationToken.None);
        await harness.ConnectHost();
        var intruder = new FakeConnection(session);
        await harness.Transport.Deliver(intruder, "hello", role, CloneProtocol.Version);
        Assert.True(intruder.Closed);
        Assert.Null(intruder.Role);
        await harness.Controller.ShutdownAsync(TimeSpan.FromSeconds(1));
        await WaitUntil(() => start.IsCompleted || harness.Controller.Snapshot.State == CloneState.Idle);
    }

    [Fact]
    public async Task HelloWithWrongVersionIsRejected()
    {
        using var harness = new Harness();
        var start = harness.Controller.StartAsync(new(), CancellationToken.None);
        await harness.WaitForStartedHost();
        var stale = new FakeConnection(MainSession);
        await harness.Transport.Deliver(stale, "hello", CloneProtocol.HostRole, "0");
        Assert.True(stale.Closed);
        await harness.Controller.ShutdownAsync(TimeSpan.FromSeconds(1));
    }

    [Fact]
    public async Task ReportedSessionMustMatchWhatWindowsReturns()
    {
        using var harness = new Harness();
        var start = harness.Controller.StartAsync(new(), CancellationToken.None);
        await harness.WaitForStartedHost();
        await harness.Transport.Deliver(harness.Host, "hello", CloneProtocol.HostRole, CloneProtocol.Version);
        harness.System.Probe = new(99);
        await harness.Transport.Deliver(harness.Host, "rdp-connected", ChildSession.ToString());
        await Assert.ThrowsAsync<CloneException>(() => start.WaitAsync(TimeSpan.FromSeconds(5)));
        Assert.DoesNotContain(harness.System.Calls, call => call.StartsWith("launch-worker", StringComparison.Ordinal));
    }

    [Fact]
    public async Task ConnectionTimeoutTerminatesTheHost()
    {
        using var harness = new Harness(Fast with { Connection = TimeSpan.FromMilliseconds(50) });
        var start = harness.Controller.StartAsync(new(), CancellationToken.None);
        var error = await Assert.ThrowsAsync<CloneException>(() => start.WaitAsync(TimeSpan.FromSeconds(5)));
        Assert.Contains("未完成登录", error.Message);
        await WaitUntil(() => harness.System.Host is { Terminated: true });
        await WaitUntil(() => !harness.Controller.Snapshot.IsActive);
        Assert.Equal(CloneState.Error, harness.Controller.Snapshot.State);
    }

    [Fact]
    public async Task CancellingStartReleasesTheSession()
    {
        using var harness = new Harness();
        using var cancellation = new CancellationTokenSource();
        var start = harness.Controller.StartAsync(new(), cancellation.Token);
        await harness.WaitForStartedHost();
        cancellation.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => start.WaitAsync(TimeSpan.FromSeconds(5)));
        Assert.True(harness.System.Host!.Terminated);
        Assert.Equal(CloneState.Idle, harness.Controller.Snapshot.State);
    }

    [Fact]
    public async Task RdpFailureAfterRetriesIsReportedWithItsCodes()
    {
        using var harness = new Harness();
        var start = harness.Controller.StartAsync(new(), CancellationToken.None);
        await harness.WaitForStartedHost();
        await harness.Transport.Deliver(harness.Host, "hello", CloneProtocol.HostRole, CloneProtocol.Version);
        await harness.Transport.Deliver(harness.Host, "rdp-retrying", "1", "1", "connect", "2", "12", CloneProtocol.Encode("内部错误"));
        Assert.Contains("1/3", harness.Controller.Snapshot.Status);
        await harness.Transport.Deliver(harness.Host, "rdp-failed", "connect", "2", "12", CloneProtocol.Encode("内部错误"));
        var error = await Assert.ThrowsAsync<CloneException>(() => start.WaitAsync(TimeSpan.FromSeconds(5)));
        Assert.Contains("code=2", error.Message);
        Assert.Contains("extended=12", error.Message);
    }

    [Fact]
    public async Task RunForwardsProgressAndReturnsToReady()
    {
        using var harness = new Harness();
        await harness.StartReady();
        var observer = new Observer();
        var run = harness.Controller.RunAsync(@"D:\request.json", observer, CancellationToken.None);
        await WaitUntil(() => harness.Worker.Received("run"));
        Assert.Equal(@"D:\request.json", CloneProtocol.Decode(harness.Worker.Find("run")[1]));
        Assert.Equal(CloneState.Running, harness.Controller.Snapshot.State);
        var item = new RunEvent("", 1, "Mirror", "mirror.floor", "Progress", null, 1500, "第一层");
        await harness.Transport.Deliver(harness.Worker, "event", CloneProtocol.Encode(JsonSerializer.Serialize(item)));
        await harness.Transport.Deliver(harness.Worker, "frame", "12", Convert.ToBase64String([1, 2, 3]));
        await harness.Transport.Deliver(harness.Worker, "mirror-queue", CloneProtocol.Encode(@"D:\queue.json"));
        await harness.Transport.Deliver(harness.Worker, "result", "Completed", CloneProtocol.Encode("完成"), "40", "1234.5");
        var result = await run.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.Equal(new RunResult(RunOutcome.Completed, "完成", 40, 1234.5), result);
        Assert.Equal(item, observer.Events.Single());
        Assert.Equal(12, observer.Frames.Single());
        Assert.Equal(@"D:\queue.json", observer.Queues.Single());
        Assert.Equal(CloneState.Ready, harness.Controller.Snapshot.State);
    }

    [Fact]
    public async Task GameOutsideTheCloneBlocksTheRun()
    {
        using var harness = new Harness();
        await harness.StartReady();
        harness.System.Conflict = "《边狱公司》在主桌面运行";
        var error = await Assert.ThrowsAsync<CloneException>(() => harness.Controller.RunAsync("r", new Observer(), CancellationToken.None));
        Assert.Contains("主桌面", error.Message);
        Assert.False(harness.Worker.Received("run"));
        Assert.Equal(CloneState.Ready, harness.Controller.Snapshot.State);
    }

    [Fact]
    public async Task CancellingARunAsksTheWorkerToStopCooperatively()
    {
        using var harness = new Harness();
        await harness.StartReady();
        using var cancellation = new CancellationTokenSource();
        harness.Worker.OnSend = parts =>
        {
            if (parts[0] == "stop") _ = harness.Transport.Deliver(harness.Worker, "result", "Cancelled", CloneProtocol.Encode("已停止"), "3", "9");
        };
        var run = harness.Controller.RunAsync("r", new Observer(), cancellation.Token);
        await WaitUntil(() => harness.Worker.Received("run"));
        cancellation.Cancel();
        var result = await run.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.Equal(RunOutcome.Cancelled, result.Outcome);
        Assert.Equal(CloneState.Ready, harness.Controller.Snapshot.State);
        Assert.Contains("分身任务已停止", harness.Controller.Snapshot.Status);
    }

    [Fact]
    public async Task UnresponsiveWorkerDoesNotHoldTheCallerButBlocksNewRuns()
    {
        using var harness = new Harness();
        await harness.StartReady();
        using var cancellation = new CancellationTokenSource();
        var run = harness.Controller.RunAsync("r", new Observer(), cancellation.Token);
        await WaitUntil(() => harness.Worker.Received("run"));
        cancellation.Cancel();
        var result = await run.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.Equal(RunOutcome.Failed, result.Outcome);
        Assert.Equal(CloneState.Running, harness.Controller.Snapshot.State);
        await Assert.ThrowsAsync<CloneException>(() => harness.Controller.RunAsync("r", new Observer(), CancellationToken.None));
    }

    [Fact]
    public async Task LosingTheWorkerFailsTheRunAndCleansUp()
    {
        using var harness = new Harness();
        await harness.StartReady();
        var run = harness.Controller.RunAsync("r", new Observer(), CancellationToken.None);
        await WaitUntil(() => harness.Worker.Received("run"));
        harness.Transport.Disconnect(harness.Worker);
        var result = await run.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.Equal(RunOutcome.Failed, result.Outcome);
        Assert.Contains("意外断开", result.Reason);
        await WaitUntil(() => harness.Controller.Snapshot is { State: CloneState.Error, IsActive: false });
        Assert.Contains("意外断开", harness.Controller.Snapshot.Status);
        Assert.Contains($"logoff {ChildSession}", harness.System.Calls);
    }

    [Fact]
    public async Task UnexpectedHostExitIsReportedWithItsCrashLog()
    {
        using var harness = new Harness();
        await harness.StartReady();
        harness.System.Host!.Exit(3);
        await WaitUntil(() => harness.Controller.Snapshot.Status.Contains("crash.txt", StringComparison.Ordinal));
        Assert.Contains("exit=3", harness.Controller.Snapshot.Status);
    }

    [Fact]
    public async Task ShutdownStopsTheRunThenTheWorkerThenLogsOff()
    {
        using var harness = new Harness();
        await harness.StartReady();
        harness.Worker.OnSend = parts =>
        {
            if (parts[0] == "stop") _ = harness.Transport.Deliver(harness.Worker, "result", "Cancelled", CloneProtocol.Encode("已停止"), "3", "9");
            if (parts[0] == "shutdown") harness.Transport.Disconnect(harness.Worker);
        };
        var run = harness.Controller.RunAsync("r", new Observer(), CancellationToken.None);
        await WaitUntil(() => harness.Worker.Received("run"));
        Assert.True(await harness.Controller.ShutdownAsync(TimeSpan.FromSeconds(2)));
        Assert.Equal(["run", "stop", "shutdown"], harness.Worker.Commands());
        Assert.True(harness.Host.Received("logoff"));
        Assert.Contains($"logoff {ChildSession}", harness.System.Calls);
        Assert.True(harness.System.Host!.Terminated);
        Assert.Equal(CloneState.Idle, harness.Controller.Snapshot.State);
        Assert.False(harness.Controller.Snapshot.IsActive);
        Assert.Equal(RunOutcome.Cancelled, (await run).Outcome);
    }

    [Fact]
    public async Task UnconfirmedLogoffKeepsTheHostAndStaysInError()
    {
        using var harness = new Harness();
        await harness.StartReady();
        harness.System.LogoffClears = false;
        Assert.False(await harness.Controller.ShutdownAsync(TimeSpan.FromSeconds(.3)));
        Assert.False(harness.System.Host!.Terminated);
        Assert.Equal(CloneState.Error, harness.Controller.Snapshot.State);
        Assert.True(harness.Controller.Snapshot.IsActive);
        await Assert.ThrowsAsync<CloneException>(() => harness.Controller.StartAsync(new(), CancellationToken.None));
    }

    [Fact]
    public async Task StaleSessionIsReportedAsNeedingWindowsSignOut()
    {
        using var harness = new Harness();
        await harness.StartReady();
        harness.System.Probe = new(ChildSession, Stale: true);
        Assert.False(await harness.Controller.ShutdownAsync(TimeSpan.FromSeconds(1)));
        Assert.Contains("注销 Windows", harness.Controller.Snapshot.Status);
        Assert.False(harness.Controller.Snapshot.IsActive);
    }

    [Fact]
    public async Task ForeignSessionIsNeverLoggedOff()
    {
        using var harness = new Harness();
        harness.System.Compatibility = new([new("现有会话", CloneCheckStatus.Failed, "检测到不属于本程序的 Child Session")]);
        harness.System.Probe = new(42);
        await Assert.ThrowsAsync<CloneException>(() => harness.Controller.StartAsync(new(), CancellationToken.None));
        await WaitUntil(() => !harness.Controller.Snapshot.IsActive);
        Assert.True(await harness.Controller.ShutdownAsync(TimeSpan.FromSeconds(1)));
        Assert.DoesNotContain(harness.System.Calls, call => call.StartsWith("logoff", StringComparison.Ordinal));
    }

    [Fact]
    public async Task WindowCommandsReachTheHostAndItsEchoUpdatesTheSnapshot()
    {
        using var harness = new Harness();
        await harness.StartReady();
        harness.Controller.ShowWindow(false);
        harness.Controller.SetMuted(true);
        harness.Controller.SetInputBlocked(true);
        await WaitUntil(() => harness.Host.Commands().Count(command => command == "tool-set") == 2 && harness.Host.Received("hide"));
        await harness.Transport.Deliver(harness.Host, "hidden");
        await harness.Transport.Deliver(harness.Host, "tool-state", "mute", "1");
        await harness.Transport.Deliver(harness.Host, "tool-state", "input", "1");
        var snapshot = harness.Controller.Snapshot;
        Assert.False(snapshot.WindowVisible);
        Assert.True(snapshot.Muted);
        Assert.True(snapshot.InputBlocked);
    }

    [Fact]
    public async Task MessagesFromAReplacedConnectionAreIgnored()
    {
        using var harness = new Harness();
        await harness.StartReady();
        var replacement = new FakeConnection(ChildSession);
        await harness.Transport.Deliver(replacement, "hello", CloneProtocol.WorkerRole, CloneProtocol.Version);
        Assert.True(harness.Worker.Closed);
        await harness.Transport.Deliver(harness.Worker, "error", CloneProtocol.Encode("过期"));
        Assert.Equal(CloneState.Ready, harness.Controller.Snapshot.State);
    }

    [Fact]
    public async Task ASecondStartJoinsTheOneInProgress()
    {
        using var harness = new Harness();
        var first = harness.Controller.StartAsync(new(), CancellationToken.None);
        var second = harness.Controller.StartAsync(new(), CancellationToken.None);
        await harness.ConnectHost();
        await harness.Transport.Deliver(harness.Worker, "hello", CloneProtocol.WorkerRole, CloneProtocol.Version);
        await harness.Transport.Deliver(harness.Worker, "ready", ChildSession.ToString());
        await Task.WhenAll(first, second).WaitAsync(TimeSpan.FromSeconds(5));
        Assert.Single(harness.System.Calls, call => call == "start-host");
    }
}
