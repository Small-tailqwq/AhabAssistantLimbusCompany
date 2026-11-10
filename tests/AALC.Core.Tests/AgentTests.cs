using System.Text.Json;
using Xunit;
using AALC.Runtime.Agent;
using AALC.Runtime.Configuration;

namespace AALC.Core.Tests;

public class AgentTests
{
    [Fact]
    public void PartialConfigurationUpdatePreservesUnmentionedValues()
    {
        var settings = new DesktopSettings(Daily: new() { ExpCount = 7, BuyStamina = false },
            Launch: new(Daily: false, Harvest: true));
        var updated = AgentConfiguration.Patch(settings, JsonSerializer.SerializeToElement(new { Daily = new { ThreadCount = 4 } }));
        Assert.Equal(7, updated.Daily!.ExpCount);
        Assert.Equal(4, updated.Daily.ThreadCount);
        Assert.False(updated.Daily.BuyStamina);
        Assert.Equal(settings.Launch, updated.Launch);
        Assert.Equal(3, settings.Daily!.ThreadCount);
        Assert.NotEqual(AgentConfiguration.Revision(settings), AgentConfiguration.Revision(updated));
    }

    [Theory]
    [InlineData("{\"Daliy\":{\"ExpCount\":1}}")]
    [InlineData("{\"Daily\":{\"ExpConut\":1}}")]
    public void UnknownConfigurationFieldsAreRejected(string patch) => Assert.Throws<JsonException>(() =>
        AgentConfiguration.Patch(new(), JsonDocument.Parse(patch).RootElement));

    [Theory]
    [InlineData("{\"Daily\":{\"ExpCount\":-1}}")]
    [InlineData("{\"Mirror\":{\"Runs\":0}}")]
    [InlineData("{\"GameLanguage\":\"unknown\"}")]
    public void InvalidConfigurationIsRejected(string patch) => Assert.Throws<ArgumentException>(() =>
        AgentConfiguration.Patch(new(), JsonDocument.Parse(patch).RootElement));

    [Fact]
    public async Task PipeCanHandleRepeatedClientsAndRecoverFromToolFailure()
    {
        var profile = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"));
        using var server = new AgentPipeServer(profile, (request, _) => request.Operation == "fail"
            ? throw new InvalidOperationException("expected failure")
            : Task.FromResult<object>(new { operation = request.Operation }));
        Assert.Equal("first", (await AgentPipe.CallAsync(profile, "first", new { }, CancellationToken.None)).GetProperty("operation").GetString());
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() => AgentPipe.CallAsync(profile, "fail", new { }, CancellationToken.None));
        Assert.Equal("expected failure", exception.Message);
        Assert.Equal("second", (await AgentPipe.CallAsync(profile, "second", new { }, CancellationToken.None)).GetProperty("operation").GetString());
        Assert.Throws<UnauthorizedAccessException>(() => new AgentPipeServer(profile, (_, _) => Task.FromResult<object>(new { })));
        server.Dispose();
        await server.Completion.WaitAsync(TimeSpan.FromSeconds(2));
    }

    [Fact]
    public async Task SlowRequestDoesNotBlockStatusOrStop()
    {
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var profile = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"));
        using var server = new AgentPipeServer(profile, async (request, ct) =>
        {
            if (request.Operation == "slow") { entered.SetResult(); await release.Task.WaitAsync(ct); }
            return new { operation = request.Operation };
        });
        var slow = AgentPipe.CallAsync(profile, "slow", new { }, CancellationToken.None);
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(2));
        var status = await AgentPipe.CallAsync(profile, "status", new { }, CancellationToken.None).WaitAsync(TimeSpan.FromSeconds(2));
        Assert.Equal("status", status.GetProperty("operation").GetString());
        release.SetResult();
        await slow.WaitAsync(TimeSpan.FromSeconds(2));
    }

    [Fact]
    public async Task PipeRejectsOversizedMessageBeforeAllocation()
    {
        using var stream = new MemoryStream(BitConverter.GetBytes(AgentPipe.MaxMessageBytes + 1));
        await Assert.ThrowsAsync<InvalidDataException>(() => AgentPipe.ReadAsync<AgentRequest>(stream, CancellationToken.None));
    }
}
