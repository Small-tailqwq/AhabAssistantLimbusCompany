using System.Diagnostics;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Markup.Xaml;
using Avalonia.Controls.Templates;
using Avalonia.Threading;
using SukiUI.Controls;

namespace AALC.Desktop;

public partial class MainWindow : Window
{
    private bool closing;
    internal string? CurrentPage => (this.FindControl<SukiSideMenu>("Navigation")?.SelectedItem as SukiSideMenuItem)?.Header?.ToString();
    public MainWindow()
    {
        AvaloniaXamlLoader.Load(this);
    }

    public MainWindow(MainViewModel viewModel) : this()
    {
        DataContext = viewModel;
        var navigation = this.FindControl<SukiSideMenu>("Navigation")!;
        var monitor = this.FindControl<SukiSideMenuItem>("MonitorItem")!;
#if WINDOWS
        SukiSideMenuItem Insert(int index, string key)
        {
            var template = (IDataTemplate)this.FindResource(key)!;
            var item = (SukiSideMenuItem)template.Build(viewModel)!;
            navigation.Items.Insert(index, item);
            return item;
        }
        var launch = Insert(0, "LaunchPage");
        var daily = Insert(1, "DailyPage");
        var mirror = Insert(2, "MirrorPage");
        Insert(4, "ClonePage");
        var startPage = viewModel.SelectedStartPage?.Key switch
        {
            "mirror" => mirror,
            "monitor" => monitor,
            "launch" => launch,
            _ => daily
        };
        Opened += (_, _) => Dispatcher.UIThread.Post(viewModel.FindWindowsAtStartup, DispatcherPriority.SystemIdle);
        Opened += (_, _) => Dispatcher.UIThread.Post(async () => await viewModel.FindGameAtStartupAsync(), DispatcherPriority.SystemIdle);
        Opened += (_, _) => Dispatcher.UIThread.Post(viewModel.RestoreCloneAutoruns, DispatcherPriority.SystemIdle);
#else
        var settings = this.FindControl<SukiSideMenuItem>("SettingsItem")!;
        viewModel.ConnectionSettingsRequested += () => navigation.SelectedItem = settings;
        var startPage = viewModel.SelectedStartPage?.Key switch
        {
            "monitor" => monitor,
            "replay" => this.FindControl<SukiSideMenuItem>("ReplayItem"),
            "settings" => settings,
            _ => this.FindControl<SukiSideMenuItem>("ToolsItem")
        };
        void ApplyMotion() => Classes.Set("motion", !Mac.MacDisplaySettings.ReduceMotion);
        ApplyMotion();
        Activated += (_, _) => ApplyMotion();
#endif
        // SukiSideMenu 初始化模板时会选中第一项；在模板就绪后应用启动页。
        navigation.Loaded += (_, _) => navigation.SelectedItem = startPage;
        viewModel.MonitorRequested += () => navigation.SelectedItem = monitor;
        navigation.PropertyChanged += (_, change) =>
        {
            if (change.Property == SukiSideMenu.SelectedItemProperty) viewModel.Error = "";
        };
    }

    protected override async void OnClosing(WindowClosingEventArgs e)
    {
        base.OnClosing(e);
        var viewModel = (MainViewModel)DataContext!;
        if (closing || !viewModel.IsRunning
#if WINDOWS
            && !viewModel.CloneActive
#endif
            ) return;
        e.Cancel = true;
        closing = true;
#if WINDOWS
        var started = Stopwatch.GetTimestamp();
#endif
        viewModel.Stop();
        try
        {
            var timeout = 5;
#if WINDOWS
            if (viewModel.CloneActive) timeout = 3;
#endif
            if (viewModel.ActiveRun is { } run) await run.WaitAsync(TimeSpan.FromSeconds(timeout));
        }
        catch (TimeoutException) { }
        catch (OperationCanceledException) { }
        // 超时后直接退出：管道断开时宿主与分身内进程会自行收尾并注销。
#if WINDOWS
        await viewModel.ShutdownCloneAsync(TimeSpan.FromSeconds(5) - Stopwatch.GetElapsedTime(started));
#endif
        Close();
    }
}
