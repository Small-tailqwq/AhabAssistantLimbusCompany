using Microsoft.Win32;

namespace AALC.Platform.Windows.Tools;

public static class SteamLocator
{
    /// <summary>分身内由 Steam 自己启动游戏，以复用同一 Windows 用户的登录态。</summary>
    public const string LaunchArguments = "-applaunch 1973530";

    public static string? FindExecutable()
    {
        foreach (var candidate in Candidates())
            if (File.Exists(candidate)) return Path.GetFullPath(candidate);
        return null;
    }

    private static IEnumerable<string> Candidates()
    {
        (RegistryKey Hive, string Key, string Value)[] sources =
        [
            (Registry.CurrentUser, @"Software\Valve\Steam", "SteamExe"),
            (Registry.CurrentUser, @"Software\Valve\Steam", "SteamPath"),
            (Registry.LocalMachine, @"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            (Registry.LocalMachine, @"SOFTWARE\Valve\Steam", "InstallPath")
        ];
        foreach (var (hive, key, value) in sources)
        {
            using var steam = hive.OpenSubKey(key);
            if (steam?.GetValue(value) is not string { Length: > 0 } path) continue;
            path = path.Replace('/', Path.DirectorySeparatorChar);
            yield return path.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) ? path : Path.Combine(path, "steam.exe");
        }
        yield return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), "Steam", "steam.exe");
    }
}
