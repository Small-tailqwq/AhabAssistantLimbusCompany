using System.Globalization;
using System.Text.RegularExpressions;

namespace AALC.Core.Features.Daily;

public static partial class DailyRewardRules
{
    public static bool TryProgress(string text, out int current, out int total)
    {
        current = total = 0;
        var match = ProgressPattern().Match(text);
        return match.Success && int.TryParse(match.Groups[1].Value, out current) && int.TryParse(match.Groups[2].Value, out total);
    }

    public static int RefillTierForPrice(int price) => price switch { 26 => 1, 52 => 2, 78 => 3, 104 => 4, _ => 0 };

    public static bool GrandetReady(string text)
    {
        var normalized = Regex.Replace(text, "[oOdD]", "0");
        var match = CountdownPattern().Match(normalized);
        return match.Success && int.Parse(match.Groups[1].Value, CultureInfo.InvariantCulture) >= 5
            && int.Parse(match.Groups[2].Value, CultureInfo.InvariantCulture) is >= 20 and < 60;
    }

    public static double OrangeRatio(byte[] bgra, int width, int height, PixelRect region)
    {
        var hits = 0;
        var count = 0;
        for (var y = Math.Max(0, region.Y); y < Math.Min(height, region.Bottom); y++)
            for (var x = Math.Max(0, region.X); x < Math.Min(width, region.Right); x++)
            {
                var (h, s, v) = Hsv(bgra, (y * width + x) * 4);
                if (h > 5 && h < 35 && s > 80 && v > 60) hits++;
                count++;
            }
        return count == 0 ? 0 : hits / (double)count;
    }

    public static bool EnabledColor(byte[] bgra, int width, int height, PixelRect region)
    {
        var saturation = 0.0;
        var brightness = 0.0;
        var count = 0;
        for (var y = Math.Max(0, region.Y); y < Math.Min(height, region.Bottom); y++)
            for (var x = Math.Max(0, region.X); x < Math.Min(width, region.Right); x++)
            {
                var (_, s, v) = Hsv(bgra, (y * width + x) * 4);
                saturation += s;
                brightness += v;
                count++;
            }
        return count > 0 && saturation / count >= 15 && brightness / count >= 65;
    }

    private static (double H, double S, double V) Hsv(byte[] pixels, int offset)
    {
        var b = (double)pixels[offset];
        var g = (double)pixels[offset + 1];
        var r = (double)pixels[offset + 2];
        var max = Math.Max(r, Math.Max(g, b));
        var min = Math.Min(r, Math.Min(g, b));
        var difference = max - min;
        var hue = difference == 0 ? 0 : max == r ? (g - b) / difference : max == g ? 2 + (b - r) / difference : 4 + (r - g) / difference;
        if (hue < 0) hue += 6;
        return (Math.Round(hue * 30), max == 0 ? 0 : Math.Round(difference * 255 / max), max);
    }

    [GeneratedRegex(@"(\d+)\s*/\s*(\d+)")]
    private static partial Regex ProgressPattern();
    [GeneratedRegex(@"(\d{1,2}):(\d{2})")]
    private static partial Regex CountdownPattern();
}
