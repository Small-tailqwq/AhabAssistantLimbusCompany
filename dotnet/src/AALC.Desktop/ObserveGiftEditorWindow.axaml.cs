using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Markup.Xaml;

namespace AALC.Desktop;

public partial class ObserveGiftEditorWindow : Window
{
    public ObserveGiftEditorWindow() => AvaloniaXamlLoader.Load(this);
    private void Cancel(object? sender, RoutedEventArgs e) => Close(false);
    private void Apply(object? sender, RoutedEventArgs e) => Close(true);
}
