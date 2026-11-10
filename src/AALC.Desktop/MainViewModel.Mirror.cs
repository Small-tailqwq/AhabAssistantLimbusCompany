using System.Collections.ObjectModel;
using AALC.Core.Features.Mirror;
using AALC.Runtime.Configuration;
using AALC.Runtime.DesktopClone;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace AALC.Desktop;

public partial class MirrorLevelItem(MirrorStarBonus definition, int level) : ObservableObject
{
    public MirrorStarBonus Definition { get; } = definition;
    public string Name => Definition.Name;
    public int Cost => Definition.Cost * Level;
    public string PriceLabel => $"{Definition.Cost * Math.Max(1, Level)} ✦";
    public bool BaseSelected => Level >= 1;
    public bool PlusSelected => Level >= 2;
    public bool DoubleSelected => Level >= 3;
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(Cost), nameof(PriceLabel), nameof(BaseSelected), nameof(PlusSelected), nameof(DoubleSelected))]
    private int level = level;
    [RelayCommand] private void ToggleBase() => Level = Level >= 1 ? 0 : 1;
    [RelayCommand] private void TogglePlus() => Level = Level >= 2 ? 1 : 2;
    [RelayCommand] private void ToggleDouble() => Level = Level >= 3 ? 2 : 3;
}

public partial class MirrorKeywordItem(string key, string name, bool selected) : ObservableObject
{
    public string Key { get; } = key;
    public string Name { get; } = name;
    [ObservableProperty] private bool selected = selected;
}

public partial class MirrorFloorItem(int number, bool selected) : ObservableObject
{
    public int Number { get; } = number;
    public string Name => $"{Number} 层";
    [ObservableProperty] private bool selected = selected;
}

public partial class MirrorTeamItem : ObservableObject
{
    private static readonly int[][] InitialGiftPermutations = [[1, 2, 3], [1, 3, 2], [2, 1, 3], [2, 3, 1], [3, 1, 2], [3, 2, 1]];
    public string[] InitialGiftOrders { get; } = InitialGiftPermutations.Select(order => string.Join(" → ", order)).ToArray();
    public static readonly string[] KeywordNames = ["烧伤", "流血", "震颤", "破裂", "呼吸", "沉沦", "充能", "斩击", "突刺", "打击"];
    public string[] Keywords => KeywordNames;
    public string[] SecondaryKeywords { get; } = ["不启用", .. KeywordNames];
    public string[] Modes { get; } = ["普通与困难", "仅普通", "仅困难"];
    public string[] CardPreferences { get; } = ["星光 → 饰品 → 经费", "星光 → 经费 → 饰品", "经费优先", "饰品优先"];
    public string[] Purchases { get; } = ["不购买", "购买体系饰品", "必需品与体系饰品"];
    public string[] Inventories { get; } = ["保留饰品", "出售指定饰品", "体系配方合成"];
    public string[] Skills { get; } = ["不替换", "一技能 → 三技能", "二技能 → 三技能", "一技能 → 二技能"];
    public ObservableCollection<MirrorLevelItem> StarLevels { get; } = [];
    [RelayCommand] private void AllStarsBase() { foreach (var item in StarLevels) item.Level = 1; }
    [RelayCommand] private void AllStarsPlus() { foreach (var item in StarLevels) item.Level = 2; }
    [RelayCommand] private void AllStarsDouble() { foreach (var item in StarLevels) item.Level = 3; }
    [RelayCommand] private void ClearStars() { foreach (var item in StarLevels) item.Level = 0; }
    private Dictionary<string, int> normalWeights;
    private Dictionary<string, int> hardWeights;
    public SinnerSelectionModel Formation { get; }
    public SinnerSelectionModel SkillSelection { get; }
    public string StarCostLabel => $"共消耗 {StarLevels.Sum(item => item.Cost)} 星芒";
    [ObservableProperty, NotifyPropertyChangedFor(nameof(ObservedGiftSummary))] private MirrorObservedGift[] observedGifts;
    public string ObservedGiftSummary => ObservedGifts.Length == 0 ? "选择观测饰品" : $"已选 {ObservedGifts.Length}/{MirrorObservation.MaximumGifts}";
    public ObservableCollection<MirrorKeywordItem> ShopKeywords { get; } = [];
    public ObservableCollection<MirrorKeywordItem> SellKeywords { get; } = [];
    public ObservableCollection<MirrorFloorItem> ShopFloors { get; } = [];
    [ObservableProperty] private string name;
    [ObservableProperty] private bool enabled;
    [ObservableProperty] private int modeIndex;
    [ObservableProperty] private int gameTeamNumber;
    [ObservableProperty] private bool selectTeamByOrder;
    [ObservableProperty] private int keywordIndex;
    [ObservableProperty] private int secondaryKeywordIndex;
    [ObservableProperty] private bool reformEachFloor;
    [ObservableProperty] private bool avoidSkill3;
    [ObservableProperty] private bool defenseForSolo;
    [ObservableProperty] private int defenseForSoloTurns;
    [ObservableProperty] private bool convertStarlight;
    [ObservableProperty] private int initialGiftOrderIndex;
    [ObservableProperty] private int cardPreferenceIndex;
    [ObservableProperty] private bool avoidWhiteGossypium;
    [ObservableProperty] private int preferredThreshold;
    [ObservableProperty] private int themeRefreshLimit;
    [ObservableProperty] private bool preferEventPack;
    [ObservableProperty] private bool skipEventPack;
    [ObservableProperty] private int unknownThemeWeight;
    [ObservableProperty] private int shopPurchasesIndex;
    [ObservableProperty] private int shopInventoryIndex;
    [ObservableProperty] private bool shopHeal;
    [ObservableProperty] private bool shopEnhance;
    [ObservableProperty] private int shopRefreshLimit;
    [ObservableProperty] private int keywordRefreshLimit;
    [ObservableProperty] private int reserveFunds;
    [ObservableProperty] private int shopSkillIndex;

    public MirrorTeamItem(MirrorTeamOptions value)
    {
        name = value.Name; enabled = value.Enabled; modeIndex = (int)value.Mode;
        gameTeamNumber = value.GameTeamNumber; selectTeamByOrder = value.SelectTeamByOrder;
        keywordIndex = Array.IndexOf(MirrorPlan.Keywords, value.Rewards.Keyword);
        secondaryKeywordIndex = value.Rewards.SecondaryKeyword is null ? 0 : Array.IndexOf(MirrorPlan.Keywords, value.Rewards.SecondaryKeyword) + 1;
        Formation = new(value.SinnerOrder); reformEachFloor = value.ReformEachFloor; avoidSkill3 = value.AvoidSkill3;
        defenseForSolo = value.DefenseForSolo; defenseForSoloTurns = value.DefenseForSoloTurns;
        convertStarlight = value.ConvertStarlight;
        initialGiftOrderIndex = Array.FindIndex(InitialGiftPermutations, order => order.SequenceEqual(value.InitialGifts));
        cardPreferenceIndex = (int)value.Rewards.CardPreference; avoidWhiteGossypium = value.Rewards.AvoidWhiteGossypium;
        preferredThreshold = value.Theme.PreferredThreshold; themeRefreshLimit = value.Theme.RefreshLimit;
        preferEventPack = value.Theme.PreferEventPack; skipEventPack = value.Theme.SkipEventPack; unknownThemeWeight = value.Theme.UnknownWeight;
        shopPurchasesIndex = (int)value.Shop.Purchases; shopInventoryIndex = (int)value.Shop.Inventory;
        shopHeal = value.Shop.Heal; shopEnhance = value.Shop.Enhance; shopRefreshLimit = value.Shop.NormalRefreshLimit;
        keywordRefreshLimit = value.Shop.KeywordRefreshLimit; reserveFunds = value.Shop.ReserveFunds;
        for (var i = 0; i < MirrorPlan.Keywords.Length; i++)
        {
            ShopKeywords.Add(new(MirrorPlan.Keywords[i], KeywordNames[i], value.Shop.Keywords.Contains(MirrorPlan.Keywords[i])));
            SellKeywords.Add(new(MirrorPlan.Keywords[i], KeywordNames[i], value.Shop.SellKeywords.Contains(MirrorPlan.Keywords[i])));
        }
        shopSkillIndex = (int)value.Shop.Skill; SkillSelection = new(value.Shop.SkillSinners, ordered: false);
        for (var floor = 1; floor <= 5; floor++) ShopFloors.Add(new(floor, value.Shop.SkipFloors.Contains(floor)));
        for (var i = 0; i < 10; i++)
        {
            var item = new MirrorLevelItem(MirrorStarBonusCatalog.All[i], value.StarLevels[i]);
            item.PropertyChanged += (_, change) => { if (change.PropertyName == nameof(MirrorLevelItem.Level)) OnPropertyChanged(nameof(StarCostLabel)); };
            StarLevels.Add(item);
        }
        normalWeights = new(value.Theme.NormalWeights, StringComparer.OrdinalIgnoreCase);
        hardWeights = new(value.Theme.HardWeights, StringComparer.OrdinalIgnoreCase);
        observedGifts = value.Rewards.ObservedGifts.ToArray();
    }

    public MirrorThemeOptions ThemeOptions() => new()
    {
        PreferredThreshold = PreferredThreshold, RefreshLimit = ThemeRefreshLimit, PreferEventPack = PreferEventPack,
        SkipEventPack = SkipEventPack, UnknownWeight = UnknownThemeWeight,
        NormalWeights = new(normalWeights, StringComparer.OrdinalIgnoreCase), HardWeights = new(hardWeights, StringComparer.OrdinalIgnoreCase)
    };

    public void ApplyThemeWeights(MirrorThemeOptions options)
    {
        normalWeights = new(options.NormalWeights, StringComparer.OrdinalIgnoreCase);
        hardWeights = new(options.HardWeights, StringComparer.OrdinalIgnoreCase);
        PreferredThreshold = options.PreferredThreshold;
    }

    public MirrorTeamOptions ToOptions() => new()
    {
        Name = Name, Enabled = Enabled, Mode = (MirrorTeamMode)ModeIndex, GameTeamNumber = GameTeamNumber,
        SelectTeamByOrder = SelectTeamByOrder, SinnerOrder = Formation.SelectedIds, ReformEachFloor = ReformEachFloor,
        AvoidSkill3 = AvoidSkill3, DefenseForSolo = DefenseForSolo, DefenseForSoloTurns = DefenseForSoloTurns,
        ConvertStarlight = ConvertStarlight, StarLevels = StarLevels.Select(item => item.Level).ToArray(),
        InitialGifts = InitialGiftPermutations[InitialGiftOrderIndex].ToArray(),
        Rewards = new()
        {
            Keyword = MirrorPlan.Keywords[KeywordIndex], SecondaryKeyword = SecondaryKeywordIndex == 0 ? null : MirrorPlan.Keywords[SecondaryKeywordIndex - 1],
            CardPreference = (MirrorCardPreference)CardPreferenceIndex, AvoidWhiteGossypium = AvoidWhiteGossypium,
            ObservedGifts = ObservedGifts.ToArray()
        },
        Theme = ThemeOptions(),
        Shop = new()
        {
            Purchases = (MirrorShopPurchases)ShopPurchasesIndex, Inventory = (MirrorShopInventory)ShopInventoryIndex,
            Heal = ShopHeal, Enhance = ShopEnhance, NormalRefreshLimit = ShopRefreshLimit, KeywordRefreshLimit = KeywordRefreshLimit,
            ReserveFunds = ReserveFunds, Keywords = ShopKeywords.Where(item => item.Selected).Select(item => item.Key).ToArray(),
            SellKeywords = SellKeywords.Where(item => item.Selected).Select(item => item.Key).ToArray(),
            Skill = (MirrorShopSkill)ShopSkillIndex, SkillSinners = SkillSelection.SelectedIds,
            SkipFloors = ShopFloors.Where(item => item.Selected).Select(item => item.Number).ToArray()
        }
    };
}

public partial class MainViewModel
{
    public string[] MirrorModes { get; } = ["普通镜牢", "困难镜牢"];
    public string[] MirrorWeeklyBonuses { get; } = ["不使用", "使用一次", "全部使用"];
    public ObservableCollection<MirrorTeamItem> MirrorTeams { get; } = [];
    [ObservableProperty, NotifyPropertyChangedFor(nameof(HasMirrorTeam))]
    [NotifyCanExecuteChangedFor(nameof(MoveMirrorTeamUpCommand))]
    [NotifyCanExecuteChangedFor(nameof(MoveMirrorTeamDownCommand))]
    [NotifyCanExecuteChangedFor(nameof(RemoveMirrorTeamCommand))]
    private MirrorTeamItem? selectedMirrorTeam;
    [ObservableProperty] private int mirrorModeIndex;
    [ObservableProperty] private int mirrorRuns = 1;
    [ObservableProperty] private bool mirrorClaimRewards;
    [ObservableProperty] private int mirrorWeeklyBonusIndex;
    public bool HasMirrorTeam => SelectedMirrorTeam is not null;

    private void LoadMirrorSettings(DesktopSettings settings)
    {
        var options = settings.Mirror ?? new MirrorOptions();
        options = options with
        {
            Teams = options.Teams?.Select(team => team with
            {
                Theme = (team.Theme ?? new()) with
                {
                    NormalWeights = LoadWeights(team.Theme?.NormalWeights, false),
                    HardWeights = LoadWeights(team.Theme?.HardWeights, true)
                }
            }).ToArray() ?? [new()]
        };
        try { MirrorPlan.ValidateConfiguration(options); }
        catch (ArgumentException exception)
        {
            Error = $"镜牢配置无效，已使用默认配置：{exception.Message}";
            options = new();
        }
        MirrorModeIndex = (int)options.Mode; MirrorRuns = options.Runs;
        MirrorClaimRewards = options.ClaimRewards; MirrorWeeklyBonusIndex = (int)options.WeeklyBonus;
        ReplaceMirrorTeams(options.Teams);

        static Dictionary<string, int> LoadWeights(Dictionary<string, int>? source, bool hard)
        {
            var result = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            if (source is null) return result;
            foreach (var pair in source)
            {
                var pack = MirrorThemeCatalog.All.FirstOrDefault(pack => pack.Id.Equals(pair.Key, StringComparison.OrdinalIgnoreCase));
                if (pack is not null && (hard ? pack.InHard : pack.InNormal) && pair.Value is >= -10 and <= 10)
                    result[pack.Id] = pair.Value;
            }
            return result;
        }
    }

    private void ReplaceMirrorTeams(MirrorTeamOptions[] teams)
    {
        MirrorTeams.Clear();
        foreach (var team in teams) MirrorTeams.Add(new(team));
        SelectedMirrorTeam = MirrorTeams.FirstOrDefault();
    }

    private MirrorOptions GetMirrorOptions() => new()
    {
        Mode = (MirrorMode)MirrorModeIndex, Runs = MirrorRuns, ClaimRewards = MirrorClaimRewards,
        WeeklyBonus = (MirrorWeeklyBonus)MirrorWeeklyBonusIndex, Teams = MirrorTeams.Select(team => team.ToOptions()).ToArray()
    };

    [RelayCommand(CanExecute = nameof(CanConfigure))]
    private void AddMirrorTeam()
    {
        var team = new MirrorTeamItem(new() { Name = $"队伍 {MirrorTeams.Count + 1}", GameTeamNumber = Math.Min(50, MirrorTeams.Count + 1) });
        MirrorTeams.Add(team); SelectedMirrorTeam = team;
    }
    private bool CanRemoveMirrorTeam() => CanConfigure && SelectedMirrorTeam is not null;
    [RelayCommand(CanExecute = nameof(CanRemoveMirrorTeam))]
    private void RemoveMirrorTeam()
    {
        if (SelectedMirrorTeam is null) return;
        var index = MirrorTeams.IndexOf(SelectedMirrorTeam);
        MirrorTeams.RemoveAt(index);
        SelectedMirrorTeam = MirrorTeams.Count == 0 ? null : MirrorTeams[Math.Min(index, MirrorTeams.Count - 1)];
    }
    private bool CanMoveMirrorTeamUp() => CanConfigure && SelectedMirrorTeam is not null && MirrorTeams.IndexOf(SelectedMirrorTeam) > 0;
    private bool CanMoveMirrorTeamDown()
    {
        var index = SelectedMirrorTeam is null ? -1 : MirrorTeams.IndexOf(SelectedMirrorTeam);
        return CanConfigure && index >= 0 && index < MirrorTeams.Count - 1;
    }
    [RelayCommand(CanExecute = nameof(CanMoveMirrorTeamUp))]
    private void MoveMirrorTeamUp() => MoveMirrorTeam(-1);
    [RelayCommand(CanExecute = nameof(CanMoveMirrorTeamDown))]
    private void MoveMirrorTeamDown() => MoveMirrorTeam(1);
    private void MoveMirrorTeam(int offset)
    {
        if (SelectedMirrorTeam is null) return;
        var selected = SelectedMirrorTeam;
        var index = MirrorTeams.IndexOf(selected); var next = index + offset;
        if (next >= 0 && next < MirrorTeams.Count)
        {
            MirrorTeams.Move(index, next);
            SelectedMirrorTeam = selected;
        }
    }
    [RelayCommand(CanExecute = nameof(CanConfigure))]
    private void SaveMirrorSettings()
    {
        try { MirrorPlan.ValidateConfiguration(GetMirrorOptions()); SaveDesktopSettings(); Error = ""; Status = "镜牢配置已保存"; }
        catch (Exception exception) { Error = exception.Message; }
    }

    private bool CanRunMirror() => !IsRunning;
    [RelayCommand(CanExecute = nameof(CanRunMirror))]
    private async Task RunMirrorAsync()
    {
        MirrorOptions options;
        try { options = GetMirrorOptions(); MirrorPlan.Validate(options); SaveDesktopSettings(); }
        catch (Exception exception) { Error = exception.Message; return; }
        if (RunTasksInClone)
        {
            await RunInCloneAsync(new(CloneTaskRequest.MirrorKind, RepositoryRoot, OcrModelsDirectory, GameLanguage, GameTheme, Mirror: options));
            return;
        }
        var context = NewTaskContext();
        RequestMonitor();
        await RunAsync(token => GameTasks.RunMirrorAsync(context, options, SaveMirrorQueueAsync, token), "mirror");
    }
}
