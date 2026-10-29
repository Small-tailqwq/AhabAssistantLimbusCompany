using AALC.Core.Automation;
using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;

namespace AALC.Runtime.Mirror;

public static class MirrorThemeFlow
{
    public const string Map = "mirror/road_in_mir/legend_assets.png";
    public const string Pack = "mirror/theme_pack/theme_pack_features.png";
    public const string Normal = "mirror/theme_pack/normal_assets.png";
    public const string Hard = "mirror/theme_pack/hard_assets.png";
    public const string Refresh = "mirror/theme_pack/refresh_assets.png";
    public static readonly ImageQuery[] Queries = [new(Map), new(Pack, Multiple: true), new(Normal), new(Hard), new(Refresh),
        new("base/waiting_assets.png")];

    public static async Task<bool> RunAsync(IGameSession s, MirrorThemeOptions options, CancellationToken ct)
    {
        var refreshes = 0;
        var submitted = false;
        var selectionAttempts = 0;
        var remainingPackFrames = 0;
        for (var attempt = 0; attempt < 35; attempt++)
        {
            ct.ThrowIfCancellationRequested();
            var frame = await s.ObserveAsync(Queries, ct);
            if (frame.Find("base/waiting_assets.png") is not null)
            {
                remainingPackFrames = 0;
                await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                continue;
            }
            if (frame.Find(Map) is not null)
            {
                if (MirrorRunner.ParseFloor(await s.ReadTextAsync(frame, ct, frame.Region(60, 168, 570, 250), 2)) == options.Floor)
                    return true;
                remainingPackFrames = 0;
                await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                continue;
            }
            if (submitted)
            {
                remainingPackFrames = frame.Find(Pack) is null ? 0 : remainingPackFrames + 1;
                if (remainingPackFrames < 3)
                {
                    await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                    continue;
                }
                if (selectionAttempts >= 3)
                {
                    s.Report("mirror.theme.stalled", "连续三次拖拽后主题包仍未进入地图");
                    return false;
                }
                s.Report("mirror.theme.retry", "主题包仍在选择页，重新确认后重试拖拽");
                submitted = false;
                remainingPackFrames = 0;
            }
            var wrong = frame.Find(options.HardMode ? Normal : Hard);
            if (wrong is not null)
            {
                s.Report("mirror.theme.difficulty", options.HardMode ? "切换困难镜牢主题" : "切换普通镜牢主题");
                await s.ClickAsync(frame, wrong.Center, "mirror.theme.switch-difficulty", ct);
                await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                continue;
            }
            if (frame.Find(options.HardMode ? Hard : Normal) is null)
            {
                var text = string.Concat((await s.ReadTextAsync(frame, ct, frame.Region(1663, 62, 1914, 123), 2)).Select(t => t.Text)).ToLowerInvariant();
                if (text.Contains(options.HardMode ? "normal" : "hard"))
                {
                    await s.ClickAsync(frame, frame.Point(options.HardMode ? 1727 : 1869, 92), "mirror.theme.switch-difficulty-ocr", ct);
                    continue;
                }
                if (!text.Contains(options.HardMode ? "hard" : "normal"))
                {
                    await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                    continue;
                }
            }
            var packs = frame.FindAll(Pack).OrderBy(p => p.Center.X).ThenBy(p => p.Center.Y).ToList();
            if (options.Floor == 4 && options.SkipEventPack && !options.PreferEventPack && packs.Count > 0) packs.RemoveAt(0);
            if (packs.Count == 0)
            {
                await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                continue;
            }
            var ranked = new List<(VisualTarget Target, string Name, int Weight)>();
            foreach (var pack in packs)
            {
                var x = pack.Center.X; var y = pack.Center.Y;
                var left = Math.Max(0, x - (int)(280 * frame.Scale));
                var top = Math.Max(0, y - (int)(80 * frame.Scale));
                var region = new PixelRect(left, top, Math.Min(frame.Identity.Width, x + (int)(80 * frame.Scale)) - left,
                    Math.Min(frame.Identity.Height, y + (int)(520 * frame.Scale)) - top);
                var name = string.Concat((await s.ReadTextAsync(frame, ct, region)).Select(t => t.Text));
                ranked.Add((pack, name, options.WeightFor(name)));
            }
            var best = options.Floor == 4 && options.PreferEventPack ? ranked[0]
                : ranked.OrderByDescending(p => p.Weight).First();
            if (selectionAttempts == 0 && !(options.Floor == 4 && options.PreferEventPack) && best.Weight < options.PreferredThreshold
                && refreshes < options.RefreshLimit && frame.Find(Refresh) is { } refresh)
            {
                refreshes++;
                s.Report("mirror.theme.refresh", $"刷新镜牢主题包（{refreshes}/{options.RefreshLimit}）");
                await s.ClickAsync(frame, refresh.Center, "mirror.theme.refresh", ct);
                await s.DelayAsync(TimeSpan.FromSeconds(1), ct);
                continue;
            }
            s.Report("mirror.theme.select", $"选择主题包：{best.Name}，权重 {best.Weight}");
            await s.DragAsync(frame, best.Target.Center,
                new PixelPoint(best.Target.Center.X, Math.Min(frame.Identity.Height - 1, best.Target.Center.Y + (int)(400 * frame.Scale))),
                TimeSpan.FromMilliseconds(500), "mirror.theme.select-pack", ct);
            submitted = true;
            selectionAttempts++;
            await s.DelayAsync(TimeSpan.FromSeconds(1), ct);
        }
        s.Report("mirror.theme.timeout", "主题包选择后未确认进入镜牢地图");
        return false;
    }
}
