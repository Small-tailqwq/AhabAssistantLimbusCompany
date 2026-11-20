using AALC.Runtime.Automation;
using System.Text.Json;
using System.Text.Json.Serialization;
using AALC.Shared;
using AALC.Runtime;
using AALC.Runtime.Mail;
using AALC.Runtime.Replay;
using AALC.Vision;
using AALC.Cli;
using AALC.Runtime.Daily;
using AALC.Core.Features.Daily;
using OpenCvSharp;

var json = new JsonSerializerOptions
{
    PropertyNamingPolicy = JsonNamingPolicy.CamelCase, WriteIndented = false,
    Converters = { new JsonStringEnumConverter() }
};
using var cancellation = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; cancellation.Cancel(); };
try
{
#if WINDOWS
    AALC.Platform.Windows.DpiAwareness.EnsurePerMonitorV2();
#endif
    if (args.Length == 0) throw new ArgumentException("命令：screenshot-test | mirror-replay | daily-replay | mail | replay | capture | match | match-many | read-text | recognize；平台命令：" + PlatformDevice.Commands + "；参数见 docs/application.md");
    var root = RepositoryPaths.Discover(Environment.CurrentDirectory) ?? RepositoryPaths.Discover(AppContext.BaseDirectory);
    switch (args[0])
    {
        case "screenshot-test":
            return await ScreenshotCommands.RunAsync(args, root, json, cancellation.Token);
        case "mirror-replay":
            return await MirrorCommands.ReplayAsync(args, json, cancellation.Token);
        case "read-text":
            return DailyCommands.ReadText(args, json, cancellation.Token);
        case "capture":
            return await DailyCommands.CaptureAsync(args, json, cancellation.Token);
        case "daily-replay":
        {
            if (args.Length != 2) throw new ArgumentException("daily-replay <场景.json>");
            var scenario = DailyScenario.Load(args[1]);
            var session = new DailyScenarioSession(scenario, item => Console.WriteLine(JsonSerializer.Serialize(item, json)));
            var result = await new DailyRunner(session, _ => throw new InvalidOperationException("场景未配置邮件回放"))
                .RunAsync(scenario.Options, cancellation.Token);
            var acceptance = session.Evaluate(result);
            Console.WriteLine(JsonSerializer.Serialize(new { scenario.Id, scenario.Evidence, result, acceptance }, json));
            return acceptance.Passed ? 0 : 1;
        }
        case "replay":
        {
            if (args.Length != 2) throw new ArgumentException("replay <场景.json>");
            var scenario = MailScenario.Load(args[1]);
            var session = new ScenarioSession(scenario);
            var result = await new MailRunner(session, session, session).RunAsync(TimeSpan.FromSeconds(30),
                e => Console.WriteLine(JsonSerializer.Serialize(e, json)), cancellation.Token);
            var acceptance = session.Evaluate(result);
            Console.WriteLine(JsonSerializer.Serialize(new { scenario.Id, scenario.Evidence, result, acceptance }, json));
            return acceptance.Passed ? 0 : 1;
        }
        case "match":
        {
            if (args.Length is < 3 or > 6) throw new ArgumentException("match <截图> <资源键> [仓库] [语言] [主题]");
            using var matcher = new TemplateMatcher(args.Length >= 4 ? args[3] : root ?? throw new ArgumentException("找不到资源仓库"),
                new(args.Length >= 5 ? args[4] : "zh_cn", args.Length >= 6 ? args[5] : "default"));
            using var bgr = Cv2.ImRead(args[1]);
            if (bgr.Empty()) throw new InvalidDataException("截图读取失败");
            using var gray = TemplateMatcher.Gray(bgr);
            foreach (var mode in Enum.GetValues<TemplateSearch>())
                Console.WriteLine(JsonSerializer.Serialize(new { mode, match = matcher.Match(gray, args[2], mode) }, json));
            return 0;
        }
        case "match-many":
        {
            if (args.Length is < 3 or > 5) throw new ArgumentException("match-many <截图> <资源键> [阈值] [仓库]");
            using var matcher = new TemplateMatcher(args.Length == 5 ? args[4] : root ?? throw new ArgumentException("找不到资源仓库"), new());
            using var source = Cv2.ImRead(args[1]);
            if (source.Empty()) throw new InvalidDataException("截图读取失败");
            using var gray = TemplateMatcher.Gray(source);
            var threshold = args.Length >= 4 ? double.Parse(args[3], System.Globalization.CultureInfo.InvariantCulture) : .8;
            Console.WriteLine(JsonSerializer.Serialize(matcher.Find(gray, new ImageQuery(args[2], threshold, true)), json));
            return 0;
        }
        case "recognize":
        {
            if (args.Length != 4) throw new ArgumentException("recognize <文字裁剪> <PP-OCRv4 rec 模型> <字典>");
            using var crop = Cv2.ImRead(args[1]);
            using var recognizer = new TextRecognizer(args[2], args[3]);
            Console.WriteLine(JsonSerializer.Serialize(recognizer.Recognize(crop), json));
            return 0;
        }
#if WINDOWS
        case "mirror":
            return await MirrorCommands.RunAsync(args, root, json, cancellation.Token);
        case "daily":
        case "daily-battle":
            return await DailyCommands.RunAsync(args, root, json, cancellation.Token);
        case "clone-verify":
            return await CloneCommands.VerifyAsync(args, root, cancellation.Token);
        case "clone-mirror":
            return await CloneCommands.MirrorAsync(args, cancellation.Token);
        case "windows":
            Console.WriteLine(JsonSerializer.Serialize(AALC.Platform.Windows.GameWindow.Find(), json));
            return 0;
#else
        case "devices":
            Console.WriteLine(JsonSerializer.Serialize(await AALC.Platform.Android.AdbClient.Local().DevicesAsync(cancellation.Token), json));
            return 0;
        case "mirror": case "daily": case "daily-battle": case "windows": case "clone-verify": case "clone-mirror":
            throw new PlatformNotSupportedException("此命令需要 Windows 原生游戏窗口；macOS 请使用 devices、capture、mail 或离线回放。");
#endif
        case "mail":
        {
            if (args.Length is < 2 or > 4) throw new ArgumentException($"mail <{PlatformDevice.Identifier}> [仓库] [en|zh_cn]");
            root = args.Length >= 3 ? Path.GetFullPath(args[2]) : root ?? throw new ArgumentException("找不到资源仓库");
            var language = args.Length == 4 ? args[3] : OperatingSystem.IsMacOS() ? "en" : "zh_cn";
            if (language is not ("en" or "zh_cn")) throw new ArgumentException("游戏语言须为 en 或 zh_cn");
            using var device = await PlatformDevice.AttachAsync(args[1], cancellation.Token);
            var result = await AttachedGameTasks.MailAsync(device, root, new(language), e => Console.WriteLine(JsonSerializer.Serialize(e, json)),
                null, cancellation.Token, json);
            return result.Outcome == RunOutcome.Completed ? 0 : 1;
        }
        default: throw new ArgumentException($"未知命令 {args[0]}");
    }
}
catch (Exception exception)
{
    Console.Error.WriteLine(JsonSerializer.Serialize(new { error = exception.ToString() }, json));
    return 2;
}
