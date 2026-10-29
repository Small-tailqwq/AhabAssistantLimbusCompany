using AALC.Runtime.Automation;
using System.Text.RegularExpressions;
using AALC.Core.Features.Daily;
using AALC.Core.Features.Mail;

namespace AALC.Runtime.Automation;

public static class TeamSelection
{
    private static readonly ImageQuery[] Queries = [new("teams/identify_assets.png"),
        new("home/first_prompt_assets.png"), new("home/back_assets.png", Search: SearchMode.Normal)];

    public static async Task<bool> RunAsync(IGameSession s, int number, bool byOrder, CancellationToken ct)
    {
        s.Report("team.select", $"选择队伍 {number}");
        var frame = await s.ObserveAsync(Queries, ct);
        if (frame.Find("home/first_prompt_assets.png") is not null && frame.Find("home/back_assets.png") is { } back)
        {
            await s.ClickAsync(frame, back.Center, "team.dismiss-prompt", ct);
            frame = await s.ObserveAsync(Queries, ct);
        }
        if (frame.Find("teams/identify_assets.png") is not { } identify) return false;
        var anchor = new PixelPoint(identify.Center.X - (int)(2150 * frame.Scale),
            identify.Center.Y + (int)(215 * frame.Scale));
        await s.ClickAsync(frame, new(1, 1), "team.dismiss-focus", ct);
        frame = await s.ObserveControlsAsync(Queries, ct);
        if (!byOrder)
        {
            var selected = HighlightedRow(frame, anchor);
            if (selected is { } row)
            {
                var text = await s.ReadTextAsync(frame, ct, row);
                if (text.Any(value => Number(value.Text) == number)) return true;
            }
            if (await ClickNamedAsync(s, frame, anchor, number, ct)) return true;
        }

        await s.ClickAsync(frame, new(anchor.X, anchor.Y + (int)(150 * frame.Scale)), "team.open-list", ct);
        await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
        for (var i = 0; i < 3; i++)
        {
            frame = await s.ObserveControlsAsync(Queries, ct);
            var from = new PixelPoint(anchor.X, anchor.Y + (int)(150 * frame.Scale));
            await s.DragAsync(frame, from, new(from.X, Math.Min(frame.Identity.Height - 1, from.Y + (int)(1333 * frame.Scale))),
                TimeSpan.FromMilliseconds(300), "team.reset-list", ct);
        }
        await s.DelayAsync(TimeSpan.FromMilliseconds(750), ct);
        var page = (number - 1) / 5;
        var pages = byOrder ? page + 1 : 10;
        for (var i = 0; i < pages; i++)
        {
            frame = await s.ObserveControlsAsync(Queries, ct);
            if (byOrder && i == page)
            {
                var y = anchor.Y + (int)((70 + (page > 2 ? 100 : 0) + 75 * ((number - 1) % 5)) * frame.Scale);
                await s.ClickAsync(frame, new(anchor.X, y), "team.choose-order", ct);
                await s.DelayAsync(TimeSpan.FromSeconds(1), ct);
                return true;
            }
            if (!byOrder)
            {
                var selected = HighlightedRow(frame, anchor);
                if (selected is { } row && (await s.ReadTextAsync(frame, ct, row)).Any(value => Number(value.Text) == number)) return true;
                if (await ClickNamedAsync(s, frame, anchor, number, ct)) return true;
            }
            var from = new PixelPoint(anchor.X, anchor.Y + (int)(445 * frame.Scale));
            await s.DragAsync(frame, from, new(from.X, from.Y - (int)((byOrder ? 385 : 375) * frame.Scale)),
                TimeSpan.FromSeconds(1.5), "team.next-page", ct);
            await s.DelayAsync(TimeSpan.FromMilliseconds(800), ct);
        }
        s.Report("team.not-found", $"未找到队伍 {number}");
        return false;
    }

    private static int? Number(string text)
    {
        var matches = Regex.Matches(text, @"\d+");
        return matches.Count > 0 && int.TryParse(matches[^1].Value, out var number) ? number : null;
    }

    private static async Task<bool> ClickNamedAsync(IGameSession s, GameFrame frame, PixelPoint anchor,
        int number, CancellationToken ct)
    {
        var crop = new PixelRect(0, 0, Math.Min(frame.Identity.Width, anchor.X + (int)(130 * frame.Scale)),
            Math.Min(frame.Identity.Height, anchor.Y + (int)(600 * frame.Scale)));
        var entries = await s.ReadTextAsync(frame, ct, crop);
        var target = entries.FirstOrDefault(text => Number(text.Text) == number);
        if (target is null) return false;
        await s.ClickAsync(frame, new(target.Bounds.X + target.Bounds.Width / 2, target.Bounds.Y + target.Bounds.Height / 2),
            "team.choose-name", ct);
        await s.DelayAsync(TimeSpan.FromSeconds(1), ct);
        return true;
    }

    private static PixelRect? HighlightedRow(GameFrame frame, PixelPoint anchor)
    {
        var left = Math.Max(0, anchor.X - (int)(150 * frame.Scale));
        var top = Math.Max(0, anchor.Y + (int)(30 * frame.Scale));
        var right = Math.Min(frame.Identity.Width, anchor.X + (int)(150 * frame.Scale));
        var bottom = Math.Min(frame.Identity.Height, anchor.Y + (int)(620 * frame.Scale));
        if (left >= right || top >= bottom) return null;
        var width = right - left;
        var height = bottom - top;
        var mask = new bool[width * height];
        var pixels = frame.Pixels.Bgra;
        for (var y = 0; y < height; y++)
            for (var x = 0; x < width; x++)
            {
                var offset = ((top + y) * frame.Identity.Width + left + x) * 4;
                var b = pixels[offset]; var g = pixels[offset + 1]; var r = pixels[offset + 2];
                var high = Math.Max(r, Math.Max(g, b));
                var low = Math.Min(r, Math.Min(g, b));
                var delta = high - low;
                if (delta == 0 || high < 180 || delta * 255 / high < 180) continue;
                var hue = high == r ? (g - b) * 30.0 / delta
                    : high == g ? 60 + (b - r) * 30.0 / delta : 120 + (r - g) * 30.0 / delta;
                if (hue < 0) hue += 180;
                mask[y * width + x] = hue is >= 15 and <= 35;
            }
        PixelRect? best = null;
        var largest = 0;
        for (var index = 0; index < mask.Length; index++)
        {
            if (!mask[index]) continue;
            var queue = new Queue<int>(); queue.Enqueue(index); mask[index] = false;
            var x1 = width; var y1 = height; var x2 = 0; var y2 = 0;
            while (queue.TryDequeue(out var current))
            {
                var x = current % width; var y = current / width;
                x1 = Math.Min(x1, x); x2 = Math.Max(x2, x); y1 = Math.Min(y1, y); y2 = Math.Max(y2, y);
                for (var dy = -1; dy <= 1; dy++)
                    for (var dx = -1; dx <= 1; dx++)
                    {
                        var nx = x + dx; var ny = y + dy;
                        if (nx < 0 || nx >= width || ny < 0 || ny >= height || !mask[ny * width + nx]) continue;
                        mask[ny * width + nx] = false; queue.Enqueue(ny * width + nx);
                    }
            }
            var area = (x2 - x1 + 1) * (y2 - y1 + 1);
            if (area <= largest || area < 8000 * frame.Scale * frame.Scale || (x2 - x1 + 1.0) / (y2 - y1 + 1) < 2.5) continue;
            largest = area;
            var padX = (int)(20 * frame.Scale); var padY = (int)(8 * frame.Scale);
            best = new(left + x1 + padX, top + y1 + padY, x2 - x1 + 1 - padX * 2, y2 - y1 + 1 - padY * 2);
        }
        return best is { Width: > 0, Height: > 0 } ? best : null;
    }
}
