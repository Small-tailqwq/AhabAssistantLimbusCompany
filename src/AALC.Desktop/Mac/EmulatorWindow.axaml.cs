using Avalonia.Controls;
using Avalonia.Markup.Xaml;

namespace AALC.Desktop.Mac;

public partial class EmulatorWindow : Window
{
    private bool closing;
    public EmulatorWindow()
    {
        AvaloniaXamlLoader.Load(this);
        ApplyDisplaySettings();
        Activated += (_, _) => ApplyDisplaySettings();
        SizeChanged += (_, e) => Classes.Set("compact", e.NewSize.Width < 790);
    }
    public EmulatorWindow(EmulatorViewModel model) : this() => DataContext = model;

    private void ApplyDisplaySettings()
    {
        var settings = MacDisplaySettings.Read();
        Classes.Set("motion", !settings.ReduceMotion);
        TransparencyLevelHint = settings.ReduceTransparency ? [WindowTransparencyLevel.None]
            : [WindowTransparencyLevel.AcrylicBlur, WindowTransparencyLevel.Blur, WindowTransparencyLevel.None];
    }

    protected override async void OnClosing(WindowClosingEventArgs e)
    {
        base.OnClosing(e);
        if (DataContext is not EmulatorViewModel model || model.Active is not { } active) return;
        e.Cancel = true;
        if (closing) return;
        closing = true;
        model.Stop();
        await Task.WhenAny(active, Task.Delay(TimeSpan.FromSeconds(5)));
        DataContext = null;
        Close();
    }
}
