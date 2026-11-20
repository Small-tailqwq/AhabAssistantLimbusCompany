using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using AALC.Runtime;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;
using AALC.Vision;
using OpenCvSharp;

namespace AALC.Shared;

[JsonSerializable(typeof(RunEvent))]
[JsonSerializable(typeof(RunResult))]
internal partial class MailRecordingJson : JsonSerializerContext;

internal static class AttachedGameTasks
{
    public static async Task<PixelFrame> CaptureAsync(IAttachedGame game, string path, CancellationToken token)
    {
        var frame = await game.CaptureAsync(token);
        using var bgra = new Mat(frame.Identity.Height, frame.Identity.Width, MatType.CV_8UC4);
        Marshal.Copy(frame.Bgra, 0, bgra.Data, frame.Bgra.Length);
        token.ThrowIfCancellationRequested();
        path = EvidencePaths.RequireExternalPath(path);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        if (!Cv2.ImWrite(path, bgra)) throw new IOException($"截图保存失败：{path}");
        return frame;
    }

    public static async Task<RunResult> MailAsync(IAttachedGame game, string root, TemplateOptions options,
        Action<RunEvent> publish, Action<PixelFrame>? frameCaptured, CancellationToken token, JsonSerializerOptions? json = null)
    {
        var directory = EvidencePaths.RequireExternalPath(Path.Combine(EvidencePaths.ResolveRoot(), "recordings", "mail",
            DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")));
        Directory.CreateDirectory(directory);
        using var events = new StreamWriter(Path.Combine(directory, "events.jsonl")) { AutoFlush = true };
        var serializer = json is null ? MailRecordingJson.Default : new MailRecordingJson(new JsonSerializerOptions(json));
        void Report(RunEvent item) { events.WriteLine(JsonSerializer.Serialize(item, serializer.RunEvent)); publish(item); }
        await game.EnsureResolutionAsync(message => Report(new("", 0, "Mail", "game.resolution", "Progress", null, 0, message)), token);
        using var matcher = new TemplateMatcher(root, options);
        var observer = new MailObserver(game, matcher, directory);
        observer.FrameCaptured += frameCaptured;
        var result = await new MailRunner(observer, game, new SystemRunClock()).RunAsync(TimeSpan.FromSeconds(30), Report, token);
        File.WriteAllText(Path.Combine(directory, "result.json"), JsonSerializer.Serialize(result, serializer.RunResult));
        return result;
    }
}
