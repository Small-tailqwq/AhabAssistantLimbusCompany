using AALC.Runtime.Automation;
using System.Text.RegularExpressions;
using AALC.Core.Features.Daily;
using AALC.Core.Features.Mail;

namespace AALC.Runtime.Automation;

public enum BattlePurpose { Luxcavation, Mirror }

public sealed class SoloDefenseState(int turns)
{
    public int RemainingTurns { get; private set; } = turns;
    public void ConsumeTurn() => RemainingTurns--;
}

public static class BattleFlow
{
    private static readonly ImageQuery[] MirrorDestinations = [new("mirror/road_in_mir/legend_assets.png"),
        new("mirror/road_in_mir/select_encounter_reward_card_assets.png"), new("mirror/theme_pack/feature_theme_pack_assets.png"),
        new("mirror/road_in_mir/acquire_ego_gift_card.png"), new("mirror/road_in_mir/ego_gift_get_confirm_assets.png"),
        new("mirror/road_in_mir/acquire_ego_gift_box_assets.png"), new("mirror/road_in_mir/acquire_ego_gift_select_assets.png"),
        new("mirror/claim_reward/claim_rewards_assets.png"), new("mirror/claim_reward/complete_mirror_100%_assets.png"),
        new("mirror/claim_reward/clear_assets.png")];
    public static readonly ImageQuery[] MirrorExitQueries = [.. MirrorDestinations, new("mirror/claim_reward/battle_statistics_assets.png"),
        new("battle/battle_finish_confirm_assets.png")];
    private static readonly ImageQuery[] StartQueries = [new("battle/normal_to_battle_assets.png"),
        new("battle/chaim_to_battle_assets.png")];
    // 多目标匹配较慢，只在点击后按钮仍在、需要检查超员时使用。
    private static readonly ImageQuery[] ExcessQueries = [.. StartQueries, new("teams/selected.png", Multiple: true)];
    private static readonly ImageQuery[] BattleQueries = [new("base/waiting_assets.png"), new("battle/pause_assets.png"),
        new("battle/more_information_assets.png"), new("battle/win_rate_assets.png", Search: SearchMode.Aggressive),
        new("battle/turn_assets.png"), new("battle/win_rate_card.png", 0.75), new("battle/gear_right.png"),
        new("battle/view_status_assets.png"), new("battle/dead_all.png", Multiple: true),
        new("battle/dead_all_confirm_assets.png"), new("battle/continue_assets.png"),
        new("base/leave_up_assets.png"), new("base/leave_up_confirm_assets.png")];

    public static async Task<bool> RunAsync(IGameSession s, int combatCount, bool events, CancellationToken ct,
        BattlePurpose purpose = BattlePurpose.Luxcavation, bool avoidSkill3 = false, SoloDefenseState? solo = null,
        Action? victorySeen = null)
    {
        s.Report("battle.start", "开始战斗");
        if (!await StartAsync(s, ct)) return false;
        return await ContinueAsync(s, combatCount, events, ct, purpose, avoidSkill3, solo, victorySeen);
    }

    /// <param name="victorySeen">看到胜利结算、点击确认之前调用：确认点击可能已生效却抛出瞬时错误，调用方须在此记下本批已胜利。</param>
    public static async Task<bool> ContinueAsync(IGameSession s, int combatCount, bool events, CancellationToken ct,
        BattlePurpose purpose = BattlePurpose.Luxcavation, bool avoidSkill3 = false, SoloDefenseState? solo = null,
        Action? victorySeen = null)
    {
        s.Report("battle.fight", "等待战斗回合与结算");
        var beginning = s.Elapsed;
        var unknown = 0;
        var deaths = 0;
        var mouseRate = false;
        var handler = new BattleEvents();
        var queries = events ? BattleQueries.Concat(BattleEvents.Queries).ToArray() : BattleQueries;
        if (purpose == BattlePurpose.Mirror) queries = queries.Concat(MirrorExitQueries).ToArray();
        if (purpose == BattlePurpose.Mirror && (avoidSkill3 || solo is not null)) queries = queries.Concat([new ImageQuery("battle/gear_left.png", 0.9)]).ToArray();
        var turnFeedbackQueries = queries.Select(query => query.Asset == "battle/pause_assets.png"
            ? query with { Threshold = 0.75 } : query).ToArray();
        while (s.Elapsed - beginning < TimeSpan.FromSeconds(900 + 300 * combatCount))
        {
            var frame = await s.ObserveControlsAsync(queries, ct);
            if (!queries.Any(query => frame.Find(query.Asset) is not null))
                frame = await s.ObserveAsync(queries, ct);
            var upgrade = frame.Find("base/leave_up_confirm_assets.png") ?? frame.Find("base/leave_up_assets.png");
            if (upgrade is not null)
            {
                await s.DelayAsync(TimeSpan.FromMilliseconds(150), ct);
                var next = await s.ObserveControlsAsync(queries, ct);
                var confirmed = next.Find(upgrade.Asset);
                if (confirmed is null || Math.Abs(confirmed.Center.X - upgrade.Center.X) > 20 * frame.Scale
                    || Math.Abs(confirmed.Center.Y - upgrade.Center.Y) > 20 * frame.Scale) continue;
                s.Report("battle.upgrade", "关闭升级提示");
                await s.ClickAsync(next, confirmed.Center, confirmed.Asset == "base/leave_up_confirm_assets.png"
                    ? "battle.leave-overlay-confirm" : "battle.leave-overlay", ct);
                unknown = 0;
                await s.DelayAsync(TimeSpan.FromMilliseconds(150), ct);
                continue;
            }
            if (purpose == BattlePurpose.Mirror && MirrorDestinations.Any(query => frame.Find(query.Asset) is not null))
            {
                s.Report("battle.mirror-exit", "战斗结束，交回镜牢流程");
                return true;
            }
            if (purpose == BattlePurpose.Mirror && frame.Find("mirror/claim_reward/battle_statistics_assets.png") is not null
                && frame.Find("battle/battle_finish_confirm_assets.png") is { } finish)
            {
                await s.ClickAsync(frame, finish.Center, "battle.mirror-statistics", ct);
                continue;
            }
            if (frame.Find("base/waiting_assets.png") is not null)
            {
                await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                continue;
            }
            if (frame.Find("battle/view_status_assets.png") is { } status)
            {
                await s.ClickAsync(frame, new(status.Center.X + (int)(100 * frame.Scale), status.Center.Y - (int)(500 * frame.Scale)),
                    "battle.dismiss-status", ct);
                continue;
            }
            if (frame.Find("battle/pause_assets.png") is not null)
            {
                unknown = 0;
                await s.DelayAsync(TimeSpan.FromSeconds(purpose == BattlePurpose.Mirror ? 1 : 3), ct);
                continue;
            }
            if (frame.Find("battle/dead_all.png") is not null)
            {
                if (++deaths >= 5)
                {
                    s.Report("battle.defeated", "战斗连续失败五次，停止本批任务");
                    return false;
                }
                s.Report("battle.retry", "战斗失败，重新挑战");
                var choices = frame.FindAll("battle/dead_all.png").OrderBy(hit => hit.Center.Y).ToArray();
                if (choices.Length == 3)
                    await s.ClickAsync(frame, choices[1].Center, "battle.retry-option", ct);
                else if (frame.Find("battle/dead_all_confirm_assets.png") is { } retry)
                    await s.ClickAsync(frame, new(retry.Center.X + (int)(200 * frame.Scale), retry.Center.Y - (int)(350 * frame.Scale)),
                        "battle.retry-option", ct);
                else return false;
                frame = await s.ObserveAsync(queries, ct);
                if (frame.Find("battle/dead_all_confirm_assets.png") is { } confirm)
                    await s.ClickAsync(frame, confirm.Center, "battle.retry-confirm", ct);
                beginning = s.Elapsed;
                unknown = 0;
                await s.DelayAsync(TimeSpan.FromSeconds(1), ct);
                continue;
            }

            var knownTurn = HasTurnControls(frame) || unknown >= 5 && frame.Find("battle/turn_assets.png") is not null
                || mouseRate && frame.Find("battle/win_rate_card.png") is not null;
            var eventPage = events && BattleEvents.Queries.Any(query => frame.Find(query.Asset) is not null);
            IReadOnlyList<RecognizedText> text = knownTurn && !eventPage ? [] : await s.ReadTextAsync(frame, ct);
            var combined = Normalize(string.Join("", text.Select(entry => entry.Text)));
            var settlement = SettlementConfirmation(text);
            if (settlement is { } settlementPoint)
            {
                s.Report("battle.settlement", "确认战斗胜利结算");
                victorySeen?.Invoke();
                await s.ClickAsync(frame, settlementPoint, "battle.confirm-settlement", ct);
                if (purpose == BattlePurpose.Luxcavation) return true;
                unknown = 0;
                continue;
            }
            if (events)
            {
                var eventResult = await handler.HandleAsync(s, frame, text, ct);
                if (eventResult.Failed) return false;
                if (eventResult.Handled)
                {
                    unknown = 0;
                    await s.DelayAsync(handler.NextObservationDelay, ct);
                    continue;
                }
            }
            if ((combined.Contains("战斗胜利") || combined.Contains("battlevictory")) && unknown < 16)
            {
                s.Report("battle.advance-settlement", "推进战斗结算动画");
                await s.ClickAsync(frame, new(frame.Identity.Width / 2, frame.Identity.Height / 2),
                    "battle.advance-settlement", ct);
                unknown++;
                await s.DelayAsync(TimeSpan.FromMilliseconds(150), ct);
                continue;
            }
            var ready = knownTurn || unknown >= 10 && combined.Contains("turn");
            if (ready)
            {
                s.Report("battle.turn", "选择并开始战斗回合");
                IReadOnlyList<PixelPoint>? path = null;
                // 回合开始时技能面板还在上滑，齿轮未就位就按 P 会让胜率自动选到三技能。
                for (var settle = 0; settle < 8 && purpose == BattlePurpose.Mirror && (avoidSkill3 || solo?.RemainingTurns > 0)
                    && frame.Find("battle/gear_left.png") is null && frame.Find("battle/pause_assets.png") is null; settle++)
                {
                    await s.DelayAsync(TimeSpan.FromMilliseconds(200), ct);
                    frame = await s.ObserveControlsAsync(queries, ct);
                }
                if (purpose == BattlePurpose.Mirror && solo?.RemainingTurns > 0
                    && frame.Find("battle/gear_left.png") is not null && frame.Find("battle/gear_right.png") is not null)
                {
                    if (!await DefendForSoloAsync(s, frame, queries, solo, ct)) return false;
                    unknown = 0;
                    continue;
                }
                if (purpose == BattlePurpose.Mirror && avoidSkill3 && frame.Find("battle/gear_left.png") is not null
                    && frame.Find("battle/gear_right.png") is not null)
                {
                    var stable = await StableChainAsync(s, frame, queries, ct);
                    frame = stable.Frame;
                    if (stable.Stable) path = BattleChain.Plan(frame);
                    if (frame.Find("battle/pause_assets.png") is not null || !HasTurnControls(frame)
                        && frame.Find("battle/turn_assets.png") is null) { unknown = 0; continue; }
                }
                if (path is not null)
                {
                    s.Report("battle.avoid-skill3", "链接战优先使用一、二技能");
                    await s.DragPathAsync(frame, path, TimeSpan.FromMilliseconds(100 * (path.Count - 1)), "battle.chain-skills", ct);
                    frame = await s.ObserveControlsAsync(queries, ct);
                    if (frame.Find("battle/pause_assets.png") is not null) { unknown = 0; continue; }
                    if (!HasTurnControls(frame) && frame.Find("battle/gear_right.png") is null) { unknown = 0; continue; }
                    await s.KeyAsync(frame, GameKey.Enter, "battle.chain-commit", ct);
                    // 与旧版一致等待 3 秒；过早判定未开战会按 P 覆盖链接选好的技能。
                    await s.DelayAsync(TimeSpan.FromSeconds(3), ct);
                    frame = await s.ObserveControlsAsync(turnFeedbackQueries, ct);
                    if (frame.Find("battle/pause_assets.png") is not null) { unknown = 0; continue; }
                    if (!HasTurnControls(frame) && frame.Find("battle/gear_right.png") is null) { unknown = 0; continue; }
                }
                await s.KeyAsync(frame, GameKey.P, "battle.win-rate", ct);
                await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                frame = await s.ObserveControlsAsync(queries, ct);
                if (!HasTurnControls(frame) && frame.Find("battle/turn_assets.png") is null
                    && frame.Find("battle/gear_right.png") is null) continue;
                await s.KeyAsync(frame, GameKey.Enter, "battle.commit-turn", ct);
                await s.DelayAsync(TimeSpan.FromSeconds(1), ct);
                frame = await s.ObserveControlsAsync(turnFeedbackQueries, ct);
                mouseRate = frame.Find("battle/pause_assets.png") is null;
                if (mouseRate && frame.Find("battle/win_rate_card.png") is { } rate)
                {
                    await s.ClickAsync(frame, new(rate.Center.X + (int)(50 * frame.Scale), rate.Center.Y - (int)(50 * frame.Scale)),
                        "battle.mouse-win-rate", ct);
                    frame = await s.ObserveControlsAsync(queries, ct);
                    if (frame.Find("battle/gear_right.png") is { } gear)
                        await s.ClickAsync(frame, gear.Center, "battle.mouse-commit", ct);
                }
                unknown = 0;
                continue;
            }
            if (frame.Find("battle/continue_assets.png") is { } resume)
            {
                s.Report("battle.resume", "继续暂停的战斗");
                await s.ClickAsync(frame, resume.Center, "battle.resume", ct);
                continue;
            }
            if (++unknown > 16)
            {
                s.Report("battle.unconfirmed", "未确认战斗结果，停止任务");
                return false;
            }
            await s.DelayAsync(TimeSpan.FromSeconds(Math.Min(3, 1.5 + unknown * 0.1)), ct);
        }
        s.Report("battle.timeout", "战斗等待超时");
        return false;
    }

    private static bool HasTurnControls(GameFrame frame) => frame.Find("battle/more_information_assets.png") is not null
        || frame.Find("battle/win_rate_assets.png") is not null && frame.Find("battle/turn_assets.png") is not null;

    private static async Task<bool> DefendForSoloAsync(IGameSession s, GameFrame frame,
        IReadOnlyList<ImageQuery> queries, SoloDefenseState solo, CancellationToken ct)
    {
        var stable = await StableChainAsync(s, frame, queries, ct);
        frame = stable.Frame;
        if (!stable.Stable || frame.Find("battle/gear_left.png") is not { } left
            || frame.Find("battle/gear_right.png") is not { } right)
        {
            s.Report("battle.solo.unconfirmed", "未确认防御技能位置，停止战斗");
            return false;
        }
        var scale = frame.Scale;
        var count = (int)((right.Center.X - left.Center.X - 200 * scale) / (145 * scale));
        if (count is < 1 or > 12) return false;
        var skills = Enumerable.Range(0, count).Select(index => new PixelPoint(
            (int)Math.Round(left.Center.X + (220 - 4.5 * count + 161 * index) * scale),
            (int)Math.Round(left.Center.Y + 250 * scale))).ToArray();
        var path = new[] { left.Center }.Concat(skills).Append(new PixelPoint(
            (int)Math.Round(right.Center.X + 5 * count * scale),
            (int)Math.Round(right.Center.Y + 150 * scale))).ToArray();
        if (path.Any(point => point.X < 0 || point.X >= frame.Identity.Width || point.Y < 0 || point.Y >= frame.Identity.Height)) return false;
        s.Report("battle.solo.defense", $"小指良单通：剩余 {solo.RemainingTurns} 个防御回合");
        foreach (var skill in skills)
        {
            await s.ClickAsync(frame, skill, "battle.solo.select-defense", ct);
            frame = await s.ObserveControlsAsync(queries, ct);
            if (frame.Find("battle/gear_left.png") is null || frame.Find("battle/gear_right.png") is null) return false;
        }
        await s.DragPathAsync(frame, path, TimeSpan.FromMilliseconds(100 * (path.Length - 1)), "battle.solo.chain-defense", ct);
        frame = await s.ObserveControlsAsync(queries, ct);
        if (frame.Find("battle/pause_assets.png") is null && HasTurnControls(frame))
        {
            await s.KeyAsync(frame, GameKey.Enter, "battle.solo.commit", ct);
            await s.DelayAsync(TimeSpan.FromSeconds(2), ct);
            frame = await s.ObserveControlsAsync(queries, ct);
        }
        if (frame.Find("battle/pause_assets.png") is null)
        {
            s.Report("battle.solo.unconfirmed", "防御回合未确认开始，停止战斗");
            return false;
        }
        solo.ConsumeTurn();
        return true;
    }

    private static async Task<(GameFrame Frame, bool Stable)> StableChainAsync(IGameSession s, GameFrame frame,
        IReadOnlyList<ImageQuery> queries, CancellationToken ct)
    {
        for (var attempt = 0; attempt < 4; attempt++)
        {
            var left = frame.Find("battle/gear_left.png")?.Center;
            var right = frame.Find("battle/gear_right.png")?.Center;
            await s.DelayAsync(TimeSpan.FromMilliseconds(200), ct);
            frame = await s.ObserveControlsAsync(queries, ct);
            if (left is { } l && right is { } r && frame.Find("battle/gear_left.png") is { } nextLeft
                && frame.Find("battle/gear_right.png") is { } nextRight
                && Math.Abs(l.X - nextLeft.Center.X) <= 4 * frame.Scale && Math.Abs(l.Y - nextLeft.Center.Y) <= 4 * frame.Scale
                && Math.Abs(r.X - nextRight.Center.X) <= 4 * frame.Scale && Math.Abs(r.Y - nextRight.Center.Y) <= 4 * frame.Scale)
                return (frame, true);
        }
        return (frame, false);
    }

    private static async Task<bool> StartAsync(IGameSession s, CancellationToken ct)
    {
        var clicked = false;
        for (var attempt = 0; attempt <= 15; attempt++)
        {
            var search = attempt > 10 ? SearchMode.Aggressive : attempt > 5 ? SearchMode.Normal : SearchMode.Clam;
            var frame = await s.ObserveAsync(StartQueries.Select(query => query with { Search = search }).ToArray(), ct);
            var button = frame.Find(StartQueries[0].Asset) ?? frame.Find(StartQueries[1].Asset);
            if (button is null)
            {
                if (clicked) return true;
                await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                continue;
            }
            if (clicked)
            {
                frame = await s.ObserveAsync(ExcessQueries, ct);
                button = frame.Find(StartQueries[0].Asset) ?? frame.Find(StartQueries[1].Asset);
                if (button is null) return true;
                await RemoveExcessAsync(s, frame, button, ct);
                frame = await s.ObserveAsync(StartQueries, ct);
                button = frame.Find(StartQueries[0].Asset) ?? frame.Find(StartQueries[1].Asset);
                if (button is null) return true;
            }
            await s.ClickAsync(frame, button.Center, "battle.start", ct);
            clicked = true;
            await s.DelayAsync(TimeSpan.FromSeconds(2), ct);
        }
        s.Report("battle.start-failed", "无法从编队页面进入战斗");
        return false;
    }

    private static async Task RemoveExcessAsync(IGameSession s, GameFrame frame, VisualTarget button, CancellationToken ct)
    {
        var shifted = button.Bounds with { Y = button.Bounds.Y - (int)(115 * frame.Scale) };
        var entries = await s.ReadTextAsync(frame, ct, shifted, 2);
        var match = Regex.Match(string.Join("", entries.Select(entry => entry.Text)), @"(\d+)\s*/\s*(\d+)");
        if (!match.Success || !int.TryParse(match.Groups[1].Value, out var current) || !int.TryParse(match.Groups[2].Value, out var maximum)
            || current <= maximum || maximum < 1 || current > 12) return;
        s.Report("team.remove-excess", "移除超出出战上限的罪人");
        var selected = frame.FindAll("teams/selected.png").ToArray();
        foreach (var sinner in selected)
        {
            frame = await s.ObserveAsync(StartQueries, ct);
            var region = new PixelRect(sinner.Center.X - (int)(40 * frame.Scale), sinner.Center.Y - (int)(120 * frame.Scale),
                (int)(80 * frame.Scale), (int)(90 * frame.Scale));
            var orderText = await s.ReadTextAsync(frame, ct, region, 2);
            var value = string.Join("", orderText.Select(entry => entry.Text)).Trim().Replace("G", "6");
            if (int.TryParse(value, out var order) && order > maximum)
            {
                await s.ClickAsync(frame, sinner.Center, "team.deselect-excess", ct);
            }
        }
    }

    public static PixelPoint? SettlementConfirmation(IReadOnlyList<RecognizedText> entries)
    {
        var combined = Normalize(string.Join("", entries.Select(entry => entry.Text)));
        if (!combined.Contains("战斗胜利") && !combined.Contains("battlevictory")) return null;
        var confirmation = entries.FirstOrDefault(entry => Normalize(entry.Text).Contains("确认") || Normalize(entry.Text).Contains("confirm"));
        return confirmation is null ? null : new(confirmation.Bounds.X + confirmation.Bounds.Width / 2,
            confirmation.Bounds.Y + confirmation.Bounds.Height / 2);
    }

    private static string Normalize(string text) => Regex.Replace(text, @"\s+", "").ToLowerInvariant();
}
