using System.Text;
using Microsoft.ML.OnnxRuntime;
using Microsoft.ML.OnnxRuntime.Tensors;
using OpenCvSharp;

namespace AALC.Vision;

public sealed record TextRecognition(string Text, double Score, int[] InputShape, int[] Tokens, float[] Probabilities);

/// <summary>Recognizes one horizontal text crop with the Chinese PP-OCRv4 recognition model.</summary>
public sealed class TextRecognizer : IDisposable
{
    private readonly InferenceSession session;
    private readonly string[] characters;

    public TextRecognizer(string modelPath, string dictionaryPath)
    {
        session = new InferenceSession(modelPath);
        var dictionary = session.ModelMetadata.CustomMetadataMap.TryGetValue("character", out var embedded)
            ? embedded.Split('\n').Select(s => s.TrimEnd('\r')).ToArray()
            : File.ReadAllLines(dictionaryPath, Encoding.UTF8);
        if (dictionary.Length > 0 && dictionary[^1] == "") dictionary = dictionary[..^1];
        characters = ["blank", .. dictionary, " "];
    }

    public TextRecognition Recognize(Mat bgrCrop)
    {
        if (bgrCrop.Empty() || bgrCrop.Type() != MatType.CV_8UC3)
            throw new ArgumentException("OCR 需要非空 BGR 三通道文字裁剪");
        using var gray = new Mat();
        Cv2.CvtColor(bgrCrop, gray, ColorConversionCodes.BGR2GRAY);
        var distinct = new HashSet<byte>();
        for (var y = 0; y < gray.Height && distinct.Count <= 2; y++)
            for (var x = 0; x < gray.Width && distinct.Count <= 2; x++) distinct.Add(gray.At<byte>(y, x));
        if (distinct.Count > 2)
        {
            using var clahe = Cv2.CreateCLAHE(2, new Size(8, 8));
            using var enhanced = new Mat();
            clahe.Apply(gray, enhanced);
            enhanced.CopyTo(gray);
        }
        using var bgr = new Mat();
        Cv2.CvtColor(gray, bgr, ColorConversionCodes.GRAY2BGR);
        return RecognizePrepared(bgr, CancellationToken.None);
    }

    internal TextRecognition RecognizePrepared(Mat bgr, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        const int height = 48;
        var ratio = bgr.Width / (double)bgr.Height;
        var width = (int)(height * Math.Max(320.0 / height, ratio));
        var resizedWidth = Math.Min(width, (int)Math.Ceiling(height * ratio));
        using var resized = new Mat();
        Cv2.Resize(bgr, resized, new Size(resizedWidth, height));
        var tensor = new DenseTensor<float>(new[] { 1, 3, height, width });
        for (var y = 0; y < height; y++)
            for (var x = 0; x < resizedWidth; x++)
            {
                var pixel = resized.At<Vec3b>(y, x);
                for (var c = 0; c < 3; c++) tensor[0, c, y, x] = (pixel[c] / 255f - 0.5f) / 0.5f;
            }
        using var run = new RunOptions();
        using var cancellation = cancellationToken.Register(() => run.Terminate = true);
        IDisposableReadOnlyCollection<DisposableNamedOnnxValue> inference;
        try
        {
            inference = session.Run([NamedOnnxValue.CreateFromTensor(session.InputMetadata.Keys.First(), tensor)],
                session.OutputMetadata.Keys.ToArray(), run);
        }
        catch (OnnxRuntimeException) when (cancellationToken.IsCancellationRequested)
        {
            throw new OperationCanceledException(cancellationToken);
        }
        using var outputs = inference;
        cancellationToken.ThrowIfCancellationRequested();
        var prediction = outputs.First().AsTensor<float>();
        if (prediction.Rank != 3 || prediction.Dimensions[0] != 1 || prediction.Dimensions[2] != characters.Length)
            throw new InvalidDataException("OCR 模型输出与 PP-OCRv4 字典不匹配");
        var steps = prediction.Dimensions[1];
        var logits = ((DenseTensor<float>)prediction).Buffer.Span;
        var tokens = new int[steps];
        var probabilities = new float[steps];
        var text = new StringBuilder();
        var confidence = new List<double>();
        for (var t = 0; t < steps; t++)
        {
            var best = 0;
            var offset = t * characters.Length;
            for (var c = 1; c < characters.Length; c++)
                if (logits[offset + c] > logits[offset + best]) best = c;
            tokens[t] = best;
            probabilities[t] = logits[offset + best];
            if (best == 0 || (t > 0 && best == tokens[t - 1])) continue;
            text.Append(characters[best]);
            confidence.Add(Math.Round((double)probabilities[t], 5, MidpointRounding.ToEven));
        }
        return new(text.ToString(), confidence.Count == 0 ? 0 : Math.Round(confidence.Average(), 5, MidpointRounding.ToEven),
            [1, 3, height, width], tokens, probabilities);
    }

    public void Dispose() => session.Dispose();
}
