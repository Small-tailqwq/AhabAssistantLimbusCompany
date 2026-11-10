namespace AALC.Platform.Windows.DesktopClone;

/// <summary>与 Python 版共用的分身状态目录，两边读写相同的标记文件。</summary>
internal static class CloneStateFiles
{
    public static string Directory => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AALC", "desktop-clone");

    public static void WriteAtomically(string path, string content)
    {
        System.IO.Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var temporary = path + ".tmp";
        File.WriteAllText(temporary, content);
        File.Move(temporary, path, overwrite: true);
    }
}
