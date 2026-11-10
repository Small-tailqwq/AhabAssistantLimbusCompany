using AALC.Core.Features.Mail;

namespace AALC.Runtime.Mail;

public sealed record PixelFrame(FrameIdentity Identity, byte[] Bgra);
public interface IScreenCapture
{
    ValueTask<PixelFrame> CaptureAsync(CancellationToken cancellationToken);
}
public interface IMailObserver
{
    ValueTask<MailObservation> ObserveAsync(CancellationToken cancellationToken);
}
public interface IMailInput
{
    ValueTask ClickAsync(TemplateHit target, FrameIdentity frame, CancellationToken cancellationToken);
}
public interface IRunClock
{
    TimeSpan Elapsed { get; }
    ValueTask DelayAsync(TimeSpan delay, CancellationToken cancellationToken);
}
public enum RunOutcome { Completed, Cancelled, Failed }
public sealed record RunEvent(string RunId, long FrameId, string Stage, string Rule, string Action,
    string? Target, double ElapsedMilliseconds, string? Detail = null);
public sealed record RunResult(RunOutcome Outcome, string Reason, int Observations, double ElapsedMilliseconds);

