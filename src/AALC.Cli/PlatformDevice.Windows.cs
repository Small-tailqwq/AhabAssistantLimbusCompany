using AALC.Platform.Windows;
using AALC.Runtime.Automation;

namespace AALC.Cli;

internal static class PlatformDevice
{
    public const string Identifier = "进程ID";
    public const string Commands = "windows | daily | daily-battle | mirror | clone-verify | clone-mirror";

    public static Task<IAttachedGame> AttachAsync(string id, CancellationToken token)
    {
        token.ThrowIfCancellationRequested();
        if (!int.TryParse(id, out var pid)) throw new ArgumentException("游戏进程 ID 无效");
        var selected = GameWindow.Find().SingleOrDefault(window => window.ProcessId == pid)
            ?? throw new InvalidOperationException("未找到指定的 Limbus Company 窗口");
        return Task.FromResult<IAttachedGame>(new GameWindow(selected));
    }
}
