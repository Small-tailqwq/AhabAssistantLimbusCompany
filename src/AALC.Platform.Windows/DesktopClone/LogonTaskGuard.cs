using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text.Json;

namespace AALC.Platform.Windows.DesktopClone;

/// <summary>
/// 登录触发的计划任务不经过 explorer，Run 策略拦不住，Child Session 登录时同样会触发，所以在登录窗口期临时禁用。
/// 禁用只阻止新实例，主桌面已在运行的实例不受影响。\Microsoft 下是系统任务，服务账户任务运行在会话 0，都不处理。
/// 先写标记再禁用，标记里的任务都是抑制前处于启用状态的，崩溃后由下一次以管理员身份运行恢复。
/// </summary>
internal static class LogonTaskGuard
{
    private const int EnumHidden = 1;
    private const int LogonServiceAccount = 5;
    private const int TriggerLogon = 9;
    private const string SystemFolder = @"\Microsoft";

    public static string MarkerPath => Path.Combine(CloneStateFiles.Directory, ".autorun-guard-tasks.json");
    public static bool IsActive => File.Exists(MarkerPath);

    /// <summary>已处于抑制状态时保留最初的记录。返回未能禁用的任务。</summary>
    public static IReadOnlyList<string> Suppress()
    {
        if (IsActive) return [];
        dynamic root = OpenRoot();
        var tasks = new List<string>();
        Collect(root, WindowsIdentity.GetCurrent().Name, tasks);
        CloneStateFiles.WriteAtomically(MarkerPath, JsonSerializer.Serialize(tasks));
        var skipped = new List<string>();
        foreach (var path in tasks)
        {
            try { root.GetTask(path).Enabled = false; }
            catch (Exception exception) when (exception is COMException or UnauthorizedAccessException) { skipped.Add(path); }
        }
        return skipped;
    }

    /// <summary>重新启用记录里的任务；有任务恢复失败时保留记录，下次重试。</summary>
    public static void Restore()
    {
        if (!IsActive) return;
        var tasks = JsonSerializer.Deserialize<string[]>(File.ReadAllText(MarkerPath))
            ?? throw new InvalidDataException("登录任务抑制记录为空");
        dynamic root = OpenRoot();
        foreach (var path in tasks)
        {
            try { root.GetTask(path).Enabled = true; }
            // 任务在窗口期内被卸载时不需要恢复。
            catch (FileNotFoundException) { }
        }
        File.Delete(MarkerPath);
    }

    private static dynamic OpenRoot()
    {
        dynamic scheduler = Activator.CreateInstance(Type.GetTypeFromProgID("Schedule.Service", true)!)!;
        scheduler.Connect();
        return scheduler.GetFolder("\\");
    }

    private static void Collect(dynamic folder, string account, List<string> tasks)
    {
        dynamic registered = folder.GetTasks(EnumHidden);
        for (var index = 1; index <= (int)registered.Count; index++)
        {
            try
            {
                dynamic task = registered[index];
                dynamic definition = task.Definition;
                if ((bool)task.Enabled && (int)definition.Principal.LogonType != LogonServiceAccount && FiresOnLogonOf(definition.Triggers, account))
                    tasks.Add((string)task.Path);
            }
            catch (Exception exception) when (exception is COMException or UnauthorizedAccessException) { }
        }
        dynamic children = folder.GetFolders(0);
        for (var index = 1; index <= (int)children.Count; index++)
        {
            dynamic child = children[index];
            if (!string.Equals((string)child.Path, SystemFolder, StringComparison.OrdinalIgnoreCase)) Collect(child, account, tasks);
        }
    }

    private static bool FiresOnLogonOf(dynamic triggers, string account)
    {
        for (var index = 1; index <= (int)triggers.Count; index++)
        {
            dynamic trigger = triggers[index];
            if ((int)trigger.Type != TriggerLogon) continue;
            var user = (string?)trigger.UserId;
            if (string.IsNullOrEmpty(user) || string.Equals(user, account, StringComparison.OrdinalIgnoreCase)) return true;
        }
        return false;
    }
}
