using System.Text.Json;
using AALC.Core.Features.Daily;
using AALC.Core.Features.Mirror;

namespace AALC.Runtime.Configuration;

public sealed record DesktopSettings(string RepositoryRoot = "", string GameLanguage = "zh_cn", string GameTheme = "default",
    DailyOptions? Daily = null, string OcrModelsDirectory = "", MirrorOptions? Mirror = null,
    string GameExecutablePath = "", AppSettings? App = null, CloneSettings? DesktopClone = null,
    LaunchSettings? Launch = null);

public sealed record LaunchSettings(bool Daily = true, bool Harvest = false, bool Mirror = false);

/// <summary>AAALC 自身的行为偏好，与游戏和任务配置无关。</summary>
public sealed record AppSettings(string StartPage = "daily", bool ShowMonitorOnRun = true, bool FindWindowsOnStartup = true,
    bool RememberAngela = false);

/// <summary>桌面分身的行为偏好。</summary>
public sealed record CloneSettings(bool RunTasksInClone = false, bool ShowWindowOnStart = true, bool IgnoreRemoteControlWarning = false);

public sealed class SettingsStore(string directory)
{
    private static string LegacyDirectory => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AALC.Next");

    /// <summary>
    /// 默认配置放在数据根下。由 Codex、Claude 等打包应用启动时，AppData 写入会被 MSIX 重定向到各自的包目录，
    /// 不同入口会读到不同的配置；数据根所在盘不存在时才沿用旧的 AppData 目录。
    /// </summary>
    public static SettingsStore OpenDefault()
    {
        string directory;
        try
        {
            directory = Path.Combine(EvidencePaths.ResolveRoot(), "profile");
            if (!Directory.Exists(Path.GetPathRoot(directory))) directory = LegacyDirectory;
        }
        catch (InvalidDataException) { directory = LegacyDirectory; }
        var store = new SettingsStore(directory);
        var legacy = Path.Combine(LegacyDirectory, "settings.json");
        if (store.DirectoryPath != Path.GetFullPath(LegacyDirectory) && !File.Exists(store.SettingsPath) && File.Exists(legacy))
        {
            Directory.CreateDirectory(store.DirectoryPath);
            File.Copy(legacy, store.SettingsPath);
        }
        return store;
    }

    public string DirectoryPath { get; } = Path.GetFullPath(directory);
    private string SettingsPath => Path.Combine(DirectoryPath, "settings.json");
    public DesktopSettings Load() => File.Exists(SettingsPath)
        ? JsonSerializer.Deserialize<DesktopSettings>(File.ReadAllText(SettingsPath)) ?? throw new InvalidDataException("配置为空")
        : new();
    public void Save(DesktopSettings settings)
    {
        Directory.CreateDirectory(DirectoryPath);
        var temporary = SettingsPath + ".tmp";
        File.WriteAllText(temporary, JsonSerializer.Serialize(settings, new JsonSerializerOptions { WriteIndented = true }));
        File.Move(temporary, SettingsPath, overwrite: true);
    }
}

