using System.ComponentModel;
using System.Runtime.InteropServices;

namespace AALC.Platform.Windows;

public static class DpiAwareness
{
    public static void EnsurePerMonitorV2()
    {
        nint perMonitorV2 = -4;
        if (AreDpiAwarenessContextsEqual(GetThreadDpiAwarenessContext(), perMonitorV2)) return;
        if (!SetProcessDpiAwarenessContext(perMonitorV2))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "无法启用 PerMonitorV2 DPI 感知，游戏截图和输入需要物理像素坐标");
    }

    [DllImport("user32.dll")]
    private static extern nint GetThreadDpiAwarenessContext();

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool AreDpiAwarenessContextsEqual(nint first, nint second);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetProcessDpiAwarenessContext(nint context);
}
