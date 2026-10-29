using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using Avalonia;
using Avalonia.Animation;
using Avalonia.Animation.Easings;
using Avalonia.Automation;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Controls.Templates;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using Avalonia.Media.Transformation;
using Avalonia.Threading;
using Avalonia.VisualTree;

namespace AALC.Desktop;

public sealed class SinnerSelectionView : UserControl
{
    public static readonly StyledProperty<SinnerSelectionModel?> ModelProperty =
        AvaloniaProperty.Register<SinnerSelectionView, SinnerSelectionModel?>(nameof(Model));
    public static readonly StyledProperty<string> AssetRootProperty =
        AvaloniaProperty.Register<SinnerSelectionView, string>(nameof(AssetRoot), "");
    public static readonly StyledProperty<bool> CompactProperty =
        AvaloniaProperty.Register<SinnerSelectionView, bool>(nameof(Compact));
    public SinnerSelectionModel? Model { get => GetValue(ModelProperty); set => SetValue(ModelProperty, value); }
    public string AssetRoot { get => GetValue(AssetRootProperty); set => SetValue(AssetRootProperty, value); }
    public bool Compact { get => GetValue(CompactProperty); set => SetValue(CompactProperty, value); }

    private readonly SinnerSelectionModel defaultModel = new();
    private SinnerSelectionModel? activeModel;
    private readonly SinnerCardView[] cards;
    private readonly Button all;
    private readonly Button firstSeven;
    private readonly TextBlock error = new() { Classes = { "error" }, FontSize = 12 };
    private string? attemptedRoot;
    private int loadVersion;

    public SinnerSelectionView()
    {
        HorizontalAlignment = HorizontalAlignment.Left;
        var grid = new UniformGrid { Name = "SinnerCards", Columns = 6, Rows = 2 };
        cards = Enumerable.Range(1, 12).Select(id => new SinnerCardView(id, () => activeModel!.Toggle(id))).ToArray();
        foreach (var card in cards) grid.Children.Add(card);
        all = Shortcut("默认全选", () => activeModel!.SelectAllCommand.Execute(null));
        firstSeven = Shortcut("前7人", () => activeModel!.SelectFirstSevenCommand.Execute(null));
        var clear = Shortcut("清空", () => activeModel!.ClearCommand.Execute(null));
        Content = new StackPanel
        {
            Spacing = 8,
            Children = { new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, Children = { all, firstSeven, clear } }, grid, error }
        };
        DataContextChanged += (_, _) => BindModel();
        EffectiveViewportChanged += (_, _) => TryLoadImages();
        BindModel();
    }

    protected override void OnPropertyChanged(AvaloniaPropertyChangedEventArgs change)
    {
        base.OnPropertyChanged(change);
        if (cards is null) return;
        if (change.Property == ModelProperty || change.Property == CompactProperty) BindModel();
        if (change.Property == IsVisibleProperty) TryLoadImages();
        if (change.Property == AssetRootProperty)
        {
            attemptedRoot = null;
            loadVersion++;
            TryLoadImages();
        }
    }

    protected override void OnAttachedToVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnAttachedToVisualTree(e);
        BindModel();
        Dispatcher.UIThread.Post(TryLoadImages, DispatcherPriority.Loaded);
    }

    protected override void OnDetachedFromVisualTree(VisualTreeAttachmentEventArgs e)
    {
        if (activeModel is not null) activeModel.PropertyChanged -= SelectionChanged;
        attemptedRoot = null;
        loadVersion++;
        base.OnDetachedFromVisualTree(e);
    }

    private static Button Shortcut(string title, Action action)
    {
        var button = new Button { Content = title, Classes = { "small" } };
        button.Click += (_, _) => action();
        return button;
    }

    private void BindModel()
    {
        if (activeModel is not null) activeModel.PropertyChanged -= SelectionChanged;
        activeModel = Model ?? DataContext as SinnerSelectionModel ?? defaultModel;
        activeModel.PropertyChanged += SelectionChanged;
        all.Content = activeModel.Ordered ? "默认全选" : "全选";
        MaxWidth = Compact ? 640 : !activeModel.Ordered ? 744 : 1008;
        firstSeven.IsVisible = activeModel.Ordered;
        UpdateCards();
    }

    private void SelectionChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(SinnerSelectionModel.SelectedIds)) UpdateCards();
    }

    private void UpdateCards()
    {
        if (activeModel is null) return;
        for (var index = 0; index < cards.Length; index++)
            cards[index].Update(activeModel.Items[index], activeModel.Ordered);
    }

    private void TryLoadImages()
    {
        if (!IsEffectivelyVisible || TopLevel.GetTopLevel(this) is null) return;
        if (attemptedRoot == AssetRoot) return;
        attemptedRoot = AssetRoot;
        _ = LoadImagesAsync(AssetRoot, ++loadVersion);
    }

    private async Task LoadImagesAsync(string root, int version)
    {
        try
        {
            error.Text = "";
            var directory = Path.Combine(Path.GetFullPath(root), "assets", "app", "sinner");
            var portraits = await Task.WhenAll(defaultModel.Items.Select(item =>
                ThumbnailCache.GetAsync(Path.Combine(directory, item.AssetName, "Sinner.png"), 160)));
            var overlays = await Task.WhenAll(new[] { "FrameOverlay", "HoverOverlay", "SinnerSelected", "SinnerBackup" }
                .Select(name => ThumbnailCache.GetAsync(Path.Combine(directory, "ui_components", name + ".png"), 160)));
            if (version != loadVersion) return;
            for (var index = 0; index < cards.Length; index++) cards[index].SetImages(portraits[index], overlays);
        }
        catch (Exception exception)
        {
            Trace.TraceError($"Sinner images: {exception}");
            if (version == loadVersion) error.Text = $"角色图片加载失败：{exception.Message}";
        }
    }
}

internal sealed class SinnerCardView : ToggleButton
{
    private static readonly IBrush Amber = new SolidColorBrush(Color.Parse("#FFB900"));
    private static readonly IBrush Teal = new SolidColorBrush(Color.Parse("#22FFE3"));
    private static readonly TransformOperations Rest = TransformOperations.Parse("scale(1)");
    private static readonly TransformOperations Hover = TransformOperations.Parse("scale(1.035)");
    private readonly Image portrait = new() { Width = 160, Height = 247, Stretch = Stretch.Fill };
    private readonly Image frame = new() { Width = 160, Height = 247, Stretch = Stretch.Fill };
    private readonly Image hover = new() { Width = 160, Height = 247, Stretch = Stretch.Fill, Opacity = 0 };
    private readonly Image banner = new() { Width = 184, Height = 56, Stretch = Stretch.Fill };
    private readonly Border mask = new() { Width = 160, Height = 247, Background = new SolidColorBrush(Color.FromArgb(100, 28, 28, 28)) };
    private readonly Canvas stage = new() { Width = 160, Height = 247 };
    private readonly TextBlock number = new() { HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center, FontSize = 32, FontWeight = FontWeight.Bold,
        Effect = new DropShadowEffect { Color = Colors.Black, BlurRadius = 5, OffsetX = 0, OffsetY = 1, Opacity = 1 } };
    private readonly TextBlock label = new() { HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Bottom, Margin = new Thickness(4, 0, 8, 12), FontSize = 12, Foreground = Amber, TextTrimming = TextTrimming.CharacterEllipsis,
        Effect = new DropShadowEffect { Color = Colors.Black, BlurRadius = 4, OffsetX = 0, OffsetY = 1, Opacity = 1 } };
    private readonly Border clip;
    private Bitmap? selectedBanner;
    private Bitmap? backupBanner;
    private bool backup;
    protected override Type StyleKeyOverride => typeof(ToggleButton);

    public SinnerCardView(int id, Action toggle)
    {
        Name = $"Sinner{id}";
        Margin = new Thickness(4);
        Padding = new Thickness(0);
        Focusable = true;
        HorizontalContentAlignment = HorizontalAlignment.Stretch;
        VerticalContentAlignment = VerticalAlignment.Stretch;
        stage.Children.Add(portrait);
        stage.Children.Add(hover);
        stage.Children.Add(mask);
        stage.Children.Add(frame);
        stage.Children.Add(banner);
        Canvas.SetLeft(banner, -12);
        Canvas.SetTop(banner, 247 * .5);
        var layers = new Grid { RowDefinitions = new RowDefinitions(".2*,.3*,.5*") };
        var viewbox = new Viewbox { Stretch = Stretch.Uniform, Child = stage };
        Grid.SetRowSpan(viewbox, 3); layers.Children.Add(viewbox);
        Grid.SetRow(number, 1); layers.Children.Add(number);
        Grid.SetRow(label, 2); layers.Children.Add(label);
        clip = new Border { Name = "SinnerClip", CornerRadius = new CornerRadius(8), ClipToBounds = true, Child = layers,
            RenderTransform = Rest, RenderTransformOrigin = new RelativePoint(.5, .5, RelativeUnit.Relative),
            Transitions = new Transitions { new TransformOperationsTransition { Property = RenderTransformProperty,
                Duration = TimeSpan.FromMilliseconds(120), Easing = new CubicEaseOut() } } };
        hover.Transitions = new Transitions { new DoubleTransition { Property = OpacityProperty, Duration = TimeSpan.FromMilliseconds(100) } };
        Template = new FuncControlTemplate<ToggleButton>((_, _) => clip);
        PointerEntered += (_, _) => { clip.RenderTransform = Hover; hover.Opacity = 1; };
        PointerExited += (_, _) => { clip.RenderTransform = Rest; hover.Opacity = 0; };
        Click += (_, _) => toggle();
    }

    public void SetImages(Bitmap image, Bitmap[] overlays)
    {
        portrait.Source = image; frame.Source = overlays[0]; hover.Source = overlays[1];
        selectedBanner = overlays[2]; backupBanner = overlays[3];
        banner.Source = backup ? backupBanner : selectedBanner;
    }

    public void Update(SinnerSelectionItem item, bool ordered)
    {
        IsChecked = item.IsSelected;
        backup = item.IsBackup;
        number.Text = ordered ? item.OrderLabel : "";
        number.Foreground = backup ? Teal : Amber;
        banner.Source = backup ? backupBanner : selectedBanner;
        banner.IsVisible = item.IsSelected;
        mask.Opacity = item.IsSelected ? 1 : 0;
        label.Text = item.Name;
        AutomationProperties.SetName(this, item.Name);
        ToolTip.SetTip(this, item.Name);
        AutomationProperties.SetHelpText(this, item.IsSelected ? ordered ? $"第 {item.Order} 顺位" : "已选中" : "未选中");
    }
}
