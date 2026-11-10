using System.Text.Json;
using System.Text.Json.Serialization;
using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;

namespace AALC.Runtime.Replay;

public sealed record ScreenshotTemplateCheck(ImageQuery Query, int Count, PixelRect? Within = null);
public sealed record ScreenshotTextCheck(PixelRect Region, int Scale = 1, string[]? Contains = null,
    string[]? Excludes = null, string? Exact = null, double MinimumConfidence = .7,
    TextPreprocessing Preprocessing = TextPreprocessing.None);
public sealed record ScreenshotPageCheck(bool? Combat = null, bool? Event = null, bool? Reward = null,
    int? SelectedGifts = null);
public sealed record ScreenshotRouteCheck(MirrorNodeKind Kind, PixelRect Destination, bool HardMode = false);
public sealed record ScreenshotCase(string Id, string Description, string Image, string Sha256, int Width, int Height,
    ScreenshotTemplateCheck[]? Templates = null, ScreenshotTextCheck[]? Text = null,
    ScreenshotPageCheck? Pages = null, ScreenshotRouteCheck? Route = null,
    string Language = "zh_cn", string Theme = "default");
public sealed record ScreenshotReplayCase(string Id, string Description, string Directory,
    Dictionary<string, string> Sha256);

public sealed record ScreenshotTestset(int Version, ScreenshotCase[] Cases, ScreenshotReplayCase[] Replays)
{
    public static readonly JsonSerializerOptions Json = new(MirrorScenario.Json)
    {
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        WriteIndented = true
    };

    public static ScreenshotTestset Load(string path)
    {
        var suite = JsonSerializer.Deserialize<ScreenshotTestset>(File.ReadAllText(path), Json)
            ?? throw new InvalidDataException("截图测试集为空");
        suite.Validate();
        return suite;
    }

    public void Validate()
    {
        if (Version != 1 || Cases is null || Replays is null || Cases.Length + Replays.Length == 0)
            throw new InvalidDataException("截图测试集须使用 version=1，且至少包含一个用例");
        var ids = Cases.Select(item => item.Id).Concat(Replays.Select(item => item.Id)).ToArray();
        if (ids.Any(string.IsNullOrWhiteSpace) || ids.Distinct(StringComparer.Ordinal).Count() != ids.Length)
            throw new InvalidDataException("截图用例 ID 为空或重复");
        foreach (var item in Cases)
        {
            RequireHash(item.Sha256);
            if (item.Width <= 0 || item.Height <= 0 || item.Language is not ("zh_cn" or "en")
                || item.Theme is not ("default" or "dark"))
                throw new InvalidDataException($"{item.Id} 的尺寸、语言或主题无效");
            if (item.Templates?.Length is not > 0 && item.Text?.Length is not > 0 && item.Route is null
                && item.Pages is not { Combat: not null } and not { Event: not null } and not { Reward: not null })
                throw new InvalidDataException($"{item.Id} 没有任何断言");
            foreach (var check in item.Templates ?? [])
                if (check.Query is null || string.IsNullOrWhiteSpace(check.Query.Asset) || check.Count < 0
                    || !double.IsFinite(check.Query.Threshold) || check.Query.Threshold is < 0 or > 1
                    || !Enum.IsDefined(check.Query.Search) || check.Within is { } box && !ValidArea(box, item))
                    throw new InvalidDataException($"{item.Id} 的模板断言无效");
            foreach (var check in item.Text ?? [])
                if (!ValidArea(check.Region, item) || check.Scale < 1
                    || !double.IsFinite(check.MinimumConfidence) || check.MinimumConfidence is < 0 or > 1
                    || check.Exact is null && check.Contains?.Length is not > 0 && check.Excludes?.Length is not > 0
                    || (check.Contains ?? []).Concat(check.Excludes ?? []).Any(string.IsNullOrWhiteSpace))
                    throw new InvalidDataException($"{item.Id} 的 OCR 断言无效");
            if (item.Route is { } route && (!ValidArea(route.Destination, item) || !Enum.IsDefined(route.Kind)))
                throw new InvalidDataException($"{item.Id} 的地图断言无效");
        }
        foreach (var replay in Replays)
        {
            if (replay.Sha256 is null || !new[] { "options.json", "events.jsonl", "result.json" }.All(replay.Sha256.ContainsKey))
                throw new InvalidDataException($"{replay.Id} 缺少录制文件校验值");
            foreach (var hash in replay.Sha256.Values) RequireHash(hash);
        }
    }

    public static string ResolveDataPath(string root, string relativePath)
    {
        root = EvidencePaths.RequireExternalPath(root);
        if (string.IsNullOrWhiteSpace(relativePath) || Path.IsPathRooted(relativePath))
            throw new InvalidDataException("测试集文件必须使用相对路径");
        var path = EvidencePaths.RequireExternalPath(Path.Combine(root, relativePath));
        if (!path.StartsWith(Path.TrimEndingDirectorySeparator(root) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("测试集文件超出数据目录");
        return path;
    }

    private static bool ValidArea(PixelRect area, ScreenshotCase item) => area.X >= 0 && area.Y >= 0
        && area.Width > 0 && area.Height > 0 && (long)area.X + area.Width <= item.Width && (long)area.Y + area.Height <= item.Height;

    private static void RequireHash(string hash)
    {
        if (hash is null || hash.Length != 64 || hash.Any(character => !char.IsAsciiHexDigit(character)))
            throw new InvalidDataException("截图与录制文件必须包含 SHA256 校验值");
    }
}
