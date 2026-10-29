using AALC.Runtime;
using System.Runtime.InteropServices;
using System.Text.Json;
using AALC.Core.Features.Mirror;
using AALC.Platform.Windows;
using AALC.Runtime.Automation;
using AALC.Runtime.Configuration;
using AALC.Runtime.Mail;
using AALC.Runtime.Mirror;
using AALC.Runtime.Replay;
using AALC.Vision;
using OpenCvSharp;

namespace AALC.Cli;

internal static class MirrorCommands
{
    public static async Task<int> RunAsync(string[] args, string? root, JsonSerializerOptions json, CancellationToken ct)
    {
        var flags = Parse(args, ["--options", "--profile", "--pid", "--root", "--models"]);
        var useOptions = flags.TryGetValue("--options", out var optionsPath);
        var useProfile = flags.TryGetValue("--profile", out var profilePath);
        if (useOptions == useProfile)
            throw new ArgumentException("mirror 必须指定 --profile <桌面配置目录> 或 --options <镜牢配置.json>，两者只能选一个");
        var settings = useProfile ? new SettingsStore(profilePath!).Load() : null;
        var source = Path.GetFullPath(useProfile ? Path.Combine(profilePath!, "settings.json") : optionsPath!);
        root = flags.TryGetValue("--root", out var repository) ? Path.GetFullPath(repository)
            : !string.IsNullOrWhiteSpace(settings?.RepositoryRoot) ? Path.GetFullPath(settings.RepositoryRoot)
            : root ?? throw new ArgumentException("找不到资源仓库");
        var options = useProfile ? settings!.Mirror ?? throw new InvalidDataException("桌面配置中没有已保存的镜牢设置")
            : JsonSerializer.Deserialize<MirrorOptions>(File.ReadAllText(source), MirrorScenario.Json)
                ?? throw new InvalidDataException("镜牢配置为空");
        MirrorPlan.Validate(options);
        var windows = GameWindow.Find();
        GameWindowInfo selected;
        if (flags.TryGetValue("--pid", out var process))
        {
            if (!int.TryParse(process, out var pid) || pid <= 0) throw new ArgumentException("游戏进程 ID 无效");
            selected = windows.SingleOrDefault(window => window.ProcessId == pid)
                ?? throw new InvalidOperationException("未找到指定的 Limbus Company 窗口");
        }
        else selected = windows.Count == 1 ? windows[0]
            : throw new InvalidOperationException("请用 --pid 指定一个 Limbus Company 窗口");
        var output = EvidencePaths.RequireExternalPath(Path.Combine(EvidencePaths.ResolveRoot(), "recordings", "mirror", DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")));
        Directory.CreateDirectory(output);
        File.WriteAllText(Path.Combine(output, "options.json"), JsonSerializer.Serialize(options, json));
        File.WriteAllText(Path.Combine(output, "configuration.json"), JsonSerializer.Serialize(new { source }, json));
        using var mapReader = new MirrorMapReader(Path.Combine(root, "assets", "model", "best.onnx"),
            Path.Combine(EvidencePaths.ResolveRoot(), "learning", "maps"), output);
        using var events = new StreamWriter(Path.Combine(output, "events.jsonl")) { AutoFlush = true };
        void Publish(RunEvent item)
        {
            if (item.Rule is "mirror.route.entered" or "mirror.route.failed") mapReader.CompleteLearningSegment();
            var line = JsonSerializer.Serialize(item, json);
            events.WriteLine(line);
            if (item.Action != "Observed" && item.Rule is not ("mirror.route.map" or "mirror.route.scan")) Console.WriteLine(line);
        }
        using var window = new GameWindow(selected);
        using var matcher = new TemplateMatcher(root, new(settings?.GameLanguage ?? "zh_cn", settings?.GameTheme ?? "default"));
        var models = flags.TryGetValue("--models", out var modelDirectory) ? modelDirectory
            : !string.IsNullOrWhiteSpace(settings?.OcrModelsDirectory) ? settings.OcrModelsDirectory
            : RepositoryPaths.OcrModels(root);
        using var observer = new GameObserver(window, matcher, models, output);
        var session = new GameSession(observer, window, new SystemRunClock(), Publish, MirrorRunner.TimeoutFor(options), "Mirror");
        session.Report("mirror.configuration", $"读取镜牢配置：{source}");
        var result = await new MirrorRunner(session, mapReader, (teams, token) =>
            File.WriteAllTextAsync(Path.Combine(output, "queue.json"), JsonSerializer.Serialize(teams, json), token))
            .RunAsync(options, ct);
        File.WriteAllText(Path.Combine(output, "result.json"), JsonSerializer.Serialize(result, json));
        Console.WriteLine(JsonSerializer.Serialize(new { output, result }, json));
        return result.Outcome == RunOutcome.Completed ? 0 : 1;
    }

    public static async Task<int> ReplayAsync(string[] args, JsonSerializerOptions json, CancellationToken ct)
    {
        var flags = Parse(args, ["--run", "--vision", "--models"]);
        if (!flags.TryGetValue("--run", out var directory))
            throw new ArgumentException("mirror-replay --run <录制目录> [--vision <仓库根目录> [--models <OCR目录>]]");
        if (flags.ContainsKey("--models") && !flags.ContainsKey("--vision")) throw new ArgumentException("--models 需要 --vision");
        var scenario = MirrorScenario.LoadRun(directory);
        using var vision = flags.TryGetValue("--vision", out var repository)
            ? new MirrorScenarioVision(Path.GetFullPath(repository), flags.GetValueOrDefault("--models")) : null;
        var stopwatch = System.Diagnostics.Stopwatch.StartNew();
        var replay = new MirrorScenarioReplay(scenario, ReadPixels,
            item => { if (item.Action != "Observed") Console.WriteLine(JsonSerializer.Serialize(item, json)); }, vision);
        var result = await replay.RunAsync(ct);
        var acceptance = replay.Evaluate(result);
        Console.WriteLine(JsonSerializer.Serialize(new { directory, mode = vision is null ? "recorded" : "vision",
            wallMilliseconds = stopwatch.Elapsed.TotalMilliseconds, result, acceptance }, json));
        return acceptance.Passed ? 0 : 1;
    }

    private static byte[] ReadPixels(MirrorScenarioFrame frame) => MirrorScenarioVision.ReadPixels(frame);

    private static Dictionary<string, string> Parse(string[] args, string[] allowed)
    {
        var flags = new Dictionary<string, string>(StringComparer.Ordinal);
        for (var index = 1; index < args.Length; index += 2)
        {
            if (!allowed.Contains(args[index]) || index + 1 >= args.Length || !flags.TryAdd(args[index], args[index + 1]))
                throw new ArgumentException($"镜牢命令参数无效：{args[index]}");
        }
        return flags;
    }
}
