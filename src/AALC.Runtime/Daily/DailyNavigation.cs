using AALC.Runtime.Automation;
using AALC.Core.Features.Daily;

namespace AALC.Runtime.Daily;

public static class DailyNavigation
{
    private static readonly ImageQuery[] Queries = [new("home/window_assets.png"),
        new("home/mail_assets.png", Search: SearchMode.Normal), new("home/drive_assets.png", Search: SearchMode.Normal),
        new("home/back_assets.png"), new("base/back_assets.png", 0.6, Search: SearchMode.Normal),
        new("home/close_anniversary_event_assets.png"), new("base/notification_close_assets.png"),
        new("base/waiting_assets.png"), new("base/waiting_2_assets.png"),
        new("base/clear_all_caches_assets.png"), new("base/update_confirm_assets.png"), new("base/update_close_assets.png"),
        new("scenes/story_skip_confirm_assets.png"), new("scenes/story_skip_assets.png"), new("scenes/story_meun_assets.png"),
        new("battle/setting_assets.png")];

    /// <param name="settlementConfirmed">看到残留胜利结算、点击确认之前调用；点击可能已生效却抛出瞬时错误。</param>
    /// <param name="resumeBattle">遇到尚未结束的战斗时调用一次以接着打完；为空或已用过则按原样报错停止。</param>
    public static async Task<bool> ReturnHomeAsync(IGameSession s, CancellationToken ct, Action? settlementConfirmed = null,
        Func<CancellationToken, Task<bool>>? resumeBattle = null)
    {
        s.Report("daily.home.begin", "返回游戏主界面");
        var attempt = 0;
        var startupDeadline = s.Elapsed + TimeSpan.FromMinutes(15);
        var nextStartupClick = TimeSpan.Zero;
        var startingGame = false;
        while (attempt < 30)
        {
            var mode = attempt >= 20 ? SearchMode.Aggressive : attempt >= 10 ? SearchMode.Normal : SearchMode.Clam;
            var frame = await s.ObserveAsync(Queries.Select(x => x with { Search = x.Search == SearchMode.Normal ? x.Search : mode }).ToArray(), ct);
            // 标题页确认下载后，游戏在加载页或主界面仍可能再弹同一提示。主界面上确认会让界面失去响应，
            // 与旧版一致改为关闭；加载页仍确认下载。
            var home = frame.Find("home/mail_assets.png") is not null
                && (frame.Find("home/window_assets.png") is not null || frame.Find("home/drive_assets.png") is not null);
            if (frame.Find("base/update_confirm_assets.png") is not null && frame.Find("base/update_close_assets.png") is not null
                && UpdatePrompt(await s.ReadTextAsync(frame, ct)) is { } prompt)
            {
                startingGame = true;
                if (s.Elapsed >= nextStartupClick)
                {
                    await s.ClickAsync(frame, home ? prompt.Close : prompt.Confirm,
                        home ? "daily.home.close-update" : "daily.home.confirm-update", ct);
                    nextStartupClick = s.Elapsed + TimeSpan.FromSeconds(5);
                }
                if (s.Elapsed >= startupDeadline) break;
                await s.DelayAsync(TimeSpan.FromSeconds(1), ct);
                continue;
            }
            if (home) return true;
            if (frame.Find("base/notification_close_assets.png") is not null)
            {
                // 与旧版一致：周四 10:00–12:00（首尔）维护期间等到结束，其他时间直接重启游戏。
                if (s.CanRestartGame && MaintenanceRemaining(DateTimeOffset.UtcNow) is { } wait)
                {
                    s.Report("daily.home.maintenance-wait", $"周常维护中，等待 {Math.Ceiling(wait.TotalMinutes)} 分钟后重启游戏");
                    s.ExtendDeadline(wait);
                    await s.DelayAsync(wait, ct);
                }
                if (await s.RestartGameAsync("游戏显示维护提示", ct)) return await ReturnHomeAsync(s, ct, settlementConfirmed);
                s.Report("daily.home.maintenance", "游戏显示维护提示，请处理后重新运行");
                return false;
            }
            if (frame.Find("base/waiting_assets.png") is not null || frame.Find("base/waiting_2_assets.png") is not null)
            {
                if (startingGame && s.Elapsed >= startupDeadline) break;
                if (!startingGame) attempt++;
                await s.DelayAsync(TimeSpan.FromSeconds(1), ct);
                continue;
            }
            var text = await s.ReadTextAsync(frame, ct);
            if (frame.Find("base/clear_all_caches_assets.png") is not null
                && text.Any(item => item.Text.Contains("清除所有缓存") || item.Text.Contains("CLEAR ALL CACHE", StringComparison.OrdinalIgnoreCase)))
            {
                startingGame = true;
                var update = text.Any(item => item.Text.Contains("下载") || item.Text.Contains("download", StringComparison.OrdinalIgnoreCase));
                if (s.Elapsed >= nextStartupClick && UpdatePrompt(text) is { } titlePrompt)
                {
                    await s.ClickAsync(frame, titlePrompt.Confirm, "daily.home.confirm-update", ct);
                    nextStartupClick = s.Elapsed + TimeSpan.FromSeconds(5);
                }
                else if (s.Elapsed >= nextStartupClick && !update
                    && text.Any(item => item.Text.Contains("FACE THE SIN", StringComparison.OrdinalIgnoreCase)))
                {
                    await s.ClickAsync(frame, new((int)(frame.Identity.Width * .86), (int)(frame.Identity.Height * .80)),
                        "daily.home.start-game", ct);
                    nextStartupClick = s.Elapsed + TimeSpan.FromSeconds(5);
                }
                if (s.Elapsed >= startupDeadline) break;
                await s.DelayAsync(TimeSpan.FromSeconds(1), ct);
                continue;
            }
            if (text.Any(item => string.Concat(item.Text.Where(char.IsLetterOrDigit)).ToUpperInvariant()
                .Replace('0', 'O').Contains("DOWNLOADING")))
            {
                startingGame = true;
                if (s.Elapsed >= startupDeadline) break;
                await s.DelayAsync(TimeSpan.FromSeconds(2), ct);
                continue;
            }
            attempt++;
            if (BattleFlow.SettlementConfirmation(text) is { } settlement)
            {
                settlementConfirmed?.Invoke();
                await s.ClickAsync(frame, settlement, "daily.home.confirm-settlement", ct);
            }
            else if (frame.Find("battle/setting_assets.png") is not null && resumeBattle is { } resume)
            {
                resumeBattle = null;
                if (!await resume(ct)) return false;
            }
            else if (frame.Find("battle/setting_assets.png") is not null)
            {
                s.Report("daily.home.active-battle", "检测到尚未结束的战斗，请完成后再运行日常");
                return false;
            }
            else
            {
                var target = new[] { "home/window_assets.png", "scenes/story_skip_confirm_assets.png", "scenes/story_skip_assets.png",
                    "scenes/story_meun_assets.png", "home/back_assets.png", "base/back_assets.png", "home/close_anniversary_event_assets.png" }
                    .Select(frame.Find).FirstOrDefault(x => x is not null);
                if (target is not null) await s.ClickAsync(frame, target.Center, "daily.home.navigate", ct);
                else await s.KeyAsync(frame, GameKey.Escape, "daily.home.escape", ct);
            }
            await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
        }
        // 与旧版 back_init_menu 一致：无法返回主界面时重启游戏后重新尝试，次数由会话限制。
        if (await s.RestartGameAsync("多次尝试后仍未返回主界面", ct)) return await ReturnHomeAsync(s, ct, settlementConfirmed);
        s.Report("daily.home.timeout", "多次尝试后仍未返回主界面");
        return false;
    }

    public static TimeSpan? MaintenanceRemaining(DateTimeOffset now)
    {
        var seoul = now.ToOffset(TimeSpan.FromHours(9));
        if (seoul.DayOfWeek != DayOfWeek.Thursday || seoul.Hour is < 10 or >= 12) return null;
        return new DateTimeOffset(seoul.Year, seoul.Month, seoul.Day, 12, 0, 0, seoul.Offset) - seoul;
    }

    private static (PixelPoint Confirm, PixelPoint Close)? UpdatePrompt(IReadOnlyList<RecognizedText> text)
    {
        if (!text.Any(item => item.Text.Contains("下载") || item.Text.Contains("download", StringComparison.OrdinalIgnoreCase))) return null;
        var confirm = text.FirstOrDefault(item => item.Text.Contains("确认") || item.Text.Equals("confirm", StringComparison.OrdinalIgnoreCase));
        var close = text.FirstOrDefault(item => item.Text.Contains("关闭") || item.Text.Equals("close", StringComparison.OrdinalIgnoreCase));
        static PixelPoint Center(RecognizedText item) => new(item.Bounds.X + item.Bounds.Width / 2, item.Bounds.Y + item.Bounds.Height / 2);
        return confirm is not null && close is not null && confirm.Bounds.X > close.Bounds.X ? (Center(confirm), Center(close)) : null;
    }
}
