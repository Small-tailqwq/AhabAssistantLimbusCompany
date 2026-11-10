using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Markup.Xaml;

namespace AALC.Desktop;

public partial class MirrorConfigurationView : UserControl
{
    public MirrorConfigurationView() => AvaloniaXamlLoader.Load(this);

    private async void OpenObservedGifts(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button { DataContext: MirrorTeamItem team }
            || DataContext is not MainViewModel main || !main.CanConfigure || TopLevel.GetTopLevel(this) is not Window owner) return;
        var editor = new ObserveGiftSelectionModel(team.ObservedGifts);
        var window = new ObserveGiftEditorWindow { DataContext = editor, Title = $"观测饰品 · {team.Name}" };
        window.Opened += async (_, _) =>
        {
            try { await editor.LoadIconsAsync(main.RepositoryRoot); }
            catch (Exception exception) { editor.Error = exception.Message; }
        };
        if (await window.ShowDialog<bool>(owner)) team.ObservedGifts = editor.ToOptions();
    }

    private async void OpenThemeWeights(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button { DataContext: MirrorTeamItem team }
            || DataContext is not MainViewModel main || !main.CanConfigure || TopLevel.GetTopLevel(this) is not Window owner) return;
        using var editor = new ThemeWeightEditorModel(team.ThemeOptions(), main.RepositoryRoot);
        var window = new ThemeWeightEditorWindow(editor) { Title = $"主题卡包权重 · {team.Name}" };
        if (await window.ShowDialog<bool>(owner)) team.ApplyThemeWeights(editor.ApplyTo(team.ThemeOptions()));
    }
}
