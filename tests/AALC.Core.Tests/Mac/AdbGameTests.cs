using System.Buffers.Binary;
using System.Runtime.InteropServices;
using AALC.Core.Features.Mail;
using AALC.Platform.Android;
using AALC.Runtime;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;
using AALC.Vision;
using OpenCvSharp;
using Xunit;

namespace AALC.Core.Tests;

[System.Runtime.Versioning.SupportedOSPlatform("macos")]
public sealed class AdbGameTests : IDisposable
{
    private readonly string directory = Directory.CreateTempSubdirectory("aaalc-adb-").FullName;
    private readonly AdbClient adb;
    private readonly AdbDevice target;
    private static readonly TemplateHit Hit = new(MailControl.HomeMail, new(1, 0), 1, "mail");

    public AdbGameTests()
    {
        var executable = Path.Combine(directory, "fake adb");
        target = new("emulator-" + Guid.NewGuid().ToString("N"), 17);
        Write("serial", target.Serial);
        Write("devices", $"List of devices attached\n{target.Serial} device product:test transport_id:17\nother offline transport_id:18\nusb unauthorized transport_id:19\n");
        Write("window", "  mCurrentFocus=Window{abc u0 com.ProjectMoon.LimbusCompany/.MainActivity}\n");
        Write("fake adb", """
            #!/bin/sh
            cd "$(dirname "$0")" || exit 1
            case "$*" in
              "devices -l") cat devices ;;
              "connect 127.0.0.1:5555") echo 'connected to 127.0.0.1:5555' ;;
              "-t 17 get-serialno") cat serial ;;
              "-t 17 shell dumpsys window") cat window ;;
              "-t 17 exec-out screencap")
                if test -f block; then exec sleep 60; elif test -f step; then cat frame-"$(cat step)"; else cat frame; fi ;;
              "-t 17 shell input tap "*) echo "$6 $7" >> taps
                if test -f step; then echo $(( $(cat step) + 1 )) > step; fi ;;
              *) echo "unexpected arguments: $*" >&2; exit 1 ;;
            esac
            """);
        File.SetUnixFileMode(executable, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        adb = new(executable);
        Frame(2, 1, 16);
    }

    [Fact]
    public async Task OnlyOnlineTransportsCanBeSelected()
    {
        await adb.ConnectLocalAsync(5555, default);
        Assert.Equal(target, Assert.Single(await adb.DevicesAsync(default)));
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => adb.ConnectLocalAsync(65536, default));
        Write("devices", $"{target.Serial} device transport_id:23");
        await Assert.ThrowsAsync<InvalidOperationException>(() => adb.AttachAsync(target, default));
    }

    [Theory]
    [InlineData(12)]
    [InlineData(16)]
    public async Task CapturePreservesPixelsAndTapConsumesOnlyTheLatestFrame(int headerSize)
    {
        using var game = await adb.AttachAsync(target, default);
        Frame(2, 1, headerSize);
        var old = await game.CaptureAsync(default);
        var frame = await game.CaptureAsync(default);
        Assert.Equal(new byte[] { 3, 2, 1, 255, 3, 2, 1, 255 }, frame.Bgra);
        Assert.Equal((2, 1, 17L), (frame.Identity.Width, frame.Identity.Height, frame.Identity.Window));
        await Assert.ThrowsAsync<GameTransientException>(() => game.ClickAsync(Hit, old.Identity, default).AsTask());
        await game.ClickAsync(Hit, frame.Identity, default);
        await Assert.ThrowsAsync<GameTransientException>(() => game.ClickAsync(Hit, frame.Identity, default).AsTask());
        Assert.Equal("1 0", Assert.Single(File.ReadAllLines(Path.Combine(directory, "taps"))));
    }

    [Fact]
    public async Task SyntheticAdbFramesDriveProductionMailRunner()
    {
        var root = RepositoryPaths.Discover(AppContext.BaseDirectory)!;
        var templates = new[] { "share/home/mail_assets", "en/mail/claim_all_assets",
            "share/mail/get_mail_prize_confirm", "en/mail/close_assets", "share/home/mail_assets" };
        for (var i = 0; i < templates.Length; i++)
        {
            using var image = Cv2.ImRead(Path.Combine(root, "assets/images/default", templates[i] + ".png"));
            using var scaled = new Mat();
            Cv2.Resize(image, scaled, default, .5, .5, InterpolationFlags.Area);
            using var canvas = new Mat(720, 1280, MatType.CV_8UC3, Scalar.Black);
            using var region = new Mat(canvas, new Rect((1280 - scaled.Width) / 2, (720 - scaled.Height) / 2, scaled.Width, scaled.Height));
            scaled.CopyTo(region);
            using var rgba = new Mat();
            Cv2.CvtColor(canvas, rgba, ColorConversionCodes.BGR2RGBA);
            var raw = new byte[16 + 720 * 1280 * 4];
            BinaryPrimitives.WriteInt32LittleEndian(raw, 1280);
            BinaryPrimitives.WriteInt32LittleEndian(raw.AsSpan(4), 720);
            BinaryPrimitives.WriteInt32LittleEndian(raw.AsSpan(8), 1);
            Marshal.Copy(rgba.Data, raw, 16, raw.Length - 16);
            File.WriteAllBytes(Path.Combine(directory, $"frame-{i}"), raw);
        }
        Write("step", "0");
        using var game = await adb.AttachAsync(target, default);
        using var matcher = new TemplateMatcher(root, new("en"));
        var events = new List<RunEvent>();
        var result = await new MailRunner(new MailObserver(game, matcher), game, new SystemRunClock())
            .RunAsync(TimeSpan.FromSeconds(20), events.Add, default);
        Assert.True(result.Outcome == RunOutcome.Completed, result.Reason);
        Assert.Equal(["mail.open", "mail.claim-all", "mail.confirm-rewards", "mail.close-after-confirm"],
            events.Where(e => e.Action == "Sent").Select(e => e.Rule));
    }

    [Fact]
    public async Task InputFailsClosedOnResizedBackgroundOrOutOfBoundsTarget()
    {
        using var game = await adb.AttachAsync(target, default);
        var first = await game.CaptureAsync(default);
        Frame(3, 1, 12);
        await Assert.ThrowsAsync<GameTransientException>(() => game.ClickAsync(Hit, first.Identity, default).AsTask());
        var second = await game.CaptureAsync(default);
        await Assert.ThrowsAsync<InvalidOperationException>(() => game.ClickAsync(Hit with { Center = new(3, 0) }, second.Identity, default).AsTask());
        var third = await game.CaptureAsync(default);
        Write("window", "  mCurrentFocus=Window{abc u0 com.android.settings/.MainActivity}\n");
        await Assert.ThrowsAsync<InvalidOperationException>(() => game.ClickAsync(Hit, third.Identity, default).AsTask());
        Assert.False(File.Exists(Path.Combine(directory, "taps")));
    }

    [Fact]
    public async Task CancelledCaptureReleasesLeaseOnlyAfterAdbStops()
    {
        var game = await adb.AttachAsync(target, default);
        Write("block", "");
        using var cancellation = new CancellationTokenSource();
        var pending = game.CaptureAsync(cancellation.Token).AsTask();
        game.Dispose();
        await Assert.ThrowsAsync<IOException>(() => adb.AttachAsync(target, default));
        cancellation.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => pending.WaitAsync(TimeSpan.FromSeconds(3)));
        using var next = await adb.AttachAsync(target, default);
    }

    [Fact]
    public async Task InvalidScreenshotOrResolutionCannotStartMail()
    {
        using var game = await adb.AttachAsync(target, default);
        await Assert.ThrowsAsync<InvalidOperationException>(() => game.EnsureResolutionAsync(_ => { }, default));
        File.WriteAllBytes(Path.Combine(directory, "frame"), [1, 2, 3]);
        await Assert.ThrowsAsync<InvalidDataException>(() => game.CaptureAsync(default).AsTask());
    }

    private void Frame(int width, int height, int header)
    {
        var raw = new byte[header + width * height * 4];
        BinaryPrimitives.WriteInt32LittleEndian(raw, width);
        BinaryPrimitives.WriteInt32LittleEndian(raw.AsSpan(4), height);
        BinaryPrimitives.WriteInt32LittleEndian(raw.AsSpan(8), 1);
        for (var i = header; i < raw.Length; i += 4)
        { raw[i] = 1; raw[i + 1] = 2; raw[i + 2] = 3; }
        File.WriteAllBytes(Path.Combine(directory, "frame"), raw);
    }

    private void Write(string file, string contents) => File.WriteAllText(Path.Combine(directory, file), contents);
    public void Dispose() => Directory.Delete(directory, true);
}
