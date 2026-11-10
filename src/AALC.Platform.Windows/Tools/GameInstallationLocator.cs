using System.Text.RegularExpressions;
using AALC.Runtime.Tools;
using Microsoft.Win32;

namespace AALC.Platform.Windows.Tools;

public static class GameInstallationLocator
{
    public static string? Find()
    {
        foreach (var path in Candidates().Distinct(StringComparer.OrdinalIgnoreCase))
        {
            var directory = GameInstallation.NormalizeDirectory(path);
            if (GameInstallation.IsInstalled(directory)) return directory;
        }
        return null;
    }

    private static IEnumerable<string> Candidates()
    {
        var steamRoots = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var hive in new[] { RegistryHive.CurrentUser, RegistryHive.LocalMachine })
        foreach (var view in new[] { RegistryView.Registry64, RegistryView.Registry32 })
        {
            using var root = RegistryKey.OpenBaseKey(hive, view);
            using var uninstall = root.OpenSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 1973530");
            if (uninstall?.GetValue("InstallLocation") is string { Length: > 0 } location) yield return location;
            using var steam = root.OpenSubKey(@"SOFTWARE\Valve\Steam");
            var valueName = hive == RegistryHive.CurrentUser ? "SteamPath" : "InstallPath";
            if (steam?.GetValue(valueName) is string { Length: > 0 } path)
                steamRoots.Add(GameInstallation.NormalizeDirectory(path));
        }

        foreach (var steam in steamRoots)
        {
            var libraries = new[] { steam }.Concat(ReadVdfValues(Path.Combine(steam, "steamapps", "libraryfolders.vdf"), "path"));
            foreach (var library in libraries.Distinct(StringComparer.OrdinalIgnoreCase))
            {
                var apps = Path.Combine(GameInstallation.NormalizeDirectory(library), "steamapps");
                foreach (var install in ReadVdfValues(Path.Combine(apps, "appmanifest_1973530.acf"), "installdir"))
                    yield return Path.Combine(apps, "common", install);
            }
        }
    }

    private static IEnumerable<string> ReadVdfValues(string file, string key)
    {
        if (!File.Exists(file)) yield break;
        foreach (Match match in Regex.Matches(File.ReadAllText(file), $"\"{key}\"\\s*\"([^\"]+)\""))
            // VDF 的双反斜杠是转义；普通 Windows 路径不做正则反转义。
            yield return match.Groups[1].Value.Replace(@"\\", @"\");
    }
}
