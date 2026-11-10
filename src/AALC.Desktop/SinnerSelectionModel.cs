using System.Collections.ObjectModel;
using System.Globalization;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace AALC.Desktop;

public sealed class SinnerSelectionItem(int id, string assetName, string name) : ObservableObject
{
    public int Id { get; } = id;
    public string AssetName { get; } = assetName;
    public string Name { get; } = name;
    private bool selected;
    private int order;
    public bool IsSelected => selected;
    public int Order => order;
    public bool IsBackup => order >= 8;
    public string OrderLabel => order == 0 ? "" : order.ToString(CultureInfo.InvariantCulture);

    internal void Update(bool isSelected, int rank)
    {
        if (selected == isSelected && order == rank) return;
        SetProperty(ref selected, isSelected, nameof(IsSelected));
        SetProperty(ref order, rank, nameof(Order));
        OnPropertyChanged(nameof(IsBackup));
        OnPropertyChanged(nameof(OrderLabel));
    }
}

public sealed partial class SinnerSelectionModel : ObservableObject
{
    private readonly List<int> selection = [];
    public bool Ordered { get; }
    public ReadOnlyCollection<SinnerSelectionItem> Items { get; }
    public int[] SelectedIds => Ordered ? selection.ToArray() : selection.Order().ToArray();
    public int SelectedCount => selection.Count;

    public SinnerSelectionModel(IEnumerable<int>? ids = null, bool ordered = true)
    {
        Ordered = ordered;
        (string Asset, string Name)[] people = [("YiSang", "李箱"), ("Faust", "浮士德"), ("DonQuixote", "堂吉诃德"),
            ("Ryoshu", "良秀"), ("Meursault", "默尔索"), ("HongLu", "鸿璐"), ("Heathcliff", "希斯克利夫"),
            ("Ishmael", "以实玛利"), ("Rodion", "罗佳"), ("Sinclair", "辛克莱"), ("Outis", "奥提斯"), ("Gregor", "格里高尔")];
        Items = Array.AsReadOnly(people.Select((person, index) => new SinnerSelectionItem(index + 1, person.Asset, person.Name)).ToArray());
        SetSelection(ids ?? Enumerable.Range(1, 12));
    }

    public void SetSelection(IEnumerable<int> ids)
    {
        var values = ids.ToArray();
        if (values.Any(id => id is < 1 or > 12) || values.Distinct().Count() != values.Length)
            throw new ArgumentException("罪人编号须为不重复的 1–12", nameof(ids));
        selection.Clear();
        selection.AddRange(values);
        UpdateItems();
    }

    public void Toggle(int id)
    {
        if (id is < 1 or > 12) throw new ArgumentOutOfRangeException(nameof(id));
        if (!selection.Remove(id)) selection.Add(id);
        UpdateItems();
    }

    [RelayCommand] private void SelectAll() => SetSelection(Enumerable.Range(1, 12));
    [RelayCommand] private void SelectFirstSeven() => SetSelection(Enumerable.Range(1, 7));
    [RelayCommand] private void Clear() => SetSelection([]);

    private void UpdateItems()
    {
        foreach (var item in Items)
        {
            var index = selection.IndexOf(item.Id);
            item.Update(index >= 0, Ordered && index >= 0 ? index + 1 : 0);
        }
        OnPropertyChanged(nameof(SelectedIds));
        OnPropertyChanged(nameof(SelectedCount));
    }
}
