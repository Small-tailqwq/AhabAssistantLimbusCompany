using System.Text.Json;
using AALC.Core.Features.Daily;
using AALC.Core.Features.Mirror;

namespace AALC.Runtime.Configuration;

public sealed record DesktopSettings(string RepositoryRoot = "", string GameLanguage = "zh_cn", string GameTheme = "default",
    DailyOptions? Daily = null, string OcrModelsDirectory = "", MirrorOptions? Mirror = null,
    string GameExecutablePath = "", AppSettings? App = null);

/// <summary>AAALC 自身的行为偏好，与游戏和任务配置无关。</summary>
public sealed record AppSettings(string StartPage = "daily", bool ShowMonitorOnRun = true, bool FindWindowsOnStartup = true,
    bool RememberAngela = false);

public sealed class SettingsStore(string directory)
{
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

