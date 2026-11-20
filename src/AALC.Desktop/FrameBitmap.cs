using System.Runtime.InteropServices;
using AALC.Runtime.Mail;
using Avalonia;
using Avalonia.Media.Imaging;
using Avalonia.Platform;

namespace AALC.Desktop;

internal static class FrameBitmap
{
    public static WriteableBitmap Create(PixelFrame frame)
    {
        var bitmap = new WriteableBitmap(new PixelSize(frame.Identity.Width, frame.Identity.Height),
            new Vector(96, 96), PixelFormat.Bgra8888, AlphaFormat.Opaque);
        using var buffer = bitmap.Lock();
        for (var y = 0; y < frame.Identity.Height; y++)
            Marshal.Copy(frame.Bgra, y * frame.Identity.Width * 4, buffer.Address + y * buffer.RowBytes, frame.Identity.Width * 4);
        return bitmap;
    }
}
