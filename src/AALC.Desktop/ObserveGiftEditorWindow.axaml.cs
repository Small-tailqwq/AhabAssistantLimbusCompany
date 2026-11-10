using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Input;
using Avalonia.Markup.Xaml;
using Avalonia.VisualTree;

namespace AALC.Desktop;

public partial class ObserveGiftEditorWindow : Window
{
    public ObserveGiftEditorWindow()
    {
        AvaloniaXamlLoader.Load(this);
        Opened += (_, _) => this.GetVisualDescendants().OfType<Button>().FirstOrDefault()?.Focus();
    }

    protected override void OnKeyDown(KeyEventArgs e)
    {
        base.OnKeyDown(e);
        if (e.Handled || e.Key != Key.Escape) return;
        e.Handled = true;
        Close(false);
    }

    private void Cancel(object? sender, RoutedEventArgs e) => Close(false);
    private void Apply(object? sender, RoutedEventArgs e) => Close(true);
}
