using Avalonia;
using Avalonia.Animation;
using Avalonia.Animation.Easings;
using Avalonia.Controls;
using Avalonia.Markup.Xaml;
using Avalonia.Media;
using Avalonia.Styling;

namespace AALC.Desktop;

public partial class AboutView : UserControl
{
    public AboutView()
    {
        AvaloniaXamlLoader.Load(this);
        AddColorWave("ice", "AngelaIce");
        AddColorWave("gold", "AngelaGold");
    }

    private void AddColorWave(string variant, string palette)
    {
        var app = Application.Current!;
        var color = (IBrush)app.FindResource($"{palette}Brush")!;
        var shade = (IBrush)app.FindResource($"{palette}ShadeBrush")!;
        var light = (IBrush)app.FindResource($"{palette}LightBrush")!;
        for (var index = 0; index < 5; index++)
        {
            var glyphClass = $"logo-wave-{index}";
            var style = new Style(selector => selector.OfType<StackPanel>().Class("logo-wordmark").Class(variant)
                .Descendant().OfType<TextBlock>().Class(glyphClass));
            style.Setters.Add(new Setter(TextBlock.ForegroundProperty, color));
            // 样式动画由 Avalonia 管理可见性，离开关于页时自动暂停。
            style.Animations.Add(new Animation
            {
                Duration = TimeSpan.FromSeconds(2.4),
                Delay = TimeSpan.FromMilliseconds(index * 180),
                IterationCount = IterationCount.Infinite,
                Easing = new SineEaseInOut(),
                Children =
                {
                    new KeyFrame { Cue = new Cue(0), Setters = { new Setter(TextBlock.ForegroundProperty, color) } },
                    new KeyFrame { Cue = new Cue(.25), Setters = { new Setter(TextBlock.ForegroundProperty, shade) } },
                    new KeyFrame { Cue = new Cue(.5), Setters = { new Setter(TextBlock.ForegroundProperty, color) } },
                    new KeyFrame { Cue = new Cue(.75), Setters = { new Setter(TextBlock.ForegroundProperty, light) } },
                    new KeyFrame { Cue = new Cue(1), Setters = { new Setter(TextBlock.ForegroundProperty, color) } }
                }
            });
            Styles.Add(style);
        }
    }
}
