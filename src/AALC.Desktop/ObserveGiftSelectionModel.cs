using System.Collections.ObjectModel;
using System.IO;
using AALC.Core.Features.Mirror;
using Avalonia.Media.Imaging;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace AALC.Desktop;

public sealed partial class ObserveSystemItem(MirrorObserveSystem definition, ObserveGiftSelectionModel owner) : ObservableObject
{
    public MirrorObserveSystem Definition { get; } = definition;
    public string Name => Definition.Name;
    public string Key => Definition.Key;
    [ObservableProperty] private Bitmap? icon;
    [ObservableProperty] private bool active;
    [RelayCommand] private void Select() => owner.SelectSystem(Key);
}

public sealed partial class ObserveTierItem(int level, ObserveGiftSelectionModel owner) : ObservableObject
{
    public int Level { get; } = level;
    public string Name => Level switch { 3 => "III", 2 => "II", _ => "I" };
    [ObservableProperty] private bool active;
    [RelayCommand] private void Select() => owner.SelectLevel(Level);
}

public sealed partial class ObservePositionCell(int row, int column, ObserveGiftSelectionModel owner) : ObservableObject
{
    public int Row { get; } = row;
    public int Column { get; } = column;
    public bool Selected => Order > 0;
    public string Label => Order > 0 ? $"✓ {Order}" : Column.ToString();
    public string Description => MirrorObservation.Describe(new(owner.System, owner.Level, Row, Column));
    [ObservableProperty, NotifyPropertyChangedFor(nameof(Selected), nameof(Label))] private int order;
    [RelayCommand] private void Toggle() => owner.Toggle(Row, Column);
    internal void Refresh()
    {
        Order = owner.IndexOf(new(owner.System, owner.Level, Row, Column)) + 1;
        OnPropertyChanged(nameof(Description));
    }
}

public sealed record ObservePositionRow(int Number, ObservePositionCell[] Cells)
{
    public string Label => $"第 {Number} 排";
}

public sealed partial class ObservedGiftChoice(MirrorObservedGift location, ObserveGiftSelectionModel owner) : ObservableObject
{
    public MirrorObservedGift Location { get; } = location;
    public string Description => MirrorObservation.Describe(Location);
    [RelayCommand] private void Remove() => owner.Remove(this);
}

public sealed partial class ObserveGiftSelectionModel : ObservableObject
{
    public ObservableCollection<ObservedGiftChoice> Selected { get; } = [];
    public ObserveSystemItem[] Systems { get; }
    public ObserveTierItem[] Tiers { get; }
    public ObservePositionRow[] Rows { get; }
    public string System { get; private set; }
    public int Level { get; private set; } = 3;
    public string CountLabel => $"已选 {Selected.Count} / {MirrorObservation.MaximumGifts}";
    [ObservableProperty] private string error = "";

    public ObserveGiftSelectionModel(IEnumerable<MirrorObservedGift> gifts)
    {
        var values = gifts.ToArray();
        MirrorObservation.Validate(values);
        System = values.FirstOrDefault()?.Keyword ?? "burn";
        Level = values.FirstOrDefault()?.Level ?? 3;
        Systems = MirrorObservation.Systems.Select(system => new ObserveSystemItem(system, this)).ToArray();
        Tiers = new[] { 3, 2, 1 }.Select(level => new ObserveTierItem(level, this)).ToArray();
        Rows = Enumerable.Range(1, MirrorObservation.MaximumRows).Select(row => new ObservePositionRow(row,
            Enumerable.Range(1, MirrorObservation.Columns).Select(column => new ObservePositionCell(row, column, this)).ToArray())).ToArray();
        foreach (var gift in values) Selected.Add(new(gift, this));
        Refresh();
    }

    public MirrorObservedGift[] ToOptions() => Selected.Select(item => item.Location).ToArray();
    public int IndexOf(MirrorObservedGift gift) => Array.IndexOf(ToOptions(), gift);
    public void SelectSystem(string system) { System = system; Error = ""; Refresh(); }
    public void SelectLevel(int level) { Level = level; Error = ""; Refresh(); }
    public void Toggle(int row, int column)
    {
        var gift = new MirrorObservedGift(System, Level, row, column);
        var existing = Selected.FirstOrDefault(item => item.Location == gift);
        if (existing is not null) { Remove(existing); return; }
        if (Selected.Count == MirrorObservation.MaximumGifts) { Error = "最多观测 3 件饰品，请先移除一件。"; return; }
        MirrorObservation.Validate([gift]);
        Selected.Add(new(gift, this));
        Error = "";
        Refresh();
    }
    public void Remove(ObservedGiftChoice item) { Selected.Remove(item); Error = ""; Refresh(); }
    [RelayCommand] private void Clear() { Selected.Clear(); Error = ""; Refresh(); }

    public async Task LoadIconsAsync(string repository)
    {
        foreach (var system in Systems)
            system.Icon = await ThumbnailCache.GetAsync(Path.Combine(repository, "assets", "app", "status_effects", system.Key + ".png"), 32);
    }

    private void Refresh()
    {
        foreach (var system in Systems) system.Active = system.Key == System;
        foreach (var tier in Tiers) tier.Active = tier.Level == Level;
        foreach (var cell in Rows.SelectMany(row => row.Cells)) cell.Refresh();
        OnPropertyChanged(nameof(CountLabel));
    }
}
