using Avalonia.Interactivity;
using Avalonia.Controls;
using Avalonia.Markup.Xaml;

namespace AALC.Desktop;

public partial class ThemeWeightEditorWindow : Window
{
    public ThemeWeightEditorWindow() => AvaloniaXamlLoader.Load(this);
    public ThemeWeightEditorWindow(ThemeWeightEditorModel model) : this()
    {
        DataContext = model;
        Opened += (_, _) => model.Load();
        Closed += (_, _) => model.Dispose();
    }
    private void Apply(object? sender, RoutedEventArgs e) => Close(true);
    private void Cancel(object? sender, RoutedEventArgs e) => Close(false);
}
