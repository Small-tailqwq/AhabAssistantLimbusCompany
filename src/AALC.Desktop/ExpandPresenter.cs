using Avalonia;
using Avalonia.Controls;

namespace AALC.Desktop;

/// <summary>按 Progress 截取内容高度的折叠容器，内容始终按完整高度排列，过渡期间只改变可见区域。</summary>
public sealed class ExpandPresenter : Decorator
{
    public static readonly StyledProperty<double> ProgressProperty =
        AvaloniaProperty.Register<ExpandPresenter, double>(nameof(Progress));

    public double Progress { get => GetValue(ProgressProperty); set => SetValue(ProgressProperty, value); }

    static ExpandPresenter()
    {
        AffectsMeasure<ExpandPresenter>(ProgressProperty);
        ClipToBoundsProperty.OverrideDefaultValue<ExpandPresenter>(true);
    }

    protected override Size MeasureOverride(Size availableSize)
    {
        var size = base.MeasureOverride(availableSize.WithHeight(double.PositiveInfinity));
        return size.WithHeight(size.Height * Math.Clamp(Progress, 0, 1));
    }

    protected override Size ArrangeOverride(Size finalSize)
    {
        Child?.Arrange(new Rect(0, 0, finalSize.Width, Child.DesiredSize.Height));
        return finalSize;
    }
}
