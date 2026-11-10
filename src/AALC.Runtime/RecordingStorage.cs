using System.Text.RegularExpressions;

namespace AALC.Runtime;

/// <summary>限制桌面运行的录制占用：单次保留结尾的帧，总量超限时删最旧的运行。CLI 用于回放验证，不受限制。</summary>
public static partial class RecordingStorage
{
    public const long MaxTotalBytes = 5L * 1024 * 1024 * 1024;
    public const int KeptFrames = 300;

    /// <summary>只处理 recordings/&lt;类型&gt;/ 下时间戳命名的运行目录；清理失败不影响任务。</summary>
    public static void Prune(string root, long maxBytes = MaxTotalBytes)
    {
        var recordings = Path.Combine(root, "recordings");
        if (!Directory.Exists(recordings)) return;
        try
        {
            var runs = Directory.GetDirectories(recordings).Where(IsRealDirectory).SelectMany(Directory.GetDirectories)
                .Where(path => RunName().IsMatch(Path.GetFileName(path)) && IsRealDirectory(path))
                .Select(path => (Path: path, Size: Directory.EnumerateFiles(path, "*", SearchOption.AllDirectories).Sum(file => new FileInfo(file).Length)))
                .OrderBy(run => Path.GetFileName(run.Path), StringComparer.Ordinal).ToList();
            var total = runs.Sum(run => run.Size);
            foreach (var (path, size) in runs)
            {
                if (total <= maxBytes) return;
                try
                {
                    Directory.Delete(path, recursive: true);
                    total -= size;
                }
                catch (Exception exception) when (exception is IOException or UnauthorizedAccessException) { }
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException) { }
    }

    private static bool IsRealDirectory(string path) => !File.GetAttributes(path).HasFlag(FileAttributes.ReparsePoint);

    [GeneratedRegex(@"^\d{8}-\d{6}-\d{3}$")]
    private static partial Regex RunName();
}

public sealed class FrameRetention(int kept)
{
    private readonly Queue<string> frames = new();

    public void Written(string path)
    {
        frames.Enqueue(path);
        if (frames.Count <= kept) return;
        try { File.Delete(frames.Dequeue()); }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException) { }
    }
}
