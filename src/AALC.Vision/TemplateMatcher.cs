using AALC.Runtime.Automation;
using System.Runtime.InteropServices;
using AALC.Core.Features.Mail;
using AALC.Runtime.Mail;
using OpenCvSharp;
using AALC.Core.Features.Daily;
using AALC.Runtime.Daily;

namespace AALC.Vision;

public enum TemplateSearch { Clam, Normal, Aggressive }
public sealed record MatchResult(string Key, string Path, double Score, PixelPoint? Center, int[]? Bounds);
public sealed record TemplateOptions(string Language = "zh_cn", string Theme = "default");

public sealed class TemplateMatcher(string repositoryRoot, TemplateOptions options) : IDisposable
{
    private readonly Dictionary<(string, int), (Mat Image, Rect? Bounds)> cache = [];
    private readonly string assetsRoot = Path.Combine(repositoryRoot, "assets", "images");

    public static Mat Gray(PixelFrame frame)
    {
        using var bgra = new Mat(frame.Identity.Height, frame.Identity.Width, MatType.CV_8UC4);
        if (frame.Bgra.Length != frame.Identity.Width * frame.Identity.Height * 4)
            throw new InvalidDataException("帧缓冲区尺寸不匹配");
        Marshal.Copy(frame.Bgra, 0, bgra.Data, frame.Bgra.Length);
        return Gray(bgra);
    }

    public static Mat Gray(Mat bgr)
    {
        if (bgr.Type() == MatType.CV_8UC1) return bgr.Clone();
        if (bgr.Type() != MatType.CV_8UC3 && bgr.Type() != MatType.CV_8UC4)
            throw new ArgumentException("截图必须是 8 位 BGR 或 BGRA");
        var gray = new Mat(bgr.Height, bgr.Width, MatType.CV_8UC1);
        var channels = bgr.Channels();
        var source = new byte[bgr.Width * channels];
        var target = new byte[bgr.Width];
        for (var y = 0; y < bgr.Height; y++)
        {
            Marshal.Copy(bgr.Ptr(y), source, 0, source.Length);
            for (var x = 0; x < bgr.Width; x++)
            {
                var offset = x * channels;
                // Automation.take_screenshot uses Pillow Image.convert("L").
                target[x] = (byte)((source[offset + 2] * 19595 + source[offset + 1] * 38470 + source[offset] * 7471 + 32768) >> 16);
            }
            Marshal.Copy(target, 0, gray.Ptr(y), target.Length);
        }
        return gray;
    }

    public MatchResult Match(Mat gray, string key, TemplateSearch search = TemplateSearch.Clam)
    {
        MatchResult? best = null;
        foreach (var path in Resolve(key))
        {
            var (template, bounds) = Load(path, key, gray.Height);
            var area = new Rect(0, 0, gray.Width, gray.Height);
            if (bounds is { } box && search != TemplateSearch.Aggressive)
            {
                var baseMargin = search == TemplateSearch.Normal ? 100 : 30;
                var margin = Math.Max(baseMargin, (int)(baseMargin * gray.Height / 1440.0));
                var x = Math.Max(0, box.X - margin);
                var y = Math.Max(0, box.Y - margin);
                area = new Rect(x, y, Math.Min(gray.Width, box.Right + margin) - x,
                    Math.Min(gray.Height, box.Bottom + margin) - y);
            }
            PixelPoint? center = null;
            double score = 0;
            if (area.Width >= template.Width && area.Height >= template.Height)
            {
                using var region = new Mat(gray, area);
                using var result = new Mat();
                Cv2.MatchTemplate(region, template, result, TemplateMatchModes.CCoeffNormed);
                Cv2.MinMaxLoc(result, out _, out score, out _, out var location);
                center = new(area.X + location.X + template.Width / 2, area.Y + location.Y + template.Height / 2);
            }
            var match = new MatchResult(key, Path.GetRelativePath(assetsRoot, path).Replace('\\', '/'), score,
                center, bounds is { } b ? [b.X, b.Y, b.Right, b.Bottom] : null);
            if (best is null || score > best.Score) best = match;
        }
        return best ?? throw new FileNotFoundException($"缺少模板 {key}");
    }

    private IEnumerable<string> Resolve(string key)
    {
        if (options.Language is not ("zh_cn" or "en") || options.Theme is not ("default" or "dark"))
            throw new InvalidDataException("图像语言或主题无效");
        var paths = new List<string>();
        foreach (var theme in options.Theme == "dark" ? new[] { "dark", "default" } : ["default"])
        {
            foreach (var language in new[] { "zh_cn", "en", "share" })
            {
                foreach (var candidate in new[] { Path.ChangeExtension(key, ".webp"), key })
                {
                    var path = Path.Combine(assetsRoot, theme, language, candidate);
                    if (File.Exists(path))
                    {
                        paths.Add(path);
                        break;
                    }
                }
            }
        }
        if (options.Theme == "dark" && paths.Any(p => Path.GetRelativePath(assetsRoot, p).StartsWith("dark/".Replace('/', Path.DirectorySeparatorChar), StringComparison.Ordinal)))
            paths = paths.Where(p => Path.GetRelativePath(assetsRoot, p).StartsWith("dark/".Replace('/', Path.DirectorySeparatorChar), StringComparison.Ordinal)).ToList();
        var preferred = paths.Where(p => Path.GetRelativePath(assetsRoot, p).Split(Path.DirectorySeparatorChar)[1] == options.Language).ToList();
        if (preferred.Count > 0) paths = preferred;
        else if (options.Language == "en")
            paths = paths.Where(p => Path.GetRelativePath(assetsRoot, p).Split(Path.DirectorySeparatorChar)[1] == "share").ToList();
        return paths;
    }

    public IReadOnlyList<VisualTarget> Find(Mat gray, ImageQuery query)
    {
        if (!query.Multiple)
        {
            var match = Match(gray, query.Asset, (TemplateSearch)query.Search);
            if (match.Center is not { } center || !double.IsFinite(match.Score) || match.Score < query.Threshold)
                return [];
            var (template, _) = Load(Path.Combine(assetsRoot, match.Path), query.Asset, gray.Height);
            return [new(query.Asset, center,
                new(center.X - template.Width / 2, center.Y - template.Height / 2, template.Width, template.Height), match.Score)];
        }
        var targets = new List<VisualTarget>();
        var paths = Resolve(query.Asset).ToArray();
        if (paths.Length == 0) throw new FileNotFoundException($"缺少模板 {query.Asset}");
        foreach (var path in paths)
        {
            var (template, _) = Load(path, query.Asset, gray.Height);
            if (template.Width > gray.Width || template.Height > gray.Height) continue;
            using var result = new Mat();
            Cv2.MatchTemplate(gray, template, result, TemplateMatchModes.CCoeffNormed);
            using var mask = new Mat();
            Cv2.InRange(result, new Scalar(query.Threshold), new Scalar(1.000001), mask);
            using var locations = new Mat();
            Cv2.FindNonZero(mask, locations);
            var candidates = new List<(Point Point, float Score)>();
            for (var index = 0; index < locations.Rows; index++)
            {
                var point = locations.At<Point>(index);
                candidates.Add((point, result.At<float>(point.Y, point.X)));
            }
            foreach (var (point, score) in candidates.OrderByDescending(item => item.Score))
            {
                var center = new PixelPoint(point.X + template.Width / 2, point.Y + template.Height / 2);
                if (targets.Any(hit => Math.Pow(center.X - hit.Center.X, 2) + Math.Pow(center.Y - hit.Center.Y, 2) <= 100)) continue;
                targets.Add(new(query.Asset, center, new(point.X, point.Y, template.Width, template.Height), score));
            }
            if (targets.Count > 0) break;
        }
        return targets;
    }

    private (Mat Image, Rect? Bounds) Load(string path, string key, int height)
    {
        if (cache.TryGetValue((path, height), out var found)) return found;
        using var raw = Cv2.ImRead(path, ImreadModes.Color);
        if (raw.Empty()) throw new InvalidDataException($"无法读取模板 {path}");
        using var resized = new Mat();
        var scale = height / 1440.0;
        Cv2.Resize(raw, resized, new Size(), scale, scale,
            height < 1440 ? InterpolationFlags.Area : InterpolationFlags.Linear);
        var gray = new Mat();
        Cv2.CvtColor(resized, gray, ColorConversionCodes.BGR2GRAY);
        Rect? bounds = null;
        if (key.EndsWith("assets.png", StringComparison.Ordinal))
        {
            using var nonzero = new Mat();
            Cv2.FindNonZero(gray, nonzero);
            if (nonzero.Empty())
            {
                gray.Dispose();
                throw new InvalidDataException($"模板没有有效像素 {key}");
            }
            bounds = Cv2.BoundingRect(nonzero);
            using var region = new Mat(gray, bounds.Value);
            var cropped = region.Clone();
            gray.Dispose();
            gray = cropped;
        }
        cache[(path, height)] = (gray, bounds);
        return (gray, bounds);
    }

    public void Dispose()
    {
        foreach (var entry in cache.Values) entry.Image.Dispose();
        cache.Clear();
    }
}

