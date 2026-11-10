namespace AALC.Runtime;

public static class EvidencePaths
{
    public static string ResolveRoot() => RequireExternalPath(
        Environment.GetEnvironmentVariable("AALC_DATA_ROOT") ?? @"D:\AALCData");

    public static string RequireExternalPath(string path) => Resolve(path, 0);

    private static string Resolve(string path, int links)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        if (links >= 40) throw new IOException("证据目录包含过多目录链接");
        var full = Path.GetFullPath(path);
        if (full.StartsWith(@"\\?\", StringComparison.Ordinal)) full = full[4..];
        if (full.Length < 3 || !char.IsAsciiLetter(full[0]) || full[1] != ':' || full[2] != '\\')
            throw new InvalidDataException("证据路径须使用可确认的本地非 C 盘路径");
        if (char.ToUpperInvariant(full[0]) == 'C') throw new InvalidDataException("证据和截图禁止写入 C 盘，请使用 D 盘或设置 AALC_DATA_ROOT");

        var current = full[..3];
        var parts = full[current.Length..].Split(Path.DirectorySeparatorChar, StringSplitOptions.RemoveEmptyEntries);
        for (var index = 0; index < parts.Length; index++)
        {
            current = Path.Combine(current, parts[index]);
            FileAttributes attributes;
            try { attributes = File.GetAttributes(current); }
            catch (FileNotFoundException) { return Path.Combine([current, .. parts[(index + 1)..]]); }
            catch (DirectoryNotFoundException) { return Path.Combine([current, .. parts[(index + 1)..]]); }
            if (!attributes.HasFlag(FileAttributes.ReparsePoint)) continue;
            FileSystemInfo entry = attributes.HasFlag(FileAttributes.Directory) ? new DirectoryInfo(current) : new FileInfo(current);
            var target = entry.ResolveLinkTarget(true) ?? throw new IOException($"无法确认链接的最终路径：{current}");
            current = Resolve(target.FullName, links + 1);
        }
        return current;
    }
}
