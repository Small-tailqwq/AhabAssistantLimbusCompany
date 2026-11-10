using AALC.Runtime;
using Xunit;

namespace AALC.Core.Tests;

public sealed class RecordingStorageTests : IDisposable
{
    private readonly string root = Path.Combine(Path.GetTempPath(), "aaalc-recordings-" + Guid.NewGuid().ToString("N"));

    private string Run(string kind, string name, int bytes)
    {
        var directory = Path.Combine(root, "recordings", kind, name);
        Directory.CreateDirectory(directory);
        File.WriteAllBytes(Path.Combine(directory, "frame-000001.png"), new byte[bytes]);
        return directory;
    }

    [Fact]
    public void OldestRunsAreRemovedAcrossKindsUntilWithinLimit()
    {
        var oldest = Run("mirror", "20261029-100000-000", 40);
        var older = Run("daily", "20261030-100000-000", 40);
        var newer = Run("mirror", "20261031-100000-000", 40);

        RecordingStorage.Prune(root, 50);

        Assert.False(Directory.Exists(oldest));
        Assert.False(Directory.Exists(older));
        Assert.True(Directory.Exists(newer));
    }

    [Fact]
    public void RunsWithinLimitAreKept()
    {
        var run = Run("mirror", "20261031-100000-000", 40);

        RecordingStorage.Prune(root, 40);

        Assert.True(Directory.Exists(run));
    }

    [Fact]
    public void DirectoriesWithoutRunTimestampAreNeverRemoved()
    {
        var other = Run("mirror", "keep-me", 100);
        var unrelated = Path.Combine(root, "validation", "20261029-100000-000");
        Directory.CreateDirectory(unrelated);
        File.WriteAllBytes(Path.Combine(unrelated, "frame.png"), new byte[100]);

        RecordingStorage.Prune(root, 0);

        Assert.True(Directory.Exists(other));
        Assert.True(Directory.Exists(unrelated));
    }

    [Fact]
    public void MissingRecordingsDirectoryIsIgnored() => RecordingStorage.Prune(root);

    [Fact]
    public void OnlyTheNewestFramesAreKept()
    {
        Directory.CreateDirectory(root);
        var frames = Enumerable.Range(1, 5).Select(index => Path.Combine(root, $"frame-{index}.png")).ToArray();
        var retention = new FrameRetention(2);

        foreach (var frame in frames)
        {
            File.WriteAllBytes(frame, [1]);
            retention.Written(frame);
        }

        Assert.Equal([false, false, false, true, true], frames.Select(File.Exists));
    }

    public void Dispose()
    {
        if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
    }
}
