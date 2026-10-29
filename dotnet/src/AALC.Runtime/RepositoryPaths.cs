namespace AALC.Runtime;

public static class RepositoryPaths
{
    public static string? Discover(string start)
    {
        var directory = new DirectoryInfo(Path.GetFullPath(start));
        while (directory is not null)
        {
            if (File.Exists(Path.Combine(directory.FullName, "assets", "config", "config.example.yaml")))
                return directory.FullName;
            directory = directory.Parent;
        }
        return null;
    }
}

