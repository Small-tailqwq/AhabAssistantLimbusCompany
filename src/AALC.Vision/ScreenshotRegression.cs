using System.Diagnostics;
using System.Security.Cryptography;
using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;
using AALC.Runtime.Mirror;
using AALC.Runtime.Replay;

namespace AALC.Vision;

public sealed record ScreenshotCheckResult(string Name, bool Passed, object? Expected, object? Actual);
public sealed record ScreenshotCaseResult(string Id, string Description, bool Passed, double Milliseconds,
    IReadOnlyList<ScreenshotCheckResult> Checks, string? Error = null);

public sealed class ScreenshotRegression(string repositoryRoot, string modelsDirectory) : IDisposable
{
    private readonly Dictionary<TemplateOptions, MirrorScenarioVision> pipelines = [];
    private long frameId;

    public ScreenshotCaseResult Run(ScreenshotCase item, string dataRoot, CancellationToken ct)
    {
        var timer = Stopwatch.StartNew();
        var checks = new List<ScreenshotCheckResult>();
        try
        {
            ct.ThrowIfCancellationRequested();
            var imagePath = ScreenshotTestset.ResolveDataPath(dataRoot, item.Image);
            VerifyHash(imagePath, item.Sha256);
            var image = new MirrorScenarioFrame(++frameId, item.Width, item.Height, imagePath);
            var pixels = new PixelFrame(new(image.Id, image.Width, image.Height, 0, 0), MirrorScenarioVision.ReadPixels(image));
            var options = new TemplateOptions(item.Language, item.Theme);
            if (!pipelines.TryGetValue(options, out var vision))
                pipelines[options] = vision = new(repositoryRoot, modelsDirectory, options);
            foreach (var check in item.Templates ?? [])
            {
                var targets = vision.FindTargets(pixels, [check.Query], ct);
                var passed = targets.Count == check.Count && (check.Within is not { } box || targets.All(target =>
                    target.Bounds.X >= box.X && target.Bounds.Y >= box.Y
                    && target.Bounds.Right <= box.Right && target.Bounds.Bottom <= box.Bottom));
                checks.Add(new("template:" + check.Query.Asset, passed, check, targets));
            }
            foreach (var check in item.Text ?? [])
            {
                var text = vision.ReadText(pixels, check.Region, check.Scale, ct, check.Preprocessing);
                var value = Normalize(string.Concat(text.Where(t => t.Confidence >= check.MinimumConfidence).Select(t => t.Text)));
                var passed = (check.Exact is null || value.Equals(Normalize(check.Exact), StringComparison.OrdinalIgnoreCase))
                    && (check.Contains ?? []).All(word => value.Contains(Normalize(word), StringComparison.OrdinalIgnoreCase))
                    && (check.Excludes ?? []).All(word => !value.Contains(Normalize(word), StringComparison.OrdinalIgnoreCase));
                checks.Add(new($"ocr:{check.Region}", passed, check, new { value, text }));
            }
            if (item.Pages is { } pages)
            {
                var frame = new GameFrame(pixels, vision.FindTargets(pixels, MirrorRunner.Queries, ct));
                if (pages.Combat is { } combat)
                    CheckPage("combat", combat, MirrorRunner.IsCombatPage(frame));
                if (pages.Event is { } eventPage)
                    CheckPage("event", eventPage, MirrorEventFlow.HasEventPageEvidence(frame));
                if (pages.Reward is { } reward)
                    CheckPage("reward", reward, MirrorRewardFlow.IsReward(frame));
                if (pages.SelectedGifts is { } selectedGifts)
                {
                    var actual = frame.FindAll(MirrorRewardFlow.Gift).Count(gift => MirrorRewardFlow.IsGiftSelected(frame, gift));
                    checks.Add(new("gift-selection", actual == selectedGifts, selectedGifts, actual));
                }
                void CheckPage(string name, bool expected, bool actual) =>
                    checks.Add(new("page:" + name, expected == actual, expected, new { matched = actual, frame.Targets }));
            }
            if (item.Route is { } route)
            {
                var busQuery = MirrorRouteFlow.Queries.Single(query => query.Asset == MirrorRouteFlow.Bus);
                var bus = vision.FindTargets(pixels, [busQuery], ct).SingleOrDefault();
                var map = bus is null ? null : vision.ReadMap(pixels, bus.Center, ct);
                var plan = map is null ? null : MirrorRoutePlanner.Choose(map, new(route.HardMode));
                var next = plan?.Nodes.FirstOrDefault();
                checks.Add(new("route", next is not null && next.Kind == route.Kind
                    && route.Destination.Contains(next.Center.X, next.Center.Y), route, new { bus, map, plan }));
            }
            return new(item.Id, item.Description, checks.All(check => check.Passed), timer.Elapsed.TotalMilliseconds, checks);
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
        catch (Exception exception)
        {
            return new(item.Id, item.Description, false, timer.Elapsed.TotalMilliseconds, checks, exception.ToString());
        }
    }

    public async Task<ScreenshotCaseResult> RunAsync(ScreenshotReplayCase item, string dataRoot, CancellationToken ct)
    {
        var timer = Stopwatch.StartNew();
        try
        {
            var directory = ScreenshotTestset.ResolveDataPath(dataRoot, item.Directory);
            foreach (var (file, hash) in item.Sha256)
            {
                ct.ThrowIfCancellationRequested();
                VerifyHash(ScreenshotTestset.ResolveDataPath(directory, file), hash);
            }
            var scenario = MirrorScenario.LoadRun(directory);
            foreach (var frame in scenario.Frames)
                if (!item.Sha256.ContainsKey(Path.GetFileName(frame.ImagePath)))
                    throw new InvalidDataException($"录制帧缺少 SHA256：{frame.ImagePath}");
            using var vision = new MirrorScenarioVision(repositoryRoot, modelsDirectory);
            var replay = new MirrorScenarioReplay(scenario, MirrorScenarioVision.ReadPixels, vision: vision);
            var result = await replay.RunAsync(ct);
            ct.ThrowIfCancellationRequested();
            var acceptance = replay.Evaluate(result);
            return new(item.Id, item.Description, acceptance.Passed, timer.Elapsed.TotalMilliseconds,
                [new("replay:vision-and-actions", acceptance.Passed, scenario.ExpectedResult, new { result, acceptance })]);
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
        catch (Exception exception)
        {
            return new(item.Id, item.Description, false, timer.Elapsed.TotalMilliseconds, [], exception.ToString());
        }
    }

    public static void VerifyHash(string path, string expected)
    {
        using var stream = File.OpenRead(path);
        var actual = Convert.ToHexStringLower(SHA256.HashData(stream));
        if (!actual.Equals(expected, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException($"文件内容与标注时不同：{path}；预期 {expected}，实际 {actual}");
    }

    private static string Normalize(string text) => string.Concat(text.Where(character => !char.IsWhiteSpace(character)));

    public void Dispose()
    {
        foreach (var pipeline in pipelines.Values) pipeline.Dispose();
    }
}
