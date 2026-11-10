namespace AALC.Runtime.Tools;

public static class GameInstallation
{
    public const string ExecutableName = "LimbusCompany.exe";

    public static string NormalizeDirectory(string directory)
    {
        var path = Environment.ExpandEnvironmentVariables(directory.Trim().Trim('"'));
        if (!Path.IsPathFullyQualified(path))
            throw new InvalidDataException("请在设置中选择 Limbus Company 的完整安装目录。");
        return Path.TrimEndingDirectorySeparator(Path.GetFullPath(path));
    }

    public static bool IsInstalled(string directory) => File.Exists(Path.Combine(directory, ExecutableName))
        && Directory.Exists(Path.Combine(directory, "LimbusCompany_Data"));

    public static string RequireDirectory(string directory)
    {
        var path = NormalizeDirectory(directory);
        if (!IsInstalled(path))
            throw new InvalidDataException("游戏安装目录中未找到 LimbusCompany.exe 或 LimbusCompany_Data，请在设置中重新搜索或选择目录。");
        return path;
    }
}
