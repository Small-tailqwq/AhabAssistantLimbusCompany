using AALC.Core.Automation;

namespace AALC.Core.Features.Mirror;

public static class MirrorMapViewport
{
    public static PixelRect Canvas(FrameIdentity frame)
    {
        var scale = frame.Height / 1440.0;
        return new((int)(80 * scale), (int)(200 * scale), frame.Width - (int)(240 * scale), (int)(1020 * scale));
    }

    public static bool Contains(FrameIdentity frame, PixelRect glyph)
    {
        var canvas = Canvas(frame);
        return glyph.X >= canvas.X && glyph.Right <= canvas.Right && glyph.Y >= canvas.Y && glyph.Bottom <= canvas.Bottom;
    }

    public static PixelPoint? Shift(MirrorMapSnapshot current, PixelRect busBounds, PixelRect? required = null,
        bool probeRight = false)
    {
        if (current.Nodes.Count == 0 && required is null) return null;
        var canvas = Canvas(current.Frame);
        var bounds = current.Nodes.Select(node => node.Bounds).ToArray();
        if (required is { } target && !Contains(current.Frame, target)) bounds = [target];
        if (bounds.Length == 0) return null;
        var left = bounds.Min(rect => rect.X);
        var right = bounds.Max(rect => rect.Right);
        var top = bounds.Min(rect => rect.Y);
        var bottom = bounds.Max(rect => rect.Bottom);
        static int Offset(int minimum, int maximum, int safeMinimum, int safeMaximum)
        {
            var lower = safeMinimum - minimum;
            var upper = safeMaximum - maximum;
            return lower <= upper ? Math.Clamp(0, lower, upper) : lower > 0 ? lower : upper < 0 ? upper : 0;
        }
        var scale = current.Frame.Height / 1440.0;
        var dx = Math.Clamp(Offset(left, right, canvas.X, canvas.Right), -(int)(340 * scale), (int)(340 * scale));
        var dy = Math.Clamp(Offset(top, bottom, canvas.Y, canvas.Bottom), -(int)(220 * scale), (int)(220 * scale));
        var lower = canvas.Y - top;
        var upper = canvas.Bottom - bottom;
        if (dy != 0 && lower <= upper)
        {
            var margin = (int)Math.Ceiling(32 * scale);
            dy = Math.Clamp(Math.Clamp(dy + Math.Sign(dy) * margin, lower, upper), -(int)(220 * scale), (int)(220 * scale));
        }
        if (probeRight && canvas.Right - right <= 160 * scale && (required is null || Contains(current.Frame, required.Value)))
            dx = -Math.Min((int)(640 * scale), canvas.Width / 4);
        // Tiny pans can be absorbed by the game's drag threshold.
        var minimum = (int)Math.Ceiling(64 * scale);
        if (dx != 0) dx = Math.Sign(dx) * Math.Max(Math.Abs(dx), minimum);
        if (dy != 0) dy = Math.Sign(dy) * Math.Max(Math.Abs(dy), minimum);
        // The bus has its own template bounds; it need not lie inside the glyph canvas.
        dx = Math.Clamp(dx, Math.Min(0, 2 - busBounds.X), Math.Max(0, current.Frame.Width - 2 - busBounds.Right));
        dy = Math.Clamp(dy, Math.Min(0, 2 - busBounds.Y), Math.Max(0, current.Frame.Height - 2 - busBounds.Bottom));
        if (Math.Abs(dx) < minimum) dx = 0;
        if (Math.Abs(dy) < minimum) dy = 0;
        return dx == 0 && dy == 0 ? null : new(dx, dy);
    }

    public static PixelRect ProjectForCamera(MirrorRouteNode vertex, MirrorMapSnapshot current)
    {
        var scale = current.Frame.Height / 1440.0;
        return new(current.Bus.X + (int)Math.Round(vertex.Bounds.X * scale),
            current.Bus.Y + (int)Math.Round((vertex.Bounds.Y + 50) * scale),
            (int)Math.Round(vertex.Bounds.Width * scale), (int)Math.Round(vertex.Bounds.Height * scale));
    }
}
