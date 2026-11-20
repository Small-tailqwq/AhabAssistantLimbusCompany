using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Markup.Xaml;
using Avalonia.Platform.Storage;

namespace AALC.Desktop;

public partial class WindowsPlatformViews : ResourceDictionary
{
    public WindowsPlatformViews() => AvaloniaXamlLoader.Load(this);

    private async void BrowseGameDirectory(object? sender, RoutedEventArgs e)
    {
        if (sender is not Control { DataContext: MainViewModel model } control || TopLevel.GetTopLevel(control) is not { } window) return;
        try
        {
            var folders = await window.StorageProvider.OpenFolderPickerAsync(new() { Title = "选择 Limbus Company 安装目录" });
            if (folders.Count > 0) model.GameDirectory = folders[0].TryGetLocalPath() ?? "";
        }
        catch (Exception exception) { model.Error = exception.Message; }
    }
}
