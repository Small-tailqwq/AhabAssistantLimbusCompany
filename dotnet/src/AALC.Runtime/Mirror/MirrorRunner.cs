using System.Text.RegularExpressions;
using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;

namespace AALC.Runtime.Mirror;

public sealed class MirrorRunner(IGameSession session, IMirrorMapReader mapReader,
    Func<MirrorTeamOptions[], CancellationToken, Task>? saveQueue = null)
{
    private static readonly string[] Combat = ["battle/more_information_assets.png", "battle/turn_assets.png", "battle/pause_assets.png",
        "battle/dead_all.png", "battle/continue_assets.png", "battle/win_rate_assets.png"];
    public static readonly ImageQuery[] Queries = [.. MirrorSettlementFlow.Queries, .. MirrorRewardFlow.Queries,
        new(MirrorThemeFlow.Pack, Multiple: true), new("mirror/theme_pack/feature_theme_pack_assets.png"),
        new("mirror/shop/shop_coins_assets.png"), new("mirror/shop/leave_assets.png"), new("mirror/shop/power_up_assets.png"),
        new("mirror/shop/power_up_confirm_assets.png"), new("mirror/shop/heal_sinner/heal_sinner_return_assets.png"),
        new("mirror/shop/heal_sinner/heal_all_sinner_assets.png"), new(MirrorRouteFlow.Enter),
        new("teams/identify_assets.png"), new("battle/normal_to_battle_assets.png"), new("battle/chaim_to_battle_assets.png"),
        new("base/waiting_assets.png"), new(MirrorRewardFlow.ObserveBurn), new(MirrorRewardFlow.ObserveBleed),
        .. Combat.Select(asset => new ImageQuery(asset)), .. MirrorEventFlow.PageQueries,
        new("mirror/claim_reward/battle_statistics_assets.png")];

    public static TimeSpan TimeoutFor(MirrorOptions options)
    {
        MirrorPlan.Validate(options);
        return TimeSpan.FromHours(options.Runs * 2);
    }

    public async Task<RunResult> RunAsync(MirrorOptions options, CancellationToken ct)
    {
        RunResult Finish(RunOutcome outcome, string reason)
        {
            session.Report("mirror.run." + outcome.ToString().ToLowerInvariant(), reason);
            return new(outcome, reason, session.Observations, session.Elapsed.TotalMilliseconds);
        }
        try
        {
            MirrorPlan.Validate(options);
            var queue = options.Teams.ToArray();
            for (var run = 0; run < options.Runs; run++)
            {
                ct.ThrowIfCancellationRequested();
                var teamIndex = Array.FindIndex(queue, team => MirrorPlan.Eligible(team, options.Mode));
                if (teamIndex < 0) return Finish(RunOutcome.Failed, "队列中没有符合当前难度的队伍");
                var team = queue[teamIndex];
                session.Report("mirror.run.begin", $"第 {run + 1}/{options.Runs} 轮 · {team.Name} · 游戏队伍 {team.GameTeamNumber}");
                if (!await MirrorEntryFlow.RunAsync(session, team, ct)) return Finish(RunOutcome.Failed, "镜牢入口未完成");
                var result = await RunDungeonAsync(options, team, ct);
                if (!result.Cleared || options.ClaimRewards && !result.Claimed)
                    return Finish(RunOutcome.Failed, result.Reason);
                if (!result.Claimed) return Finish(RunOutcome.Completed, result.Reason + "；队伍队列保持当前顺序");
                queue = MirrorPlan.Rotate(queue, teamIndex);
                if (saveQueue is not null) await saveQueue(queue, ct);
                session.Report("mirror.queue.rotated", $"第 {run + 1} 轮结算完成，队伍移至队尾");
            }
            return Finish(RunOutcome.Completed, $"已完成 {options.Runs} 轮镜牢并领取结算奖励");
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { return Finish(RunOutcome.Cancelled, "已停止镜牢任务"); }
        catch (Exception exception)
        {
            session.Report("mirror.run.error", exception.ToString());
            return Finish(RunOutcome.Failed, exception.Message);
        }
    }

    private async Task<MirrorSettlementResult> RunDungeonAsync(MirrorOptions options, MirrorTeamOptions team, CancellationToken ct)
    {
        var route = new MirrorRouteFlow(session, mapReader);
        var started = session.Elapsed;
        var unknown = 0;
        var floor = 0;
        var formedFloor = -1;
        var readFloor = true;
        while (session.Elapsed - started < TimeSpan.FromHours(2))
        {
            var frame = await session.ObserveAsync(Queries, ct);
            if (frame.Find(MirrorSettlementFlow.Complete) is not null || frame.Find(MirrorSettlementFlow.Clear) is not null
                || frame.Find(MirrorSettlementFlow.Claim) is not null)
                return await MirrorSettlementFlow.RunAsync(session, options, ct);
            var rewards = await MirrorRewardFlow.HandleAsync(session, frame, team.Rewards, ct);
            if (rewards.Failed) return Failed("镜牢奖励选择未完成");
            if (rewards.Handled) { unknown = 0; continue; }
            if (frame.Find("base/waiting_assets.png") is not null)
            {
                if (++unknown > 90) return Failed("镜牢加载超时");
                await session.DelayAsync(TimeSpan.FromSeconds(1), ct);
                continue;
            }
            if (frame.Find("mirror/theme_pack/feature_theme_pack_assets.png") is not null || frame.Find(MirrorThemeFlow.Pack) is not null)
            {
                var nextFloor = ParseFloor(await session.ReadTextAsync(frame, ct, frame.Region(800, 170, 1760, 290), 2));
                if (nextFloor is null)
                {
                    if (++unknown > 12) return Failed("主题卡包楼层未识别");
                    await session.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                    continue;
                }
                if (!await MirrorThemeFlow.RunAsync(session, team.Theme with { HardMode = options.Mode == MirrorMode.Hard, Floor = nextFloor.Value }, ct))
                    return Failed("主题包选择未完成");
                floor = nextFloor.Value;
                route.ResetForFloor();
                readFloor = false;
                session.Report("mirror.floor", $"进入第 {floor} 层");
            }
            else if (frame.Find(MirrorRewardFlow.ObserveBurn) is not null || frame.Find(MirrorRewardFlow.ObserveBleed) is not null)
            {
                if (!await MirrorRewardFlow.ObserveGiftsAsync(session, team.Rewards.ObservedGifts, ct)) return Failed("观测饰品选择未完成");
            }
            else if (frame.Find("mirror/shop/shop_coins_assets.png") is not null
                || await MirrorShopFlow.IsHealingResultAsync(session, frame, ct)
                || await MirrorShopFlow.IsHealingChoicesAsync(session, frame, ct)
                || await MirrorShopFlow.EnhancementExitAsync(session, frame, ct) is not null)
            {
                if (!await MirrorShopFlow.RunAsync(session, team.Shop, team.Rewards.Keyword, floor, ct)) return Failed("商店操作未完成");
                route.NotifyShopExited();
            }
            else if (frame.Find("battle/normal_to_battle_assets.png") is not null || frame.Find("battle/chaim_to_battle_assets.png") is not null
                || frame.Find("teams/identify_assets.png") is not null)
            {
                if (formedFloor < 0 || team.ReformEachFloor && formedFloor != floor)
                {
                    if (!await MirrorFormationFlow.RunAsync(session, team.SinnerOrder, ct)) return Failed("出战顺序未确认");
                    formedFloor = floor;
                }
                if (!await BattleFlow.RunAsync(session, 1, true, ct, BattlePurpose.Mirror, team.AvoidSkill3)) return Failed("镜牢战斗未完成");
            }
            else if (IsCombatPage(frame))
            {
                if (!await BattleFlow.ContinueAsync(session, 1, true, ct, BattlePurpose.Mirror, team.AvoidSkill3)) return Failed("镜牢战斗未完成");
            }
            else if (MirrorEventFlow.HasEventPageEvidence(frame))
            {
                if (!await MirrorEventFlow.RunAsync(session, ct)) return Failed("镜牢事件未完成");
            }
            else if (frame.Find(MirrorThemeFlow.Map) is not null || frame.Find(MirrorRouteFlow.Enter) is not null)
            {
                if (readFloor)
                {
                    var observedFloor = ParseFloor(await session.ReadTextAsync(frame, ct, frame.Region(60, 168, 570, 250), 2));
                    if (observedFloor is { } current)
                    {
                        if (floor > 0 && current != floor) route.ResetForFloor();
                        floor = current;
                    }
                    readFloor = observedFloor is null;
                }
                var step = await route.AdvanceAsync(new(options.Mode == MirrorMode.Hard), ct);
                if (step.Outcome == MirrorRouteOutcome.Failed) return Failed("寻路未完成：" + step.Reason);
            }
            else
            {
                var text = await session.ReadTextAsync(frame, ct);
                if (BattleEvents.HasNarration(frame, text) || text.Any(t => t.Text.Contains("选项")
                    || t.Text.Equals("Choices", StringComparison.OrdinalIgnoreCase)))
                {
                    if (!await MirrorEventFlow.RunAsync(session, ct)) return Failed("镜牢事件未完成");
                    unknown = 0;
                    continue;
                }
                if (++unknown > 12) return Failed("镜牢当前页面无法确认，已保留最后截图");
                await session.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                continue;
            }
            unknown = 0;
        }
        return Failed("单轮镜牢超过两小时");
    }

    public static bool IsCombatPage(GameFrame frame) =>
        (frame.Find(MirrorThemeFlow.Map) is null && Combat.Any(asset => frame.Find(asset) is not null))
        || frame.Find("mirror/claim_reward/battle_statistics_assets.png") is not null;

    public static int? ParseFloor(IReadOnlyList<RecognizedText> text)
    {
        var value = string.Concat(text.Select(t => t.Text));
        var match = Regex.Match(value, @"(?:第\s*)?([1-5])\s*(?:层|F\b|st\s*Floor|nd\s*Floor|rd\s*Floor|th\s*Floor)|Floor\s*([1-5])", RegexOptions.IgnoreCase);
        if (!match.Success) return null;
        return int.Parse(match.Groups[1].Success ? match.Groups[1].Value : match.Groups[2].Value);
    }

    private static MirrorSettlementResult Failed(string reason) => new(false, false, reason);
}
