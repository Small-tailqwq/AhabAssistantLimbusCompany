using System.ComponentModel;
using System.Diagnostics;
using System.Text.Json;
using AALC.Runtime;
using AALC.Runtime.Agent;
using AALC.Runtime.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using ModelContextProtocol;
using ModelContextProtocol.Protocol;
using ModelContextProtocol.Server;

namespace AALC.Mcp;

internal static class McpCommands
{
    public static async Task<int> RunAsync(string[] args, string? root, CancellationToken ct)
    {
        string? profile = null;
        string? desktop = null;
        for (var i = 1; i < args.Length; i++)
        {
            if (i + 1 >= args.Length) throw new ArgumentException("mcp [--profile 配置目录] [--desktop AAALC.exe]");
            switch (args[i])
            {
                case "--profile": profile = args[++i]; break;
                case "--desktop": desktop = args[++i]; break;
                default: throw new ArgumentException($"未知 MCP 参数：{args[i]}");
            }
        }
        var builder = Host.CreateApplicationBuilder(new HostApplicationBuilderSettings { Args = [], DisableDefaults = true });
        builder.Logging.AddConsole(options => options.LogToStandardErrorThreshold = LogLevel.Trace);
        var tools = new AalcTools(profile is null ? SettingsStore.OpenDefault().DirectoryPath : Path.GetFullPath(profile), desktop, root);
        builder.Services.AddMcpServer().WithStdioServerTransport().WithTools(tools);
        using var host = builder.Build();
        await host.RunAsync(ct);
        return 0;
    }
}

[McpServerToolType]
public sealed class AalcTools(string profile, string? desktop, string? root)
{
    private async Task<JsonElement> Call(string operation, object args, CancellationToken ct)
    {
        try { return await AgentPipe.CallAsync(profile, operation, args, ct); }
        catch (Exception exception) when (exception is InvalidOperationException or IOException or TimeoutException)
        { throw new McpException(exception.Message); }
    }
    private async Task<string> Text(string operation, object args, CancellationToken ct) => (await Call(operation, args, ct)).GetRawText();

    [McpServerTool(Name = "aalc_open", OpenWorld = false), Description("连接或启动当前用户的 AAALC 桌面端，不启动游戏。无需管理员权限。")]
    public async Task<string> Open(CancellationToken cancellationToken)
    {
        try { return (await AgentPipe.CallAsync(profile, "status", new { }, cancellationToken)).GetRawText(); }
        catch (AgentUnavailableException) { }
        var candidates = new[]
        {
            desktop,
            Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "AAALC.exe")),
            root is null ? null : Path.Combine(root, "src", "AALC.Desktop", "bin", "Release", "net10.0-windows", "AAALC.exe")
        };
        var executable = candidates.FirstOrDefault(path => path is not null && File.Exists(path))
            ?? throw new McpException("未找到 AAALC.exe，请用 --desktop 指定桌面端路径");
        var start = new ProcessStartInfo(executable) { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Path.GetDirectoryName(executable)! };
        start.ArgumentList.Add("--profile"); start.ArgumentList.Add(profile);
        using var process = Process.Start(start) ?? throw new McpException("启动 AAALC 失败");
        for (var attempt = 0; attempt < 5; attempt++)
        {
            if (process.HasExited) throw new McpException($"AAALC 已退出：{process.ExitCode}");
            try { return (await AgentPipe.CallAsync(profile, "status", new { }, cancellationToken)).GetRawText(); }
            catch (AgentUnavailableException) { await Task.Delay(250, cancellationToken); }
        }
        throw new McpException("AAALC 未在启动时限内开放 Agent 接口");
    }

    [McpServerTool(Name = "aalc_get_status", ReadOnly = true, OpenWorld = false), Description("获取任务编号、运行状态、结果、最近事件、帧龄、录制目录、游戏窗口和分身状态。任务运行中可调用。")]
    public Task<string> Status(CancellationToken cancellationToken) => Text("status", new { }, cancellationToken);

    [McpServerTool(Name = "aalc_get_config", ReadOnly = true, OpenWorld = false), Description("读取桌面端当前配置和 revision。包括尚未保存的界面编辑；任务使用启动时的配置快照。")]
    public Task<string> GetConfig(CancellationToken cancellationToken) => Text("config.get", new { }, cancellationToken);

    [McpServerTool(Name = "aalc_update_config", OpenWorld = false), Description("空闲时递归合并 JSON patch，验证后通过 SettingsStore 保存并同步界面。数组整体替换，字段名区分大小写，未知字段拒绝。须携带刚读取的 revision，配置变化则拒绝覆盖。")]
    public Task<string> UpdateConfig([Description("aalc_get_config 返回的 revision")] string revision,
        [Description("JSON 对象，例如 {\"Launch\":{\"Mirror\":true,\"Daily\":false}}。遵循 get_config 中的字段和枚举数值。")] JsonElement patch,
        CancellationToken cancellationToken) => Text("config.patch", new { revision, patch }, cancellationToken);

    [McpServerTool(Name = "aalc_start_task", OpenWorld = false), Description("按已配置选项开始任务并立即返回任务编号。kind：launch 一键计划、daily 日常、harvest 换饼（含配置的狂气兑换）、mirror 镜牢。游戏不存在时自动启动。用 get_status/get_events 监督，禁止重叠任务。")]
    public Task<string> StartTask(string kind, CancellationToken cancellationToken) => Text("task.start", new { kind }, cancellationToken);

    [McpServerTool(Name = "aalc_stop_task", Idempotent = true, OpenWorld = false), Description("请求协作停止，等待 get_status 的 isRunning=false 后才能改配置或关闭游戏。提供 taskId 时只停止指定任务。")]
    public Task<string> StopTask(CancellationToken cancellationToken, string? taskId = null) => Text("task.stop", new { taskId }, cancellationToken);

    [McpServerTool(Name = "aalc_get_events", ReadOnly = true, OpenWorld = false), Description("分页读取当前任务的结构化事件。after 从 0 开始，后续用 nextCursor；最多保留 1000 条，oldestSequence 可判断缺失。完整事件在 recordingDirectory/events.jsonl。")]
    public Task<string> Events(CancellationToken cancellationToken, long after = 0, int limit = 50) => Text("events", new { after, limit }, cancellationToken);

    [McpServerTool(Name = "aalc_launch_game", OpenWorld = false), Description("空闲时启动游戏并立即返回；轮询 get_status，游戏窗口稳定后任务完成。已打开的窗口直接复用。")]
    public Task<string> LaunchGame(CancellationToken cancellationToken) => Text("game.launch", new { }, cancellationToken);

    [McpServerTool(Name = "aalc_close_game", OpenWorld = false), Description("空闲时正常关闭游戏，30 秒未退出则结束游戏进程。先停止运行任务并等到空闲。立即返回，用 get_status 检查结果。")]
    public Task<string> CloseGame(CancellationToken cancellationToken) => Text("game.close", new { }, cancellationToken);

    [McpServerTool(Name = "aalc_game_action", OpenWorld = false), Description("仅在任务空闲时处理已核对的游戏弹窗。先获取截图，使用五秒内的 actionToken 发送一次 click（原图像素 x/y）或 key（Escape/Enter/P/Space 等 GameKey 名称）。令牌用后作废；输入仍校验窗口、帧龄和坐标。操作后重新截图确认，不自动重试。")]
    public Task<string> GameAction(string actionToken, string action, CancellationToken cancellationToken,
        int? x = null, int? y = null, string? key = null) => Text("game.action", new { actionToken, action, x, y, key }, cancellationToken);

    [McpServerTool(Name = "aalc_get_screenshot", ReadOnly = true, OpenWorld = false), Description("返回游戏 PNG 图片及本地路径、帧编号、帧龄。空闲时从生产窗口截图；运行时返回最近观察帧，不争用窗口。source=clone-preview 是缩小的分身预览。")]
    public async Task<IEnumerable<ContentBlock>> Screenshot(CancellationToken cancellationToken)
    {
        var value = await Call("screenshot", new { }, cancellationToken);
        return
        [
            new TextContentBlock { Text = JsonSerializer.Serialize(new
            {
                source = value.GetProperty("source"), frame = value.GetProperty("frame"), ageMilliseconds = value.GetProperty("ageMilliseconds"),
                path = value.GetProperty("path"), actionToken = value.GetProperty("actionToken")
            }) },
            ImageContentBlock.FromBytes(Convert.FromBase64String(value.GetProperty("data").GetString()!), "image/png")
        ];
    }
}
