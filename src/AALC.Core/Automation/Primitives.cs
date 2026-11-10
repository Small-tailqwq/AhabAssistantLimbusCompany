namespace AALC.Core.Automation;

public enum GameKey { Escape, Enter, P, Space, Up, Down, Right, W }
public enum SearchMode { Clam, Normal, Aggressive }
public readonly record struct PixelRect(int X, int Y, int Width, int Height)
{
    public int Right => X + Width;
    public int Bottom => Y + Height;
    public bool Contains(int x, int y) => x >= X && x < Right && y >= Y && y < Bottom;
}
public readonly record struct PixelPoint(int X, int Y);
public sealed record FrameIdentity(long Id, int Width, int Height, long Window, long CapturedAt);
