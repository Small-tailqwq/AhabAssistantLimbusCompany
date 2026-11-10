using AALC.Mcp;
using AALC.Runtime;

using var cancellation = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; cancellation.Cancel(); };
try
{
    var root = RepositoryPaths.Discover(Environment.CurrentDirectory) ?? RepositoryPaths.Discover(AppContext.BaseDirectory);
    return await McpCommands.RunAsync(["mcp", .. args], root, cancellation.Token);
}
catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { return 0; }
catch (Exception exception) { Console.Error.WriteLine(exception.Message); return 1; }
