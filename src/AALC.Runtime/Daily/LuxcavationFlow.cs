using AALC.Runtime.Automation;
using AALC.Core.Features.Daily;
using AALC.Core.Features.Mail;

namespace AALC.Runtime.Daily;

public static class LuxcavationFlow
{
    private static readonly ImageQuery[] Queries = [
        new("teams/identify_assets.png"),
        new("luxcavation/exp_enter.png", Multiple: true), new("luxcavation/thread_enter_assets.png", 0.78),
        new("luxcavation/thread_assets.png"), new("luxcavation/thread_consume.png", Multiple: true),
        new("luxcavation/thread_scroll_bar.png"), new("home/luxcavation_assets.png"),
        new("home/inferno_bus_assets.png"), new("home/window_assets.png"),
        new("home/drive_assets.png"), new("base/renew_confirm_assets.png")];

    public static async Task<bool> RunAsync(IGameSession s, LuxcavationKind kind, int combatCount, int team,
        DailyOptions options, CancellationToken ct)
    {
        var name = kind == LuxcavationKind.Experience ? "经验本" : "纺锤本";
        s.Report("daily.luxcavation.enter", $"进入{name}，本批 {combatCount} 场");
        if (!await EnterAsync(s, kind, combatCount, ct)) return false;
        if (!await TeamSelection.RunAsync(s, team, options.SelectTeamByOrder, ct)) return false;
        return await BattleFlow.RunAsync(s, combatCount, options.HandleChoiceEvents, ct);
    }

    private static async Task<bool> EnterAsync(IGameSession s, LuxcavationKind kind, int count, CancellationToken ct)
    {
        for (var recovery = 0; recovery < 2; recovery++)
        {
            var continuousReady = count <= 1;
            for (var attempt = 0; attempt <= 30; attempt++)
            {
                var mode = attempt > 20 ? SearchMode.Aggressive : attempt > 10 ? SearchMode.Normal : SearchMode.Clam;
                var queries = Queries.Select(query => query.Search == SearchMode.Normal ? query : query with { Search = mode }).ToArray();
                var frame = await s.ObserveAsync(queries, ct);
                if (frame.Find("teams/identify_assets.png") is not null) return true;
                var entry = kind == LuxcavationKind.Experience ? "luxcavation/exp_enter.png" : "luxcavation/thread_enter_assets.png";
                var entryRecognized = kind == LuxcavationKind.Experience
                    ? frame.FindAll(entry).Any(hit => hit.Score >= 0.85)
                    : frame.Find(entry) is not null;
                if (kind == LuxcavationKind.Experience)
                {
                    var levels = entryRecognized
                        ? frame.FindAll(entry).Where(hit => hit.Score >= 0.8).OrderByDescending(hit => hit.Center.X).ToArray()
                        : [];
                    foreach (var level in levels)
                    {
                        if (count > 1)
                        {
                            var box = new PixelPoint(level.Center.X + (int)(300 * frame.Scale), level.Center.Y - (int)(450 * frame.Scale));
                            var setting = await SetCountAsync(s, frame, count, box, ct);
                            frame = setting.Frame;
                            if (!setting.Ready) continue;
                            frame = await s.ObserveControlsAsync(queries, ct);
                        }
                        var entrance = await TryLevelAsync(s, frame, level.Center, queries, ct);
                        frame = entrance.Frame;
                        if (entrance.Entered) return true;
                    }
                }
                else if (frame.Find(entry) is not null)
                {
                    if (!continuousReady)
                    {
                        var setting = await SetCountAsync(s, frame, count, null, ct);
                        frame = setting.Frame;
                        if (!setting.Ready) continue;
                        continuousReady = true;
                        frame = await s.ObserveControlsAsync(queries, ct);
                    }
                    if (frame.Find(entry) is not { } currentEntry) continue;
                    await s.ClickAsync(frame, currentEntry.Center, "daily.thread.open-levels", ct);
                    await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                    frame = await s.ObserveControlsAsync(queries, ct);
                    if (frame.Find("teams/identify_assets.png") is not null) return true;
                    if (frame.Find("luxcavation/thread_consume.png") is { } consume)
                    {
                        var scroll = frame.Find("luxcavation/thread_scroll_bar.png");
                        var from = scroll?.Center ?? consume.Center;
                        var direction = scroll is null ? -1 : 1;
                        await s.DragAsync(frame, from, new(from.X, Math.Clamp(from.Y + (int)(600 * frame.Scale) * direction, 0, frame.Identity.Height - 1)),
                            TimeSpan.FromMilliseconds(400), "daily.thread.bottom", ct);
                        frame = await s.ObserveControlsAsync(queries, ct);
                        var levels = ThreadLevels(frame);
                        for (var slide = 0; levels.Count == 0 && slide < 11; slide++)
                        {
                            var start = frame.Point(1300, 960);
                            await s.DragAsync(frame, start, new(start.X, start.Y + (int)(200 * frame.Scale)),
                                TimeSpan.FromMilliseconds(500), "daily.thread.previous-levels", ct);
                            frame = await s.ObserveControlsAsync(queries, ct);
                            levels = ThreadLevels(frame);
                        }
                        foreach (var level in levels)
                        {
                            var entrance = await TryLevelAsync(s, frame, level, queries, ct);
                            frame = entrance.Frame;
                            if (entrance.Entered) return true;
                        }
                    }
                }
                if (frame.Find("teams/identify_assets.png") is not null) return true;
                if (kind == LuxcavationKind.Thread && frame.Find("luxcavation/thread_assets.png") is { } tab)
                    await s.ClickAsync(frame, tab.Center, "daily.thread.tab", ct);
                else if (frame.Find("home/luxcavation_assets.png") is { } lux)
                    await s.ClickAsync(frame, lux.Center, "daily.luxcavation.open", ct);
                else if (frame.Find("base/renew_confirm_assets.png") is { } renew && frame.Find("home/drive_assets.png") is not null)
                {
                    await s.ClickAsync(frame, renew.Center, "daily.luxcavation.renew", ct);
                    if (!await DailyNavigation.ReturnHomeAsync(s, ct)) return false;
                }
                else if (frame.Find("home/drive_assets.png") is { } drive)
                    await s.ClickAsync(frame, drive.Center, "daily.luxcavation.drive", ct);
                else if (frame.Find("home/inferno_bus_assets.png") is not null && frame.Find("home/window_assets.png") is { } window)
                    await s.ClickAsync(frame, window.Center, "daily.luxcavation.window", ct);
                await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
            }
            if (recovery == 0)
            {
                s.Report("daily.luxcavation.recover", "采光入口未出现，返回主页后重试一次");
                if (!await DailyNavigation.ReturnHomeAsync(s, ct)) return false;
            }
        }
        s.Report("daily.luxcavation.not-found", "采光入口搜索失败");
        return false;
    }

    private static async Task<(bool Entered, GameFrame Frame)> TryLevelAsync(IGameSession s, GameFrame frame,
        PixelPoint level, ImageQuery[] queries, CancellationToken ct)
    {
        s.Report("daily.luxcavation.choose-level", "选择可进入的采光关卡");
        for (var attempt = 0; attempt < 3; attempt++)
        {
            if (frame.Find("teams/identify_assets.png") is not null) return (true, frame);
            await s.ClickAsync(frame, level, "daily.luxcavation.choose-level", ct);
            await s.DelayAsync(TimeSpan.FromSeconds(1), ct);
            for (var check = 0; check < 3; check++)
            {
                frame = await s.ObserveControlsAsync(queries, ct);
                if (frame.Find("teams/identify_assets.png") is not null) return (true, frame);
                await s.DelayAsync(TimeSpan.FromMilliseconds(300), ct);
            }
        }
        return (false, frame);
    }

    private static List<PixelPoint> ThreadLevels(GameFrame frame)
    {
        var result = new List<PixelPoint>();
        foreach (var hit in frame.FindAll("luxcavation/thread_consume.png"))
            if (hit.Center.X >= 700 * frame.Scale && !result.Any(point => Math.Abs(point.Y - hit.Center.Y) < Math.Max(20, (int)(70 * frame.Scale))))
                result.Add(hit.Center);
        return result.OrderByDescending(point => point.Y).ToList();
    }

    private static async Task<(bool Ready, GameFrame Frame)> SetCountAsync(IGameSession s, GameFrame frame,
        int count, PixelPoint? box, CancellationToken ct)
    {
        s.Report("daily.luxcavation.count", $"设置本批连战次数为 {count}");
        ImageQuery[] queries = [new("luxcavation/thread_continuous_combat_show_box.png", 0.85),
            new("luxcavation/continuous_combat_up_box.png", 0.85)];
        if (box is null)
        {
            frame = await s.ObserveControlsAsync(queries, ct);
            box = frame.Find(queries[0].Asset)?.Center;
            if (box is null) return (false, frame);
        }
        await s.ClickAsync(frame, box.Value, "daily.luxcavation.open-count", ct);
        for (var attempt = 0; attempt < 2; attempt++)
        {
            await s.DelayAsync(TimeSpan.FromMilliseconds(attempt == 0 ? 400 : 200), ct);
            frame = await s.ObserveControlsAsync(queries, ct);
            if (frame.Find(queries[1].Asset) is not { } up) continue;
            for (var i = 1; i < count; i++)
            {
                await s.ClickAsync(frame, up.Center, "daily.luxcavation.increase-count", ct);
                await s.DelayAsync(TimeSpan.FromMilliseconds(100), ct);
                if (i + 1 < count)
                {
                    frame = await s.ObserveControlsAsync(queries, ct);
                    if (frame.Find(queries[1].Asset) is not { } next) return (false, frame);
                    up = next;
                }
            }
            return (true, frame);
        }
        return (false, frame);
    }
}
