using System.Runtime.InteropServices;
using System.Diagnostics;
using AALC.Core.Features.Daily;
using AALC.Runtime.Mail;
using OpenCvSharp;

namespace AALC.Vision;

/// <summary>跨进程传递的预览帧：缩小并压缩，只用于显示，不参与识别。</summary>
public static class FramePreview
{
    private const int PreviewWidth = 800;
    private static readonly int[] Qualities = [60, 40];

    /// <summary>压缩后仍超过 <paramref name="maxBytes"/> 时返回 null，调用方丢弃这一帧。</summary>
    public static byte[]? Encode(PixelFrame frame, int maxBytes)
    {
        using var bgra = new Mat(frame.Identity.Height, frame.Identity.Width, MatType.CV_8UC4);
        Marshal.Copy(frame.Bgra, 0, bgra.Data, frame.Bgra.Length);
        using var bgr = new Mat();
        Cv2.CvtColor(bgra, bgr, ColorConversionCodes.BGRA2BGR);
        using var scaled = new Mat();
        var scale = Math.Min(1.0, (double)PreviewWidth / frame.Identity.Width);
        Cv2.Resize(bgr, scaled, new Size(0, 0), scale, scale, InterpolationFlags.Area);
        foreach (var quality in Qualities)
        {
            Cv2.ImEncode(".jpg", scaled, out var encoded, new ImageEncodingParam(ImwriteFlags.JpegQuality, quality));
            if (encoded.Length <= maxBytes) return encoded;
        }
        return null;
    }

    public static PixelFrame Decode(long id, byte[] encoded)
    {
        using var bgr = Cv2.ImDecode(encoded, ImreadModes.Color);
        if (bgr.Empty()) throw new InvalidDataException("预览帧解码失败");
        using var bgra = new Mat();
        Cv2.CvtColor(bgr, bgra, ColorConversionCodes.BGR2BGRA);
        var pixels = new byte[bgra.Width * bgra.Height * 4];
        Marshal.Copy(bgra.Data, pixels, 0, pixels.Length);
        return new(new FrameIdentity(id, bgra.Width, bgra.Height, 0, Stopwatch.GetTimestamp()), pixels);
    }
}
