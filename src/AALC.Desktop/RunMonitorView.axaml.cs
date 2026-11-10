using System.Collections.Specialized;
using Avalonia.Controls;
using Avalonia.Markup.Xaml;
using Avalonia.Threading;

namespace AALC.Desktop;

public partial class RunMonitorView : UserControl
{
    private MainViewModel? observed;

    public RunMonitorView()
    {
        AvaloniaXamlLoader.Load(this);
        DataContextChanged += (_, _) =>
        {
            if (observed is not null) observed.Messages.CollectionChanged -= FollowLatest;
            observed = DataContext as MainViewModel;
            if (observed is not null) observed.Messages.CollectionChanged += FollowLatest;
        };
    }

    // 停在底部时跟随新记录；用户向上翻阅时保持位置。
    private void FollowLatest(object? sender, NotifyCollectionChangedEventArgs e)
    {
        if (e.Action != NotifyCollectionChangedAction.Add) return;
        var scroller = this.FindControl<ScrollViewer>("MessageScroller")!;
        if (scroller.Offset.Y + scroller.Viewport.Height < scroller.Extent.Height - 48) return;
        Dispatcher.UIThread.Post(scroller.ScrollToEnd, DispatcherPriority.Background);
    }
}
