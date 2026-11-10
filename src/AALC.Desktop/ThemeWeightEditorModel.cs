using System.Collections.ObjectModel;
using System.IO;
using AALC.Core.Features.Mirror;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace AALC.Desktop;

public sealed partial class ThemePackItem(ThemePackDefinition definition, ThemeWeightEditorModel owner) : ObservableObject
{
    public ThemePackDefinition Definition { get; } = definition;
    public string Name => Definition.TitleZh;
    public string FullName => $"{Definition.TitleZh}\n{Definition.TitleEn}";
    [ObservableProperty] private Bitmap? cover;
    public int Weight { get => owner.WeightFor(Definition); set => owner.SetWeight(Definition, value); }
    public IBrush Outline => Weight > 0 && Weight >= owner.PreferredThreshold ? PreferredOutline : StandardOutline;
    public double CoverOpacity => Weight < 0 ? .42 : 1;
    private static readonly IBrush PreferredOutline = new SolidColorBrush(Color.Parse("#D3AF65"));
    private static readonly IBrush StandardOutline = new SolidColorBrush(Color.Parse("#3A4658"));
    internal void Refresh()
    {
        OnPropertyChanged(nameof(Weight));
        OnPropertyChanged(nameof(Outline));
        OnPropertyChanged(nameof(CoverOpacity));
    }
}

public sealed partial class ThemeWeightEditorModel : ObservableObject, IDisposable
{
    private readonly string root;
    private readonly Dictionary<string, int> normal;
    private readonly Dictionary<string, int> hard;
    private readonly ThemePackItem[] all;
    private int generation;
    private bool disposed;
    public ObservableCollection<ThemePackItem> VisiblePacks { get; } = [];
    public string[] Modes { get; } = ["普通模式", "困难模式"];
    [ObservableProperty] private int modeIndex;
    [ObservableProperty] private string searchText = "";
    [ObservableProperty] private int preferredThreshold;
    [ObservableProperty] private string error = "";
    [ObservableProperty] private string countLabel = "";
    public Task PendingLoad { get; private set; } = Task.CompletedTask;

    public ThemeWeightEditorModel(MirrorThemeOptions options, string repositoryRoot)
    {
        root = repositoryRoot;
        normal = new(options.NormalWeights, StringComparer.OrdinalIgnoreCase);
        hard = new(options.HardWeights, StringComparer.OrdinalIgnoreCase);
        preferredThreshold = options.PreferredThreshold;
        all = MirrorThemeCatalog.All.Select(pack => new ThemePackItem(pack, this)).ToArray();
    }

    public void Load() => PendingLoad = RefreshVisibleAsync();
    partial void OnModeIndexChanged(int value) { foreach (var item in all) item.Refresh(); Load(); }
    partial void OnSearchTextChanged(string value) => Load();
    partial void OnPreferredThresholdChanged(int value) { foreach (var item in all) item.Refresh(); }

    internal int WeightFor(ThemePackDefinition pack) => ModeIndex == 0
        ? normal.GetValueOrDefault(pack.Id, pack.DefaultNormalWeight)
        : hard.GetValueOrDefault(pack.Id, pack.DefaultHardWeight);

    internal void SetWeight(ThemePackDefinition pack, int value)
    {
        var weights = ModeIndex == 0 ? normal : hard;
        var baseline = ModeIndex == 0 ? pack.DefaultNormalWeight : pack.DefaultHardWeight;
        value = Math.Clamp(value, -10, 10);
        if (value == baseline) weights.Remove(pack.Id); else weights[pack.Id] = value;
        all.First(item => item.Definition.Id == pack.Id).Refresh();
    }

    [RelayCommand] private void ResetDefaults()
    {
        (ModeIndex == 0 ? normal : hard).Clear();
        foreach (var item in all) item.Refresh();
    }

    [RelayCommand] private void SetAllLow()
    {
        foreach (var item in all.Where(item => ModeIndex == 0 ? item.Definition.InNormal : item.Definition.InHard))
            SetWeight(item.Definition, -5);
    }

    [RelayCommand] private void CopyNormalToHard()
    {
        foreach (var pack in MirrorThemeCatalog.All.Where(pack => pack.InNormal && pack.InHard))
        {
            var value = normal.GetValueOrDefault(pack.Id, pack.DefaultNormalWeight);
            if (value == pack.DefaultHardWeight) hard.Remove(pack.Id); else hard[pack.Id] = value;
        }
        foreach (var item in all) item.Refresh();
    }

    public MirrorThemeOptions ApplyTo(MirrorThemeOptions options) => options with
    {
        PreferredThreshold = PreferredThreshold,
        NormalWeights = new(normal, StringComparer.OrdinalIgnoreCase),
        HardWeights = new(hard, StringComparer.OrdinalIgnoreCase)
    };

    private async Task RefreshVisibleAsync()
    {
        var version = ++generation;
        var isHard = ModeIndex == 1;
        var search = SearchText.Trim();
        var matches = all.Where(item => (isHard ? item.Definition.InHard : item.Definition.InNormal)
            && (search.Length == 0 || item.FullName.Contains(search, StringComparison.OrdinalIgnoreCase)
                || item.Definition.Id.Contains(search, StringComparison.OrdinalIgnoreCase)
                || item.Definition.OcrAliases.Any(alias => alias.Contains(search, StringComparison.OrdinalIgnoreCase)))).ToArray();
        VisiblePacks.Clear();
        Error = "";
        CountLabel = $"{matches.Length} 个卡包";
        var loads = new List<Task>();
        for (var index = 0; index < matches.Length; index++)
        {
            if (disposed || version != generation) return;
            var item = matches[index];
            item.Cover = null;
            VisiblePacks.Add(item);
            loads.Add(LoadCoverAsync(item, isHard, version));
            // 让布局、绘制和输入先处理，避免普通优先级的续体连续填满首屏。
            if (index % 6 == 5)
            {
                await Dispatcher.UIThread.InvokeAsync(() => { }, DispatcherPriority.Background);
                await Task.Delay(16);
            }
        }
        await Task.WhenAll(loads);
    }

    private async Task LoadCoverAsync(ThemePackItem item, bool isHard, int version)
    {
        try
        {
            var relative = isHard ? item.Definition.HardImage ?? item.Definition.NormalImage : item.Definition.NormalImage;
            var bitmap = await ThumbnailCache.GetAsync(Path.Combine(root, relative), 240);
            if (!disposed && version == generation) item.Cover = bitmap;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            if (!disposed && version == generation) Error = $"封面读取失败：{item.Name}（{exception.Message}）";
        }
    }

    public void Dispose() { disposed = true; generation++; }
}
