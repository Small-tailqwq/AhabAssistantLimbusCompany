using Avalonia;
using Avalonia.Controls;
using Avalonia.Markup.Xaml;
using Avalonia.Media;
using Avalonia.Threading;

namespace AALC.Desktop;

public partial class AngelaMemoryLabel : UserControl
{
    private const string Signal = "COGNITION FILTER";
    private const string Noise = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%/|_<>[]░▒▓";
    private readonly DispatcherTimer timer = new() { Interval = TimeSpan.FromMilliseconds(120) };
    private readonly IBrush[] colors;
    private readonly TextBlock signalText;
    private readonly TextBlock signalEcho;
    private bool attached;
    private bool inViewport;
    private int frame;

    public AngelaMemoryLabel()
    {
        AvaloniaXamlLoader.Load(this);
        signalText = this.FindControl<TextBlock>("SignalText")!;
        signalEcho = this.FindControl<TextBlock>("SignalEcho")!;
        colors = new[] { "AngelaIceBrush", "AngelaGoldBrush", "AngelaIceShadeBrush", "AngelaGoldLightBrush" }
            .Select(key => (IBrush)Application.Current!.FindResource(key)!).ToArray();
        timer.Tick += (_, _) => Advance();
        EffectiveViewportChanged += (_, e) =>
        {
            inViewport = e.EffectiveViewport.Intersects(new Rect(Bounds.Size));
            UpdatePlayback();
        };
    }

    protected override void OnAttachedToVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnAttachedToVisualTree(e);
        attached = true;
        UpdatePlayback();
    }

    protected override void OnDetachedFromVisualTree(VisualTreeAttachmentEventArgs e)
    {
        attached = false;
        inViewport = false;
        timer.Stop();
        base.OnDetachedFromVisualTree(e);
    }

    private void UpdatePlayback()
    {
        if (attached && inViewport && IsEffectivelyVisible) timer.Start();
        else timer.Stop();
    }

    private void Advance()
    {
        frame++;
        var characters = Signal.ToCharArray();
        for (var i = 0; i < characters.Length; i++)
            if (Random.Shared.Next(3) != 0) characters[i] = Noise[(frame + i + Random.Shared.Next(Noise.Length)) % Noise.Length];
        signalText.Text = frame % 48 < 6 ? "记忆同步 // A" : new string(characters);
        signalText.Foreground = colors[frame / 3 % colors.Length];
        signalEcho.Text = signalText.Text;
        signalEcho.Opacity = frame % 11 == 0 ? .55 : 0;
    }
}
