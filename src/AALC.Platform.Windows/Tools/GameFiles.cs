using System.Diagnostics;
using System.Text.Json.Nodes;
using AALC.Runtime.Tools;
using Microsoft.Win32;

namespace AALC.Platform.Windows.Tools;

public static class GameFiles
{
    public static string TutorialDirectory => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "AppData", "LocalLow", "ProjectMoon", "LimbusCompany");

    public static void RequireGameClosed()
    {
        var processes = Process.GetProcessesByName("LimbusCompany");
        try
        {
            if (processes.Length > 0) throw new InvalidOperationException("请先退出 Limbus Company，再安装汉化或修改新手提示。");
        }
        finally { foreach (var process in processes) process.Dispose(); }
    }

    public static async Task<string> SetTutorialsDisabledAsync(bool disabled, IProgress<string> progress, CancellationToken cancellationToken)
    {
        RequireGameClosed();
        using var registry = Registry.CurrentUser.OpenSubKey(@"Software\ProjectMoon\LimbusCompany");
        var preference = registry?.GetValueNames().SingleOrDefault(name => name.Contains("LocalSave.LocalGameOptionData", StringComparison.Ordinal));
        if (preference is null || registry!.GetValue(preference) is not byte[] bytes)
            throw new InvalidDataException("无法从注册表读取存档密钥，请确认游戏已至少运行过一次。");
        var options = JsonNode.Parse(bytes.AsSpan(0, Array.FindLastIndex(bytes, value => value != 0) + 1))!;
        var key = Convert.FromBase64String(options["key"]!.GetValue<string>());
        var iv = Convert.FromBase64String(options["iv"]!.GetValue<string>());
        var slots = Directory.Exists(TutorialDirectory) ? Directory.GetFiles(TutorialDirectory, "save_slot_*.json") : [];
        if (slots.Length == 0) throw new FileNotFoundException($"未找到存档：{TutorialDirectory}");
        var patches = new List<(string Path, TutorialSavePatch Patch)>();
        foreach (var path in slots)
        {
            cancellationToken.ThrowIfCancellationRequested();
            progress.Report($"正在读取 {Path.GetFileName(path)}…");
            var patch = TutorialSave.Patch(await File.ReadAllTextAsync(path, cancellationToken), key, iv, disabled);
            if (patch.ModifiedModels + patch.AddedModels > 0) patches.Add((path, patch));
        }
        var suffix = ".aaalc-backup-" + DateTime.Now.ToString("yyyyMMdd-HHmmss-fff") + "-" + Guid.NewGuid().ToString("N")[..8];
        foreach (var (path, patch) in patches)
        {
            cancellationToken.ThrowIfCancellationRequested();
            RequireGameClosed();
            var temporary = path + ".aaalc-" + Guid.NewGuid().ToString("N") + ".tmp";
            var backup = path + suffix;
            try
            {
                await File.WriteAllTextAsync(temporary, patch.Encrypted, cancellationToken);
                cancellationToken.ThrowIfCancellationRequested();
                File.Replace(temporary, path, backup);
                progress.Report($"{Path.GetFileName(path)}：修改 {patch.ModifiedModels} 个模型，补充 {patch.AddedModels} 个；备份：{backup}");
            }
            finally { if (File.Exists(temporary)) File.Delete(temporary); }
        }
        return patches.Count == 0 ? "新手提示状态无需修改。"
            : $"已{(disabled ? "关闭" : "恢复")}新手提示，修改 {patches.Count} 个存档。原文件备份保存在存档目录。";
    }
}
