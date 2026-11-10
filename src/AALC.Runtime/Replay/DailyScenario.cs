using System.Text.Json;
using System.Text.Json.Serialization;
using AALC.Core.Features.Daily;
using AALC.Core.Features.Mail;
using AALC.Runtime.Daily;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;

namespace AALC.Runtime.Replay;

public enum DailyScenarioActionKind { Click, Key, Drag }
public sealed record DailyScenarioTarget(string Asset, PixelPoint Center, double Score = 1,
    PixelRect? Bounds = null);
public sealed record DailyScenarioAction(string Rule, DailyScenarioActionKind Kind = DailyScenarioActionKind.Click,
    PixelPoint? Target = null, GameKey? Key = null, PixelPoint? From = null, PixelPoint? To = null);
public sealed record DailyScenarioStep(DailyScenarioTarget[] Targets, DailyScenarioAction[] ExpectedActions,
    RecognizedText[]? Text = null, bool AdvanceAfterObservation = false);
public sealed record DailyScenario(string Id, string Evidence, string Source, DailyOptions Options,
    DailyScenarioStep[] Steps, RunOutcome ExpectedOutcome = RunOutcome.Completed,
    string ExpectedReason = "日常任务已完成", int Width = 1280, int Height = 720)
{
    public static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase, WriteIndented = true,
        Converters = { new JsonStringEnumConverter() }
    };

    public static DailyScenario Load(string path) =>
        JsonSerializer.Deserialize<DailyScenario>(File.ReadAllText(path), Json)
        ?? throw new InvalidDataException("日常场景文件为空");
}
