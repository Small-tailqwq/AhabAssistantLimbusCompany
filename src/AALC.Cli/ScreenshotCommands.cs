using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using AALC.Runtime;
using AALC.Runtime.Replay;
using AALC.Vision;

namespace AALC.Cli;

internal static class ScreenshotCommands
{
    public static async Task<int> RunAsync(string[] args, string? root, JsonSerializerOptions json, CancellationToken ct)
    {
        var flags = new Dictionary<string, string>();
        string[] allowed = ["--suite", "--data", "--root", "--models", "--filter"];
        for (var index = 1; index < args.Length; index += 2)
            if (!allowed.Contains(args[index]) || index + 1 >= args.Length || !flags.TryAdd(args[index], args[index + 1]))
                throw new ArgumentException("screenshot-test [--suite <用例.json>] [--data <非C盘测试集目录>] [--root <仓库>] [--models <OCR目录>] [--filter <用例ID片段>]");
        root = flags.TryGetValue("--root", out var repository) ? Path.GetFullPath(repository)
            : root ?? throw new ArgumentException("找不到资源仓库");
        var suitePath = flags.GetValueOrDefault("--suite", Path.Combine(root, "tests", "screenshots", "mirror.json"));
        var suite = ScreenshotTestset.Load(suitePath);
        var data = EvidencePaths.RequireExternalPath(flags.GetValueOrDefault("--data", Path.Combine(EvidencePaths.ResolveRoot(), "testsets")));
        var models = flags.GetValueOrDefault("--models", Path.Combine(root, "assets", "models", "ocr"));
        var filter = flags.GetValueOrDefault("--filter", "");
        var cases = suite.Cases.Where(item => item.Id.Contains(filter, StringComparison.OrdinalIgnoreCase)).ToArray();
        var replays = suite.Replays.Where(item => item.Id.Contains(filter, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (cases.Length + replays.Length == 0) throw new ArgumentException("筛选后没有用例");
        var directory = EvidencePaths.RequireExternalPath(Path.Combine(EvidencePaths.ResolveRoot(), "reports", "screenshots",
            DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")));
        Directory.CreateDirectory(directory);
        var reportPath = Path.Combine(directory, "report.json");
        var results = new List<ScreenshotCaseResult>();
        var timer = Stopwatch.StartNew();
        var cancelled = false;
        // 模型和模板来源用于复现失败，不把当前识别输出自动写回期望。
        var files = new[] { Path.Combine(models, "ch_PP-OCRv4_det_infer.onnx"), Path.Combine(models, "ch_PP-OCRv4_rec_infer.onnx"),
            Path.Combine(models, "ppocr_keys_v1.txt"), Path.Combine(root, "assets", "model", "best.onnx") };
        var fingerprints = files.Concat([typeof(ScreenshotRegression).Assembly.Location,
            typeof(MirrorScenarioReplay).Assembly.Location, typeof(AALC.Core.Features.Mirror.MirrorOptions).Assembly.Location])
            .Where(File.Exists).ToDictionary(path => path, Hash);
        var templateDirectory = Path.Combine(root, "assets", "images");
        var templateHashes = Directory.EnumerateFiles(templateDirectory, "*", SearchOption.AllDirectories)
            .Where(path => Path.GetExtension(path) is ".png" or ".webp").Order(StringComparer.Ordinal)
            .ToDictionary(path => Path.GetRelativePath(templateDirectory, path), Hash);
        try
        {
            using var regression = new ScreenshotRegression(root, models);
            foreach (var item in cases)
            {
                ct.ThrowIfCancellationRequested();
                Record(regression.Run(item, data, ct));
            }
            foreach (var item in replays)
            {
                ct.ThrowIfCancellationRequested();
                Record(await regression.RunAsync(item, data, ct));
            }
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { cancelled = true; }
        finally { Save(); }
        var passed = !cancelled && results.Count == cases.Length + replays.Length && results.All(result => result.Passed);
        Console.WriteLine(JsonSerializer.Serialize(new { passed, cancelled, total = cases.Length + replays.Length,
            completed = results.Count, failed = results.Count(result => !result.Passed), milliseconds = timer.Elapsed.TotalMilliseconds, reportPath }, json));
        return passed ? 0 : cancelled ? 2 : 1;

        void Record(ScreenshotCaseResult result)
        {
            results.Add(result);
            Save();
            Console.WriteLine(JsonSerializer.Serialize(new { result.Id, result.Passed, result.Milliseconds, result.Error,
                failed = result.Checks.Where(check => !check.Passed) }, json));
        }
        void Save() => File.WriteAllText(reportPath, JsonSerializer.Serialize(new { suitePath = Path.GetFullPath(suitePath),
            suiteHash = Hash(suitePath), data, filter, cancelled, total = cases.Length + replays.Length,
            milliseconds = timer.Elapsed.TotalMilliseconds, assembly = typeof(ScreenshotRegression).Assembly.GetName().Version?.ToString(),
            fingerprints, templateHashes, results }, ScreenshotTestset.Json));
    }

    private static string Hash(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexStringLower(SHA256.HashData(stream));
    }
}
