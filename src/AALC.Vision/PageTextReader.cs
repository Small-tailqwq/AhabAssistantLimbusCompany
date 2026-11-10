using AALC.Runtime.Automation;
using System.Runtime.InteropServices;
using AALC.Core.Features.Daily;
using AALC.Runtime.Daily;
using AALC.Runtime.Mail;
using OpenCvSharp;

namespace AALC.Vision;

public sealed class PageTextReader(string modelsDirectory) : IDisposable
{
    private TextDetector? detector;
    private TextRecognizer? recognizer;

    public IReadOnlyList<RecognizedText> Read(PixelFrame frame, PixelRect? region = null, int scale = 1,
        CancellationToken cancellationToken = default, TextPreprocessing preprocessing = TextPreprocessing.None)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (scale < 1) throw new ArgumentOutOfRangeException(nameof(scale));
        if (frame.Bgra.Length != frame.Identity.Width * frame.Identity.Height * 4)
            throw new InvalidDataException("OCR 帧缓冲区尺寸不匹配");
        var area = region ?? new PixelRect(0, 0, frame.Identity.Width, frame.Identity.Height);
        var left = Math.Clamp(area.X, 0, frame.Identity.Width);
        var top = Math.Clamp(area.Y, 0, frame.Identity.Height);
        var right = Math.Clamp(area.Right, left, frame.Identity.Width);
        var bottom = Math.Clamp(area.Bottom, top, frame.Identity.Height);
        if (right == left || bottom == top) return [];
        using var bgra = new Mat(frame.Identity.Height, frame.Identity.Width, MatType.CV_8UC4);
        Marshal.Copy(frame.Bgra, 0, bgra.Data, frame.Bgra.Length);
        using var crop = new Mat(bgra, new Rect(left, top, right - left, bottom - top));
        if (preprocessing == TextPreprocessing.FormationOrder)
            return ReadFormationOrder(crop, new(left, top, right - left, bottom - top), cancellationToken);
        if (preprocessing != TextPreprocessing.None) throw new ArgumentOutOfRangeException(nameof(preprocessing));
        using var resized = new Mat();
        Cv2.Resize(crop, resized, new Size(crop.Width * scale, crop.Height * scale));
        using var gray = new Mat();
        Cv2.CvtColor(resized, gray, ColorConversionCodes.BGRA2GRAY);
        Cv2.MinMaxLoc(gray, out double minimum, out double maximum);
        using var binaryMask = new Mat();
        Cv2.InRange(gray, Scalar.All(minimum + 1), Scalar.All(maximum - 1), binaryMask);
        if (minimum != maximum && Cv2.CountNonZero(binaryMask) > 0)
        {
            using var clahe = Cv2.CreateCLAHE(2, new Size(8, 8));
            using var enhanced = new Mat();
            clahe.Apply(gray, enhanced);
            enhanced.CopyTo(gray);
        }
        using var bgr = new Mat();
        Cv2.CvtColor(gray, bgr, ColorConversionCodes.GRAY2BGR);
        using var limited = new Mat();
        var image = bgr;
        var maxSide = Math.Max(bgr.Width, bgr.Height);
        if (maxSide > 1600)
        {
            var ratio = 1600.0 / maxSide;
            var width = Math.Max(32, (int)Math.Round((int)(bgr.Width * ratio) / 32.0) * 32);
            var height = Math.Max(32, (int)Math.Round((int)(bgr.Height * ratio) / 32.0) * 32);
            Cv2.Resize(bgr, limited, new Size(width, height));
            image = limited;
        }
        recognizer ??= new TextRecognizer(Path.Combine(modelsDirectory, "ch_PP-OCRv4_rec_infer.onnx"),
            Path.Combine(modelsDirectory, "ppocr_keys_v1.txt"));
        if (crop.Height <= 30 || crop.Width / (double)crop.Height > 8)
        {
            using var padded = new Mat();
            Cv2.CopyMakeBorder(image, padded, 0, 0, 4, 4, BorderTypes.Constant, Scalar.All(0));
            var line = recognizer.RecognizePrepared(padded, cancellationToken);
            return line.Score >= .5 && line.Text.Length > 0
                ? [new(line.Text, line.Score, new(left, top, right - left, bottom - top))]
                : [];
        }
        detector ??= new TextDetector(Path.Combine(modelsDirectory, "ch_PP-OCRv4_det_infer.onnx"));
        var result = new List<RecognizedText>();
        foreach (var box in detector.Detect(image, cancellationToken))
        {
            cancellationToken.ThrowIfCancellationRequested();
            var width = Math.Max(1, (int)Math.Max(TextDetector.Distance(box[0], box[1]), TextDetector.Distance(box[2], box[3])));
            var height = Math.Max(1, (int)Math.Max(TextDetector.Distance(box[0], box[3]), TextDetector.Distance(box[1], box[2])));
            using var transform = Cv2.GetPerspectiveTransform(box,
                [new Point2f(0, 0), new Point2f(width, 0), new Point2f(width, height), new Point2f(0, height)]);
            using var text = new Mat();
            Cv2.WarpPerspective(image, text, transform, new Size(width, height), InterpolationFlags.Cubic, BorderTypes.Replicate);
            if (height / (double)width >= 1.5) Cv2.Rotate(text, text, RotateFlags.Rotate90Counterclockwise);
            var recognition = recognizer.RecognizePrepared(text, cancellationToken);
            if (recognition.Score < .5 || recognition.Text.Length == 0) continue;
            var x = left + (int)(box.Min(p => p.X) * (right - left) / image.Width);
            var y = top + (int)(box.Min(p => p.Y) * (bottom - top) / image.Height);
            var x2 = left + (int)(box.Max(p => p.X) * (right - left) / image.Width);
            var y2 = top + (int)(box.Max(p => p.Y) * (bottom - top) / image.Height);
            result.Add(new(recognition.Text, recognition.Score, new(x, y, x2 - x, y2 - y)));
        }
        return result;
    }

    private IReadOnlyList<RecognizedText> ReadFormationOrder(Mat crop, PixelRect area, CancellationToken ct)
    {
        using var mask = new Mat(crop.Height, crop.Width, MatType.CV_8UC1, Scalar.All(0));
        for (var y = 0; y < crop.Height; y++)
            for (var x = 0; x < crop.Width; x++)
            {
                var pixel = crop.At<Vec4b>(y, x);
                var b = pixel.Item0; var g = pixel.Item1; var r = pixel.Item2;
                if (r >= 235 && g is >= 100 and <= 235 && b <= 70 && r - g >= 15
                    || b >= 160 && g >= 180 && r <= 65 && Math.Min(b, g) - r >= 120)
                    mask.Set(y, x, (byte)255);
            }
        using var labels = new Mat();
        using var stats = new Mat();
        using var centroids = new Mat();
        var components = Cv2.ConnectedComponentsWithStats(mask, labels, stats, centroids);
        var retained = new HashSet<int>();
        var left = crop.Width; var top = crop.Height; var right = 0; var bottom = 0;
        for (var component = 1; component < components; component++)
        {
            if (stats.At<int>(component, (int)ConnectedComponentsTypes.Height) < crop.Height * .4) continue;
            retained.Add(component);
            var x = stats.At<int>(component, (int)ConnectedComponentsTypes.Left);
            var y = stats.At<int>(component, (int)ConnectedComponentsTypes.Top);
            left = Math.Min(left, x); top = Math.Min(top, y);
            right = Math.Max(right, x + stats.At<int>(component, (int)ConnectedComponentsTypes.Width));
            bottom = Math.Max(bottom, y + stats.At<int>(component, (int)ConnectedComponentsTypes.Height));
        }
        if (retained.Count == 0) return [];
        for (var y = 0; y < crop.Height; y++)
            for (var x = 0; x < crop.Width; x++)
                if (!retained.Contains(labels.At<int>(y, x))) mask.Set(y, x, (byte)0);
        using var glyphs = new Mat(mask, new Rect(left, top, right - left, bottom - top));
        using var normalized = new Mat();
        Cv2.Resize(glyphs, normalized, new Size(Math.Max(1, (int)Math.Round(glyphs.Width * 28.0 / glyphs.Height)), 28));
        using var padded = new Mat();
        Cv2.CopyMakeBorder(normalized, padded, 1, 1, 6, 6, BorderTypes.Constant, Scalar.All(0));
        using var bgr = new Mat();
        Cv2.CvtColor(padded, bgr, ColorConversionCodes.GRAY2BGR);
        recognizer ??= new TextRecognizer(Path.Combine(modelsDirectory, "ch_PP-OCRv4_rec_infer.onnx"),
            Path.Combine(modelsDirectory, "ppocr_keys_v1.txt"));
        var recognition = recognizer.RecognizePrepared(bgr, ct);
        return recognition.Text.Length > 0 ? [new(recognition.Text, recognition.Score, area)] : [];
    }

    public void Dispose()
    {
        detector?.Dispose();
        recognizer?.Dispose();
    }
}
