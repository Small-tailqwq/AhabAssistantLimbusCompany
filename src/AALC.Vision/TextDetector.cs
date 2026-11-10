using System.Runtime.InteropServices;
using Microsoft.ML.OnnxRuntime;
using Microsoft.ML.OnnxRuntime.Tensors;
using OpenCvSharp;

namespace AALC.Vision;

/// <summary>PP-OCRv4 DB text detection with quadrilateral boxes in source-image coordinates.</summary>
public sealed class TextDetector(string modelPath) : IDisposable
{
    private readonly InferenceSession session = new(modelPath);

    public IReadOnlyList<Point2f[]> Detect(Mat bgr, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var ratio = Math.Max(1, 736.0 / Math.Min(bgr.Width, bgr.Height));
        var width = (int)Math.Round((int)(bgr.Width * ratio) / 32.0) * 32;
        var height = (int)Math.Round((int)(bgr.Height * ratio) / 32.0) * 32;
        using var resized = new Mat();
        Cv2.Resize(bgr, resized, new Size(width, height));
        var input = new DenseTensor<float>(new[] { 1, 3, height, width });
        var inputValues = input.Buffer.Span;
        var sourceRow = new byte[width * 3];
        for (var y = 0; y < height; y++)
        {
            Marshal.Copy(resized.Ptr(y), sourceRow, 0, sourceRow.Length);
            for (var x = 0; x < width; x++)
            {
                for (var c = 0; c < 3; c++)
                    inputValues[c * height * width + y * width + x] = (sourceRow[x * 3 + c] * (1f / 255f) - .5f) / .5f;
            }
        }
        cancellationToken.ThrowIfCancellationRequested();
        using var run = new RunOptions();
        using var cancellation = cancellationToken.Register(() => run.Terminate = true);
        IDisposableReadOnlyCollection<DisposableNamedOnnxValue> inference;
        try
        {
            inference = session.Run([NamedOnnxValue.CreateFromTensor(session.InputMetadata.Keys.First(), input)],
                session.OutputMetadata.Keys.ToArray(), run);
        }
        catch (OnnxRuntimeException) when (cancellationToken.IsCancellationRequested)
        {
            throw new OperationCanceledException(cancellationToken);
        }
        using var outputs = inference;
        cancellationToken.ThrowIfCancellationRequested();
        var probabilities = outputs.First().AsTensor<float>();
        var mapHeight = probabilities.Dimensions[2];
        var mapWidth = probabilities.Dimensions[3];
        using var map = new Mat(mapHeight, mapWidth, MatType.CV_32FC1);
        using var mask = new Mat(mapHeight, mapWidth, MatType.CV_8UC1);
        var probabilityValues = ((DenseTensor<float>)probabilities).Buffer.ToArray();
        Marshal.Copy(probabilityValues, 0, map.Data, probabilityValues.Length);
        Cv2.Threshold(map, mask, .3f, 255, ThresholdTypes.Binary);
        mask.ConvertTo(mask, MatType.CV_8UC1);
        using var kernel = Cv2.GetStructuringElement(MorphShapes.Rect, new Size(2, 2));
        Cv2.Dilate(mask, mask, kernel);
        Cv2.FindContours(mask, out Point[][] contours, out _, RetrievalModes.List, ContourApproximationModes.ApproxSimple);
        var boxes = new List<Point2f[]>();
        foreach (var contour in contours.Take(1000))
        {
            cancellationToken.ThrowIfCancellationRequested();
            var rectangle = Cv2.MinAreaRect(contour);
            if (Math.Min(rectangle.Size.Width, rectangle.Size.Height) < 3) continue;
            var points = Order(rectangle.Points());
            var x1 = Math.Clamp((int)Math.Floor(points.Min(p => p.X)), 0, mapWidth - 1);
            var y1 = Math.Clamp((int)Math.Floor(points.Min(p => p.Y)), 0, mapHeight - 1);
            var x2 = Math.Clamp((int)Math.Ceiling(points.Max(p => p.X)), 0, mapWidth - 1);
            var y2 = Math.Clamp((int)Math.Ceiling(points.Max(p => p.Y)), 0, mapHeight - 1);
            using var scoreMask = Mat.Zeros(y2 - y1 + 1, x2 - x1 + 1, MatType.CV_8UC1).ToMat();
            Cv2.FillPoly(scoreMask, [points.Select(p => new Point((int)(p.X - x1), (int)(p.Y - y1))).ToArray()], Scalar.All(1));
            using var scoreMap = new Mat(map, new Rect(x1, y1, scoreMask.Width, scoreMask.Height));
            if (Cv2.Mean(scoreMap, scoreMask).Val0 < .5) continue;
            var distance = rectangle.Size.Width * rectangle.Size.Height * 1.6f /
                (2 * (rectangle.Size.Width + rectangle.Size.Height));
            // DB expands the minimum rectangle by area * unclip_ratio / perimeter.
            var expanded = new RotatedRect(rectangle.Center,
                new Size2f(rectangle.Size.Width + 2 * distance, rectangle.Size.Height + 2 * distance), rectangle.Angle);
            if (Math.Min(expanded.Size.Width, expanded.Size.Height) < 5) continue;
            var box = Order(expanded.Points()).Select(p => new Point2f(
                Math.Clamp((float)Math.Round(p.X / mapWidth * bgr.Width), 0, bgr.Width - 1),
                Math.Clamp((float)Math.Round(p.Y / mapHeight * bgr.Height), 0, bgr.Height - 1))).ToArray();
            if (Distance(box[0], box[1]) <= 3 || Distance(box[0], box[3]) <= 3) continue;
            boxes.Add(box);
        }
        boxes = boxes.OrderBy(b => b[0].Y).ThenBy(b => b[0].X).ToList();
        for (var i = 0; i < boxes.Count - 1; i++)
            for (var j = i; j >= 0; j--)
            {
                if (Math.Abs(boxes[j + 1][0].Y - boxes[j][0].Y) >= 10 || boxes[j + 1][0].X >= boxes[j][0].X) break;
                (boxes[j], boxes[j + 1]) = (boxes[j + 1], boxes[j]);
            }
        return boxes;
    }

    private static Point2f[] Order(Point2f[] points)
    {
        var sorted = points.OrderBy(p => p.X).ToArray();
        var left = sorted[..2].OrderBy(p => p.Y).ToArray();
        var right = sorted[2..].OrderBy(p => p.Y).ToArray();
        return [left[0], right[0], right[1], left[1]];
    }

    internal static double Distance(Point2f a, Point2f b) => Math.Sqrt(Math.Pow(a.X - b.X, 2) + Math.Pow(a.Y - b.Y, 2));
    public void Dispose() => session.Dispose();
}
