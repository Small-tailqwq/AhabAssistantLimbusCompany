using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;
using AALC.Core.Features.Daily;
using AALC.Core.Features.Mail;
using AALC.Platform.Windows;
using AALC.Runtime;
using AALC.Runtime.Daily;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;
using AALC.Vision;
using OpenCvSharp;

namespace AALC.Cli;

internal static class DailyCommands
{
    public static async Task<int> CaptureAsync(string[] args, JsonSerializerOptions json, CancellationToken ct)
    {
        if (args.Length != 3 || !int.TryParse(args[1], out var pid)) throw new ArgumentException("capture <进程ID> <输出.png>");
        var path = EvidencePaths.RequireExternalPath(args[2]);
        var selected = GameWindow.Find().SingleOrDefault(window => window.ProcessId == pid)
            ?? throw new InvalidOperationException("未找到指定的 Limbus Company 窗口");
        using var window = new GameWindow(selected);
        var frame = await window.CaptureAsync(ct);
        using var bgra = new Mat(frame.Identity.Height, frame.Identity.Width, MatType.CV_8UC4);
        Marshal.Copy(frame.Bgra, 0, bgra.Data, frame.Bgra.Length);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        Cv2.ImWrite(EvidencePaths.RequireExternalPath(path), bgra);
        Console.WriteLine(JsonSerializer.Serialize(new { path, frame.Identity }, json));
        return 0;
    }

    public static async Task<int> RunAsync(string[] args, string? root, JsonSerializerOptions json, CancellationToken ct)
    {
        if (args.Length is < 3 or > 5 || !int.TryParse(args[1], out var pid))
            throw new ArgumentException("daily <进程ID> <配置.json> [仓库] [OCR模型目录] | daily-battle <进程ID> <当前批次数> [仓库] [OCR模型目录]");
        root = args.Length >= 4 ? Path.GetFullPath(args[3]) : root ?? throw new ArgumentException("找不到资源仓库");
        var models = args.Length == 5 ? args[4] : Path.Combine(root, ".venv", "Lib", "site-packages", "rapidocr", "models");
        var continueBattle = args[0] == "daily-battle";
        var combatCount = continueBattle ? int.Parse(args[2]) : 0;
        if (continueBattle && combatCount is < 1 or > 10) throw new ArgumentOutOfRangeException(nameof(combatCount), "当前批次数须为 1–10");
        DailyOptions? options = null;
        if (!continueBattle)
        {
            options = JsonSerializer.Deserialize<DailyOptions>(File.ReadAllText(args[2]),
                new JsonSerializerOptions(json) { PropertyNameCaseInsensitive = true }) ?? throw new InvalidDataException("日常配置为空");
            DailyPlan.Validate(options);
        }
        var selected = GameWindow.Find().SingleOrDefault(window => window.ProcessId == pid)
            ?? throw new InvalidOperationException("未找到指定的 Limbus Company 窗口");
        var output = EvidencePaths.RequireExternalPath(Path.Combine(EvidencePaths.ResolveRoot(), "recordings", "daily", DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")));
        Directory.CreateDirectory(output);
        if (options is not null) File.WriteAllText(Path.Combine(output, "options.json"), JsonSerializer.Serialize(options, json));
        else File.WriteAllText(Path.Combine(output, "command.json"), JsonSerializer.Serialize(new { command = "daily-battle", combatCount }, json));
        using var events = new StreamWriter(Path.Combine(output, "events.jsonl")) { AutoFlush = true };
        void Publish(RunEvent item)
        {
            var line = JsonSerializer.Serialize(item, json);
            events.WriteLine(line);
            if (item.Action != "Observed") Console.WriteLine(line);
        }
        using var window = new GameWindow(selected);
        using var matcher = new TemplateMatcher(root, new());
        using var observer = new GameObserver(window, matcher, models, output);
        var clock = new SystemRunClock();
        var session = new GameSession(observer, window, clock, Publish,
            options is not null ? DailyRunner.TimeoutFor(options) : TimeSpan.FromSeconds(900 + 300 * combatCount));
        var runner = new DailyRunner(session, token => new MailRunner(new MailObserver(window, matcher, Path.Combine(output, "mail")),
            window, clock).RunAsync(TimeSpan.FromSeconds(30), Publish, token));
        var result = options is not null ? await runner.RunAsync(options, ct) : await ContinueBattleAsync(session, combatCount, ct);
        File.WriteAllText(Path.Combine(output, "result.json"), JsonSerializer.Serialize(result, json));
        Console.WriteLine(JsonSerializer.Serialize(new { output, result }, json));
        return result.Outcome == RunOutcome.Completed ? 0 : 1;
    }

    private static async Task<RunResult> ContinueBattleAsync(IGameSession session, int combatCount, CancellationToken ct)
    {
        RunOutcome outcome;
        string reason;
        try
        {
            var completed = await BattleFlow.ContinueAsync(session, combatCount, true, ct);
            outcome = completed ? RunOutcome.Completed : RunOutcome.Failed;
            reason = completed ? "当前采光战斗已完成" : "当前采光战斗未完成";
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { outcome = RunOutcome.Cancelled; reason = "已停止当前战斗任务"; }
        catch (Exception exception) { outcome = RunOutcome.Failed; reason = exception.Message; }
        session.Report("daily.run." + outcome.ToString().ToLowerInvariant(), reason);
        return new(outcome, reason, session.Observations, session.Elapsed.TotalMilliseconds);
    }

    public static int ReadText(string[] args, JsonSerializerOptions json, CancellationToken ct)
    {
        if (args.Length != 3 && args.Length != 8) throw new ArgumentException("read-text <截图> <模型目录> [x y width height scale]");
        using var source = Cv2.ImRead(args[1]);
        if (source.Empty()) throw new InvalidDataException("截图读取失败");
        using var bgra = new Mat();
        Cv2.CvtColor(source, bgra, ColorConversionCodes.BGR2BGRA);
        var bytes = new byte[bgra.Width * bgra.Height * 4];
        Marshal.Copy(bgra.Data, bytes, 0, bytes.Length);
        var frame = new PixelFrame(new FrameIdentity(1, bgra.Width, bgra.Height, 0, Stopwatch.GetTimestamp()), bytes);
        PixelRect? region = args.Length == 8 ? new(int.Parse(args[3]), int.Parse(args[4]), int.Parse(args[5]), int.Parse(args[6])) : null;
        using var reader = new PageTextReader(args[2]);
        Console.WriteLine(JsonSerializer.Serialize(reader.Read(frame, region, args.Length == 8 ? int.Parse(args[7]) : 1, ct), json));
        return 0;
    }
}
