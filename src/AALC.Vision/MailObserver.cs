using AALC.Runtime;
using AALC.Core.Features.Mail;
using AALC.Runtime.Mail;
using OpenCvSharp;

namespace AALC.Vision;

public sealed class MailObserver(IScreenCapture capture, TemplateMatcher matcher, string? recordingDirectory = null) : IMailObserver
{
    private readonly string? recordingPath = recordingDirectory is null ? null : EvidencePaths.RequireExternalPath(recordingDirectory);
    public static readonly IReadOnlyDictionary<MailControl, string> Assets = new Dictionary<MailControl, string>
    {
        [MailControl.HomeMail] = "home/mail_assets.png",
        [MailControl.ClaimAll] = "mail/claim_all_assets.png",
        [MailControl.Confirm] = "mail/get_mail_prize_confirm.png",
        [MailControl.Close] = "mail/close_assets.png"
    };
    public event Action<PixelFrame>? FrameCaptured;
    public async ValueTask<MailObservation> ObserveAsync(CancellationToken cancellationToken)
    {
        var frame = await capture.CaptureAsync(cancellationToken);
        cancellationToken.ThrowIfCancellationRequested();
        using var gray = TemplateMatcher.Gray(frame);
        if (recordingPath is not null)
        {
            var directory = EvidencePaths.RequireExternalPath(recordingPath);
            Directory.CreateDirectory(directory);
            Cv2.ImWrite(EvidencePaths.RequireExternalPath(Path.Combine(directory, $"frame-{frame.Identity.Id:D4}.png")), gray);
        }
        FrameCaptured?.Invoke(frame);
        var hits = new List<TemplateHit>();
        foreach (var (control, key) in Assets)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var result = matcher.Match(gray, key);
            if (result.Center is { } center && double.IsFinite(result.Score) && result.Score >= 0.8)
                hits.Add(new(control, center, result.Score, result.Path));
        }
        return new(frame.Identity, hits);
    }
}

