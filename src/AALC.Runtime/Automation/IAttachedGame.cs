using AALC.Runtime.Mail;

namespace AALC.Runtime.Automation;

public interface IAttachedGame : IScreenCapture, IMailInput, IDisposable
{
    Task EnsureResolutionAsync(Action<string> report, CancellationToken cancellationToken);
}
