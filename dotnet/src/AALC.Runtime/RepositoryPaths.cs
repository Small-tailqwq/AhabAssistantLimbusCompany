namespace AALC.Runtime;

public static class RepositoryPaths
{
    public static string? Discover(string start)
    {
        var directory = new DirectoryInfo(Path.GetFullPath(start));
        while (directory is not null)
        {
            if (Directory.Exists(Path.Combine(directory.FullName, "assets", "images")))
                return directory.FullName;
            directory = directory.Parent;
        }
        return null;
    }

    public static string OcrModels(string root) => Path.Combine(root, "assets", "models", "ocr");
}

