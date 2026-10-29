namespace AALC.Core.Features.Daily;

public sealed record DailyOptions
{
    public bool RunLuxcavation { get; init; } = true;
    public int ExpCount { get; init; } = 1;
    public int ThreadCount { get; init; } = 3;
    public int TeamNumber { get; init; } = 1;
    public bool SelectTeamByOrder { get; init; }
    public bool UseContinuousCombat { get; init; }
    public int MaxContinuousCombat { get; init; } = 1;
    public bool ExpTeamByDay { get; init; }
    public int[] ExpTeams { get; init; } = [1, 1, 1, 1];
    public bool ThreadTeamByDay { get; init; }
    public int[] ThreadTeams { get; init; } = [1, 1, 1, 1, 1, 1, 1];
    public bool HandleChoiceEvents { get; init; } = true;
    public bool ConvertModules { get; init; } = true;
    public bool ClaimRewards { get; init; }
    public bool ClaimMail { get; init; } = true;
    public bool ClaimMissions { get; init; } = true;
    public bool ClaimSeasonMissions { get; init; }
    public bool ClaimPassLevels { get; init; }
    public bool BuyStamina { get; init; }
    public int RefillTier { get; init; } = 2;
    public bool GrandetMode { get; init; }
}

public enum LuxcavationKind { Experience, Thread }
