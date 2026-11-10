namespace AALC.Runtime.Automation;

public static class GameResolution
{
    public const int DefaultWidth = 1280, DefaultHeight = 720;

    public static bool IsTooSmall(int width, int height) => width < DefaultWidth || height < DefaultHeight;
}
