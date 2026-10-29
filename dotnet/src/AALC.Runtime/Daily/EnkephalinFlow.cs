using AALC.Runtime.Automation;
using System.Text.RegularExpressions;
using AALC.Core.Features.Daily;

namespace AALC.Runtime.Daily;

public static class EnkephalinFlow
{
    private const string Entry = "home/enkephalin_box_assets.png";
    private const string UseLunacy = "enkephalin/use_lunacy_assets.png";
    private const string AllIn = "enkephalin/all_in_assets.png";
    private const string Disabled = "enkephalin/all_in_disabled_assets.png";
    private const string Confirm = "enkephalin/enkephalin_confirm_assets.png";
    private const string Cancel = "enkephalin/enkephalin_cancel_assets.png";
    private const string Lunacy = "enkephalin/lunacy_assets.png";
    private static readonly (string Asset, int Price)[] Prices = [
        ("enkephalin/lunacy_spend_26_assets.png", 26), ("enkephalin/lunacy_spend_52_assets.png", 52),
        ("enkephalin/lunacy_spend_78_assets.png", 78)];
    private static readonly ImageQuery[] Queries = [new(Entry, .75), new(UseLunacy, .45), new(AllIn, .5),
        new(Disabled, .55), new(Cancel, .55), new(Confirm), new(Lunacy),
        .. Prices.Select(p => new ImageQuery(p.Asset))];

    public static Task<bool> ConvertAsync(IGameSession s, CancellationToken ct) => ConvertAsync(s, true, ct);

    private static bool PanelVisible(GameFrame frame) => frame.Find(UseLunacy) is not null || frame.Find(Cancel) is not null
        || frame.Find(Disabled) is not null || frame.Find(AllIn) is not null;

    private static bool Enabled(GameFrame frame) => frame.Find(AllIn) is { } target &&
        DailyRewardRules.EnabledColor(frame.Pixels.Bgra, frame.Identity.Width, frame.Identity.Height, target.Bounds);

    private static bool ConfirmationEnabled(GameFrame frame)
    {
        if (frame.Find(Confirm) is not { } target) return false;
        var brightness = 0.0;
        var count = 0;
        for (var y = Math.Max(0, target.Bounds.Y); y < Math.Min(frame.Identity.Height, target.Bounds.Bottom); y++)
            for (var x = Math.Max(0, target.Bounds.X); x < Math.Min(frame.Identity.Width, target.Bounds.Right); x++)
            {
                var offset = (y * frame.Identity.Width + x) * 4;
                var pixels = frame.Pixels.Bgra;
                brightness += Math.Max(pixels[offset], Math.Max(pixels[offset + 1], pixels[offset + 2]));
                count++;
            }
        return count > 0 && brightness / count >= 120;
    }

    private static async Task<int?> CurrentStaminaAsync(IGameSession s, GameFrame frame, CancellationToken ct)
    {
        var text = await s.ReadTextAsync(frame, ct, frame.Region(1150, 800, 1380, 930), 2);
        var values = text.Select(t => Regex.Match(t.Text, @"^\s*(\d{1,3})\s*/"))
            .Where(match => match.Success).Select(match => int.Parse(match.Groups[1].Value)).Distinct().ToArray();
        return values.Length == 1 ? values[0] : null;
    }

    private static async Task<GameFrame?> OpenAsync(IGameSession s, CancellationToken ct)
    {
        var deadline = s.Elapsed + TimeSpan.FromSeconds(30);
        var lastClick = TimeSpan.MinValue;
        while (s.Elapsed < deadline)
        {
            ct.ThrowIfCancellationRequested();
            var frame = await s.ObserveAsync(Queries, ct);
            if (PanelVisible(frame)) return frame;
            if (frame.Find(Entry) is { } entry && (lastClick == TimeSpan.MinValue || s.Elapsed - lastClick >= TimeSpan.FromSeconds(1.2)))
            {
                await s.ClickAsync(frame, entry.Center, "daily.modules.open", ct);
                lastClick = s.Elapsed;
            }
            await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
        }
        s.Report("daily.modules.open-timeout", "未能打开体力兑换面板");
        return null;
    }

    private static async Task<bool> ConvertAsync(IGameSession s, bool close, CancellationToken ct)
    {
        s.Report("daily.modules.begin", "检查体力并转换模块");
        var frame = await OpenAsync(s, ct);
        if (frame is null) return false;
        var selectAll = Enabled(frame);
        int? singleStamina = null;
        if (!selectAll && frame.Find(Disabled) is not null && ConfirmationEnabled(frame))
        {
            var quantity = await s.ReadTextAsync(frame, ct, frame.Region(1300, 620, 1440, 700), 2);
            if (quantity.Count != 1 || quantity[0].Text.Trim() != "1")
            {
                s.Report("daily.modules.single-unverified", "无法确认默认单模块数量，停止兑换");
                return false;
            }
            singleStamina = await CurrentStaminaAsync(s, frame, ct);
            if (singleStamina is not (>= 20 and < 40))
            {
                s.Report("daily.modules.single-unverified", "已选一个模块，但无法确认当前体力，停止兑换");
                return false;
            }
            s.Report("daily.modules.single-selected", "当前已选一个模块，确认兑换");
        }
        if (!selectAll && singleStamina is null)
        {
            if (frame.Find(Disabled) is null && frame.Find(AllIn) is null)
            {
                s.Report("daily.modules.unrecognized", "兑换按钮状态无法识别");
                return false;
            }
            s.Report("daily.modules.unavailable", "当前体力不足，跳过模块兑换");
            return !close || await CloseAsync(s, ct);
        }
        if (selectAll)
        {
            await s.ClickAsync(frame, frame.Find(AllIn)!.Center, "daily.modules.select-all", ct);
            await s.DelayAsync(TimeSpan.FromMilliseconds(200), ct);
        }
        var deadline = s.Elapsed + TimeSpan.FromSeconds(10);
        GameFrame? confirmation = singleStamina is not null ? frame : null;
        while (confirmation is null && s.Elapsed < deadline)
        {
            frame = await s.ObserveAsync(Queries, ct);
            if (frame.Find(Confirm) is not null) { confirmation = frame; break; }
            await s.DelayAsync(TimeSpan.FromMilliseconds(300), ct);
        }
        if (confirmation is null)
        {
            s.Report("daily.modules.confirm-missing", "未识别到模块兑换确认按钮");
            return false;
        }
        await s.ClickAsync(confirmation, confirmation.Find(Confirm)!.Center, "daily.modules.confirm", ct);
        deadline = s.Elapsed + TimeSpan.FromSeconds(10);
        while (s.Elapsed < deadline)
        {
            await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
            frame = await s.ObserveAsync(Queries, ct);
            if (frame.Identity.Id <= confirmation.Identity.Id) continue;
            var disabled = !Enabled(frame) && frame.Find(Disabled) is not null;
            var completed = singleStamina is { } before
                ? disabled && await CurrentStaminaAsync(s, frame, ct) == before - 20
                : !PanelVisible(frame) || disabled;
            if (completed)
            {
                s.Report("daily.modules.converted", "模块兑换完成");
                return !close || await CloseAsync(s, ct);
            }
        }
        s.Report("daily.modules.unverified", "模块确认后未观察到体力减少后的按钮状态，停止重复确认");
        return false;
    }

    private static async Task<bool> CloseAsync(IGameSession s, CancellationToken ct)
    {
        var deadline = s.Elapsed + TimeSpan.FromSeconds(10);
        var clicked = false;
        while (s.Elapsed < deadline)
        {
            var frame = await s.ObserveAsync(Queries, ct);
            if (!PanelVisible(frame)) return true;
            if (!clicked && frame.Find(Cancel) is { } cancel)
            {
                await s.ClickAsync(frame, cancel.Center, "daily.modules.close", ct);
                clicked = true;
            }
            await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
        }
        s.Report("daily.modules.close-timeout", "体力面板关闭后仍未消失");
        return false;
    }

    private static async Task<int?> PriceAsync(IGameSession s, GameFrame frame, CancellationToken ct)
    {
        var matches = Prices.Select(p => (Price: p.Price, Hit: frame.Find(p.Asset))).Where(p => p.Hit is not null)
            .OrderByDescending(p => p.Hit!.Score).ToArray();
        if (matches.Length > 0) return matches[0].Price;
        var text = await s.ReadTextAsync(frame, ct, frame.Region(1130, 510, 1320, 660), 2);
        var numbers = text.Select(t => t.Text.Trim()).Where(t => Regex.IsMatch(t, @"^\d+$"))
            .Select(t => int.TryParse(t, out var value) ? value : 0).Where(p => DailyRewardRules.RefillTierForPrice(p) > 0).Distinct().ToArray();
        return numbers.Length == 1 ? numbers[0] : null;
    }

    public static async Task<bool> RefillAsync(IGameSession s, int tier, bool grandet, CancellationToken ct)
    {
        if (tier is < 0 or > 3) throw new ArgumentOutOfRangeException(nameof(tier));
        if (tier == 0) { s.Report("daily.refill.skipped", "设置为不使用狂气换体"); return true; }
        s.Report("daily.refill.begin", $"狂气换体最多执行到每日第 {tier} 档");
        if (!await ConvertAsync(s, false, ct)) return false;
        var frame = await OpenAsync(s, ct);
        if (frame?.Find(UseLunacy) is not { } use) return false;
        await s.ClickAsync(frame, use.Center, "daily.refill.open", ct);
        await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
        var lastPrice = 0;
        var waitingForAdvance = false;
        var waitedForTimer = false;
        var deadline = s.Elapsed + TimeSpan.FromSeconds(15);
        while (s.Elapsed < deadline)
        {
            ct.ThrowIfCancellationRequested();
            frame = await s.ObserveAsync(Queries, ct);
            var price = await PriceAsync(s, frame, ct);
            if (price is null || (waitingForAdvance && price <= lastPrice))
            {
                await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                continue;
            }
            if (waitingForAdvance)
            {
                s.Report("daily.refill.confirmed", $"已观察到狂气价格从 {lastPrice} 变为 {price}");
                waitingForAdvance = false;
            }
            if (DailyRewardRules.RefillTierForPrice(price.Value) > tier)
            {
                if (!await CloseAsync(s, ct)) return false;
                return await ConvertAsync(s, true, ct);
            }
            if (frame.Find(Confirm) is not { } confirm)
            {
                await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                continue;
            }
            if (grandet && !waitedForTimer)
            {
                if (!await WaitForTimerAsync(s, ct)) return false;
                waitedForTimer = true;
                deadline = s.Elapsed + TimeSpan.FromSeconds(15);
                continue;
            }
            lastPrice = price.Value;
            await s.ClickAsync(frame, confirm.Center, "daily.refill.confirm", ct);
            waitingForAdvance = true;
            deadline = s.Elapsed + TimeSpan.FromSeconds(15);
            await s.DelayAsync(TimeSpan.FromSeconds(1), ct);
        }
        s.Report("daily.refill.unverified", "未能确认狂气价格变化，停止继续消费");
        return false;
    }

    private static async Task<bool> WaitForTimerAsync(IGameSession s, CancellationToken ct)
    {
        s.Report("daily.refill.wait-timer", "等待体力恢复倒计时符合葛朗台模式");
        var deadline = s.Elapsed + TimeSpan.FromMinutes(6);
        while (s.Elapsed < deadline)
        {
            var frame = await s.ObserveAsync(Queries, ct);
            if (frame.Find(Lunacy) is { } anchor)
            {
                var region = new PixelRect(anchor.Center.X - (int)(200 * frame.Scale), anchor.Center.Y + (int)(150 * frame.Scale),
                    (int)(800 * frame.Scale), (int)(70 * frame.Scale));
                var text = await s.ReadTextAsync(frame, ct, region);
                if (DailyRewardRules.GrandetReady(string.Concat(text.Select(t => t.Text)))) return true;
            }
            await s.DelayAsync(TimeSpan.FromSeconds(2), ct);
        }
        s.Report("daily.refill.timer-timeout", "体力倒计时未满足葛朗台模式条件");
        return false;
    }
}
