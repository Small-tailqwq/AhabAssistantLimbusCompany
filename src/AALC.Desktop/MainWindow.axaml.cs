using System.Diagnostics;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Markup.Xaml;
using Avalonia.Platform.Storage;
using Avalonia.Threading;
using SukiUI.Controls;

namespace AALC.Desktop;

public partial class MainWindow : Window
{
    private bool closing;
    public MainWindow()
    {
        AvaloniaXamlLoader.Load(this);
    }

    public MainWindow(MainViewModel viewModel) : this()
    {
        DataContext = viewModel;
        var navigation = this.FindControl<SukiSideMenu>("Navigation")!;
        var monitor = this.FindControl<SukiSideMenuItem>("MonitorItem")!;
        navigation.SelectedItem = viewModel.SelectedStartPage?.Key switch
        {
            "mirror" => this.FindControl<SukiSideMenuItem>("MirrorItem"),
            "monitor" => monitor,
            "launch" => this.FindControl<SukiSideMenuItem>("LaunchItem"),
            _ => this.FindControl<SukiSideMenuItem>("DailyItem")
        };
        viewModel.MonitorRequested += () => navigation.SelectedItem = monitor;
        navigation.PropertyChanged += (_, change) =>
        {
            if (change.Property == SukiSideMenu.SelectedItemProperty) viewModel.Error = "";
        };
        // 窗口查找放到首帧之后，不计入启动就绪时间。
        Opened += (_, _) => Dispatcher.UIThread.Post(viewModel.FindWindowsAtStartup, DispatcherPriority.SystemIdle);
        Opened += (_, _) => Dispatcher.UIThread.Post(async () => await viewModel.FindGameAtStartupAsync(), DispatcherPriority.SystemIdle);
        Opened += (_, _) => Dispatcher.UIThread.Post(viewModel.RestoreCloneAutoruns, DispatcherPriority.SystemIdle);
    }

    private async void BrowseGameDirectory(object? sender, RoutedEventArgs e)
    {
        var viewModel = (MainViewModel)DataContext!;
        try
        {
            var folders = await StorageProvider.OpenFolderPickerAsync(new() { Title = "选择 Limbus Company 安装目录" });
            if (folders.Count > 0) viewModel.GameDirectory = folders[0].TryGetLocalPath() ?? "";
        }
        catch (Exception exception) { viewModel.Error = exception.Message; }
    }

    protected override async void OnClosing(WindowClosingEventArgs e)
    {
        base.OnClosing(e);
        var viewModel = (MainViewModel)DataContext!;
        if (closing || !viewModel.IsRunning && !viewModel.CloneActive) return;
        e.Cancel = true;
        closing = true;
        var started = Stopwatch.GetTimestamp();
        viewModel.Stop();
        try
        {
            if (viewModel.ActiveRun is { } run) await run.WaitAsync(TimeSpan.FromSeconds(viewModel.CloneActive ? 3 : 5));
        }
        catch (TimeoutException) { }
        // 超时后直接退出：管道断开时宿主与分身内进程会自行收尾并注销。
        await viewModel.ShutdownCloneAsync(TimeSpan.FromSeconds(5) - Stopwatch.GetElapsedTime(started));
        Close();
    }
}
