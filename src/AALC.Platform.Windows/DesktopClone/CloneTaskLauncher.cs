using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Principal;

namespace AALC.Platform.Windows.DesktopClone;

/// <summary>
/// 把进程投递到 Child Session。没有 SeTcb 时无法 CreateProcessAsUser，临时任务计划的 RunEx 是唯一的跨会话启动入口。
/// 分身内进程用受限令牌运行：Steam 与游戏由它拉起，保持普通权限，与主桌面的日常运行一致。
/// </summary>
internal static class CloneTaskLauncher
{
    private const int ActionExecute = 0;
    private const int CreateTask = 2;
    private const int LogonInteractiveToken = 3;
    private const int RunLevelLimited = 0;
    private const int RunUseSessionId = 0x4;
    private const int StateQueued = 2;
    private static readonly TimeSpan StartTimeout = TimeSpan.FromSeconds(15);
    private static readonly TimeSpan StatePoll = TimeSpan.FromSeconds(.2);

    public static void Launch(string executable, string arguments, string workingDirectory, int sessionId, CancellationToken cancellationToken)
    {
        if (!File.Exists(executable)) throw new FileNotFoundException("分身内进程的启动程序不存在", executable);
        var account = WindowsIdentity.GetCurrent().Name;
        var taskName = $"AAALC-DesktopClone-Launch-{Guid.NewGuid():N}";
        dynamic scheduler = Activator.CreateInstance(Type.GetTypeFromProgID("Schedule.Service", true)!)!;
        scheduler.Connect();
        cancellationToken.ThrowIfCancellationRequested();
        dynamic root = scheduler.GetFolder("\\");
        dynamic definition = scheduler.NewTask(0);
        definition.RegistrationInfo.Author = "AAALC";
        definition.RegistrationInfo.Description = $"临时启动 AAALC 到 Windows Child Session {sessionId}";
        definition.Settings.Enabled = true;
        definition.Settings.Hidden = true;
        definition.Settings.AllowDemandStart = true;
        definition.Settings.DisallowStartIfOnBatteries = false;
        definition.Settings.StopIfGoingOnBatteries = false;
        definition.Settings.ExecutionTimeLimit = "PT0S";
        definition.Principal.UserId = account;
        definition.Principal.LogonType = LogonInteractiveToken;
        definition.Principal.RunLevel = RunLevelLimited;
        dynamic action = definition.Actions.Create(ActionExecute);
        action.Path = executable;
        action.Arguments = arguments;
        action.WorkingDirectory = workingDirectory;
        cancellationToken.ThrowIfCancellationRequested();
        dynamic registered = root.RegisterTaskDefinition(taskName, definition, CreateTask, account, null, LogonInteractiveToken);
        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            // user 必须传空串：任务以已登录目标会话的当前用户身份交互式启动。
            dynamic? running = registered.RunEx(null, RunUseSessionId, sessionId, "");
            if (running is null) throw new InvalidOperationException("任务计划程序没有返回 Child Session 运行实例");
            if (WaitUntilLeavesQueue(running, cancellationToken) == StateQueued)
                throw new TimeoutException($"Child Session 启动任务在 {StartTimeout.TotalSeconds:0} 秒内仍在排队，任务计划程序未创建进程");
        }
        finally
        {
            try { root.DeleteTask(taskName, 0); }
            catch (COMException) { }
        }
    }

    /// <summary>RunEx 只是入队；运行实例离开排队前删除任务定义，进程可能不会被创建，且不留任何记录。</summary>
    private static int? WaitUntilLeavesQueue(dynamic running, CancellationToken cancellationToken)
    {
        var started = Stopwatch.GetTimestamp();
        int? state = null;
        while (Stopwatch.GetElapsedTime(started) < StartTimeout)
        {
            cancellationToken.ThrowIfCancellationRequested();
            try { state = (int)running.State; }
            // 任务引擎在动作启动后释放运行对象，读取失败就是离开队列的信号。
            catch (COMException) { return state; }
            if (state != StateQueued) return state;
            Thread.Sleep(StatePoll);
        }
        return state;
    }
}
