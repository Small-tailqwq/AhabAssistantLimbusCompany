using System.ComponentModel;
using System.Diagnostics;
using System.Net.Sockets;
using System.Runtime.Versioning;
using System.Security.Principal;
using AALC.Platform.Windows.Tools;
using AALC.Runtime;
using AALC.Runtime.DesktopClone;
using Microsoft.Win32;

namespace AALC.Platform.Windows.DesktopClone;

/// <summary><see cref="ICloneSystem"/> 的 Windows 实现。</summary>
public sealed class WindowsCloneSystem(string hostExecutable, Func<CloneWorkerStart, (string Executable, string Arguments, string WorkingDirectory)> workerCommand) : ICloneSystem
{
    private const int DefaultRdpPort = 3389;
    private const string TerminalServerKey = @"SYSTEM\CurrentControlSet\Control\Terminal Server";
    private const string RdpKey = TerminalServerKey + @"\WinStations\RDP-Tcp";
    // 能抢占活动桌面的交互式进程才算风险；常驻后台服务通常无法彻底退出，不提示。
    private static readonly (string Process, string Label)[] RemoteControlProcesses =
        [("ToDesk", "ToDesk"), ("GameViewer", "UU远程"), ("GameViewerServer", "UU远程"), ("MuMuRemoteBackend", "MuMu远程")];

    private static string SetupMarkerPath => Path.Combine(CloneStateFiles.Directory, ".child-sessions-enabled-logon");
    public string HostCrashLogPath => EvidencePaths.RequireExternalPath(Path.Combine(EvidencePaths.ResolveRoot(), "clone", "logs", "host-startup-error.txt"));

    public static bool IsElevated
    {
        get
        {
            using var identity = WindowsIdentity.GetCurrent();
            return new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator);
        }
    }

    public CloneCompatibility CheckCompatibility(int? ownedSessionId)
    {
        var items = new List<CloneCheckItem>();
        void Add(string name, CloneCheckStatus status, string detail) => items.Add(new(name, status, detail));
        var elevated = IsElevated;

        var (edition, home) = WindowsEdition();
        Add("系统版本", home ? CloneCheckStatus.Failed : CloneCheckStatus.Passed, home ? $"{edition} 不支持 Child Session 远程连接" : edition);
        Add("管理员权限", elevated ? CloneCheckStatus.Passed : CloneCheckStatus.Failed,
            elevated ? "已以管理员身份运行" : "需要以管理员身份运行 AAALC；普通权限连接会留下只能靠注销 Windows 清除的会话");

        var rdpEnabled = IsRemoteDesktopEnabled();
        var port = RdpPort;
        if (!rdpEnabled) Add("远程桌面", CloneCheckStatus.Failed, "Windows 远程桌面未开启");
        else if (!IsListening(port)) Add("远程桌面", CloneCheckStatus.Failed, $"RDP 本机端口 {port} 未监听，请检查 Remote Desktop Services");
        else Add("远程桌面", CloneCheckStatus.Passed, $"已开启，端口 {port}");

        try
        {
            if (WasEnabledDuringCurrentLogon()) Add("Child Session", CloneCheckStatus.Failed, "本次登录后才启用，请注销 Windows 并重新登录；不要在凭据窗口中输入密码");
            else if (ChildSessionApi.IsEnabled()) Add("Child Session", CloneCheckStatus.Passed, "已启用");
            else Add("Child Session", CloneCheckStatus.Warning, "未启用，首次启动时启用，之后需要注销 Windows 并重新登录一次");
            var probe = ChildSessionApi.Probe();
            if (probe.Stale) Add("现有会话", CloneCheckStatus.Failed, $"Child Session {probe.Id} 已失效，系统无法清除，请注销 Windows 后重试");
            else if (probe.Id is { } session && session != ownedSessionId)
                Add("现有会话", CloneCheckStatus.Failed, $"检测到不属于本程序的 Child Session {session}，为避免注销其中的程序不会接管");
            else Add("现有会话", CloneCheckStatus.Passed, probe.Id is null ? "无" : $"Child Session {probe.Id}");
        }
        catch (Exception exception) when (exception is Win32Exception or DllNotFoundException or EntryPointNotFoundException)
        {
            Add("Child Session", CloneCheckStatus.Failed, $"Child Session API 不可用：{exception.Message}");
        }

        Add("RDP 宿主", File.Exists(hostExecutable) ? CloneCheckStatus.Passed : CloneCheckStatus.Failed,
            File.Exists(hostExecutable) ? Path.GetFileName(hostExecutable) : $"缺少 {hostExecutable}");

        var steam = SteamLocator.FindExecutable();
        Add("Steam", steam is null ? CloneCheckStatus.Failed : CloneCheckStatus.Passed, steam ?? "未找到 steam.exe；分身内的游戏必须通过 Steam 完成账户验证");

        var conflict = FindGameConflict(ownedSessionId);
        Add("主桌面", conflict is null ? CloneCheckStatus.Passed : CloneCheckStatus.Failed, conflict ?? "游戏与 Steam 未在运行");

        var remote = RemoteControlProcesses.Where(item => IsRunning(item.Process)).Select(item => item.Label).Distinct().ToArray();
        if (remote.Length > 0)
            Add("远程控制软件", CloneCheckStatus.Warning, $"{string.Join("、", remote)} 正在运行。Child Session 会成为新的活动桌面，远程控制画面可能被切换到分身");
        return new(items, !elevated, elevated && !home && !rdpEnabled);
    }

    private static (string Name, bool Home) WindowsEdition()
    {
        using var key = Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\Windows NT\CurrentVersion");
        var edition = key?.GetValue("EditionID") as string ?? "";
        var build = key?.GetValue("CurrentBuildNumber") as string ?? "";
        // ProductName 在 Windows 11 上仍写着 Windows 10，以版本号为准。
        var product = (key?.GetValue("ProductName") as string ?? "Windows").Replace("Windows 10", int.TryParse(build, out var number) && number >= 22000 ? "Windows 11" : "Windows 10");
        return ($"{product}（{build}）", edition.StartsWith("Core", StringComparison.OrdinalIgnoreCase));
    }

    private static bool IsRunning(string process)
    {
        var running = Process.GetProcessesByName(process);
        foreach (var item in running) item.Dispose();
        return running.Length > 0;
    }

    public ChildSessionProbe ProbeChildSession() => ChildSessionApi.Probe();
    public bool ChildSessionsEnabled => ChildSessionApi.IsEnabled();

    /// <summary>先写入本次登录标记再启用：误判只会多要求一次重新登录，反之会对启用前的登录发起连接。</summary>
    public void EnableChildSessions()
    {
        CloneStateFiles.WriteAtomically(SetupMarkerPath, ChildSessionApi.CurrentLogonId());
        try { ChildSessionApi.Enable(); }
        catch
        {
            File.Delete(SetupMarkerPath);
            throw;
        }
    }

    private static bool WasEnabledDuringCurrentLogon()
    {
        try { return File.ReadAllText(SetupMarkerPath).Trim() == ChildSessionApi.CurrentLogonId(); }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException) { return false; }
    }

    public int RdpPort
    {
        get
        {
            using var key = Registry.LocalMachine.OpenSubKey(RdpKey);
            return key?.GetValue("PortNumber") is int port and > 0 and <= 65535 ? port : DefaultRdpPort;
        }
    }

    private static bool IsRemoteDesktopEnabled()
    {
        using var key = Registry.LocalMachine.OpenSubKey(TerminalServerKey);
        return key?.GetValue("fDenyTSConnections") is 0;
    }

    private static bool IsListening(int port)
    {
        try
        {
            using var client = new TcpClient();
            return client.ConnectAsync("127.0.0.1", port).Wait(TimeSpan.FromSeconds(.5)) && client.Connected;
        }
        catch (AggregateException) { return false; }
    }

    /// <summary>通过 WMI 开启远程桌面及其防火墙例外，受组策略管理时报告失败。</summary>
    public void EnableRemoteDesktop(CancellationToken cancellationToken)
    {
        if (IsRemoteDesktopEnabled()) return;
        if (!IsElevated) throw new CloneException("开启 Windows 远程桌面需要管理员权限");
        cancellationToken.ThrowIfCancellationRequested();
        dynamic locator = Activator.CreateInstance(Type.GetTypeFromProgID("WbemScripting.SWbemLocator", true)!)!;
        dynamic service = locator.ConnectServer(".", @"root\CIMV2\TerminalServices");
        dynamic? setting = null;
        var count = 0;
        foreach (var item in service.ExecQuery("SELECT * FROM Win32_TerminalServiceSetting")) { setting = item; count++; }
        if (count != 1) throw new CloneException("Windows 未返回唯一的远程桌面服务配置");
        cancellationToken.ThrowIfCancellationRequested();
        dynamic parameters = setting!.Methods_.Item("SetAllowTSConnections").InParameters.SpawnInstance_();
        parameters.AllowTSConnections = 1;
        parameters.ModifyFirewallException = 1;
        var result = (int)service.ExecMethod_(setting.Path_.Path, "SetAllowTSConnections", parameters).ReturnValue;
        if (result != 0) throw new CloneException($"无法开启 Windows 远程桌面（WMI 错误 {result}），该设置可能受组策略管理");
        if (!IsRemoteDesktopEnabled()) throw new CloneException("Windows 未确认远程桌面已经开启，该设置可能受组策略管理");
        var started = Stopwatch.GetTimestamp();
        while (!IsListening(RdpPort))
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (Stopwatch.GetElapsedTime(started) > TimeSpan.FromSeconds(5))
                throw new CloneException($"已开启 Windows 远程桌面，但 RDP 本机端口 {RdpPort} 未开始监听");
            Thread.Sleep(100);
        }
    }

    public IReadOnlyList<string> SuppressAutoruns() => AutorunGuard.Suppress();
    public void RestoreAutoruns() => AutorunGuard.Restore();
    public void LogoffChildSession(int sessionId) => ChildSessionApi.Logoff(sessionId);

    public ICloneHostProcess StartHost(CloneHostStart start)
    {
        var information = new ProcessStartInfo(hostExecutable)
        {
            UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Path.GetDirectoryName(hostExecutable)!
        };
        foreach (var argument in new[]
        {
            "--pipe-name", start.PipeName, "--width", start.Width.ToString(), "--height", start.Height.ToString(),
            "--rdp-port", start.RdpPort.ToString(), "--show", start.Show ? "true" : "false", "--crash-log", HostCrashLogPath
        }) information.ArgumentList.Add(argument);
        return new HostProcess(Process.Start(information) ?? throw new CloneException("无法启动 RDP 宿主"));
    }

    public void LaunchWorker(CloneWorkerStart start, CancellationToken cancellationToken)
    {
        var (executable, arguments, directory) = workerCommand(start);
        CloneTaskLauncher.Launch(executable, arguments, directory, start.SessionId, cancellationToken);
    }

    public string? FindGameConflict(int? childSessionId)
    {
        var current = Process.GetCurrentProcess().SessionId;
        string? Conflict(string name, string label, Func<int, bool> conflicts)
        {
            var processes = Process.GetProcessesByName(name);
            try
            {
                var found = processes.Where(process => conflicts(process.SessionId)).Select(process => $"PID {process.Id}/Session {process.SessionId}").ToArray();
                return found.Length == 0 ? null : $"{label}（{string.Join("，", found)}）";
            }
            finally { foreach (var process in processes) process.Dispose(); }
        }
        var conflicts = new[]
        {
            Conflict("LimbusCompany", "《边狱公司》在主桌面运行", session => session == current),
            Conflict("steam", "Steam 在分身以外运行", session => session != childSessionId)
        }.OfType<string>().ToArray();
        return conflicts.Length == 0 ? null : $"{string.Join("；", conflicts)}，请完全退出后重试";
    }

    private sealed class HostProcess(Process process) : ICloneHostProcess
    {
        public bool HasExited
        {
            get
            {
                try { return process.HasExited; }
                catch (InvalidOperationException) { return true; }
            }
        }

        public int ExitCode => process.ExitCode;
        public Task WaitForExitAsync(CancellationToken cancellationToken) => process.WaitForExitAsync(cancellationToken);

        public void Terminate()
        {
            try { process.Kill(); }
            catch (Exception exception) when (exception is InvalidOperationException or Win32Exception) { }
        }

        public void Dispose() { }
    }
}
