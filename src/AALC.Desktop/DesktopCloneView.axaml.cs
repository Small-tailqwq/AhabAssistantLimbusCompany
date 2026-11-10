using Avalonia;
using Avalonia.Controls;
using Avalonia.Markup.Xaml;

namespace AALC.Desktop;

public partial class DesktopCloneView : UserControl
{
    public DesktopCloneView() => AvaloniaXamlLoader.Load(this);

    protected override void OnAttachedToVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnAttachedToVisualTree(e);
        (DataContext as MainViewModel)?.EnterClonePage();
    }
}
