using System.Diagnostics;
using AALC.Core.Features.Mail;

namespace AALC.Runtime.Mail;

public sealed class SystemRunClock : IRunClock
{
    private readonly Stopwatch timer = Stopwatch.StartNew();
    public TimeSpan Elapsed => timer.Elapsed;
    public ValueTask DelayAsync(TimeSpan delay, CancellationToken cancellationToken) =>
        new(Task.Delay(delay, cancellationToken));
}

public sealed class MailRunner(IMailObserver observer, IMailInput input, IRunClock clock)
{
    public async Task<RunResult> RunAsync(TimeSpan timeout, Action<RunEvent> publish, CancellationToken cancellationToken)
    {
        if (timeout <= TimeSpan.Zero) throw new ArgumentOutOfRangeException(nameof(timeout));
        var runId = Guid.NewGuid().ToString("N");
        var state = new MailState();
        var beginning = clock.Elapsed;
        var observations = 0;
        long lastFrame = 0;
        double elapsed() => (clock.Elapsed - beginning).TotalMilliseconds;
        RunResult finish(RunOutcome outcome, string reason)
        {
            publish(new(runId, lastFrame, state.Stage.ToString(), reason, outcome.ToString(), null, elapsed()));
            return new(outcome, reason, observations, elapsed());
        }
        try
        {
            while (clock.Elapsed - beginning < timeout)
            {
                cancellationToken.ThrowIfCancellationRequested();
                var observation = await observer.ObserveAsync(cancellationToken);
                if (observation.Frame.Id <= lastFrame)
                    return finish(RunOutcome.Failed, "mail.stale-frame");
                lastFrame = observation.Frame.Id;
                observations++;
                cancellationToken.ThrowIfCancellationRequested();
                if (clock.Elapsed - beginning >= timeout)
                    return finish(RunOutcome.Failed, "mail.timeout");
                var decision = MailFlow.Decide(state, observation);
                publish(new(runId, lastFrame, state.Stage.ToString(), decision.Rule, decision.Kind.ToString(),
                    decision.Target?.Control.ToString(), elapsed()));
                if (decision.Kind == DecisionKind.Complete)
                    return finish(RunOutcome.Completed, decision.Rule);
                if (decision.Kind == DecisionKind.Click)
                {
                    cancellationToken.ThrowIfCancellationRequested();
                    if (clock.Elapsed - beginning >= timeout)
                        return finish(RunOutcome.Failed, "mail.timeout");
                    await input.ClickAsync(decision.Target!, observation.Frame, cancellationToken);
                    publish(new(runId, lastFrame, state.Stage.ToString(), decision.Rule, "Sent",
                        decision.Target!.Control.ToString(), elapsed()));
                }
                state = decision.Next;
                await clock.DelayAsync(TimeSpan.FromMilliseconds(500), cancellationToken);
            }
            return finish(RunOutcome.Failed, "mail.timeout");
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            return finish(RunOutcome.Cancelled, "mail.cancelled");
        }
        catch (Exception exception)
        {
            publish(new(runId, lastFrame, state.Stage.ToString(), "mail.error", "Error", null, elapsed(), exception.ToString()));
            return finish(RunOutcome.Failed, exception.Message);
        }
    }
}

