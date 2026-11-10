using Avalonia.Interactivity;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Markup.Xaml;

namespace AALC.Desktop;

public partial class ThemeWeightEditorWindow : Window
{
    public ThemeWeightEditorWindow()
    {
        AvaloniaXamlLoader.Load(this);
        Opened += (_, _) => this.FindControl<TextBox>("SearchBox")!.Focus();
    }
    public ThemeWeightEditorWindow(ThemeWeightEditorModel model) : this()
    {
        DataContext = model;
        Opened += (_, _) => model.Load();
        Closed += (_, _) => model.Dispose();
    }

    protected override void OnKeyDown(KeyEventArgs e)
    {
        base.OnKeyDown(e);
        if (e.Handled || e.Key != Key.Escape) return;
        e.Handled = true;
        Close(false);
    }

    private void Apply(object? sender, RoutedEventArgs e) => Close(true);
    private void Cancel(object? sender, RoutedEventArgs e) => Close(false);
}
