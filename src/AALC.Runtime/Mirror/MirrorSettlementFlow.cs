using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;

namespace AALC.Runtime.Mirror;

public sealed record MirrorSettlementResult(bool Cleared, bool Claimed, string Reason);

/// <summary>一轮镜牢结算的进度。由运行器按轮持有，跨越重启、拒绝输入和瞬时错误，
/// 使已提交的模块不会再次提交，已确认的回执不会因重新入口而多开一轮。</summary>
public sealed class MirrorSettlementProgress
{
    public bool Cleared { get; set; }
    /// <summary>使用模块的点击已开始发送；点击中途出错时可能已生效，只能经结算页或人工核对接续。</summary>
    public bool SubmitStarted { get; set; }
    public bool Submitted { get; set; }
    public bool Acknowledged { get; set; }
}

public static class MirrorSettlementFlow
{
    private const string Root = "mirror/claim_reward/";
    public const string Complete = Root + "complete_mirror_100%_assets.png";
    public const string Clear = Root + "clear_assets.png";
    public const string Claim = Root + "claim_rewards_assets.png";
    public const string UseModules = Root + "use_enkephalin_assets.png";
    public const string Weekly = Root + "weekly_bonuses.png";
    public static readonly ImageQuery[] Queries = [new(Complete), new(Clear), new(Claim), new(UseModules),
        new(Weekly, Multiple: true), new(Root + "claim_rewards_confirm_assets.png", .75),
        new(Root + "rewards_acquired_assets.png"), new("battle/battle_finish_confirm_assets.png"),
        new("home/drive_assets.png"), new("mirror/road_to_mir/enter_mirror_assets.png", .78),
        new("base/leave_up_assets.png"), new("base/leave_up_confirm_assets.png")];

    private const int MaxOpenClicks = 3;
    private static readonly TimeSpan OpenRetryDelay = TimeSpan.FromSeconds(3);

    public static Task<MirrorSettlementResult> RunAsync(IGameSession s, MirrorOptions options, CancellationToken ct) =>
        RunAsync(s, options, new MirrorSettlementProgress(), ct);

    public static async Task<MirrorSettlementResult> RunAsync(IGameSession s, MirrorOptions options,
        MirrorSettlementProgress progress, CancellationToken ct)
    {
        var openClicks = 0;
        var nextOpenClick = TimeSpan.Zero;
        int? previousWeeklyCount = null;
        var waitingWeekly = 0;
        for (var attempt = 0; attempt < 65; attempt++)
        {
            var frame = await s.ObserveAsync(Queries, ct);
            if (frame.Find(Complete) is not null || frame.Find(Clear) is not null) progress.Cleared = true;
            if (await MirrorEntryFlow.ClickFirstAsync(s, frame, ["base/leave_up_confirm_assets.png", "base/leave_up_assets.png"],
                "mirror.settlement.upgrade", ct)) continue;
            if (progress.Cleared && !options.ClaimRewards)
            {
                s.Report("mirror.settlement.pending", "镜牢已通关，结算奖励保留待领取");
                return new(true, false, "已通关，结算奖励待领取");
            }
            if (frame.Find("home/drive_assets.png") is not null || frame.Find("mirror/road_to_mir/enter_mirror_assets.png") is not null)
                return new(progress.Cleared, progress.Cleared && progress.Submitted && progress.Acknowledged, "奖励确认后返回镜牢入口");
            if (progress.SubmitStarted && await MirrorEntryFlow.ClickFirstAsync(s, frame,
                [Root + "claim_rewards_confirm_assets.png", Root + "rewards_acquired_assets.png", "battle/battle_finish_confirm_assets.png"],
                "mirror.settlement.acknowledge", ct))
            {
                // 出现回执说明模块已支付，即使提交点击本身未确认。
                progress.Submitted = progress.Acknowledged = true;
                await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
                continue;
            }
            if (progress.Cleared && !progress.Submitted && frame.Find(UseModules) is { } use)
            {
                var bonuses = frame.FindAll(Weekly).OrderBy(hit => hit.Center.X).ToArray();
                if (previousWeeklyCount is { } previous && bonuses.Length >= previous)
                {
                    if (++waitingWeekly >= 8) return new(true, false, "周奖励选择未发生变化");
                    await s.DelayAsync(TimeSpan.FromMilliseconds(300), ct);
                    continue;
                }
                previousWeeklyCount = null;
                waitingWeekly = 0;
                var desired = options.WeeklyBonus switch { MirrorWeeklyBonus.None => 0, MirrorWeeklyBonus.One => 1, _ => bonuses.Length };
                if (bonuses.Length > desired)
                {
                    previousWeeklyCount = bonuses.Length;
                    await s.ClickAsync(frame, bonuses[^1].Center, "mirror.settlement.weekly-bonus", ct);
                    continue;
                }
                s.Report("mirror.settlement.spend-modules", "领取本轮镜牢结算奖励");
                // 发送前记下已开始：点击抛出时可能已生效，运行器须回到结算页而不是重新入口。
                // 发送成功才记为已提交；重新观察时按钮仍在，说明模块尚未支付，可再点一次。
                progress.SubmitStarted = true;
                await s.ClickAsync(frame, use.Center, "mirror.settlement.use-modules", ct);
                progress.Submitted = true;
            }
            else if (progress.Cleared && !progress.Submitted && openClicks < MaxOpenClicks && s.Elapsed >= nextOpenClick
                && frame.Find(Claim) is { } claim)
            {
                // 打开领取面板不消耗资源；面板未出现时冷却后重点，避免一次点击丢失后空转到上限。
                await s.ClickAsync(frame, claim.Center, "mirror.settlement.open", ct);
                openClicks++;
                nextOpenClick = s.Elapsed + OpenRetryDelay;
            }
            await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
        }
        return new(progress.Cleared, false, progress.SubmitStarted ? "奖励已提交，尚未确认领取完成" : "未能确认镜牢通关结算");
    }
}
