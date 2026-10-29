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
            _ => navigation.Items[0]
        };
        viewModel.MonitorRequested += () => navigation.SelectedItem = monitor;
        // 窗口查找放到首帧之后，不计入启动就绪时间。
        Opened += (_, _) => Dispatcher.UIThread.Post(viewModel.FindWindowsAtStartup, DispatcherPriority.SystemIdle);
        Opened += (_, _) => Dispatcher.UIThread.Post(async () => await viewModel.FindGameAtStartupAsync(), DispatcherPriority.SystemIdle);
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
        if (closing || !viewModel.IsRunning) return;
        e.Cancel = true;
        closing = true;
        viewModel.Stop();
        try
        {
            if (viewModel.ActiveRun is { } run) await run.WaitAsync(TimeSpan.FromSeconds(5));
        }
        catch (TimeoutException) { }
        Close();
    }
}
