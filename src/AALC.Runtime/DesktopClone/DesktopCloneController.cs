using System.Diagnostics;
using System.Globalization;
using System.Text.Json;
using AALC.Runtime.Mail;

namespace AALC.Runtime.DesktopClone;

/// <summary>
/// 主程序一侧的分身生命周期：启动 RDP 宿主、确认 Child Session 归属、把任务交给分身内进程，
/// 停止时依次停任务、退进程、注销会话。状态只在 <c>gate</c> 内改变，事件在锁外发出。
/// </summary>
public sealed class DesktopCloneController : IDisposable
{
    private const int DesktopWidth = 1920;
    private const int DesktopHeight = 1080;
    private readonly object gate = new();
    private readonly ICloneSystem system;
    private readonly ICloneTransport transport;
    private readonly CloneTimings timings;
    private readonly Action<string> log;
    private readonly SemaphoreSlim shutdownLock = new(1, 1);
    private CloneState state;
    private string status = "";
    private int? sessionId;
    private ICloneConnection? host;
    private ICloneConnection? worker;
    private ICloneHostProcess? hostProcess;
    private TaskCompletionSource? ready;
    private TaskCompletionSource loggedOff = NewSignal();
    private TaskCompletionSource workerGone = NewSignal();
    private CancellationTokenSource startup = new();
    private Task launchingHost = Task.CompletedTask;
    private Task launchingWorker = Task.CompletedTask;
    private ActiveRun? run;
    private bool expectedShutdown;
    private string? failure;
    private bool windowVisible;
    private bool muted;
    private bool inputBlocked;
    private Timer? connectionTimer;
    private Timer? autorunTimer;
    private bool transportStarted;
    private bool disposed;

    private sealed class ActiveRun(ICloneRunObserver observer)
    {
        public ICloneRunObserver Observer { get; } = observer;
        public TaskCompletionSource<RunResult> Result { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    }

    public DesktopCloneController(ICloneSystem system, ICloneTransport transport, Action<string> log, CloneTimings? timings = null)
    {
        this.system = system;
        this.transport = transport;
        this.log = log;
        this.timings = timings ?? new();
        RestoreAutorunsQuietly();
    }

    public event Action? Changed;

    public CloneSnapshot Snapshot
    {
        get
        {
            lock (gate) return new(state, status, sessionId, IsActive, windowVisible && IsActive, muted, inputBlocked);
        }
    }

    private bool IsActive => sessionId is not null || host is not null || worker is not null || hostProcess is not null
        || !launchingHost.IsCompleted || !launchingWorker.IsCompleted;

    private static TaskCompletionSource NewSignal() => new(TaskCreationOptions.RunContinuationsAsynchronously);

    private void SetState(CloneState value, string text)
    {
        state = value;
        status = text;
        log($"state={value} {text}");
    }

    private void Notify() => Changed?.Invoke();

    /// <summary>启动分身并等到分身内进程就绪；取消时注销本次创建的会话。</summary>
    public async Task StartAsync(CloneStartOptions options, CancellationToken cancellationToken)
    {
        Task waiting;
        lock (gate)
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            switch (state)
            {
                case CloneState.Ready or CloneState.Running: return;
                case CloneState.Stopping: throw new CloneException("桌面分身正在停止，请等待注销完成后重试");
                case CloneState.Connecting or CloneState.LaunchingWorker: waiting = ready!.Task; break;
                default:
                    if (IsActive) throw new CloneException("桌面分身仍有残留会话，请先停止并注销");
                    startup = new();
                    ready = NewSignal();
                    loggedOff = NewSignal();
                    workerGone = NewSignal();
                    expectedShutdown = false;
                    muted = inputBlocked = false;
                    windowVisible = options.ShowWindow;
                    SetState(CloneState.Connecting, "正在创建 Windows Child Session");
                    connectionTimer = new(_ => OnConnectionTimeout(), null, timings.Connection, Timeout.InfiniteTimeSpan);
                    var token = startup.Token;
                    launchingHost = Task.Run(() => LaunchHost(options, token), CancellationToken.None);
                    _ = launchingHost.ContinueWith(_ => Notify(), TaskScheduler.Default);
                    waiting = ready.Task;
                    break;
            }
        }
        Notify();
        try { await waiting.WaitAsync(cancellationToken); }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            await ShutdownAsync(TimeSpan.FromSeconds(5));
            throw;
        }
    }

    private void LaunchHost(CloneStartOptions options, CancellationToken token)
    {
        var process = default(ICloneHostProcess);
        try
        {
            token.ThrowIfCancellationRequested();
            if (options.EnableRemoteDesktop) system.EnableRemoteDesktop(token);
            var compatibility = system.CheckCompatibility(null);
            if (!compatibility.Supported)
                throw new CloneException(string.Join("；", compatibility.Items.Where(item => item.Status == CloneCheckStatus.Failed).Select(item => item.Detail)));
            foreach (var warning in compatibility.Warnings) log($"warning {warning}");
            lock (gate)
            {
                if (!transportStarted)
                {
                    transport.Start(OnMessage, OnDisconnect);
                    transportStarted = true;
                }
            }
            if (!system.ChildSessionsEnabled)
            {
                system.EnableChildSessions();
                throw new CloneException("Windows Child Session 已成功启用。请注销 Windows 并重新登录一次，使免凭据登录生效；重新登录后无需再次设置。");
            }
            if (options.SuppressAutoruns)
            {
                try { foreach (var task in system.SuppressAutoruns()) log($"未能禁用登录任务：{task}"); }
                catch (Exception exception)
                {
                    RestoreAutorunsQuietly();
                    log($"抑制登录自启动失败，分身将带自启动运行：{exception.Message}");
                }
            }
            token.ThrowIfCancellationRequested();
            process = system.StartHost(new(transport.PipeName, DesktopWidth, DesktopHeight, system.RdpPort, options.ShowWindow));
            lock (gate) hostProcess = process;
            _ = MonitorHostAsync(process);
            token.ThrowIfCancellationRequested();
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested)
        {
            // 取消发生在启动宿主之后时，宿主已登记，由停止流程按归属注销。
            if (process is null) RestoreAutorunsQuietly();
        }
        catch (Exception exception)
        {
            RestoreAutorunsQuietly();
            Fail(exception is CloneException ? exception.Message : $"启动桌面分身失败：{exception.Message}");
        }
    }

    private async Task MonitorHostAsync(ICloneHostProcess process)
    {
        await process.WaitForExitAsync(CancellationToken.None).ConfigureAwait(false);
        process.Dispose();
        bool unexpected;
        lock (gate)
        {
            if (hostProcess != process) return;
            hostProcess = null;
            unexpected = !expectedShutdown && state is not (CloneState.Idle or CloneState.Error);
        }
        if (unexpected) FailAndCleanup($"RDP 宿主意外退出（exit={process.ExitCode}），详情见 {system.HostCrashLogPath}");
        Notify();
    }

    private void OnConnectionTimeout()
    {
        lock (gate)
        {
            if (state is not (CloneState.Connecting or CloneState.LaunchingWorker)) return;
        }
        FailAndCleanup($"桌面分身在 {timings.Connection.TotalSeconds:0} 秒内未完成登录，已清理 Child Session。若出现凭据窗口，请注销 Windows 后重新登录再试");
    }

    private void Fail(string message)
    {
        ActiveRun? active;
        TaskCompletionSource? starting;
        lock (gate)
        {
            connectionTimer?.Dispose();
            connectionTimer = null;
            SetState(CloneState.Error, message);
            active = run;
            run = null;
            starting = ready;
            ready = null;
        }
        starting?.TrySetException(new CloneException(message));
        active?.Result.TrySetResult(new(RunOutcome.Failed, message, 0, 0));
        Notify();
    }

    private void FailAndCleanup(string message)
    {
        lock (gate)
        {
            if (state is CloneState.Idle or CloneState.Stopping) return;
            if (state == CloneState.Error && startup.IsCancellationRequested) return;
            startup.Cancel();
            failure = message;
        }
        Fail(message);
        _ = Task.Run(() => ShutdownAsync(TimeSpan.FromSeconds(5)));
    }

    /// <summary>把任务交给分身内进程。取消只发送停止请求，由分身内进程协作结束并回报结果。</summary>
    public async Task<RunResult> RunAsync(string requestPath, ICloneRunObserver observer, CancellationToken cancellationToken)
    {
        ActiveRun active;
        ICloneConnection connection;
        int? child;
        lock (gate)
        {
            if (state != CloneState.Ready || worker is null) throw new CloneException("桌面分身尚未就绪");
            child = sessionId;
        }
        if (system.FindGameConflict(child) is { } conflict) throw new CloneException(conflict);
        lock (gate)
        {
            if (state != CloneState.Ready || worker is null) throw new CloneException("桌面分身尚未就绪");
            active = run = new(observer);
            connection = worker;
            SetState(CloneState.Running, "分身任务运行中");
        }
        Notify();
        try { await connection.SendAsync(timings.Send, "run", CloneProtocol.Encode(requestPath)); }
        catch (Exception exception) when (exception is IOException or OperationCanceledException or ObjectDisposedException)
        {
            FailAndCleanup($"发送分身任务失败：{exception.Message}");
            return await active.Result.Task;
        }
        await using var registration = cancellationToken.Register(() => _ = RequestStopAsync(connection));
        var cancelled = Task.Delay(Timeout.Infinite, cancellationToken);
        if (await Task.WhenAny(active.Result.Task, cancelled) == active.Result.Task) return await active.Result.Task;
        // 窗口关闭、用户再次操作都不能被一个不回应的分身卡住；状态保持运行中，确认前不接受新任务。
        var stopped = await Task.WhenAny(active.Result.Task, Task.Delay(timings.RunStop));
        return stopped == active.Result.Task ? await active.Result.Task
            : new(RunOutcome.Failed, "分身任务未确认停止，请停止并注销分身", 0, 0);
    }

    private async Task RequestStopAsync(ICloneConnection connection)
    {
        lock (gate)
        {
            if (state == CloneState.Running) SetState(CloneState.Running, "正在请求分身任务安全停止");
        }
        Notify();
        try { await connection.SendAsync(timings.Send, "stop"); }
        catch (Exception exception) when (exception is IOException or OperationCanceledException or ObjectDisposedException)
        {
            log($"请求分身任务停止失败：{exception.Message}");
        }
    }

    public void ShowWindow(bool visible) => SendHost(visible ? "show" : "hide");
    public void SetMuted(bool value) => SendHost("tool-set", "mute", value ? "1" : "0");
    public void SetInputBlocked(bool value) => SendHost("tool-set", "input", value ? "1" : "0");

    private void SendHost(params string[] parts)
    {
        ICloneConnection? connection;
        lock (gate) connection = host;
        if (connection is null) return;
        _ = SendQuietlyAsync(connection, parts);
    }

    private async Task SendQuietlyAsync(ICloneConnection connection, string[] parts)
    {
        try { await connection.SendAsync(timings.Send, parts); }
        catch (Exception exception) when (exception is IOException or OperationCanceledException or ObjectDisposedException)
        {
            log($"发送 {parts[0]} 失败：{exception.Message}");
        }
    }

    /// <summary>停止任务、退出分身内进程并注销会话；只有确认 Child Session 消失才回到空闲。</summary>
    public async Task<bool> ShutdownAsync(TimeSpan timeout)
    {
        var started = Stopwatch.GetTimestamp();
        TimeSpan Remaining(TimeSpan? limit = null)
        {
            var left = timeout - Stopwatch.GetElapsedTime(started);
            if (left < TimeSpan.Zero) left = TimeSpan.Zero;
            return limit is { } value && value < left ? value : left;
        }
        if (!await shutdownLock.WaitAsync(timeout)) return false;
        try
        {
            ActiveRun? active;
            TaskCompletionSource? starting;
            lock (gate)
            {
                startup.Cancel();
                if (state == CloneState.Idle && !IsActive) return true;
                connectionTimer?.Dispose();
                connectionTimer = null;
                expectedShutdown = true;
                active = run;
                starting = ready;
                ready = null;
                SetState(CloneState.Stopping, "正在停止分身任务并注销");
            }
            starting?.TrySetCanceled();
            Notify();
            await WaitQuietlyAsync(launchingHost, Remaining(timings.WorkerExit));
            RestoreAutorunsQuietly();
            await WaitQuietlyAsync(launchingWorker, Remaining(timings.WorkerExit));
            ICloneConnection? workerConnection, hostConnection;
            lock (gate) { workerConnection = worker; hostConnection = host; }
            if (workerConnection is not null)
            {
                if (active is not null)
                {
                    await SendForShutdownAsync(workerConnection, Remaining, "stop");
                    await WaitQuietlyAsync(active.Result.Task, Remaining(timings.SessionStop));
                }
                await SendForShutdownAsync(workerConnection, Remaining, "shutdown");
                await WaitQuietlyAsync(workerGone.Task, Remaining(timings.WorkerExit));
            }
            if (hostConnection is not null)
            {
                await SendForShutdownAsync(hostConnection, Remaining, "logoff");
                await WaitQuietlyAsync(loggedOff.Task, Remaining(timings.HostLogoff));
            }
            await WaitForLogoffAsync(Remaining);
            return await FinishAsync(active, Remaining);
        }
        finally { shutdownLock.Release(); }
    }

    private async Task WaitForLogoffAsync(Func<TimeSpan?, TimeSpan> remaining)
    {
        var failureLogged = false;
        while (true)
        {
            var probe = system.ProbeChildSession();
            int? owned;
            bool hostAlive;
            lock (gate) { owned = sessionId; hostAlive = hostProcess is not null; }
            if (probe.Id is null || probe.Stale || (owned is null && !hostAlive)) return;
            if (probe.Id == owned)
            {
                try { system.LogoffChildSession(probe.Id.Value); }
                catch (Exception exception)
                {
                    if (!failureLogged) log($"注销 Child Session {probe.Id} 失败：{exception.Message}");
                    failureLogged = true;
                }
            }
            var wait = remaining(timings.Poll);
            if (wait <= TimeSpan.Zero) return;
            await Task.Delay(wait);
        }
    }

    private async Task<bool> FinishAsync(ActiveRun? active, Func<TimeSpan?, TimeSpan> remaining)
    {
        var probe = system.ProbeChildSession();
        ICloneHostProcess? process;
        int? owned;
        lock (gate) { process = hostProcess; owned = sessionId; }
        // 启动前已确认没有其他会话，这里仍有会话而本程序没有持有任何部分时，它不属于本程序。
        var foreign = owned is null && process is null;
        var stale = probe.Stale && !foreign;
        var released = probe.Id is null || foreign || stale;
        if (process is not null && released)
        {
            await WaitQuietlyAsync(process.WaitForExitAsync(CancellationToken.None), remaining(timings.WorkerExit));
            if (!process.HasExited)
            {
                process.Terminate();
                await WaitQuietlyAsync(process.WaitForExitAsync(CancellationToken.None), remaining(timings.WorkerExit));
            }
            released = process.HasExited;
        }
        var stopped = released && !stale && launchingHost.IsCompleted && launchingWorker.IsCompleted;
        lock (gate)
        {
            if (released)
            {
                host = null;
                worker = null;
                hostProcess = null;
                sessionId = null;
                run = null;
                ready = null;
                windowVisible = false;
            }
            if (stopped && failure is not null) SetState(CloneState.Error, failure);
            else if (stopped) SetState(CloneState.Idle, "桌面分身已停止");
            else if (stale) SetState(CloneState.Error, $"Child Session {probe.Id} 已失效，系统无法清除，请注销 Windows 后重试");
            else if (state != CloneState.Error) SetState(CloneState.Error, "Windows 尚未确认 Child Session 已注销");
            expectedShutdown = false;
            failure = null;
        }
        if (released) active?.Result.TrySetResult(new(RunOutcome.Cancelled, "桌面分身已注销", 0, 0));
        Notify();
        return stopped;
    }

    private async Task SendForShutdownAsync(ICloneConnection connection, Func<TimeSpan?, TimeSpan> remaining, string command)
    {
        var timeout = remaining(timings.HostLogoff);
        if (timeout <= TimeSpan.Zero) return;
        try { await connection.SendAsync(timeout, command); }
        catch (Exception exception) when (exception is IOException or OperationCanceledException or ObjectDisposedException)
        {
            log($"停止时发送 {command} 失败：{exception.Message}");
            connection.Close();
        }
    }

    private static async Task WaitQuietlyAsync(Task task, TimeSpan timeout)
    {
        try { await task.WaitAsync(timeout); }
        catch (TimeoutException) { }
        catch (Exception) when (task.IsCompleted) { }
    }

    private void RestoreAutorunsQuietly()
    {
        try { system.RestoreAutoruns(); }
        catch (Exception exception)
        {
            log($"恢复登录自启动策略失败：{exception.Message}");
        }
    }

    private void OnMessage(ICloneConnection connection, string[] message)
    {
        if (connection.Role is null) HandleHello(connection, message);
        else if (connection.Role == CloneProtocol.HostRole)
        {
            lock (gate) { if (connection != host) return; }
            HandleHost(message);
        }
        else if (connection.Role == CloneProtocol.WorkerRole)
        {
            lock (gate) { if (connection != worker) return; }
            HandleWorker(message);
        }
    }

    private void HandleHello(ICloneConnection connection, string[] message)
    {
        if (message is not ["hello", var role, CloneProtocol.Version])
        {
            log($"拒绝管道 hello（协议不匹配）：pid={connection.PeerProcessId}");
            connection.Close();
            return;
        }
        ICloneConnection? previous = null;
        var accepted = false;
        lock (gate)
        {
            if (role == CloneProtocol.HostRole && connection.PeerSessionId == transport.CurrentSessionId)
            {
                previous = host;
                host = connection;
                accepted = true;
            }
            else if (role == CloneProtocol.WorkerRole && sessionId is { } child && connection.PeerSessionId == child)
            {
                previous = worker;
                worker = connection;
                accepted = true;
            }
        }
        if (!accepted)
        {
            log($"拒绝管道 hello：role={role} pid={connection.PeerProcessId} session={connection.PeerSessionId}");
            connection.Close();
            return;
        }
        connection.Role = role;
        log($"管道已连接：role={role} pid={connection.PeerProcessId} session={connection.PeerSessionId}");
        if (previous is not null && previous != connection) previous.Close();
    }

    private bool IsStopping
    {
        get
        {
            lock (gate) return expectedShutdown || startup.IsCancellationRequested || state == CloneState.Stopping;
        }
    }

    private void HandleHost(string[] message)
    {
        switch (message)
        {
            case ["rdp-retrying" or "rdp-failed" or "rdp-disconnected" or "error", ..] when IsStopping:
                log($"停止期间忽略宿主消息：{message[0]}");
                break;
            case ["rdp-connected", var reported]: OnRdpConnected(reported); break;
            case ["shown"]: SetVisible(true); break;
            case ["hidden"]: SetVisible(false); break;
            case ["tool-state", var tool and ("mute" or "input"), var value and ("0" or "1")]:
                lock (gate)
                {
                    if (tool == "mute") muted = value == "1";
                    else inputBlocked = value == "1";
                }
                Notify();
                break;
            case ["logged-off"]: loggedOff.TrySetResult(); break;
            case ["rdp-diagnostic", var key, var value, ..]: log($"host {key}={value}"); break;
            case ["rdp-transport-connected"]:
                lock (gate)
                {
                    if (state == CloneState.Connecting && !startup.IsCancellationRequested)
                        SetState(CloneState.Connecting, "RDP 已连接，正在等待 Windows 完成登录");
                }
                Notify();
                break;
            case ["rdp-login-complete"]: log("RDP 登录完成"); break;
            case ["rdp-retrying", var attempt, var delay, var stage, var code, var extended, var description, ..]:
                log($"RDP 首次连接失败，{delay} 秒后重试（{attempt}/3，stage={stage}，code={code}，extended={extended}）：{CloneProtocol.Decode(description)}");
                lock (gate) SetState(CloneState.Connecting, $"桌面分身首次初始化尚未完成，{delay} 秒后自动重试（{attempt}/3）");
                Notify();
                break;
            case ["rdp-failed", var stage, var code, var extended, var description, ..]:
                FailAndCleanup($"RDP 连接失败（stage={stage}，code={code}，extended={extended}）：{CloneProtocol.Decode(description)}");
                break;
            case ["rdp-disconnected", ..]:
                FailAndCleanup($"RDP 意外断开（reason={(message.Length > 1 ? message[1] : "unknown")}）");
                break;
            case ["error", var text]: FailAndCleanup(CloneProtocol.Decode(text)); break;
        }
    }

    private void SetVisible(bool visible)
    {
        lock (gate) windowVisible = visible;
        Notify();
    }

    private void OnRdpConnected(string reported)
    {
        if (!int.TryParse(reported, NumberStyles.None, CultureInfo.InvariantCulture, out var id))
        {
            FailAndCleanup($"RDP 宿主上报了无效的 Child Session ID：{reported}");
            return;
        }
        var actual = system.ProbeChildSession();
        ICloneConnection? hostConnection;
        bool stopping;
        lock (gate)
        {
            hostConnection = host;
            stopping = IsStopping;
            if (stopping && actual.Id == id) sessionId = id;
        }
        if (stopping)
        {
            if (hostConnection is not null) _ = SendQuietlyAsync(hostConnection, ["logoff"]);
            return;
        }
        if (actual.Id != id)
        {
            FailAndCleanup($"RDP 宿主上报了错误的 Child Session：reported={id}，actual={actual.Id}");
            return;
        }
        lock (gate)
        {
            sessionId = id;
            SetState(CloneState.LaunchingWorker, $"Child Session {id} 已连接，正在启动分身内进程");
            autorunTimer?.Dispose();
            autorunTimer = new(_ => RestoreAutorunsQuietly(), null, timings.AutorunRestore, Timeout.InfiniteTimeSpan);
            var token = startup.Token;
            launchingWorker = Task.Run(() => LaunchWorker(id, token), CancellationToken.None);
        }
        Notify();
    }

    private void LaunchWorker(int id, CancellationToken token)
    {
        try { system.LaunchWorker(new(id, transport.PipeName), token); }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { log("已取消在 Child Session 启动分身内进程"); }
        catch (Exception exception)
        {
            log(exception.ToString());
            FailAndCleanup($"在 Child Session 启动分身内进程失败：{exception.Message}");
        }
    }

    private void HandleWorker(string[] message)
    {
        ActiveRun? active;
        lock (gate) active = run;
        switch (message)
        {
            case ["ready", ..]: OnWorkerReady(); break;
            case ["audio-prime", var result, var detail]: log($"分身音频端点预热 {result}：{CloneProtocol.Decode(detail)}"); break;
            case ["event", var payload] when active is not null:
                active.Observer.OnEvent(JsonSerializer.Deserialize<RunEvent>(CloneProtocol.Decode(payload))
                    ?? throw new InvalidDataException("分身运行事件为空"));
                break;
            case ["frame", var id, var payload] when active is not null:
                active.Observer.OnFrame(long.Parse(id, CultureInfo.InvariantCulture), Convert.FromBase64String(payload));
                break;
            case ["mirror-queue", var path] when active is not null:
                active.Observer.OnMirrorQueue(CloneProtocol.Decode(path));
                break;
            case ["result", var outcome, var reason, var observations, var elapsed]:
                OnRunResult(active, new(Enum.Parse<RunOutcome>(outcome), CloneProtocol.Decode(reason),
                    int.Parse(observations, CultureInfo.InvariantCulture), double.Parse(elapsed, CultureInfo.InvariantCulture)));
                break;
            case ["error", var text]:
                if (IsStopping) log($"停止期间忽略分身内错误：{CloneProtocol.Decode(text)}");
                else FailAndCleanup(CloneProtocol.Decode(text));
                break;
        }
    }

    private void OnWorkerReady()
    {
        TaskCompletionSource? starting = null;
        lock (gate)
        {
            connectionTimer?.Dispose();
            connectionTimer = null;
            if (IsStopping || state == CloneState.Error) { log("忽略迟到的分身就绪消息"); return; }
            SetState(CloneState.Ready, "分身已就绪");
            starting = ready;
            ready = null;
        }
        starting?.TrySetResult();
        Notify();
    }

    private void OnRunResult(ActiveRun? active, RunResult result)
    {
        lock (gate)
        {
            run = null;
            if (state == CloneState.Running)
                SetState(CloneState.Ready, result.Outcome switch
                {
                    RunOutcome.Completed => "分身任务已完成",
                    RunOutcome.Cancelled => "分身任务已停止",
                    _ => $"分身任务已结束：{result.Reason}"
                });
        }
        active?.Result.TrySetResult(result);
        Notify();
    }

    private void OnDisconnect(ICloneConnection connection)
    {
        var workerLost = false;
        var hostLost = false;
        lock (gate)
        {
            if (connection == worker)
            {
                worker = null;
                workerGone.TrySetResult();
                workerLost = !expectedShutdown && state is not (CloneState.Idle or CloneState.Error);
            }
            else if (connection == host)
            {
                host = null;
                hostLost = !expectedShutdown && state is not (CloneState.Idle or CloneState.Error);
            }
        }
        if (workerLost) FailAndCleanup($"分身内进程意外断开（pid={connection.PeerProcessId}）");
        if (hostLost) FailAndCleanup("RDP 宿主连接已断开");
        Notify();
    }

    public void Dispose()
    {
        lock (gate)
        {
            if (disposed) return;
            disposed = true;
            connectionTimer?.Dispose();
            autorunTimer?.Dispose();
        }
        RestoreAutorunsQuietly();
        transport.Dispose();
    }
}
