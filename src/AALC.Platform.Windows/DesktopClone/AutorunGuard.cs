using System.Text.Json;
using Microsoft.Win32;

namespace AALC.Platform.Windows.DesktopClone;

/// <summary>
/// Child Session 是完整交互登录，explorer 会重放用户全部 Run 自启动项；终端服务的初始程序在客户端系统上被忽略，
/// 所以在登录窗口期临时设置 Explorer 策略。主会话的 explorer 只在启动时读取这些策略，不受影响。
/// 实测 build 26300 只有 HKLM 下的策略生效。HKCU 部分的标记文件与 Python 版同名同格式，任一方崩溃遗留的抑制都能由另一方恢复；
/// HKLM 部分需要管理员权限，普通权限启动时恢复失败并保留标记，等下一次以管理员身份运行。
/// </summary>
public static class AutorunGuard
{
    private const string PolicyKey = @"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer";
    private static readonly string[] PolicyValues =
        ["DisableLocalMachineRun", "DisableLocalMachineRunOnce", "DisableCurrentUserRun", "DisableCurrentUserRunOnce"];

    public static string MarkerPath => Path.Combine(CloneStateFiles.Directory, ".autorun-guard.json");
    public static string MachineMarkerPath => Path.Combine(CloneStateFiles.Directory, ".autorun-guard-machine.json");
    public static bool IsActive => File.Exists(MarkerPath) || File.Exists(MachineMarkerPath) || LogonTaskGuard.IsActive;

    /// <summary>返回未能禁用的登录任务。</summary>
    public static IReadOnlyList<string> Suppress()
    {
        Suppress(Registry.CurrentUser, MarkerPath);
        Suppress(Registry.LocalMachine, MachineMarkerPath);
        return LogonTaskGuard.Suppress();
    }

    /// <summary>恢复到抑制前的原始值；没有记录时不做任何事。</summary>
    public static void Restore()
    {
        Restore(Registry.CurrentUser, MarkerPath);
        try { Restore(Registry.LocalMachine, MachineMarkerPath); }
        finally { LogonTaskGuard.Restore(); }
    }

    /// <summary>已处于抑制状态时保留最初的快照。</summary>
    private static void Suppress(RegistryKey hive, string marker)
    {
        if (File.Exists(marker)) return;
        using var key = hive.CreateSubKey(PolicyKey, writable: true);
        var previous = new Dictionary<string, int?>();
        foreach (var name in PolicyValues)
        {
            var value = key.GetValue(name, null, RegistryValueOptions.DoNotExpandEnvironmentNames);
            if (value is not (null or int)) throw new InvalidDataException($"Explorer Run 策略值 {name} 不是 DWORD，跳过自启动抑制");
            previous[name] = value as int?;
        }
        CloneStateFiles.WriteAtomically(marker, JsonSerializer.Serialize(previous));
        foreach (var name in PolicyValues) key.SetValue(name, 1, RegistryValueKind.DWord);
    }

    private static void Restore(RegistryKey hive, string marker)
    {
        if (!File.Exists(marker)) return;
        var previous = JsonSerializer.Deserialize<Dictionary<string, int?>>(File.ReadAllText(marker))
            ?? throw new InvalidDataException("自启动抑制记录为空");
        using var key = hive.CreateSubKey(PolicyKey, writable: true);
        foreach (var name in PolicyValues)
        {
            if (previous.GetValueOrDefault(name) is { } prior) key.SetValue(name, prior, RegistryValueKind.DWord);
            else key.DeleteValue(name, throwOnMissingValue: false);
        }
        File.Delete(marker);
    }
}
