using AALC.Runtime.DesktopClone;
using AALC.Runtime.Mail;

var failures = 0;
await CheckShutdownDuringStartup();
await CheckRunExclusion();
return failures == 0 ? 0 : 1;

async Task CheckShutdownDuringStartup()
{
    var system = new FakeSystem();
    var transport = new FakeTransport();
    using var controller = new DesktopCloneController(system, transport, _ => { }, Fast());
    var start = controller.StartAsync(new(), CancellationToken.None);
    var otherStart = controller.StartAsync(new(), CancellationToken.None);
    await system.HostStarted.Task.WaitAsync(TimeSpan.FromSeconds(5));
    var stopped = await controller.ShutdownAsync(TimeSpan.FromSeconds(1));
    try { await Task.WhenAll(start, otherStart).WaitAsync(TimeSpan.FromSeconds(5)); }
    catch (OperationCanceledException) { }
    catch (TimeoutException) { }
    var pass = stopped && start.IsCanceled && otherStart.IsCanceled;
    Console.WriteLine($"{(pass ? "PASS" : "FAIL")} ShutdownCompletesStart: shutdown={stopped}, state={controller.Snapshot.State}, startCancelled={start.IsCanceled}, otherStartCancelled={otherStart.IsCanceled}");
    if (!pass) failures++;
}

async Task CheckRunExclusion()
{
    var system = new FakeSystem();
    var transport = new FakeTransport();
    using var controller = new DesktopCloneController(system, transport, _ => { }, Fast());
    var start = controller.StartAsync(new(), CancellationToken.None);
    await system.HostStarted.Task.WaitAsync(TimeSpan.FromSeconds(5));
    var host = new FakeConnection(1);
    transport.Deliver(host, "hello", CloneProtocol.HostRole, CloneProtocol.Version);
    system.Probe = new(2);
    transport.Deliver(host, "rdp-connected", "2");
    await system.WorkerStarted.Task.WaitAsync(TimeSpan.FromSeconds(5));
    var worker = new FakeConnection(2);
    transport.Deliver(worker, "hello", CloneProtocol.WorkerRole, CloneProtocol.Version);
    transport.Deliver(worker, "ready", "2");
    await start;
    var first = controller.RunAsync("first", new Observer(), default);
    var second = controller.RunAsync("second", new Observer(), default);
    var rejected = false;
    try { if (second.IsCompleted) await second; }
    catch (CloneException) { rejected = true; }
    var pass = rejected && worker.Runs == 1 && controller.Snapshot.State == CloneState.Running;
    Console.WriteLine($"{(pass ? "PASS" : "FAIL")} SingleActiveRun: secondRejected={rejected}, runMessages={worker.Runs}");
    if (!pass) failures++;
    transport.Deliver(worker, "result", "Completed", CloneProtocol.Encode("done"), "1", "1");
    await controller.ShutdownAsync(TimeSpan.FromSeconds(1));
    _ = first.Exception;
}

static CloneTimings Fast() => new()
{
    Connection = TimeSpan.FromMinutes(1), AutorunRestore = TimeSpan.FromMinutes(1),
    RunStop = TimeSpan.FromMilliseconds(20), SessionStop = TimeSpan.FromMilliseconds(20),
    WorkerExit = TimeSpan.FromMilliseconds(20), HostLogoff = TimeSpan.FromMilliseconds(20), Poll = TimeSpan.FromMilliseconds(1)
};

sealed class FakeProcess : ICloneHostProcess
{
    private readonly TaskCompletionSource exit = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public bool HasExited => exit.Task.IsCompleted;
    public int ExitCode => 0;
    public Task WaitForExitAsync(CancellationToken ct) => exit.Task.WaitAsync(ct);
    public void Terminate() => exit.TrySetResult();
    public void Dispose() { }
}
sealed class FakeSystem : ICloneSystem
{
    public TaskCompletionSource HostStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public TaskCompletionSource WorkerStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public ChildSessionProbe Probe { get; set; } = new(null);
    public string HostCrashLogPath => "unused";
    public bool ChildSessionsEnabled => true;
    public int RdpPort => 3389;
    public CloneCompatibility CheckCompatibility(int? ownedSessionId) => new([]);
    public ChildSessionProbe ProbeChildSession() => Probe;
    public void EnableChildSessions() { }
    public void EnableRemoteDesktop(CancellationToken ct) { }
    public IReadOnlyList<string> SuppressAutoruns() => [];
    public void RestoreAutoruns() { }
    public void LogoffChildSession(int id) => Probe = new(null);
    public ICloneHostProcess StartHost(CloneHostStart start) { HostStarted.TrySetResult(); return new FakeProcess(); }
    public void LaunchWorker(CloneWorkerStart start, CancellationToken ct) => WorkerStarted.TrySetResult();
    public string? FindGameConflict(int? childSessionId) => null;
}
sealed class FakeTransport : ICloneTransport
{
    private Action<ICloneConnection, string[]>? receive;
    public string PipeName => "synthetic";
    public int CurrentSessionId => 1;
    public void Start(Action<ICloneConnection, string[]> onMessage, Action<ICloneConnection> onDisconnect) => receive = onMessage;
    public void Deliver(ICloneConnection connection, params string[] message) => receive!(connection, message);
    public void Dispose() { }
}
sealed class FakeConnection(int session) : ICloneConnection
{
    public int Runs { get; private set; }
    public string? Role { get; set; }
    public int PeerProcessId => session + 100;
    public int PeerSessionId => session;
    public ValueTask SendAsync(TimeSpan timeout, params string[] parts) { if (parts[0] == "run") Runs++; return ValueTask.CompletedTask; }
    public void Close() { }
}
sealed class Observer : ICloneRunObserver
{
    public void OnEvent(RunEvent item) { }
    public void OnFrame(long id, byte[] jpeg) { }
    public void OnMirrorQueue(string path) { }
}
