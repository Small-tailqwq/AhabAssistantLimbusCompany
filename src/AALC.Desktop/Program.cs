using System.Runtime.CompilerServices;
using AALC.Runtime.DesktopClone;
using Avalonia;

namespace AALC.Desktop;

internal static class Program
{
    [STAThread]
    public static int Main(string[] args)
    {
#if WINDOWS
        if (args.Contains(CloneProtocol.WorkerFlag)) return CloneWorker.Run(args);
#else
        if (args.Contains(CloneProtocol.WorkerFlag))
        {
            Console.Error.WriteLine("桌面分身仅支持 Windows。");
            return 2;
        }
#endif
        return RunDesktop(args);
    }

    // 独立方法：分身内进程走到 Main 时不解析 Avalonia 类型，也就不加载它的程序集。
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static int RunDesktop(string[] args) => BuildAvaloniaApp().StartWithClassicDesktopLifetime(args);

    public static AppBuilder BuildAvaloniaApp() => AppBuilder.Configure<App>()
#if WINDOWS
        .UsePlatformDetect().WithDeveloperTools()
#else
        .UseAvaloniaNative().UseSkia().UseHarfBuzz()
#endif
        .LogToTrace();
}
