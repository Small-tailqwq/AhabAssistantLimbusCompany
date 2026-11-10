using AALC.Runtime.Automation;

namespace AALC.Runtime.Mirror;

public static class MirrorEventFlow
{
    public static bool HasEventPageEvidence(GameFrame frame) => frame.Targets.Any(target =>
        IsPageControl(target.Asset));

    private static bool IsPageControl(string asset) => asset.StartsWith("event/", StringComparison.Ordinal)
        && asset is not ("event/very_high.png" or "event/high.png" or "event/normal.png"
            or "event/low.png" or "event/very_low.png");

    public static readonly ImageQuery[] Queries = [.. BattleEvents.Queries,
        new("event/commence_battle_assets.png"), new("event/unknown_event.png"),
        new("event/select_to_gain_ego.png", .75, true), new("event/advantage_check.png"),
        new("event/gain_a_ego_depending_on_result.png"), new(MirrorThemeFlow.Map), new("battle/turn_assets.png"),
        new("teams/identify_assets.png"), new("battle/normal_to_battle_assets.png"), new("battle/chaim_to_battle_assets.png"),
        new(MirrorRewardFlow.Gift, Multiple: true), new(MirrorRewardFlow.GiftBox), new(MirrorRewardFlow.GiftConfirm),
        new(MirrorRewardFlow.GiftSelect, Search: SearchMode.Normal)];

    public static readonly ImageQuery[] PageQueries = [.. Queries.Where(query => IsPageControl(query.Asset))];

    public static async Task<bool> RunAsync(IGameSession s, CancellationToken ct)
    {
        var events = new BattleEvents();
        var unknown = 0;
        s.Report("mirror.event.start", "处理镜牢事件");
        var observationWait = TimeSpan.Zero;
        while (observationWait < TimeSpan.FromSeconds(30))
        {
            ct.ThrowIfCancellationRequested();
            var nextObservationDelay = TimeSpan.FromMilliseconds(500);
            var frame = await s.ObserveAsync(Queries, ct);
            var eventVisible = HasEventPageEvidence(frame);
            var giftOverlay = frame.Find(MirrorRewardFlow.GiftConfirm) is not null || frame.Find(MirrorRewardFlow.GiftSelect) is not null
                && (frame.Find(MirrorRewardFlow.Gift) is not null || frame.Find(MirrorRewardFlow.GiftBox) is not null);
            if (giftOverlay || !eventVisible && (frame.Find(MirrorThemeFlow.Map) is not null || frame.Find("battle/turn_assets.png") is not null
                || frame.Find("teams/identify_assets.png") is not null && (frame.Find("battle/normal_to_battle_assets.png") is not null
                    || frame.Find("battle/chaim_to_battle_assets.png") is not null)
                || frame.Find(MirrorRewardFlow.Gift) is not null || frame.Find(MirrorRewardFlow.GiftBox) is not null))
            {
                s.Report("mirror.event.exited", "镜牢事件已交回地图、战斗或饰品页面");
                return true;
            }
            var preferred = frame.Find("event/unknown_event.png") ?? frame.FindAll("event/select_to_gain_ego.png")
                .OrderBy(t => t.Center.Y).ThenBy(t => t.Center.X).FirstOrDefault();
            if (preferred is not null)
            {
                await s.ClickAsync(frame, preferred.Center, "mirror.event.preferred-choice", ct);
                unknown = 0;
            }
            else if (frame.Find("event/commence_battle_assets.png") is { } battle)
            {
                await s.ClickAsync(frame, battle.Center, "mirror.event.commence-battle", ct);
                unknown = 0;
            }
            else
            {
                var quickSkip = frame.Find("event/skip_assets.png") is { Score: >= 0.9 }
                    && frame.Find("event/choices_assets.png") is null
                    && frame.Find("event/perform_the_check_feature_assets.png") is null
                    && !new[] { "event/very_high.png", "event/high.png", "event/normal.png",
                        "event/low.png", "event/very_low.png" }.Any(asset => frame.Find(asset) is not null);
                var entries = quickSkip ? [] : await s.ReadTextAsync(frame, ct);
                var result = await events.HandleAsync(s, frame, entries, ct);
                if (result.Failed) return false;
                nextObservationDelay = quickSkip ? TimeSpan.FromMilliseconds(150) : events.NextObservationDelay;
                if (result.Handled) unknown = 0;
                else if ((frame.Find("event/advantage_check.png") ?? frame.Find("event/gain_a_ego_depending_on_result.png")) is { } check)
                {
                    await s.ClickAsync(frame, check.Center, "mirror.event.check-choice", ct);
                    unknown = 0;
                }
                else if (++unknown >= 10)
                {
                    s.Report("mirror.event.unknown", "镜牢事件页面无法识别，未确认退出");
                    return false;
                }
            }
            await s.DelayAsync(nextObservationDelay, ct);
            observationWait += nextObservationDelay;
        }
        s.Report("mirror.event.timeout", "镜牢事件未推进到明确出口");
        return false;
    }
}
