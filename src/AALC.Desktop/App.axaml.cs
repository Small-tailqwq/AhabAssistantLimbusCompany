using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;
using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using Avalonia.Threading;
using AALC.Runtime.Configuration;

namespace AALC.Desktop;

internal sealed record StartupReport(string Kind, double ReadyMonotonicSeconds, bool WindowVisible,
    string?[] LoadedAssemblies, string Measurement);

[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
[JsonSerializable(typeof(StartupReport))]
internal partial class StartupJson : JsonSerializerContext;

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
            var store = profile is null ? SettingsStore.OpenDefault() : new SettingsStore(profile);
#if WINDOWS
            var viewModel = new MainViewModel(store);
            var window = new MainWindow(viewModel);
            viewModel.StartAgentServer();
            desktop.Exit += (_, _) => { viewModel.DisposeAgentServer(); ThumbnailCache.Dispose(); viewModel.DisposeClone(); };
#else
            var window = new Mac.EmulatorWindow(new Mac.EmulatorViewModel(store));
#endif
            desktop.MainWindow = window;
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
                        var ready = new StartupReport(OperatingSystem.IsMacOS() ? "avalonia-native" : "avalonia-suki", (double)Stopwatch.GetTimestamp() / Stopwatch.Frequency,
                            window.IsVisible, AppDomain.CurrentDomain.GetAssemblies().Select(a => a.GetName().Name).Order().ToArray(),
                            "Opened, two animation-frame callbacks, then ApplicationIdle callback");
                        File.WriteAllText(path, JsonSerializer.Serialize(ready, StartupJson.Default.StartupReport));
                    }
                    if (args.Contains("--exit-after-ready")) desktop.Shutdown();
                }, DispatcherPriority.ApplicationIdle)));
            };
        }
        base.OnFrameworkInitializationCompleted();
    }
}
