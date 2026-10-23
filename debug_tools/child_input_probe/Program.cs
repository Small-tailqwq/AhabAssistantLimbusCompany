using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

namespace ChildInputProbe;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        if (args.Contains("--integrity", StringComparer.OrdinalIgnoreCase))
        {
            WriteIntegritySnapshot();
            return;
        }
        if (args.Contains("--compare", StringComparer.OrdinalIgnoreCase))
        {
            WriteScanComparison();
            return;
        }
        if (args.Contains("--route-zero", StringComparer.OrdinalIgnoreCase))
        {
            WriteRouteZeroTest();
            return;
        }
        if (args.Contains("--route-mapped", StringComparer.OrdinalIgnoreCase))
        {
            WriteRouteMappedTest();
            return;
        }
        if (args.Contains("--focused-route-zero", StringComparer.OrdinalIgnoreCase))
        {
            WriteFocusedRouteTest(mappedScan: false);
            return;
        }
        if (args.Contains("--focused-route-mapped", StringComparer.OrdinalIgnoreCase))
        {
            WriteFocusedRouteTest(mappedScan: true);
            return;
        }
        if (args.Contains("--focused-right-zero", StringComparer.OrdinalIgnoreCase))
        {
            WriteFocusedDirectionTest(mappedScan: false);
            return;
        }
        if (args.Contains("--focused-right-mapped", StringComparer.OrdinalIgnoreCase))
        {
            WriteFocusedDirectionTest(mappedScan: true);
            return;
        }
        if (args.Contains("--focused-sendinput-right", StringComparer.OrdinalIgnoreCase))
        {
            WriteFocusedSendInputTest();
            return;
        }
        if (args.Contains("--gui", StringComparer.OrdinalIgnoreCase))
        {
            WriteGuiSnapshot();
            return;
        }
        ApplicationConfiguration.Initialize();
        Application.Run(new ProbeForm());
    }

    private static void WriteIntegritySnapshot()
    {
        var output = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "AALC",
            "desktop-clone",
            "logs",
            "child-process-integrity.log"
        );
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var lines = new List<string>
        {
            $"Probe PID={Environment.ProcessId}, Session={Process.GetCurrentProcess().SessionId}, Integrity={ProbeForm.GetIntegrityHint()}",
        };
        foreach (var name in new[] { "python", "LimbusCompany" })
        {
            foreach (var process in Process.GetProcessesByName(name))
            {
                try
                {
                    lines.Add($"{name} PID={process.Id}, Session={process.SessionId}, Integrity={Native.GetProcessIntegrityHint(process.Id)}");
                }
                catch (Exception ex) { lines.Add($"{name} PID={process.Id}, error={ex.GetType().Name}:{ex.Message}"); }
                finally { process.Dispose(); }
            }
        }
        File.WriteAllLines(output, lines, Encoding.UTF8);
    }

    private static void WriteScanComparison()
    {
        var root = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "AALC",
            "desktop-clone",
            "logs",
            "child-input-compare"
        );
        Directory.CreateDirectory(root);
        var output = Path.Combine(root, "result.log");
        var hwnd = FindLimbusWindow();
        var lines = new List<string>
        {
            $"pid={Environment.ProcessId} session={Process.GetCurrentProcess().SessionId} target=0x{hwnd.ToInt64():X}",
        };
        File.WriteAllLines(output, lines, Encoding.UTF8);
        try
        {
            if (hwnd == IntPtr.Zero)
                return;

            CaptureWindow(hwnd, Path.Combine(root, "before.png"), lines);
            File.WriteAllLines(output, lines, Encoding.UTF8);
            SendWmActivateKeybd(hwnd, Native.VK_RIGHT, 0, lines, "scan0");
            Thread.Sleep(500);
            CaptureWindow(hwnd, Path.Combine(root, "after-scan0.png"), lines);
            File.WriteAllLines(output, lines, Encoding.UTF8);
            SendWmActivateKeybd(hwnd, Native.VK_RIGHT, (byte)Native.MapVirtualKey(Native.VK_RIGHT, Native.MAPVK_VK_TO_VSC), lines, "mapped-scan");
            Thread.Sleep(500);
            CaptureWindow(hwnd, Path.Combine(root, "after-mapped-scan.png"), lines);
        }
        catch (Exception ex)
        {
            lines.Add($"exception={ex.GetType().Name}:{ex.Message}");
        }
        File.WriteAllLines(output, lines, Encoding.UTF8);
    }

    private static void WriteGuiSnapshot()
    {
        var root = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "AALC",
            "desktop-clone",
            "logs",
            "child-gui-snapshot"
        );
        Directory.CreateDirectory(root);
        var output = Path.Combine(root, "result.log");
        var target = FindLimbusWindow();
        var foreground = Native.GetForegroundWindow();
        var targetThread = target == IntPtr.Zero ? 0 : Native.GetWindowThreadProcessId(target, out _);
        var foregroundThread = foreground == IntPtr.Zero ? 0 : Native.GetWindowThreadProcessId(foreground, out _);
        var lines = new List<string>
        {
            $"probe pid={Environment.ProcessId} session={Process.GetCurrentProcess().SessionId} integrity={ProbeForm.GetIntegrityHint()}",
            $"foreground={DescribeWindow(foreground)} thread={foregroundThread}",
            $"target={DescribeWindow(target)} thread={targetThread}",
            $"current_thread={Native.GetCurrentThreadId()} desktop={Native.GetDesktopName(Native.GetThreadDesktop(Native.GetCurrentThreadId()))}",
        };

        if (foregroundThread != 0)
            lines.Add($"foreground_thread_desktop={Native.GetDesktopName(Native.GetThreadDesktop(foregroundThread))}");
        if (targetThread != 0)
            lines.Add($"target_thread_desktop={Native.GetDesktopName(Native.GetThreadDesktop(targetThread))}");

        var inputDesktop = Native.OpenInputDesktop(0, false, Native.DESKTOP_READOBJECTS);
        if (inputDesktop == IntPtr.Zero)
            lines.Add($"input_desktop=<error {Marshal.GetLastWin32Error()}>");
        else
        {
            lines.Add($"input_desktop={Native.GetDesktopName(inputDesktop)}");
            Native.CloseDesktop(inputDesktop);
        }

        AddGuiThreadInfo(lines, "foreground_gui", foregroundThread);
        AddGuiThreadInfo(lines, "target_gui", targetThread);
        foreach (var process in Process.GetProcessesByName("python").Where(p => SafeSessionId(p) == Process.GetCurrentProcess().SessionId))
        {
            try
            {
                var threadInfo = process.Threads.Cast<ProcessThread>().Take(6)
                    .Select(thread => $"{thread.Id}:{Native.GetDesktopName(Native.GetThreadDesktop((uint)thread.Id))}");
                lines.Add($"python_pid={process.Id} threads=" + string.Join(",", threadInfo));
            }
            catch (Exception ex)
            {
                lines.Add($"python_pid={process.Id} threads=<error {ex.GetType().Name}:{ex.Message}>");
            }
            finally { process.Dispose(); }
        }
        File.WriteAllLines(output, lines, Encoding.UTF8);
    }

    private static void WriteRouteZeroTest()
    {
        var root = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "AALC",
            "desktop-clone",
            "logs",
            "child-input-route-zero"
        );
        Directory.CreateDirectory(root);
        var output = Path.Combine(root, "result.log");
        var hwnd = FindLimbusWindow();
        var lines = new List<string>
        {
            $"pid={Environment.ProcessId} session={Process.GetCurrentProcess().SessionId} target=0x{hwnd.ToInt64():X}",
        };
        File.WriteAllLines(output, lines, Encoding.UTF8);
        try
        {
            if (hwnd == IntPtr.Zero)
                return;
            CaptureWindow(hwnd, Path.Combine(root, "before.png"), lines);
            BringProbeForeground(lines);
            SendWmActivateKeybd(hwnd, Native.VK_UP, 0, lines, "up-scan0");
            Thread.Sleep(500);
            CaptureWindow(hwnd, Path.Combine(root, "after-up.png"), lines);
            SendWmActivateKeybd(hwnd, Native.VK_RETURN, 0, lines, "enter-scan0");
            Thread.Sleep(1500);
            CaptureWindow(hwnd, Path.Combine(root, "after-enter.png"), lines);
        }
        catch (Exception ex)
        {
            lines.Add($"exception={ex.GetType().Name}:{ex.Message}");
        }
        File.WriteAllLines(output, lines, Encoding.UTF8);
    }

    private static void WriteRouteMappedTest()
    {
        var root = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "AALC",
            "desktop-clone",
            "logs",
            "child-input-route-mapped"
        );
        Directory.CreateDirectory(root);
        var output = Path.Combine(root, "result.log");
        var hwnd = FindLimbusWindow();
        var upScan = (byte)Native.MapVirtualKey(Native.VK_UP, Native.MAPVK_VK_TO_VSC);
        var enterScan = (byte)Native.MapVirtualKey(Native.VK_RETURN, Native.MAPVK_VK_TO_VSC);
        var lines = new List<string>
        {
            $"pid={Environment.ProcessId} session={Process.GetCurrentProcess().SessionId} target=0x{hwnd.ToInt64():X} upScan=0x{upScan:X2} enterScan=0x{enterScan:X2}",
        };
        File.WriteAllLines(output, lines, Encoding.UTF8);
        try
        {
            if (hwnd == IntPtr.Zero)
                return;
            CaptureWindow(hwnd, Path.Combine(root, "before.png"), lines);
            BringProbeForeground(lines);
            SendWmActivateKeybd(hwnd, Native.VK_UP, upScan, lines, "up-mapped");
            Thread.Sleep(500);
            CaptureWindow(hwnd, Path.Combine(root, "after-up.png"), lines);
            SendWmActivateKeybd(hwnd, Native.VK_RETURN, enterScan, lines, "enter-mapped");
            Thread.Sleep(1500);
            CaptureWindow(hwnd, Path.Combine(root, "after-enter.png"), lines);
        }
        catch (Exception ex)
        {
            lines.Add($"exception={ex.GetType().Name}:{ex.Message}");
        }
        File.WriteAllLines(output, lines, Encoding.UTF8);
    }

    private static void WriteFocusedRouteTest(bool mappedScan)
    {
        var root = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "AALC",
            "desktop-clone",
            "logs",
            mappedScan ? "child-input-focused-mapped" : "child-input-focused-zero"
        );
        Directory.CreateDirectory(root);
        var output = Path.Combine(root, "result.log");
        var hwnd = FindLimbusWindow();
        var upScan = (byte)Native.MapVirtualKey(Native.VK_UP, Native.MAPVK_VK_TO_VSC);
        var enterScan = (byte)Native.MapVirtualKey(Native.VK_RETURN, Native.MAPVK_VK_TO_VSC);
        var lines = new List<string>
        {
            $"pid={Environment.ProcessId} session={Process.GetCurrentProcess().SessionId} target=0x{hwnd.ToInt64():X} " +
            $"mode={(mappedScan ? "mapped" : "scan0")} upScan=0x{upScan:X2} enterScan=0x{enterScan:X2}",
        };
        File.WriteAllLines(output, lines, Encoding.UTF8);
        try
        {
            if (hwnd == IntPtr.Zero)
                return;
            BringTargetForeground(hwnd, lines);
            CaptureWindow(hwnd, Path.Combine(root, "before.png"), lines);
            SendWmActivateKeybd(hwnd, Native.VK_UP, mappedScan ? upScan : (byte)0, lines, "up");
            Thread.Sleep(500);
            CaptureWindow(hwnd, Path.Combine(root, "after-up.png"), lines);
            SendWmActivateKeybd(hwnd, Native.VK_RETURN, mappedScan ? enterScan : (byte)0, lines, "enter");
            Thread.Sleep(1500);
            CaptureWindow(hwnd, Path.Combine(root, "after-enter.png"), lines);
        }
        catch (Exception ex)
        {
            lines.Add($"exception={ex.GetType().Name}:{ex.Message}");
        }
        File.WriteAllLines(output, lines, Encoding.UTF8);
    }

    private static void WriteFocusedDirectionTest(bool mappedScan)
    {
        var root = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "AALC",
            "desktop-clone",
            "logs",
            mappedScan ? "child-input-focused-right-mapped" : "child-input-focused-right-zero"
        );
        Directory.CreateDirectory(root);
        var output = Path.Combine(root, "result.log");
        var hwnd = FindLimbusWindow();
        var rightScan = (byte)Native.MapVirtualKey(Native.VK_RIGHT, Native.MAPVK_VK_TO_VSC);
        var enterScan = (byte)Native.MapVirtualKey(Native.VK_RETURN, Native.MAPVK_VK_TO_VSC);
        var lines = new List<string>
        {
            $"pid={Environment.ProcessId} session={Process.GetCurrentProcess().SessionId} target=0x{hwnd.ToInt64():X} " +
            $"mode={(mappedScan ? "mapped" : "scan0")} rightScan=0x{rightScan:X2} enterScan=0x{enterScan:X2}",
        };
        File.WriteAllLines(output, lines, Encoding.UTF8);
        try
        {
            if (hwnd == IntPtr.Zero)
                return;
            BringTargetForeground(hwnd, lines);
            CaptureWindow(hwnd, Path.Combine(root, "before.png"), lines);
            SendWmActivateKeybd(hwnd, Native.VK_RIGHT, mappedScan ? rightScan : (byte)0, lines, "right");
            Thread.Sleep(500);
            CaptureWindow(hwnd, Path.Combine(root, "after-right.png"), lines);
            SendWmActivateKeybd(hwnd, Native.VK_RETURN, mappedScan ? enterScan : (byte)0, lines, "enter");
            Thread.Sleep(1500);
            CaptureWindow(hwnd, Path.Combine(root, "after-enter.png"), lines);
        }
        catch (Exception ex)
        {
            lines.Add($"exception={ex.GetType().Name}:{ex.Message}");
        }
        File.WriteAllLines(output, lines, Encoding.UTF8);
    }

    private static void WriteFocusedSendInputTest()
    {
        var root = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "AALC",
            "desktop-clone",
            "logs",
            "child-input-focused-sendinput-right"
        );
        Directory.CreateDirectory(root);
        var output = Path.Combine(root, "result.log");
        var hwnd = FindLimbusWindow();
        var lines = new List<string>
        {
            $"pid={Environment.ProcessId} session={Process.GetCurrentProcess().SessionId} target=0x{hwnd.ToInt64():X} mode=SendInput",
        };
        File.WriteAllLines(output, lines, Encoding.UTF8);
        try
        {
            if (hwnd == IntPtr.Zero)
                return;
            BringTargetForeground(hwnd, lines);
            CaptureWindow(hwnd, Path.Combine(root, "before.png"), lines);
            var before = Native.GetForegroundWindow();
            Native.SendVirtualKey(Native.VK_RIGHT);
            lines.Add($"right: vk=0x{Native.VK_RIGHT:X2} foreground_before=0x{before.ToInt64():X} foreground_after=0x{Native.GetForegroundWindow().ToInt64():X}");
            Thread.Sleep(500);
            CaptureWindow(hwnd, Path.Combine(root, "after-right.png"), lines);
            Native.SendVirtualKey(Native.VK_RETURN);
            lines.Add($"enter: vk=0x{Native.VK_RETURN:X2} foreground_after=0x{Native.GetForegroundWindow().ToInt64():X}");
            Thread.Sleep(1500);
            CaptureWindow(hwnd, Path.Combine(root, "after-enter.png"), lines);
        }
        catch (Exception ex)
        {
            lines.Add($"exception={ex.GetType().Name}:{ex.Message}");
        }
        File.WriteAllLines(output, lines, Encoding.UTF8);
    }

    private static void BringTargetForeground(IntPtr hwnd, List<string> lines)
    {
        var currentThread = Native.GetCurrentThreadId();
        var foreground = Native.GetForegroundWindow();
        var foregroundThread = foreground == IntPtr.Zero ? 0 : Native.GetWindowThreadProcessId(foreground, out _);
        var targetThread = Native.GetWindowThreadProcessId(hwnd, out _);
        var attachedForeground = foregroundThread != 0 && foregroundThread != currentThread && Native.AttachThreadInput(currentThread, foregroundThread, true);
        var attachedTarget = targetThread != 0 && targetThread != currentThread && Native.AttachThreadInput(currentThread, targetThread, true);
        bool ok;
        try
        {
            Native.ShowWindow(hwnd, Native.SW_SHOWNORMAL);
            Native.BringWindowToTop(hwnd);
            ok = Native.SetForegroundWindow(hwnd);
            Native.SetActiveWindow(hwnd);
            Native.SetFocus(hwnd);
        }
        finally
        {
            if (attachedTarget) Native.AttachThreadInput(currentThread, targetThread, false);
            if (attachedForeground) Native.AttachThreadInput(currentThread, foregroundThread, false);
        }
        Thread.Sleep(200);
        lines.Add($"target_foreground=ok={ok}, attachForeground={attachedForeground}, attachTarget={attachedTarget}, " +
            $"before={DescribeWindow(foreground)}, now={DescribeWindow(Native.GetForegroundWindow())}");
    }

    private static void BringProbeForeground(List<string> lines)
    {
        var candidates = Process.GetProcessesByName("ChildInputProbe")
            .Where(process => process.Id != Environment.ProcessId && SafeSessionId(process) == Process.GetCurrentProcess().SessionId)
            .OrderByDescending(process => SafeStartTime(process))
            .ToArray();
        Process? probe = null;
        IntPtr hwnd = IntPtr.Zero;
        foreach (var candidate in candidates)
        {
            var candidateHwnd = FindTopLevelWindow(candidate.Id);
            if (candidateHwnd != IntPtr.Zero)
            {
                probe = candidate;
                hwnd = candidateHwnd;
                break;
            }
            candidate.Dispose();
        }
        if (probe is null)
        {
            lines.Add("probe_foreground=<no probe process>");
            return;
        }
        try
        {
            Native.ShowWindow(hwnd, Native.SW_SHOWNORMAL);
            var currentThread = Native.GetCurrentThreadId();
            var foregroundThread = Native.GetWindowThreadProcessId(Native.GetForegroundWindow(), out _);
            var targetThread = Native.GetWindowThreadProcessId(hwnd, out _);
            var attachedForeground = foregroundThread != 0 && foregroundThread != currentThread && Native.AttachThreadInput(currentThread, foregroundThread, true);
            var attachedTarget = targetThread != 0 && targetThread != currentThread && Native.AttachThreadInput(currentThread, targetThread, true);
            bool ok;
            try
            {
                Native.BringWindowToTop(hwnd);
                ok = Native.SetForegroundWindow(hwnd);
                Native.SetActiveWindow(hwnd);
                Native.SetFocus(hwnd);
            }
            finally
            {
                if (attachedTarget) Native.AttachThreadInput(currentThread, targetThread, false);
                if (attachedForeground) Native.AttachThreadInput(currentThread, foregroundThread, false);
            }
            Thread.Sleep(150);
            lines.Add($"probe_foreground=PID={probe.Id}, HWND=0x{hwnd.ToInt64():X}, set={ok}, attachForeground={attachedForeground}, attachTarget={attachedTarget}, now={DescribeWindow(Native.GetForegroundWindow())}");
        }
        finally { probe.Dispose(); }
    }

    private static IntPtr FindTopLevelWindow(int processId)
    {
        var result = IntPtr.Zero;
        Native.EnumWindows((hwnd, _) =>
        {
            Native.GetWindowThreadProcessId(hwnd, out var pid);
            if (pid == processId && Native.IsWindowVisible(hwnd) && Native.GetWindow(hwnd, Native.GW_OWNER) == IntPtr.Zero)
            {
                result = hwnd;
                return false;
            }
            return true;
        }, IntPtr.Zero);
        return result;
    }

    private static void AddGuiThreadInfo(List<string> lines, string label, uint threadId)
    {
        if (threadId == 0)
        {
            lines.Add($"{label}=<none>");
            return;
        }
        var info = new Native.GUITHREADINFO { cbSize = (uint)Marshal.SizeOf<Native.GUITHREADINFO>() };
        if (!Native.GetGUIThreadInfo(threadId, ref info))
        {
            lines.Add($"{label}=<error {Marshal.GetLastWin32Error()}>");
            return;
        }
        lines.Add(
            $"{label}: flags=0x{info.flags:X} active={DescribeWindow(info.hwndActive)} " +
            $"focus={DescribeWindow(info.hwndFocus)} capture={DescribeWindow(info.hwndCapture)} " +
            $"menu={DescribeWindow(info.hwndMenuOwner)} caret={DescribeWindow(info.hwndCaret)}"
        );
    }

    private static string DescribeWindow(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero) return "HWND=0";
        Native.GetWindowThreadProcessId(hwnd, out var pid);
        return $"0x{hwnd.ToInt64():X}/PID={pid}/'{Native.GetWindowText(hwnd)}'";
    }

    private static int SafeSessionId(Process process)
    {
        try { return process.SessionId; }
        catch { return -1; }
    }

    private static DateTime SafeStartTime(Process process)
    {
        try { return process.StartTime; }
        catch { return DateTime.MinValue; }
    }

    private static IntPtr FindLimbusWindow()
    {
        var result = IntPtr.Zero;
        Native.EnumWindows((hwnd, _) =>
        {
            if (Native.GetWindowText(hwnd) == "LimbusCompany")
            {
                result = hwnd;
                return false;
            }
            return true;
        }, IntPtr.Zero);
        return result;
    }

    private static void SendWmActivateKeybd(IntPtr hwnd, ushort vk, byte scan, List<string> lines, string label)
    {
        Native.SendMessageTimeout(hwnd, Native.WM_ACTIVATE, (IntPtr)Native.WA_ACTIVE, IntPtr.Zero, Native.SMTO_ABORTIFHUNG, 1000, out _);
        var before = Native.GetForegroundWindow();
        Native.keybd_event((byte)vk, scan, 0, UIntPtr.Zero);
        Thread.Sleep(30);
        Native.keybd_event((byte)vk, scan, Native.KEYEVENTF_KEYUP, UIntPtr.Zero);
        lines.Add($"{label}: vk=0x{vk:X2} scan=0x{scan:X2} foreground_before=0x{before.ToInt64():X} foreground_after=0x{Native.GetForegroundWindow().ToInt64():X}");
    }

    private static void CaptureWindow(IntPtr hwnd, string path, List<string> lines)
    {
        if (!Native.GetWindowRect(hwnd, out var rect))
        {
            lines.Add($"capture={Path.GetFileName(path)} failed rect={Marshal.GetLastWin32Error()}");
            return;
        }
        var width = Math.Max(1, rect.Right - rect.Left);
        var height = Math.Max(1, rect.Bottom - rect.Top);
        using var bitmap = new Bitmap(width, height, PixelFormat.Format32bppArgb);
        using var graphics = Graphics.FromImage(bitmap);
        var hdc = graphics.GetHdc();
        var ok = Native.PrintWindow(hwnd, hdc, 3);
        graphics.ReleaseHdc(hdc);
        bitmap.Save(path, ImageFormat.Png);
        using var stream = File.OpenRead(path);
        var hash = Convert.ToHexString(SHA256.HashData(stream));
        lines.Add($"capture={Path.GetFileName(path)} ok={ok} sha256={hash}");
    }
}

internal sealed class ProbeForm : Form
{
    private readonly string _logPath = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "AALC",
        "desktop-clone",
        "logs",
        "child-input-probe.log"
    );
    private readonly ComboBox _keyBox = new() { DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly Label _targetLabel = new() { AutoSize = true };
    private readonly TextBox _logBox = new()
    {
        Multiline = true,
        ReadOnly = true,
        ScrollBars = ScrollBars.Vertical,
        WordWrap = false,
        Dock = DockStyle.Fill,
        Font = new Font("Consolas", 9F),
    };

    private readonly System.Windows.Forms.Timer _timer = new() { Interval = 1000 };
    private Action? _pendingAction;
    private Process? _target;
    private IntPtr _targetHwnd;

    internal ProbeForm()
    {
        Text = "AALC Child Session Input Probe";
        Width = 980;
        Height = 680;
        StartPosition = FormStartPosition.CenterScreen;
        TopMost = true;

        _keyBox.Items.AddRange(["Up", "Right", "Enter", "P"]);
        _keyBox.SelectedIndex = 0;

        var top = new FlowLayoutPanel
        {
            Dock = DockStyle.Top,
            AutoSize = true,
            Padding = new Padding(8),
            WrapContents = true,
        };
        top.Controls.Add(new Label { Text = "Key:", AutoSize = true, Margin = new Padding(3, 8, 3, 3) });
        top.Controls.Add(_keyBox);
        top.Controls.Add(MakeButton("Refresh target", () => RefreshTarget()));
        top.Controls.Add(MakeButton("1 SendInput", () => Schedule("SendInput", SendUsingSendInput)));
        top.Controls.Add(MakeButton("2 keybd_event", () => Schedule("keybd_event", SendUsingKeybdEvent)));
        top.Controls.Add(MakeButton("3 PostMessage", () => Schedule("PostMessage", SendUsingPostMessage)));
        top.Controls.Add(MakeButton("4 SendMessage", () => Schedule("SendMessageTimeout", SendUsingSendMessage)));
        top.Controls.Add(MakeButton("5 WM_ACTIVATE + SendInput", () => Schedule("WM_ACTIVATE + SendInput", SendUsingWmActivateThenSendInput)));
        top.Controls.Add(MakeButton("6 SetForeground + SendInput", () => Schedule("SetForegroundWindow + SendInput", SendUsingSetForegroundThenSendInput)));
        top.Controls.Add(MakeButton("7 AttachThreadInput + SendInput", () => Schedule("AttachThreadInput + SetForegroundWindow + SendInput", SendUsingAttachedForeground)));
        top.Controls.Add(MakeButton("8 ScanCode SendInput", () => Schedule("scan-code SendInput", SendUsingScanCode)));
        top.Controls.Add(MakeButton("9 WM_ACTIVATE + keybd_event", () => Schedule("WM_ACTIVATE + keybd_event", SendUsingWmActivateThenKeybdEvent)));
        top.Controls.Add(MakeButton("10 SetForeground + keybd_event", () => Schedule("SetForegroundWindow + keybd_event", SendUsingSetForegroundThenKeybdEvent)));
        top.Controls.Add(MakeButton("11 WM_ACTIVATE + keybd(scan=0)", () => Schedule("WM_ACTIVATE + keybd_event(scan=0)", SendUsingWmActivateThenKeybdEventZeroScan)));

        var targetPanel = new Panel { Dock = DockStyle.Top, Height = 48, Padding = new Padding(10, 6, 10, 6) };
        _targetLabel.Dock = DockStyle.Fill;
        targetPanel.Controls.Add(_targetLabel);

        Controls.Add(_logBox);
        Controls.Add(targetPanel);
        Controls.Add(top);

        _timer.Tick += (_, _) =>
        {
            _timer.Stop();
            var action = _pendingAction;
            _pendingAction = null;
            action?.Invoke();
        };

        Shown += (_, _) =>
        {
            Log($"Probe PID={Environment.ProcessId}, Session={Process.GetCurrentProcess().SessionId}, Integrity={GetIntegrityHint()}, INPUT size={Marshal.SizeOf<Native.INPUT>()}");
            Log("Each button waits 1 second. The probe stays foreground so focus behavior matches clicking AALC UI.");
            RefreshTarget();
            foreach (var process in Process.GetProcessesByName("python"))
            {
                try
                {
                    if (process.SessionId == Process.GetCurrentProcess().SessionId)
                        Log($"Python PID={process.Id}, Integrity={Native.GetProcessIntegrityHint(process.Id)}");
                }
                catch { }
                finally { process.Dispose(); }
            }
        };
    }

    private Button MakeButton(string text, Action action)
    {
        var button = new Button { Text = text, AutoSize = true, Margin = new Padding(4) };
        button.Click += (_, _) => action();
        return button;
    }

    private void Schedule(string name, Action action)
    {
        if (!RefreshTarget())
            return;
        Log($"--- scheduling {name}, key={SelectedKeyName}, foreground={DescribeWindow(Native.GetForegroundWindow())}");
        _pendingAction = () => Execute(name, action);
        _timer.Start();
    }

    private void Execute(string name, Action action)
    {
        var before = Native.GetForegroundWindow();
        Native.SetLastError(0);
        try
        {
            action();
            var error = Marshal.GetLastWin32Error();
            Thread.Sleep(120);
            var after = Native.GetForegroundWindow();
            Log($"{name}: before={DescribeWindow(before)}; after={DescribeWindow(after)}; lastError={error} ({new Win32Exception(error).Message})");
        }
        catch (Win32Exception ex)
        {
            Log($"{name}: EXCEPTION Win32Exception({ex.NativeErrorCode}): {ex.Message}");
        }
        catch (Exception ex)
        {
            Log($"{name}: EXCEPTION {ex.GetType().Name}: {ex.Message}");
        }
    }

    private bool RefreshTarget()
    {
        _target?.Dispose();
        _target = null;
        _targetHwnd = IntPtr.Zero;
        var session = Process.GetCurrentProcess().SessionId;
        var candidates = Process.GetProcessesByName("LimbusCompany")
            .Where(process => SafeSessionId(process) == session)
            .OrderByDescending(process => SafeStartTime(process))
            .ToArray();
        _target = candidates.FirstOrDefault();
        foreach (var unused in candidates.Skip(1))
            unused.Dispose();
        if (_target is null)
        {
            _targetLabel.Text = $"No LimbusCompany.exe found in Session {session}";
            Log(_targetLabel.Text);
            return false;
        }

        _targetHwnd = _target.MainWindowHandle;
        if (_targetHwnd == IntPtr.Zero)
            _targetHwnd = FindTopLevelWindow(_target.Id);
        _targetLabel.Text = $"Target PID={_target.Id}, Session={session}, HWND=0x{_targetHwnd.ToInt64():X}, Title={Native.GetWindowText(_targetHwnd)}";
        Log(_targetLabel.Text);
        return _targetHwnd != IntPtr.Zero;
    }

    private static int SafeSessionId(Process process)
    {
        try { return process.SessionId; }
        catch { return -1; }
    }

    private static DateTime SafeStartTime(Process process)
    {
        try { return process.StartTime; }
        catch { return DateTime.MinValue; }
    }

    private static IntPtr FindTopLevelWindow(int processId)
    {
        var result = IntPtr.Zero;
        Native.EnumWindows((hwnd, _) =>
        {
            Native.GetWindowThreadProcessId(hwnd, out var pid);
            if (pid == processId && Native.IsWindowVisible(hwnd) && Native.GetWindow(hwnd, Native.GW_OWNER) == IntPtr.Zero)
            {
                result = hwnd;
                return false;
            }
            return true;
        }, IntPtr.Zero);
        return result;
    }

    private string SelectedKeyName => _keyBox.SelectedItem?.ToString() ?? "Up";

    private ushort SelectedVirtualKey => SelectedKeyName switch
    {
        "Up" => Native.VK_UP,
        "Right" => Native.VK_RIGHT,
        "Enter" => Native.VK_RETURN,
        "P" => Native.VK_P,
        _ => Native.VK_UP,
    };

    private void SendUsingSendInput() => Native.SendVirtualKey(SelectedVirtualKey);

    private void SendUsingKeybdEvent()
    {
        var vk = (byte)SelectedVirtualKey;
        var scan = (byte)Native.MapVirtualKey(vk, Native.MAPVK_VK_TO_VSC);
        Native.keybd_event(vk, scan, 0, UIntPtr.Zero);
        Thread.Sleep(30);
        Native.keybd_event(vk, scan, Native.KEYEVENTF_KEYUP, UIntPtr.Zero);
    }

    private void SendUsingPostMessage()
    {
        var vk = SelectedVirtualKey;
        Native.PostMessage(_targetHwnd, Native.WM_KEYDOWN, (IntPtr)vk, Native.MakeKeyLParam(vk, false));
        Thread.Sleep(30);
        Native.PostMessage(_targetHwnd, Native.WM_KEYUP, (IntPtr)vk, Native.MakeKeyLParam(vk, true));
    }

    private void SendUsingSendMessage()
    {
        var vk = SelectedVirtualKey;
        Native.SendMessageTimeout(_targetHwnd, Native.WM_KEYDOWN, (IntPtr)vk, Native.MakeKeyLParam(vk, false), Native.SMTO_ABORTIFHUNG, 1000, out _);
        Thread.Sleep(30);
        Native.SendMessageTimeout(_targetHwnd, Native.WM_KEYUP, (IntPtr)vk, Native.MakeKeyLParam(vk, true), Native.SMTO_ABORTIFHUNG, 1000, out _);
    }

    private void SendUsingWmActivateThenSendInput()
    {
        Native.SendMessageTimeout(_targetHwnd, Native.WM_ACTIVATE, (IntPtr)Native.WA_ACTIVE, IntPtr.Zero, Native.SMTO_ABORTIFHUNG, 1000, out _);
        Native.SendVirtualKey(SelectedVirtualKey);
    }

    private void SendUsingWmActivateThenKeybdEvent()
    {
        Native.SendMessageTimeout(_targetHwnd, Native.WM_ACTIVATE, (IntPtr)Native.WA_ACTIVE, IntPtr.Zero, Native.SMTO_ABORTIFHUNG, 1000, out _);
        SendUsingKeybdEvent();
    }

    private void SendUsingWmActivateThenKeybdEventZeroScan()
    {
        Native.SendMessageTimeout(_targetHwnd, Native.WM_ACTIVATE, (IntPtr)Native.WA_ACTIVE, IntPtr.Zero, Native.SMTO_ABORTIFHUNG, 1000, out _);
        var vk = (byte)SelectedVirtualKey;
        Native.keybd_event(vk, 0, 0, UIntPtr.Zero);
        Thread.Sleep(30);
        Native.keybd_event(vk, 0, Native.KEYEVENTF_KEYUP, UIntPtr.Zero);
    }

    private void SendUsingSetForegroundThenSendInput()
    {
        var ok = Native.SetForegroundWindow(_targetHwnd);
        Log($"SetForegroundWindow returned {ok}, foreground now {DescribeWindow(Native.GetForegroundWindow())}");
        Thread.Sleep(100);
        Native.SendVirtualKey(SelectedVirtualKey);
    }

    private void SendUsingSetForegroundThenKeybdEvent()
    {
        var ok = Native.SetForegroundWindow(_targetHwnd);
        Log($"SetForegroundWindow returned {ok}, foreground now {DescribeWindow(Native.GetForegroundWindow())}");
        Thread.Sleep(100);
        SendUsingKeybdEvent();
    }

    private void SendUsingAttachedForeground()
    {
        var foreground = Native.GetForegroundWindow();
        var currentThread = Native.GetCurrentThreadId();
        var foregroundThread = Native.GetWindowThreadProcessId(foreground, out _);
        var targetThread = Native.GetWindowThreadProcessId(_targetHwnd, out _);
        var attachForeground = foregroundThread != 0 && foregroundThread != currentThread && Native.AttachThreadInput(currentThread, foregroundThread, true);
        var attachTarget = targetThread != 0 && targetThread != currentThread && Native.AttachThreadInput(currentThread, targetThread, true);
        try
        {
            Native.BringWindowToTop(_targetHwnd);
            Native.SetForegroundWindow(_targetHwnd);
            Native.SetActiveWindow(_targetHwnd);
            Native.SetFocus(_targetHwnd);
        }
        finally
        {
            if (attachTarget) Native.AttachThreadInput(currentThread, targetThread, false);
            if (attachForeground) Native.AttachThreadInput(currentThread, foregroundThread, false);
        }
        Log($"AttachThreadInput foreground={attachForeground}, target={attachTarget}, foreground now {DescribeWindow(Native.GetForegroundWindow())}");
        Thread.Sleep(100);
        Native.SendVirtualKey(SelectedVirtualKey);
    }

    private void SendUsingScanCode()
    {
        var vk = SelectedVirtualKey;
        var scan = (ushort)Native.MapVirtualKey(vk, Native.MAPVK_VK_TO_VSC);
        Native.SendScanCode(scan, vk is Native.VK_UP or Native.VK_RIGHT);
    }

    private string DescribeWindow(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero) return "HWND=0";
        Native.GetWindowThreadProcessId(hwnd, out var pid);
        return $"0x{hwnd.ToInt64():X}/PID={pid}/'{Native.GetWindowText(hwnd)}'";
    }

    private void Log(string message)
    {
        var line = $"{DateTime.Now:HH:mm:ss.fff} {message}";
        _logBox.AppendText(line + Environment.NewLine);
        Debug.WriteLine(line);
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(_logPath)!);
            File.AppendAllText(_logPath, line + Environment.NewLine, Encoding.UTF8);
        }
        catch
        {
            // The on-screen log remains available if the profile directory is unavailable.
        }
    }

    internal static string GetIntegrityHint()
    {
        try
        {
            using var identity = System.Security.Principal.WindowsIdentity.GetCurrent();
            var principal = new System.Security.Principal.WindowsPrincipal(identity);
            return principal.IsInRole(System.Security.Principal.WindowsBuiltInRole.Administrator) ? "elevated" : "standard";
        }
        catch { return "unknown"; }
    }
}

internal static class Native
{
    internal const ushort VK_RETURN = 0x0D;
    internal const ushort VK_P = 0x50;
    internal const ushort VK_UP = 0x26;
    internal const ushort VK_RIGHT = 0x27;
    internal const uint WM_ACTIVATE = 0x0006;
    internal const uint WM_KEYDOWN = 0x0100;
    internal const uint WM_KEYUP = 0x0101;
    internal const int WA_ACTIVE = 1;
    internal const uint INPUT_KEYBOARD = 1;
    internal const uint KEYEVENTF_EXTENDEDKEY = 0x0001;
    internal const uint KEYEVENTF_KEYUP = 0x0002;
    internal const uint KEYEVENTF_SCANCODE = 0x0008;
    internal const uint MAPVK_VK_TO_VSC = 0;
    internal const uint SMTO_ABORTIFHUNG = 0x0002;
    internal const uint GW_OWNER = 4;
    internal const uint DESKTOP_READOBJECTS = 0x0001;
    internal const int UOI_NAME = 2;
    internal const int SW_SHOWNORMAL = 1;

    [StructLayout(LayoutKind.Sequential)]
    internal struct INPUT
    {
        internal uint type;
        internal InputUnion U;
    }

    // INPUT's native union is 32 bytes on x64 because MOUSEINPUT is larger
    // than KEYBDINPUT. SendInput rejects a 32-byte INPUT with ERROR_INVALID_PARAMETER;
    // the complete x64 INPUT structure must be 40 bytes.
    [StructLayout(LayoutKind.Explicit, Size = 32)]
    internal struct InputUnion
    {
        [FieldOffset(0)] internal KEYBDINPUT ki;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct KEYBDINPUT
    {
        internal ushort wVk;
        internal ushort wScan;
        internal uint dwFlags;
        internal uint time;
        internal UIntPtr dwExtraInfo;
    }

    internal delegate bool EnumWindowsProc(IntPtr hwnd, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential)]
    internal struct RECT
    {
        internal int Left;
        internal int Top;
        internal int Right;
        internal int Bottom;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct GUITHREADINFO
    {
        internal uint cbSize;
        internal uint flags;
        internal IntPtr hwndActive;
        internal IntPtr hwndFocus;
        internal IntPtr hwndCapture;
        internal IntPtr hwndMenuOwner;
        internal IntPtr hwndMoveSize;
        internal IntPtr hwndCaret;
        internal RECT rcCaret;
    }

    [DllImport("user32.dll", SetLastError = true)] internal static extern uint SendInput(uint count, INPUT[] inputs, int size);
    [DllImport("user32.dll", SetLastError = true)] internal static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extraInfo);
    [DllImport("user32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool PostMessage(IntPtr hwnd, uint msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll", SetLastError = true)] internal static extern IntPtr SendMessageTimeout(IntPtr hwnd, uint msg, IntPtr wParam, IntPtr lParam, uint flags, uint timeout, out IntPtr result);
    [DllImport("user32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll")] internal static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll", SetLastError = true)] internal static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);
    [DllImport("user32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool AttachThreadInput(uint attach, uint attachTo, [MarshalAs(UnmanagedType.Bool)] bool value);
    [DllImport("user32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool BringWindowToTop(IntPtr hwnd);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool ShowWindow(IntPtr hwnd, int command);
    [DllImport("user32.dll", SetLastError = true)] internal static extern IntPtr SetActiveWindow(IntPtr hwnd);
    [DllImport("user32.dll", SetLastError = true)] internal static extern IntPtr SetFocus(IntPtr hwnd);
    [DllImport("user32.dll")] internal static extern uint MapVirtualKey(uint code, uint mapType);
    [DllImport("kernel32.dll")] internal static extern uint GetCurrentThreadId();
    [DllImport("user32.dll", SetLastError = true)] internal static extern IntPtr GetThreadDesktop(uint threadId);
    [DllImport("user32.dll", SetLastError = true)] internal static extern IntPtr OpenInputDesktop(uint flags, [MarshalAs(UnmanagedType.Bool)] bool inherit, uint desiredAccess);
    [DllImport("user32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool CloseDesktop(IntPtr desktop);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool GetUserObjectInformation(IntPtr handle, int index, StringBuilder data, uint length, out uint needed);
    [DllImport("user32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool GetGUIThreadInfo(uint threadId, ref GUITHREADINFO info);
    [DllImport("kernel32.dll", SetLastError = true)] internal static extern IntPtr OpenProcess(uint access, [MarshalAs(UnmanagedType.Bool)] bool inheritHandle, int processId);
    [DllImport("advapi32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool OpenProcessToken(IntPtr processHandle, uint desiredAccess, out IntPtr tokenHandle);
    [DllImport("advapi32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool GetTokenInformation(IntPtr tokenHandle, int tokenInformationClass, IntPtr tokenInformation, int tokenInformationLength, out int returnLength);
    [DllImport("advapi32.dll")] internal static extern IntPtr GetSidSubAuthority(IntPtr sid, uint index);
    [DllImport("advapi32.dll")] internal static extern IntPtr GetSidSubAuthorityCount(IntPtr sid);
    [DllImport("kernel32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll")] internal static extern void SetLastError(uint error);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")] internal static extern IntPtr GetWindow(IntPtr hwnd, uint command);
    [DllImport("user32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool GetWindowRect(IntPtr hwnd, out RECT rect);
    [DllImport("user32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool PrintWindow(IntPtr hwnd, IntPtr hdc, uint flags);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int maxCount);

    internal static string GetWindowText(IntPtr hwnd)
    {
        var buffer = new StringBuilder(512);
        GetWindowText(hwnd, buffer, buffer.Capacity);
        return buffer.ToString();
    }

    internal static string GetDesktopName(IntPtr desktop)
    {
        if (desktop == IntPtr.Zero) return "<null>";
        var buffer = new StringBuilder(256);
        if (!GetUserObjectInformation(desktop, UOI_NAME, buffer, (uint)buffer.Capacity, out _))
            return $"<error {Marshal.GetLastWin32Error()}>";
        return buffer.ToString();
    }

    internal static IntPtr MakeKeyLParam(ushort vk, bool keyUp)
    {
        var scan = MapVirtualKey(vk, MAPVK_VK_TO_VSC) & 0xFF;
        long value = 1 | ((long)scan << 16);
        if (vk is VK_UP or VK_RIGHT) value |= 1L << 24;
        if (keyUp) value |= (1L << 30) | (1L << 31);
        return (IntPtr)value;
    }

    internal static void SendVirtualKey(ushort vk)
    {
        var extended = vk is VK_UP or VK_RIGHT ? KEYEVENTF_EXTENDEDKEY : 0;
        var inputs = new[]
        {
            new INPUT { type = INPUT_KEYBOARD, U = new InputUnion { ki = new KEYBDINPUT { wVk = vk, dwFlags = extended } } },
            new INPUT { type = INPUT_KEYBOARD, U = new InputUnion { ki = new KEYBDINPUT { wVk = vk, dwFlags = extended | KEYEVENTF_KEYUP } } },
        };
        var sent = SendInput((uint)inputs.Length, inputs, Marshal.SizeOf<INPUT>());
        if (sent != inputs.Length) throw new Win32Exception(Marshal.GetLastWin32Error(), $"SendInput sent {sent}/{inputs.Length}");
    }

    internal static void SendScanCode(ushort scan, bool extended)
    {
        var baseFlags = KEYEVENTF_SCANCODE | (extended ? KEYEVENTF_EXTENDEDKEY : 0);
        var inputs = new[]
        {
            new INPUT { type = INPUT_KEYBOARD, U = new InputUnion { ki = new KEYBDINPUT { wScan = scan, dwFlags = baseFlags } } },
            new INPUT { type = INPUT_KEYBOARD, U = new InputUnion { ki = new KEYBDINPUT { wScan = scan, dwFlags = baseFlags | KEYEVENTF_KEYUP } } },
        };
        var sent = SendInput((uint)inputs.Length, inputs, Marshal.SizeOf<INPUT>());
        if (sent != inputs.Length) throw new Win32Exception(Marshal.GetLastWin32Error(), $"scan-code SendInput sent {sent}/{inputs.Length}");
    }

    internal static string GetProcessIntegrityHint(int processId)
    {
        const uint PROCESS_QUERY_LIMITED_INFORMATION = 0x1000;
        const uint TOKEN_QUERY = 0x0008;
        const int TOKEN_MANDATORY_LABEL = 25;
        var process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, processId);
        if (process == IntPtr.Zero) return $"open-error={Marshal.GetLastWin32Error()}";
        try
        {
            if (!OpenProcessToken(process, TOKEN_QUERY, out var token)) return $"token-error={Marshal.GetLastWin32Error()}";
            try
            {
                GetTokenInformation(token, TOKEN_MANDATORY_LABEL, IntPtr.Zero, 0, out var size);
                var buffer = Marshal.AllocHGlobal(size);
                try
                {
                    if (!GetTokenInformation(token, TOKEN_MANDATORY_LABEL, buffer, size, out _))
                        return $"info-error={Marshal.GetLastWin32Error()}";
                    var sid = Marshal.ReadIntPtr(buffer);
                    var count = Marshal.ReadByte(GetSidSubAuthorityCount(sid));
                    var rid = Marshal.ReadInt32(GetSidSubAuthority(sid, (uint)(count - 1)));
                    return $"rid=0x{rid:X}";
                }
                finally { Marshal.FreeHGlobal(buffer); }
            }
            finally { CloseHandle(token); }
        }
        finally { CloseHandle(process); }
    }
}
