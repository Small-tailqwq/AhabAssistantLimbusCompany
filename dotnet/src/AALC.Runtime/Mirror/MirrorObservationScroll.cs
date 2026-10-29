using AALC.Runtime.Mail;

namespace AALC.Runtime.Mirror;

public static class MirrorObservationScroll
{
    public static int? MeasureUpward(PixelFrame before, PixelFrame after, PixelRect area, int maximum)
    {
        if (before.Identity.Width != after.Identity.Width || before.Identity.Height != after.Identity.Height) return null;
        var width = before.Identity.Width;
        var height = before.Identity.Height;
        var limit = Math.Min(maximum, area.Height - 40);
        if (limit < 0 || area.X < 0 || area.Y < 0 || area.Right > width || area.Bottom > height) return null;
        var samples = new List<int>();
        var step = Math.Max(2, height / 240);
        // 亮色卡框和文字随列表移动，深色固定底纹不参与位移估计。
        for (var y = area.Y + limit; y < area.Bottom; y += step)
            for (var x = area.X; x < area.Right; x += step)
            {
                var index = (y * width + x) * 4;
                if (Math.Max(before.Bgra[index], Math.Max(before.Bgra[index + 1], before.Bgra[index + 2])) > 150)
                    samples.Add(index);
            }
        if (samples.Count < 32) return null;
        var best = double.MaxValue;
        var unchanged = double.MaxValue;
        var displacement = 0;
        for (var offset = 0; offset <= limit; offset++)
        {
            long error = 0;
            var delta = offset * width * 4;
            foreach (var index in samples)
                for (var channel = 0; channel < 3; channel++)
                    error += Math.Abs(before.Bgra[index + channel] - after.Bgra[index - delta + channel]);
            var average = (double)error / (samples.Count * 3);
            if (offset == 0) unchanged = average;
            if (average < best) { best = average; displacement = offset; }
        }
        if (best > 24 || displacement > 0 && unchanged - best < 5) return null;
        return displacement;
    }
}
