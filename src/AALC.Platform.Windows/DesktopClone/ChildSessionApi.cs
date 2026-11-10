using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Principal;
using AALC.Runtime.DesktopClone;

namespace AALC.Platform.Windows.DesktopClone;

/// <summary>Child Session 相关的 WTS 调用。</summary>
internal static class ChildSessionApi
{
    private const int ErrorNotFound = 1168;
    private const uint NoChildSession = 0xFFFFFFFF;
    private const int TokenStatistics = 10;
    private const uint WtsSessionId = 4;

    public static bool IsEnabled() => WTSIsChildSessionsEnabled(out var enabled) ? enabled : throw new Win32Exception();

    public static void Enable()
    {
        if (!WTSEnableChildSessions(true)) throw new Win32Exception();
    }

    public static ChildSessionProbe Probe()
    {
        if (!WTSGetChildSessionId(out var session))
        {
            var error = Marshal.GetLastPInvokeError();
            return error == ErrorNotFound ? new(null) : throw new Win32Exception(error);
        }
        if (session == NoChildSession) return new(null);
        // 普通权限连接失败后 WTSGetChildSessionId 会一直返回已消失的 ID，WTSLogoffSession 也报错误 2。
        if (!WTSQuerySessionInformationW(0, session, WtsSessionId, out var buffer, out _)) return new((int)session, Stale: true);
        WTSFreeMemory(buffer);
        return new((int)session);
    }

    public static void Logoff(int session)
    {
        if (!WTSLogoffSession(0, (uint)session, false)) throw new Win32Exception();
    }

    /// <summary>当前登录的 LUID，格式与 Python 版的标记文件一致。</summary>
    public static string CurrentLogonId()
    {
        using var identity = WindowsIdentity.GetCurrent();
        var buffer = new byte[56];
        if (!GetTokenInformation(identity.Token, TokenStatistics, buffer, buffer.Length, out _)) throw new Win32Exception();
        // TOKEN_STATISTICS：TokenId(LUID) 之后是 AuthenticationId(LUID)，低位在前。
        var low = BitConverter.ToUInt32(buffer, 8);
        var high = BitConverter.ToUInt32(buffer, 12);
        return $"{high:x8}{low:x8}";
    }

    [DllImport("wtsapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool WTSEnableChildSessions([MarshalAs(UnmanagedType.Bool)] bool enable);

    [DllImport("wtsapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool WTSIsChildSessionsEnabled([MarshalAs(UnmanagedType.Bool)] out bool enabled);

    [DllImport("wtsapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool WTSGetChildSessionId(out uint sessionId);

    [DllImport("wtsapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool WTSLogoffSession(nint server, uint sessionId, [MarshalAs(UnmanagedType.Bool)] bool wait);

    [DllImport("wtsapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool WTSQuerySessionInformationW(nint server, uint sessionId, uint infoClass, out nint buffer, out uint bytes);

    [DllImport("wtsapi32.dll")]
    private static extern void WTSFreeMemory(nint memory);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetTokenInformation(nint token, int informationClass, [Out] byte[] information, int length, out int returned);
}
