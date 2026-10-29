using AALC.Runtime.Automation;

namespace AALC.Runtime.Mirror;

public static class MirrorFormationFlow
{
    private static readonly ImageQuery[] FeedbackQueries = [new("teams/identify_assets.png"), new("teams/selected.png", Multiple: true)];
    private static readonly ImageQuery[] Queries = [new("teams/identify_assets.png"), new("teams/selected.png", Multiple: true),
        new("teams/clear_selection_assets.png"), new("teams/clear_selection_confirm_assets.png", Search: SearchMode.Normal)];

    public static async Task<bool> RunAsync(IGameSession s, IReadOnlyList<int> order, CancellationToken ct)
    {
        for (var attempt = 0; attempt < 3; attempt++)
        {
            ct.ThrowIfCancellationRequested();
            var completed = await RunOnceAsync(s, order, ct);
            ct.ThrowIfCancellationRequested();
            if (completed) return true;
            if (attempt == 2) break;
            var frame = await s.ObserveControlsAsync(Queries, ct);
            if (frame.Find("teams/identify_assets.png") is null || frame.Find("teams/clear_selection_assets.png") is null
                && frame.Find("teams/clear_selection_confirm_assets.png") is null)
            {
                s.Report("mirror.formation.unavailable", "本次编队未确认，未找到可用的重置页面");
                return false;
            }
            s.Report("mirror.formation.recover", $"本次编队未确认，正在清空后按配置重建（{attempt + 1}/2）");
        }
        s.Report("mirror.formation.failed", "两次恢复后仍未确认编队，停止开战");
        return false;
    }

    private static async Task<bool> RunOnceAsync(IGameSession s, IReadOnlyList<int> order, CancellationToken ct)
    {
        var frame = await s.ObserveControlsAsync(Queries, ct);
        if (frame.Find("teams/identify_assets.png") is null) return false;
        if (frame.Find("teams/clear_selection_confirm_assets.png") is null && await MatchesOrderAsync(s, frame, order, ct))
        {
            s.Report("mirror.formation.reused", "当前实际出战顺序符合配置，复用编队");
            return true;
        }
        if (frame.Find("teams/clear_selection_assets.png") is { } || frame.Find("teams/clear_selection_confirm_assets.png") is not null)
        {
            var initialSelections = frame.FindAll("teams/selected.png");
            var sawConfirmation = frame.Find("teams/clear_selection_confirm_assets.png") is not null;
            var openRetried = false;
            if (frame.Find("teams/clear_selection_confirm_assets.png") is null)
                await s.ClickAsync(frame, frame.Find("teams/clear_selection_assets.png")!.Center, "mirror.formation.clear", ct);
            PixelPoint? previous = null;
            var confirmed = false;
            for (var poll = 0; poll < (openRetried ? 24 : 12); poll++)
            {
                await s.DelayAsync(TimeSpan.FromMilliseconds(120), ct);
                frame = await s.ObserveControlsAsync(Queries, ct);
                var confirm = frame.Find("teams/clear_selection_confirm_assets.png");
                sawConfirmation |= confirm is not null;
                if (confirm is not null && previous is { } point
                    && Math.Abs(confirm.Center.X - point.X) <= 6 * frame.Scale
                    && Math.Abs(confirm.Center.Y - point.Y) <= 6 * frame.Scale)
                {
                    await s.ClickAsync(frame, confirm.Center, "mirror.formation.clear-confirm", ct);
                    confirmed = true;
                    break;
                }
                previous = confirm?.Center;
                var visibleSelections = frame.FindAll("teams/selected.png");
                if (poll == 11 && !sawConfirmation && frame.Find("teams/identify_assets.png") is not null
                    && frame.Find("teams/clear_selection_assets.png") is { } retry && initialSelections.Count > 0
                    && visibleSelections.Count == initialSelections.Count && initialSelections.All(before => visibleSelections.Any(after =>
                        Math.Abs(before.Center.X - after.Center.X) <= 6 * frame.Scale && Math.Abs(before.Center.Y - after.Center.Y) <= 6 * frame.Scale)))
                {
                    s.Report("mirror.formation.clear-retry", "原编队仍在，重新打开重置弹窗");
                    await s.ClickAsync(frame, retry.Center, "mirror.formation.clear", ct);
                    openRetried = true;
                }
            }
            if (!confirmed)
            {
                s.Report("mirror.formation.not-cleared", "本次未确认重置编队弹窗");
                return false;
            }
            var emptyFrames = 0;
            var confirmRetried = false;
            for (var poll = 0; poll < (confirmRetried ? 24 : 12); poll++)
            {
                await s.DelayAsync(TimeSpan.FromMilliseconds(120), ct);
                frame = await s.ObserveControlsAsync(Queries, ct);
                var pending = frame.Find("teams/clear_selection_confirm_assets.png");
                emptyFrames = pending is null
                    && frame.Find("teams/identify_assets.png") is not null && frame.FindAll("teams/selected.png").Count == 0
                    ? emptyFrames + 1 : 0;
                if (emptyFrames == 2) break;
                if (poll == 11 && pending is not null && previous is { } point
                    && frame.Find("teams/identify_assets.png") is not null
                    && Math.Abs(pending.Center.X - point.X) <= 6 * frame.Scale
                    && Math.Abs(pending.Center.Y - point.Y) <= 6 * frame.Scale)
                {
                    s.Report("mirror.formation.clear-confirm-retry", "重置弹窗仍在，重新确认");
                    await s.ClickAsync(frame, pending.Center, "mirror.formation.clear-confirm", ct);
                    confirmRetried = true;
                }
                previous = pending?.Center;
            }
            if (emptyFrames != 2)
            {
                s.Report("mirror.formation.not-cleared", "本次重置弹窗未关闭或原出战顺序仍存在");
                return false;
            }
        }
        if (frame.FindAll("teams/selected.png").Count != 0)
        {
            s.Report("mirror.formation.not-cleared", "未确认清空出战顺序");
            return false;
        }
        if (frame.Find("teams/identify_assets.png") is not { } anchor) return false;
        var scale = frame.Scale;
        var slots = SinnerSlots(anchor, scale);
        var selected = new HashSet<int>();
        if (SelectedSinners(frame, slots, scale) is not { Count: 0 })
        {
            s.Report("mirror.formation.unverified", "本次未确认清空出战顺序");
            return false;
        }
        foreach (var number in order)
        {
            var expected = selected.Append(number).ToHashSet();
            var confirmed = false;
            for (var attempt = 0; attempt < 2 && !confirmed; attempt++)
            {
                if (attempt > 0) s.Report("mirror.formation.retry", $"罪人 {number} 尚未选中，重新选择");
                await s.ClickAsync(frame, slots[number - 1], "mirror.formation.sinner", ct);
                var unchanged = 0;
                for (var poll = 0; poll < 6; poll++)
                {
                    await s.DelayAsync(TimeSpan.FromMilliseconds(120), ct);
                    frame = await s.ObserveControlsAsync(FeedbackQueries, ct);
                    var actual = SelectedSinners(frame, slots, scale);
                    if (frame.Find("teams/identify_assets.png") is null)
                    {
                        s.Report("mirror.formation.unverified", "本次未识别到编队选择反馈");
                        return false;
                    }
                    if (actual is null)
                    {
                        unchanged = 0;
                        continue;
                    }
                    if (actual.SetEquals(expected))
                    {
                        confirmed = true;
                        break;
                    }
                    if (!actual.IsSubsetOf(expected))
                    {
                        s.Report("mirror.formation.unverified", "本次实际已选罪人与出战顺序不符");
                        return false;
                    }
                    unchanged = actual.SetEquals(selected) ? unchanged + 1 : 0;
                }
                if (!confirmed && unchanged != 6) break;
            }
            if (!confirmed)
            {
                s.Report("mirror.formation.unverified", $"本次未确认罪人 {number} 已选中");
                return false;
            }
            selected.Add(number);
            s.Report("mirror.formation.selected", $"已确认出战顺序 {selected.Count}/{order.Count}");
        }
        return true;
    }

    private static PixelPoint[] SinnerSlots(VisualTarget anchor, double scale) =>
        Enumerable.Range(0, 12).Select(index => new PixelPoint(
            anchor.Center.X + (int)((-1800 + index % 6 * 270) * scale),
            anchor.Center.Y + (int)((130 + index / 6 * 500) * scale))).ToArray();

    private static async Task<bool> MatchesOrderAsync(IGameSession s, GameFrame frame, IReadOnlyList<int> order, CancellationToken ct)
    {
        var scale = frame.Scale;
        var slots = SinnerSlots(frame.Find("teams/identify_assets.png")!, scale);
        var selected = SelectedSinners(frame, slots, scale);
        if (order.Count == 0 || selected is null || selected.Count != order.Count || !selected.SetEquals(order)) return false;
        for (var index = 0; index < order.Count; index++)
        {
            var slot = slots[order[index] - 1];
            var banners = frame.FindAll("teams/selected.png").Where(hit =>
                Math.Abs(hit.Center.X - slot.X) <= 110 * scale && Math.Abs(hit.Center.Y - slot.Y) <= 150 * scale).ToArray();
            var center = banners.Length == 1 ? banners[0].Center : BackupBannerCenter(frame, slot, scale);
            if (center is null) return false;
            var region = new PixelRect(center.Value.X - (int)(60 * scale), center.Value.Y - (int)(115 * scale),
                (int)(120 * scale), (int)(75 * scale));
            var text = await s.ReadTextAsync(frame, ct, region, preprocessing: TextPreprocessing.FormationOrder);
            if (text.Count != 1 || text[0].Confidence < .9 || !int.TryParse(text[0].Text, out var position) || position != index + 1)
                return false;
        }
        return true;
    }

    private static HashSet<int>? SelectedSinners(GameFrame frame, IReadOnlyList<PixelPoint> slots, double scale)
    {
        var selected = new HashSet<int>();
        foreach (var hit in frame.FindAll("teams/selected.png"))
        {
            var matches = Enumerable.Range(0, slots.Count).Where(index =>
                Math.Abs(hit.Center.X - slots[index].X) <= 110 * scale
                && Math.Abs(hit.Center.Y - slots[index].Y) <= 150 * scale).ToArray();
            if (matches.Length != 1) return null;
            selected.Add(matches[0] + 1);
        }
        for (var index = 0; index < slots.Count; index++)
            if (BackupBannerCenter(frame, slots[index], scale) is not null) selected.Add(index + 1);
        return selected;
    }

    private static PixelPoint? BackupBannerCenter(GameFrame frame, PixelPoint slot, double scale)
    {
        if (frame.Pixels.Bgra.Length != frame.Identity.Width * frame.Identity.Height * 4) return null;
        var consecutive = 0;
        var longest = 0;
        var firstY = -1;
        var lastY = 0;
        for (var y = Math.Max(0, slot.Y - (int)(150 * scale)); y < Math.Min(frame.Identity.Height, slot.Y + (int)(100 * scale)); y++)
        {
            var cyan = 0;
            for (var x = Math.Max(0, slot.X - (int)(110 * scale)); x < Math.Min(frame.Identity.Width, slot.X + (int)(110 * scale)); x++)
            {
                var offset = (y * frame.Identity.Width + x) * 4;
                var b = frame.Pixels.Bgra[offset]; var g = frame.Pixels.Bgra[offset + 1]; var r = frame.Pixels.Bgra[offset + 2];
                if (b >= 60 && g >= 60 && r <= 60 && Math.Min(b, g) - r >= 35) cyan++;
            }
            consecutive = cyan >= 160 * scale ? consecutive + 1 : 0;
            longest = Math.Max(longest, consecutive);
            if (consecutive > 0)
            {
                if (firstY < 0) firstY = y;
                lastY = y;
            }
        }
        return longest >= 12 * scale ? new(slot.X, (firstY + lastY) / 2) : null;
    }

}
