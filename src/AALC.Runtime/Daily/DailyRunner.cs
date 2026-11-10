using AALC.Runtime.Automation;
using AALC.Core.Features.Daily;
using AALC.Runtime.Mail;

namespace AALC.Runtime.Daily;

public sealed class DailyRunner(IGameSession session, Func<CancellationToken, Task<RunResult>> runMail)
{
    private sealed class RunProgress
    {
        public HashSet<string> Done { get; } = [];
        public string? PendingBatch { get; set; }

        public void CompleteBatch()
        {
            if (PendingBatch is not { } batch) return;
            Done.Add(batch);
            PendingBatch = null;
        }
    }

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
        // 游戏重启后从主界面重新开始，已完成的步骤不重复执行（避免重复消耗体力）。
        var progress = new RunProgress();
        try
        {
            DailyPlan.Validate(options);
            while (true)
            {
                try
                {
                    return await RunStepsAsync(options, progress, Finish, observations => mailObservations += observations, ct);
                }
                catch (GameRestartedException exception)
                {
                    session.Report("daily.run.resume", $"{exception.Message}，游戏已重启，从未完成的步骤继续");
                }
            }
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { return Finish(RunOutcome.Cancelled, "已停止日常任务"); }
        catch (Exception exception)
        {
            session.Report("daily.run.error", exception.ToString());
            return Finish(RunOutcome.Failed, exception.Message);
        }
    }

    private async Task<RunResult> RunStepsAsync(DailyOptions options, RunProgress progress,
        Func<RunOutcome, string, RunResult> finish, Action<int> countMail, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        var done = progress.Done;
        if (!await DailyNavigation.ReturnHomeAsync(session, ct, progress.CompleteBatch))
            return finish(RunOutcome.Failed, "无法返回游戏主界面");
        if (options.ConvertModules && !done.Contains("modules"))
        {
            if (!await EnkephalinFlow.ConvertAsync(session, ct)) return finish(RunOutcome.Failed, "体力转换模块失败");
            done.Add("modules");
        }
        if (options.RunLuxcavation)
        {
            foreach (var (kind, count) in new[] { (LuxcavationKind.Experience, options.ExpCount), (LuxcavationKind.Thread, options.ThreadCount) })
            {
                if (done.Contains($"{kind}")) continue;
                var team = DailyPlan.TeamFor(options, kind, DateTimeOffset.UtcNow);
                var batches = DailyPlan.Batches(count, options.UseContinuousCombat, options.MaxContinuousCombat).ToArray();
                for (var index = 0; index < batches.Length; index++)
                {
                    if (done.Contains($"{kind}.{index}")) continue;
                    progress.PendingBatch = $"{kind}.{index}";
                    if (!await LuxcavationFlow.RunAsync(session, kind, batches[index], team, options, ct))
                        return finish(RunOutcome.Failed, $"{(kind == LuxcavationKind.Experience ? "经验" : "纺锤")}采光未完成");
                    progress.CompleteBatch();
                }
                if (count > 0 && (!await DailyNavigation.ReturnHomeAsync(session, ct)
                    || options.ConvertModules && !await EnkephalinFlow.ConvertAsync(session, ct)))
                    return finish(RunOutcome.Failed, "采光结束后的返回主页或模块转换失败");
                done.Add($"{kind}");
            }
        }
        if (options.ClaimRewards)
        {
            if (options.ClaimMail && !done.Contains("mail"))
            {
                session.Report("daily.mail.begin", "领取邮件奖励");
                var mail = await runMail(ct);
                countMail(mail.Observations);
                if (mail.Outcome != RunOutcome.Completed) return finish(mail.Outcome, "领取邮件未完成：" + mail.Reason);
                done.Add("mail");
            }
            if ((options.ClaimMissions || options.ClaimSeasonMissions || options.ClaimPassLevels) && !done.Contains("pass"))
            {
                if (!await PassRewardFlow.RunAsync(session, options.ClaimMissions, options.ClaimPassLevels, options.ClaimSeasonMissions, ct))
                    return finish(RunOutcome.Failed, "通行证奖励领取未完成");
                done.Add("pass");
            }
        }
        if (options.BuyStamina && !done.Contains("stamina"))
        {
            if (!await DailyNavigation.ReturnHomeAsync(session, ct)) return finish(RunOutcome.Failed, "狂气兑换前未返回主界面");
            if (!await EnkephalinFlow.RefillAsync(session, options.RefillTier, options.GrandetMode, ct))
                return finish(RunOutcome.Failed, "狂气体力兑换未完成");
            done.Add("stamina");
        }
        if (!await DailyNavigation.ReturnHomeAsync(session, ct)) return finish(RunOutcome.Failed, "任务结束后未确认主界面");
        ct.ThrowIfCancellationRequested();
        return finish(RunOutcome.Completed, "日常任务已完成");
    }
}
