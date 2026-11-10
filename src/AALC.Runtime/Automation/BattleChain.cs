using AALC.Core.Automation;

namespace AALC.Runtime.Automation;

public static class BattleChain
{
    private static readonly (int B, int G, int R)[] SinColors =
    [ (0, 0, 254), (239, 197, 26), (49, 205, 251), (0, 108, 254),
        (213, 75, 1), (1, 228, 146), (222, 1, 150) ];

    public static IReadOnlyList<PixelPoint>? Plan(GameFrame frame)
    {
        if (frame.Find("battle/gear_left.png") is not { } left || frame.Find("battle/gear_right.png") is not { } right)
            return null;
        var scale = frame.Scale;
        var start = left.Center.X + 94 * scale;
        var end = right.Center.X - 100 * scale;
        var bottom = left.Center.Y - 37 * scale;
        var count = (int)((end - start) / (145 * scale));
        if (count is < 1 or > 12) return null;
        if (count >= 10) start += 50 * scale;
        var x1 = (int)Math.Round(start); var x2 = (int)Math.Round(end);
        var y1 = (int)Math.Round(bottom - 15 * scale); var y2 = (int)Math.Round(bottom);
        if (x1 < 0 || y1 < 0 || x2 > frame.Identity.Width || y2 > frame.Identity.Height || x2 <= x1 || y2 <= y1)
            return null;
        var skills = ThirdSkills(frame, new(x1, y1, x2 - x1, y2 - y1), count);
        var path = new List<PixelPoint> { left.Center };
        for (var index = 0; index < count; index++)
        {
            var center = count / 2;
            var adjustment = (center - index) * 8 * scale;
            var x = left.Center.X + (220 - 4.5 * count + 161 * index) * scale + adjustment;
            // 按下齿轮后技能行下移，两排分别在齿轮下方 125 与 250（1440p）。
            var y = left.Center.Y + 125 * scale;
            if (skills.Contains(index + 1))
            {
                y += 125 * scale;
                x -= (center - index - 1) * 8 * scale;
            }
            path.Add(new((int)Math.Round(x), (int)Math.Round(y)));
        }
        path.Add(new((int)Math.Round(right.Center.X + 5 * count * scale), (int)Math.Round(right.Center.Y + 150 * scale)));
        return path.All(point => point.X >= 0 && point.X < frame.Identity.Width && point.Y >= 0 && point.Y < frame.Identity.Height)
            ? path : null;
    }

    private static HashSet<int> ThirdSkills(GameFrame frame, PixelRect crop, int count)
    {
        var length = crop.Width * crop.Height;
        var histograms = new int[3, 256];
        for (var y = 0; y < crop.Height; y++)
            for (var x = 0; x < crop.Width; x++)
            {
                var offset = ((crop.Y + y) * frame.Identity.Width + crop.X + x) * 4;
                for (var channel = 0; channel < 3; channel++) histograms[channel, frame.Pixels.Bgra[offset + channel]]++;
            }
        var median = Enumerable.Range(0, 3).Select(channel => Median(histograms, channel, length)).ToArray();
        var result = new HashSet<int>();
        foreach (var color in SinColors)
        {
            var target = new[] { (int)(median[0] * .45 + color.B * .55),
                (int)(median[1] * .45 + color.G * .55), (int)(median[2] * .45 + color.R * .55) };
            var mask = new bool[length];
            for (var y = 0; y < crop.Height; y++)
                for (var x = 0; x < crop.Width; x++)
                {
                    var offset = ((crop.Y + y) * frame.Identity.Width + crop.X + x) * 4;
                    mask[y * crop.Width + x] = Math.Abs(frame.Pixels.Bgra[offset] - target[0]) <= 40
                        && Math.Abs(frame.Pixels.Bgra[offset + 1] - target[1]) <= 40
                        && Math.Abs(frame.Pixels.Bgra[offset + 2] - target[2]) <= 40;
                }
            mask = Morph(mask, crop.Width, crop.Height, true);
            for (var i = 0; i < 3; i++) mask = Morph(mask, crop.Width, crop.Height, false);
            var centers = Clusters(mask, crop.Width, crop.Height);
            while (centers.Count > 0)
            {
                var last = centers[^1]; centers.RemoveAt(centers.Count - 1);
                var group = centers.Where(point => Math.Pow(point.X - last.X, 2) + Math.Pow(point.Y - last.Y, 2) <= 67 * 67).ToArray();
                foreach (var point in group) centers.Remove(point);
                var x = (last.X + group.Sum(point => point.X)) / (group.Length + 1);
                var index = (int)Math.Round(x / (145 * frame.Scale));
                if (index >= 1 && index <= count) result.Add(index);
            }
        }
        return result;
    }

    private static int Median(int[,] histogram, int channel, int length)
    {
        var seen = 0; var low = -1;
        for (var value = 0; value < 256; value++)
        {
            seen += histogram[channel, value];
            if (low < 0 && seen > (length - 1) / 2) low = value;
            if (seen > length / 2) return (low + value) / 2;
        }
        return 0;
    }

    private static bool[] Morph(bool[] source, int width, int height, bool erode)
    {
        var result = new bool[source.Length];
        for (var y = 0; y < height; y++)
            for (var x = 0; x < width; x++)
            {
                var value = erode;
                for (var dy = -1; dy <= 1; dy++)
                    for (var dx = -1; dx <= 1; dx++)
                    {
                        var xx = x + dx; var yy = y + dy;
                        var neighbor = xx < 0 || xx >= width || yy < 0 || yy >= height ? erode : source[yy * width + xx];
                        value = erode ? value && neighbor : value || neighbor;
                    }
                result[y * width + x] = value;
            }
        return result;
    }

    private static List<(double X, double Y)> Clusters(bool[] mask, int width, int height)
    {
        var visited = new bool[mask.Length]; var result = new List<(double X, double Y)>();
        for (var y = 0; y < height; y++)
            for (var x = 0; x < width; x++)
            {
                var first = y * width + x;
                if (!mask[first] || visited[first]) continue;
                var queue = new Queue<int>(); queue.Enqueue(first); visited[first] = true;
                var area = 0; double totalX = 0, totalY = 0;
                while (queue.TryDequeue(out var point))
                {
                    var xx = point % width; var yy = point / width;
                    area++; totalX += xx; totalY += yy;
                    for (var dy = -1; dy <= 1; dy++)
                        for (var dx = -1; dx <= 1; dx++)
                        {
                            var nx = xx + dx; var ny = yy + dy;
                            if (nx < 0 || nx >= width || ny < 0 || ny >= height) continue;
                            var next = ny * width + nx;
                            if (mask[next] && !visited[next]) { visited[next] = true; queue.Enqueue(next); }
                        }
                }
                if (area < 10) continue;
                var cx = (int)(totalX / area); var nearby = 0;
                for (var yy = 0; yy < Math.Min(13, height); yy++)
                    for (var xx = Math.Max(0, cx - 33); xx < Math.Min(width, cx + 33); xx++)
                        if (mask[yy * width + xx]) nearby++;
                if (nearby >= 26) result.Add((totalX / area, totalY / area));
            }
        return result.OrderBy(point => point.X).ToList();
    }
}
