using AALC.Runtime.Automation;
using AALC.Core.Features.Daily;
using AALC.Runtime.Mail;

namespace AALC.Runtime.Daily;

public sealed class DailyRunner(IGameSession session, Func<CancellationToken, Task<RunResult>> runMail)
{
    public static TimeSpan TimeoutFor(DailyOptions options)
    {
        DailyPlan.Validate(options);
        var batches = options.RunLuxcavation
            ? DailyPlan.Batches(options.ExpCount, options.UseContinuousCombat, options.MaxContinuousCombat)
                .Concat(DailyPlan.Batches(options.ThreadCount, options.UseContinuousCombat, options.MaxContinuousCombat))
            : [];
        return TimeSpan.FromSeconds(240 + batches.Sum(count => 960.0 + 300.0 * count)
            + (options.ClaimRewards ? 240 : 0) + (options.BuyStamina ? 540 : 0));
    }

    public async Task<RunResult> RunAsync(DailyOptions options, CancellationToken ct)
    {
        var mailObservations = 0;
        RunResult Finish(RunOutcome outcome, string reason)
        {
            session.Report("daily.run." + outcome.ToString().ToLowerInvariant(), reason);
            return new(outcome, reason, session.Observations + mailObservations, session.Elapsed.TotalMilliseconds);
        }
        try
        {
            DailyPlan.Validate(options);
            ct.ThrowIfCancellationRequested();
            if (!await DailyNavigation.ReturnHomeAsync(session, ct)) return Finish(RunOutcome.Failed, "无法返回游戏主界面");
            if (options.ConvertModules && !await EnkephalinFlow.ConvertAsync(session, ct))
                return Finish(RunOutcome.Failed, "体力转换模块失败");
            if (options.RunLuxcavation)
            {
                foreach (var (kind, count) in new[] { (LuxcavationKind.Experience, options.ExpCount), (LuxcavationKind.Thread, options.ThreadCount) })
                {
                    var team = DailyPlan.TeamFor(options, kind, DateTimeOffset.UtcNow);
                    foreach (var batch in DailyPlan.Batches(count, options.UseContinuousCombat, options.MaxContinuousCombat))
                        if (!await LuxcavationFlow.RunAsync(session, kind, batch, team, options, ct))
                            return Finish(RunOutcome.Failed, $"{(kind == LuxcavationKind.Experience ? "经验" : "纺锤")}采光未完成");
                    if (count > 0 && (!await DailyNavigation.ReturnHomeAsync(session, ct)
                        || options.ConvertModules && !await EnkephalinFlow.ConvertAsync(session, ct)))
                        return Finish(RunOutcome.Failed, "采光结束后的返回主页或模块转换失败");
                }
            }
            if (options.ClaimRewards)
            {
                if (options.ClaimMail)
                {
                    session.Report("daily.mail.begin", "领取邮件奖励");
                    var mail = await runMail(ct);
                    mailObservations += mail.Observations;
                    if (mail.Outcome != RunOutcome.Completed) return Finish(mail.Outcome, "领取邮件未完成：" + mail.Reason);
                }
                if ((options.ClaimMissions || options.ClaimSeasonMissions || options.ClaimPassLevels)
                    && !await PassRewardFlow.RunAsync(session, options.ClaimMissions, options.ClaimPassLevels,
                        options.ClaimSeasonMissions, ct))
                    return Finish(RunOutcome.Failed, "通行证奖励领取未完成");
            }
            if (options.BuyStamina)
            {
                if (!await DailyNavigation.ReturnHomeAsync(session, ct)) return Finish(RunOutcome.Failed, "狂气兑换前未返回主界面");
                if (!await EnkephalinFlow.RefillAsync(session, options.RefillTier, options.GrandetMode, ct))
                    return Finish(RunOutcome.Failed, "狂气体力兑换未完成");
            }
            if (!await DailyNavigation.ReturnHomeAsync(session, ct)) return Finish(RunOutcome.Failed, "任务结束后未确认主界面");
            ct.ThrowIfCancellationRequested();
            return Finish(RunOutcome.Completed, "日常任务已完成");
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { return Finish(RunOutcome.Cancelled, "已停止日常任务"); }
        catch (Exception exception)
        {
            session.Report("daily.run.error", exception.ToString());
            return Finish(RunOutcome.Failed, exception.Message);
        }
    }
}
