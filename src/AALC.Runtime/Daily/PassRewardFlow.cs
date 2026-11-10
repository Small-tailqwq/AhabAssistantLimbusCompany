using AALC.Runtime.Automation;
using AALC.Core.Features.Daily;
using AALC.Core.Features.Mail;

namespace AALC.Runtime.Daily;

public static class PassRewardFlow
{
    private const string Missions = "pass/pass_missions_assets.png";
    private const string Weekly = "pass/weekly_assets.png";
    private const string Season = "home/season_assets.png";
    private const string RewardConfirm = "mail/get_mail_prize_confirm.png";
    private static readonly ImageQuery[] Queries = [new(Missions), new(Weekly)];
    private static readonly ImageQuery[] RewardQueries = [.. Queries, new(RewardConfirm)];
    private enum Tab { Levels, Missions, Daily, Weekly, Season }

    public static async Task<bool> RunAsync(IGameSession s, bool missions, bool levels, bool seasonMissions,
        CancellationToken ct)
    {
        if (!missions && !levels && !seasonMissions) return true;
        s.Report("daily.pass.begin", "进入通行证领取奖励");
        var frame = await OpenAsync(s, ct);
        if (frame is null) return false;
        if (missions || seasonMissions)
        {
            frame = await SelectTabAsync(s, frame, Tab.Missions, ct);
            if (frame is null) return false;
            foreach (var tab in new[] { Tab.Daily, Tab.Weekly, Tab.Season })
            {
                if (tab == Tab.Season ? !seasonMissions : !missions) continue;
                // 提示属于整个分区，包括滚动区域外的任务；提示消失后无需继续翻页。
                if (!HasBadge(frame, tab)) continue;
                frame = await SelectTabAsync(s, frame, tab, ct);
                if (frame is null) return false;
                frame = await ClaimRowsAsync(s, frame, tab, ct);
                if (frame is null) return false;
            }
        }
        if (levels)
        {
            frame = await SelectTabAsync(s, frame, Tab.Levels, ct);
            if (frame is null) return false;
            if (HasBadge(frame, Tab.Levels))
            {
                var labels = await s.ReadTextAsync(frame, ct, frame.Region(1540, 1140, 1845, 1240), 2);
                var label = string.Concat(labels.OrderBy(t => t.Bounds.X).Select(t => t.Text))
                    .Replace(" ", "").Replace("\n", "");
                if (!label.Contains("全部领取") && !label.Contains("领取全部")
                    && !label.Contains("ClaimAll", StringComparison.OrdinalIgnoreCase))
                {
                    s.Report("daily.pass.level-button-missing", "等级奖励提示仍在，但未识别到全部领取按钮");
                    return false;
                }
                var left = labels.Min(t => t.Bounds.X);
                var top = labels.Min(t => t.Bounds.Y);
                var right = labels.Max(t => t.Bounds.Right);
                var bottom = labels.Max(t => t.Bounds.Bottom);
                await s.ClickAsync(frame, new((left + right) / 2, (top + bottom) / 2), "daily.pass.claim-levels", ct);
                var confirmed = false;
                var claimedAt = s.Elapsed;
                var deadline = claimedAt + TimeSpan.FromSeconds(30);
                var nextPresentationCheck = claimedAt;
                var completed = false;
                while (s.Elapsed < deadline)
                {
                    await s.DelayAsync(TimeSpan.FromMilliseconds(200), ct);
                    frame = await s.ObserveAsync(RewardQueries, ct);
                    if (frame.Find(RewardConfirm) is { } confirm)
                    {
                        if (!confirmed)
                        {
                            await s.ClickAsync(frame, confirm.Center, "daily.pass.confirm-levels", ct);
                            confirmed = true;
                        }
                    }
                    else if (IsSelected(frame, Tab.Levels) && !HasBadge(frame, Tab.Levels)
                        && (confirmed || s.Elapsed - claimedAt >= TimeSpan.FromSeconds(3)))
                    {
                        completed = true;
                        break;
                    }
                    else if (frame.Find(Missions) is null && frame.Find(Weekly) is null && s.Elapsed >= nextPresentationCheck)
                    {
                        nextPresentationCheck = s.Elapsed + TimeSpan.FromSeconds(1);
                        var text = await s.ReadTextAsync(frame, ct, frame.Region(1600, 800, 2450, 1250), 2);
                        if (IsEgoPresentation(text))
                        {
                            await s.ClickAsync(frame, frame.Point(2200, 1260), "daily.pass.dismiss-ego", ct);
                            nextPresentationCheck = s.Elapsed + TimeSpan.FromSeconds(2);
                        }
                    }
                }
                if (!completed)
                {
                    s.Report("daily.pass.levels-unverified", "等级奖励领取后未确认弹窗关闭及提示消失");
                    return false;
                }
                s.Report("daily.pass.levels-claimed", "通行证等级奖励已领取");
            }
            else s.Report("daily.pass.no-level-rewards", "没有可领取的通行证等级奖励");
        }
        s.Report("daily.pass.finished", "通行证奖励处理完成");
        return true;
    }

    private static bool IsEgoPresentation(IReadOnlyList<RecognizedText> text)
    {
        var labels = text.Select(item => string.Concat(item.Text.Where(char.IsLetterOrDigit)).ToUpperInvariant()).ToArray();
        return labels.Any(label => label.StartsWith("SEASON", StringComparison.Ordinal)
                && label.Length > 6 && label[6..].All(char.IsAsciiDigit))
            && labels.Any(label => label is "ZAYIN" or "TETH" or "HE" or "WAW" or "ALEPH");
    }

    private static async Task<GameFrame?> OpenAsync(IGameSession s, CancellationToken ct)
    {
        var nextClick = TimeSpan.Zero;
        for (var attempt = 0; attempt < 16; attempt++)
        {
            var frame = await s.ObserveAsync([new(Missions), new(Weekly), new(Season)], ct);
            if (frame.Find(Missions) is not null) return frame;
            if (s.Elapsed >= nextClick)
            {
                if (frame.Find(Season) is { } season)
                    await s.ClickAsync(frame, season.Center, "daily.pass.open", ct);
                else
                {
                    var region = frame.Region(1860, 350, 2460, 590);
                    var text = await s.ReadTextAsync(frame, ct, region);
                    if (text.Any(t => t.Text.Contains("season", StringComparison.OrdinalIgnoreCase)))
                        await s.ClickAsync(frame, new(region.X + region.Width / 2, region.Y + region.Height / 2), "daily.pass.open-ocr", ct);
                }
                nextClick = s.Elapsed + TimeSpan.FromSeconds(1);
            }
            await s.DelayAsync(TimeSpan.FromMilliseconds(200), ct);
        }
        s.Report("daily.pass.open-timeout", "未能打开通行证页面");
        return null;
    }

    private static async Task<GameFrame?> SelectTabAsync(IGameSession s, GameFrame frame, Tab tab, CancellationToken ct)
    {
        if (IsSelected(frame, tab)) return frame;
        if (frame.Find(Missions) is null) return null;
        var point = tab switch
        {
            Tab.Levels => frame.Point(435, 110),
            Tab.Missions => frame.Find(Missions)!.Center,
            _ => frame.Point(545, 515 + ((int)tab - (int)Tab.Daily) * 286)
        };
        await s.ClickAsync(frame, point, "daily.pass." + tab.ToString().ToLowerInvariant(), ct);
        for (var attempt = 0; attempt < 12; attempt++)
        {
            await s.DelayAsync(TimeSpan.FromMilliseconds(150), ct);
            frame = await s.ObserveAsync(Queries, ct);
            if (IsSelected(frame, tab)) return frame;
        }
        s.Report("daily.pass.tab-unverified", $"未确认{TabName(tab)}标签切换完成");
        return null;
    }

    private static async Task<GameFrame?> ClaimRowsAsync(IGameSession s, GameFrame frame, Tab tab, CancellationToken ct)
    {
        PixelRect? pending = null;
        var unchanged = 0;
        var missing = 0;
        var direction = -1;
        GameFrame? beforeScroll = null;
        for (var attempt = 0; attempt < 60; attempt++)
        {
            ct.ThrowIfCancellationRequested();
            if (!IsSelected(frame, tab)) return null;
            if (!HasBadge(frame, tab))
            {
                s.Report("daily.pass.section-finished", $"{TabName(tab)}没有可领取的奖励");
                return frame;
            }
            if (pending is { } claimed && OrangeRatio(frame, claimed) >= .12)
            {
                if (++unchanged >= 12)
                {
                    s.Report("daily.pass.claim-unverified", $"{TabName(tab)}领取后画面没有变化");
                    return null;
                }
                await s.DelayAsync(TimeSpan.FromMilliseconds(150), ct);
                frame = await s.ObserveAsync(Queries, ct);
                continue;
            }
            pending = null;
            unchanged = 0;
            var text = await s.ReadTextAsync(frame, ct, frame.Region(1180, 350, 1420, 1240));
            PixelRect? selected = null;
            foreach (var row in text.OrderBy(t => t.Bounds.Y))
            {
                if (!DailyRewardRules.TryProgress(row.Text, out var current, out var total)
                    || total <= 0 || current != total || row.Bounds.Y < 380 * frame.Scale
                    || row.Bounds.Bottom > 1240 * frame.Scale) continue;
                var left = Math.Max(0, (int)(row.Bounds.X - 150 * frame.Scale));
                var top = Math.Max(0, (int)(row.Bounds.Y - 18 * frame.Scale));
                var right = Math.Min(frame.Identity.Width, (int)(row.Bounds.Right + 25 * frame.Scale));
                var bottom = Math.Min(frame.Identity.Height, (int)(row.Bounds.Bottom + 18 * frame.Scale));
                var bounds = new PixelRect(left, top, right - left, bottom - top);
                if (OrangeRatio(frame, bounds) < .12) continue;
                selected = bounds;
                break;
            }
            if (selected is { } target)
            {
                pending = target;
                beforeScroll = null;
                missing = 0;
                await s.ClickAsync(frame, new(target.X + target.Width / 2, target.Y + target.Height / 2),
                    "daily.pass.claim-row", ct);
            }
            else if (tab == Tab.Season)
            {
                if (beforeScroll is not null && SameList(beforeScroll, frame))
                {
                    if (direction > 0)
                    {
                        s.Report("daily.pass.season-unresolved", "赛季任务提示仍在，双向滚动后列表均未变化");
                        return null;
                    }
                    direction = 1;
                }
                beforeScroll = frame;
                var from = frame.Point(1000, direction < 0 ? 1080 : 560);
                var to = frame.Point(1000, direction < 0 ? 560 : 1080);
                await s.DragAsync(frame, from, to, TimeSpan.FromMilliseconds(600),
                    direction < 0 ? "daily.pass.scroll-down" : "daily.pass.scroll-up", ct);
            }
            else if (++missing >= 4)
            {
                s.Report("daily.pass.progress-missing", $"{TabName(tab)}提示仍在，但未识别到可领取行");
                return null;
            }
            await s.DelayAsync(TimeSpan.FromMilliseconds(150), ct);
            frame = await s.ObserveAsync(Queries, ct);
        }
        s.Report("daily.pass.rows-timeout", $"{TabName(tab)}领取未完成");
        return null;
    }

    private static string TabName(Tab tab) => tab switch
    {
        Tab.Daily => "每日任务", Tab.Weekly => "每周任务", Tab.Season => "赛季任务",
        Tab.Missions => "通行证任务", _ => "战斗通行证"
    };

    private static bool HasBadge(GameFrame frame, Tab tab)
    {
        var top = 380 + ((int)tab - (int)Tab.Daily) * 286;
        var bounds = tab == Tab.Levels ? frame.Region(538, 52, 600, 88)
            : frame.Region(532, top, 600, top + 34);
        return ColorRatio(frame, bounds, red: true) > .3;
    }

    private static bool IsSelected(GameFrame frame, Tab tab)
    {
        if (frame.Find(Missions) is null) return false;
        if (tab == Tab.Levels ? frame.Find(Weekly) is not null : frame.Find(Weekly) is null) return false;
        double Border(Tab value)
        {
            var top = 440 + ((int)value - (int)Tab.Daily) * 286;
            var bounds = value switch
            {
                Tab.Levels => frame.Region(344, 144, 598, 156),
                Tab.Missions => frame.Region(620, 144, 874, 156),
                _ => frame.Region(504, top, 518, top + 150)
            };
            return ColorRatio(frame, bounds, red: false);
        }
        var selected = Border(tab);
        if (selected < .25) return false;
        if (tab is Tab.Levels or Tab.Missions)
        {
            if (selected <= Border(tab == Tab.Levels ? Tab.Missions : Tab.Levels) * 1.6) return false;
            if (tab == Tab.Levels) return true;
            var sections = new[] { Border(Tab.Daily), Border(Tab.Weekly), Border(Tab.Season) }
                .OrderDescending().ToArray();
            return sections[0] >= .25 && sections[0] > sections[1] * 1.6;
        }
        return IsSelected(frame, Tab.Missions) && new[] { Tab.Daily, Tab.Weekly, Tab.Season }
            .Where(other => other != tab).All(other => selected > Border(other) * 1.6);
    }

    private static double ColorRatio(GameFrame frame, PixelRect region, bool red)
    {
        var hits = 0;
        var count = 0;
        for (var y = Math.Max(0, region.Y); y < Math.Min(frame.Identity.Height, region.Bottom); y++)
        for (var x = Math.Max(0, region.X); x < Math.Min(frame.Identity.Width, region.Right); x++)
        {
            var offset = (y * frame.Identity.Width + x) * 4;
            var b = frame.Pixels.Bgra[offset];
            var g = frame.Pixels.Bgra[offset + 1];
            var r = frame.Pixels.Bgra[offset + 2];
            if (red ? r > 100 && r > g * 1.7 && r > b * 1.7
                : r > 150 && g > r * .35 && g < r * .9 && b < r * .5) hits++;
            count++;
        }
        return count == 0 ? 0 : hits / (double)count;
    }

    private static double OrangeRatio(GameFrame frame, PixelRect bounds) =>
        DailyRewardRules.OrangeRatio(frame.Pixels.Bgra, frame.Identity.Width, frame.Identity.Height, bounds);

    private static bool SameList(GameFrame before, GameFrame after)
    {
        if (before.Identity.Width != after.Identity.Width || before.Identity.Height != after.Identity.Height) return false;
        var region = after.Region(830, 400, 1180, 1190);
        long difference = 0;
        var count = 0;
        for (var y = region.Y; y < region.Bottom; y += 3)
        for (var x = region.X; x < region.Right; x += 3)
        {
            var offset = (y * after.Identity.Width + x) * 4;
            for (var c = 0; c < 3; c++) difference += Math.Abs(before.Pixels.Bgra[offset + c] - after.Pixels.Bgra[offset + c]);
            count += 3;
        }
        return count > 0 && difference / (double)count < 3;
    }
}
