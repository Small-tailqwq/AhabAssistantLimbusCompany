namespace AALC.Core.Features.Mail;

public enum MailControl { HomeMail, ClaimAll, Confirm, Close }
public enum MailStage { Locate, Opening, Claiming, Confirming, Closing, Completed }
public enum DecisionKind { Wait, Click, Complete }
public sealed record TemplateHit(MailControl Control, PixelPoint Center, double Score, string Asset);
public sealed record MailObservation(FrameIdentity Frame, IReadOnlyList<TemplateHit> Hits)
{
    public TemplateHit? Find(MailControl control) =>
        Hits.FirstOrDefault(hit => hit.Control == control && double.IsFinite(hit.Score) && hit.Score >= 0.8);
}
public sealed record MailState(MailStage Stage = MailStage.Locate, int ClaimWaitFrames = 0);
public sealed record MailDecision(DecisionKind Kind, MailState Next, string Rule, TemplateHit? Target = null);

public static class MailFlow
{
    public static MailDecision Decide(MailState state, MailObservation observation)
    {
        var confirm = observation.Find(MailControl.Confirm);
        var claim = observation.Find(MailControl.ClaimAll);
        var close = observation.Find(MailControl.Close);
        var home = observation.Find(MailControl.HomeMail);
        if (state.Stage == MailStage.Closing)
        {
            if (home is not null && close is null && confirm is null && claim is null)
                return new(DecisionKind.Complete, new(MailStage.Completed), "mail.returned-home");
            return Wait(state, "mail.wait-home");
        }
        if (state.Stage == MailStage.Confirming)
        {
            if (confirm is null && close is not null)
                return Click(close, new(MailStage.Closing), "mail.close-after-confirm");
            return Wait(state, "mail.wait-confirm-dismissal");
        }
        if (confirm is not null)
            return Click(confirm, new(MailStage.Confirming), "mail.confirm-rewards");
        if (state.Stage == MailStage.Claiming)
        {
            var next = state with { ClaimWaitFrames = claim is not null && close is not null ? state.ClaimWaitFrames + 1 : 0 };
            // 连续两次新观察仍有领取和关闭按钮，沿用空邮箱处理；未知帧不算空邮箱证据。
            if (close is not null && (claim is null || next.ClaimWaitFrames >= 2))
                return Click(close, new(MailStage.Closing), "mail.close-without-confirm");
            return Wait(next, "mail.wait-claim-result");
        }
        if (claim is not null)
            return Click(claim, new(MailStage.Claiming), "mail.claim-all");
        if (state.Stage == MailStage.Locate && home is not null && close is null)
            return Click(home, new(MailStage.Opening), "mail.open");
        return Wait(state, "mail.wait-recognized-state");
    }

    private static MailDecision Click(TemplateHit hit, MailState next, string rule) =>
        new(DecisionKind.Click, next, rule, hit);
    private static MailDecision Wait(MailState state, string rule) => new(DecisionKind.Wait, state, rule);
}

