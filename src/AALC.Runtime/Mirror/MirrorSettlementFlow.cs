using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;

namespace AALC.Runtime.Mirror;

public sealed record MirrorSettlementResult(bool Cleared, bool Claimed, string Reason);

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

    public static async Task<MirrorSettlementResult> RunAsync(IGameSession s, MirrorOptions options, CancellationToken ct)
    {
        var cleared = false;
        var opened = false;
        var submitted = false;
        var acknowledged = false;
        int? previousWeeklyCount = null;
        var waitingWeekly = 0;
        for (var attempt = 0; attempt < 65; attempt++)
        {
            var frame = await s.ObserveAsync(Queries, ct);
            if (frame.Find(Complete) is not null || frame.Find(Clear) is not null) cleared = true;
            if (await MirrorEntryFlow.ClickFirstAsync(s, frame, ["base/leave_up_confirm_assets.png", "base/leave_up_assets.png"],
                "mirror.settlement.upgrade", ct)) continue;
            if (cleared && !options.ClaimRewards)
            {
                s.Report("mirror.settlement.pending", "镜牢已通关，结算奖励保留待领取");
                return new(true, false, "已通关，结算奖励待领取");
            }
            if (frame.Find("home/drive_assets.png") is not null || frame.Find("mirror/road_to_mir/enter_mirror_assets.png") is not null)
                return new(cleared, cleared && submitted && acknowledged, "奖励确认后返回镜牢入口");
            if (submitted && await MirrorEntryFlow.ClickFirstAsync(s, frame,
                [Root + "claim_rewards_confirm_assets.png", Root + "rewards_acquired_assets.png", "battle/battle_finish_confirm_assets.png"],
                "mirror.settlement.acknowledge", ct))
            {
                acknowledged = true;
                await s.DelayAsync(TimeSpan.FromMilliseconds(400), ct);
                continue;
            }
            if (cleared && !submitted && frame.Find(UseModules) is { } use)
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
                await s.ClickAsync(frame, use.Center, "mirror.settlement.use-modules", ct);
                submitted = true;
            }
            else if (cleared && !opened && !submitted && frame.Find(Claim) is { } claim)
            {
                await s.ClickAsync(frame, claim.Center, "mirror.settlement.open", ct);
                opened = true;
            }
            await s.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
        }
        return new(cleared, false, submitted ? "奖励已提交，尚未确认领取完成" : "未能确认镜牢通关结算");
    }
}
