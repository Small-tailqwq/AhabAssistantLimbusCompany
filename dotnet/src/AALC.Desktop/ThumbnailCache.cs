using System.IO;
using Avalonia.Media.Imaging;

namespace AALC.Desktop;

public static class ThumbnailCache
{
    private static readonly object Sync = new();
    private static readonly Dictionary<(string Path, int Width), Task<Bitmap>> Images = [];
    private static readonly SemaphoreSlim Decoders = new(2);
    private static bool disposed;

    public static Task<Bitmap> GetAsync(string fullPath, int decodeWidth)
    {
        var key = (Path.GetFullPath(fullPath).ToUpperInvariant(), decodeWidth);
        lock (Sync)
        {
            ObjectDisposedException.ThrowIf(disposed, typeof(ThumbnailCache));
            if (Images.TryGetValue(key, out var cached)) return cached;
            var task = Task.Run(async () =>
            {
                await Decoders.WaitAsync().ConfigureAwait(false);
                try
                {
                    using var stream = File.OpenRead(fullPath);
                    return Bitmap.DecodeToWidth(stream, decodeWidth);
                }
                finally { Decoders.Release(); }
            });
            Images.Add(key, task);
            _ = task.ContinueWith(completed =>
            {
                lock (Sync)
                    if (Images.TryGetValue(key, out var current) && ReferenceEquals(current, completed)) Images.Remove(key);
            }, CancellationToken.None, TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously,
                TaskScheduler.Default);
            return task;
        }
    }

    public static void Dispose()
    {
        lock (Sync)
        {
            disposed = true;
            foreach (var task in Images.Values)
                _ = task.ContinueWith(completed => completed.Result.Dispose(), CancellationToken.None,
                    TaskContinuationOptions.OnlyOnRanToCompletion | TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
            Images.Clear();
        }
    }
}
