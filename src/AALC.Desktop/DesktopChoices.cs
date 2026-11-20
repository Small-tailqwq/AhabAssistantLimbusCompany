namespace AALC.Desktop;

public sealed record ScenarioItem(string Name, string Path)
{
    public string DisplayName => Name switch
    {
        "mail-empty" => "空邮箱", "mail-rewards" => "领取奖励",
        "mail-unknown" => "无法识别的画面", _ => Name
    };
}

public sealed record ChoiceItem(string Key, string Name);
