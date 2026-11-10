using System.Text.Json;
using AALC.Core.Features.Daily;
using AALC.Core.Features.Mirror;
using AALC.Runtime.Mail;
using AALC.Runtime.Configuration;

namespace AALC.Runtime.DesktopClone;

public enum CloneState { Idle, Connecting, LaunchingWorker, Ready, Running, Stopping, Error }
public enum CloneCheckStatus { Passed, Warning, Failed }

public sealed record CloneSnapshot(CloneState State, string Status, int? SessionId, bool IsActive,
    bool WindowVisible, bool Muted, bool InputBlocked);

public sealed record CloneCheckItem(string Name, CloneCheckStatus Status, string Detail);

public sealed record CloneCompatibility(IReadOnlyList<CloneCheckItem> Items, bool NeedsElevation = false, bool CanEnableRemoteDesktop = false)
{
    public bool Supported => Items.All(item => item.Status != CloneCheckStatus.Failed);
    public IEnumerable<string> Warnings => Items.Where(item => item.Status == CloneCheckStatus.Warning).Select(item => item.Detail);
}

/// <param name="Id">WTSGetChildSessionId 返回的会话。</param>
/// <param name="Stale">系统仍返回该 ID，但会话已不存在，只有注销 Windows 才能清除。</param>
public sealed record ChildSessionProbe(int? Id, bool Stale = false);

public sealed record CloneHostStart(string PipeName, int Width, int Height, int RdpPort, bool Show);
public sealed record CloneWorkerStart(int SessionId, string PipeName);
public sealed record CloneStartOptions(bool ShowWindow = true, bool EnableRemoteDesktop = false, bool SuppressAutoruns = true);

public sealed class CloneException(string message, Exception? inner = null) : Exception(message, inner);

public interface ICloneHostProcess : IDisposable
{
    bool HasExited { get; }
    int ExitCode { get; }
    Task WaitForExitAsync(CancellationToken cancellationToken);
    void Terminate();
}

/// <summary>分身生命周期用到的全部系统效果。</summary>
public interface ICloneSystem
{
    string HostCrashLogPath { get; }
    CloneCompatibility CheckCompatibility(int? ownedSessionId);
    ChildSessionProbe ProbeChildSession();
    bool ChildSessionsEnabled { get; }
    void EnableChildSessions();
    void EnableRemoteDesktop(CancellationToken cancellationToken);
    int RdpPort { get; }
    IReadOnlyList<string> SuppressAutoruns();
    void RestoreAutoruns();
    void LogoffChildSession(int sessionId);
    ICloneHostProcess StartHost(CloneHostStart start);
    void LaunchWorker(CloneWorkerStart start, CancellationToken cancellationToken);
    /// <summary>主桌面仍有游戏或 Steam 时返回说明；游戏和 Steam 只能在分身内运行。</summary>
    string? FindGameConflict(int? childSessionId);
}

public interface ICloneConnection
{
    string? Role { get; set; }
    int PeerProcessId { get; }
    int PeerSessionId { get; }
    ValueTask SendAsync(TimeSpan timeout, params string[] parts);
    void Close();
}

public interface ICloneTransport : IDisposable
{
    string PipeName { get; }
    int CurrentSessionId { get; }
    void Start(Action<ICloneConnection, string[]> onMessage, Action<ICloneConnection> onDisconnect);
}

public interface ICloneRunObserver
{
    void OnEvent(RunEvent item);
    void OnFrame(long id, byte[] jpeg);
    void OnMirrorQueue(string path);
}

public sealed record CloneTimings
{
    public TimeSpan Connection { get; init; } = TimeSpan.FromSeconds(120);
    /// <summary>explorer 在登录后约 10 秒才处理启动项，恢复不能挂在分身就绪上。</summary>
    public TimeSpan AutorunRestore { get; init; } = TimeSpan.FromSeconds(180);
    public TimeSpan RunStop { get; init; } = TimeSpan.FromSeconds(30);
    public TimeSpan SessionStop { get; init; } = TimeSpan.FromSeconds(3);
    public TimeSpan WorkerExit { get; init; } = TimeSpan.FromSeconds(.75);
    public TimeSpan HostLogoff { get; init; } = TimeSpan.FromSeconds(4);
    public TimeSpan Send { get; init; } = TimeSpan.FromSeconds(1);
    public TimeSpan Poll { get; init; } = TimeSpan.FromSeconds(.1);
}

/// <summary>交给分身内进程执行的任务。配置经文件传递，主程序仍是配置的唯一写入者。</summary>
public sealed record CloneTaskRequest(string Kind, string RepositoryRoot, string OcrModelsDirectory, string GameLanguage,
    string GameTheme, DailyOptions? Daily = null, MirrorOptions? Mirror = null, LaunchSettings? Launch = null)
{
    public const string DailyKind = "daily";
    public const string MirrorKind = "mirror";
    public const string LaunchKind = "launch";

    /// <summary>写入数据根而不是系统临时目录：两个会话的 TEMP 不同，证据也不能落到 C 盘。</summary>
    public string Save()
    {
        var directory = EvidencePaths.RequireExternalPath(Path.Combine(EvidencePaths.ResolveRoot(), "clone", "requests"));
        Directory.CreateDirectory(directory);
        var path = EvidencePaths.RequireExternalPath(Path.Combine(directory, $"{DateTime.Now:yyyyMMdd-HHmmss-fff}.json"));
        File.WriteAllText(path, JsonSerializer.Serialize(this));
        return path;
    }

    public static CloneTaskRequest Load(string path) =>
        JsonSerializer.Deserialize<CloneTaskRequest>(File.ReadAllText(path)) ?? throw new InvalidDataException("分身任务请求为空");
}
