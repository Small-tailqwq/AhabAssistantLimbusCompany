using System.Diagnostics;
using System.Text.Json;
using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using Avalonia.Threading;
using AALC.Runtime.Configuration;

namespace AALC.Desktop;

public partial class App : Application
{
    public override void Initialize() => AvaloniaXamlLoader.Load(this);

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            var args = desktop.Args ?? [];
            string? Argument(string key)
            {
                var index = Array.IndexOf(args, key);
                return index >= 0 && index + 1 < args.Length ? args[index + 1] : null;
            }
            var profile = Argument("--profile");
            var viewModel = new MainViewModel(profile is null ? SettingsStore.OpenDefault() : new SettingsStore(profile));
            var window = new MainWindow(viewModel);
            desktop.MainWindow = window;
            viewModel.StartAgentServer();
            desktop.Exit += (_, _) => { viewModel.DisposeAgentServer(); ThumbnailCache.Dispose(); viewModel.DisposeClone(); };
            var reported = false;
            window.Opened += (_, _) =>
            {
                if (reported) return;
                reported = true;
                window.RequestAnimationFrame(_ => window.RequestAnimationFrame(_ => Dispatcher.UIThread.Post(() =>
                {
                    if (Argument("--startup-report") is { } report)
                    {
                        var path = Path.GetFullPath(report);
                        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                        File.WriteAllText(path, JsonSerializer.Serialize(new
                        {
                            kind = "avalonia-suki", readyMonotonicSeconds = (double)Stopwatch.GetTimestamp() / Stopwatch.Frequency,
                            windowVisible = window.IsVisible,
                            loadedAssemblies = AppDomain.CurrentDomain.GetAssemblies().Select(a => a.GetName().Name).Order().ToArray(),
                            measurement = "Opened, two animation-frame callbacks, then ApplicationIdle callback"
                        }));
                    }
                    if (args.Contains("--exit-after-ready")) desktop.Shutdown();
                }, DispatcherPriority.ApplicationIdle)));
            };
        }
        base.OnFrameworkInitializationCompleted();
    }
}
