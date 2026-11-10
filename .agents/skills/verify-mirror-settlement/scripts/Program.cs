using System.Text.Json;
using AALC.Core.Automation;
using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;
using AALC.Runtime.Mirror;

var failures = 0;
foreach (var test in new[]
{
    new Case("PaidRoundRotatesOnce"),
    new Case("NextEligibleTeamRunsNext", Runs: 2),
    new Case("KeepRewardsPreservesQueue", Fault: Fault.KeepRewards),
    new Case("NoClearEvidenceCannotSpend", Fault: Fault.NoClear),
    new Case("NoReceiptCannotRotate", Fault: Fault.NoReceipt),
    new Case("ReturnedWithoutReceiptCannotRotate", Fault: Fault.NoReceiptReturned),
    new Case("NoReturnedEntranceCannotRotate", Fault: Fault.NoReturn),
    new Case("UnchangedSubmissionCannotRepeat", Fault: Fault.UnchangedSubmission),
    new Case("WeeklyNone", Weekly: MirrorWeeklyBonus.None, Bonuses: 3),
    new Case("WeeklyOne", Weekly: MirrorWeeklyBonus.One, Bonuses: 3),
    new Case("WeeklyAll", Weekly: MirrorWeeklyBonus.All, Bonuses: 3),
    new Case("UnchangedWeeklyCannotSpend", Fault: Fault.UnchangedWeekly, Bonuses: 3),
    new Case("RestartBeforePaymentCanResume", Fault: Fault.RestartBeforePayment),
    new Case("RestartAfterReceiptCannotStartAnotherRound", Fault: Fault.RestartAfterReceipt),
    new Case("BlockedReceiptCanResume", Fault: Fault.BlockReceipt),
    new Case("CancelAfterClaimKeepsRotation", Fault: Fault.CancelBeforeSave),
    new Case("CancelBeforeRunCannotSpend", Fault: Fault.CancelBeforeRun)
})
{
    using var stop = new CancellationTokenSource();
    var host = new Host(test);
    var events = new List<RunEvent>();
    var session = new GameSession(host, host, host, events.Add, TimeSpan.FromHours(6), "Mirror",
        test.Fault is Fault.RestartAfterReceipt or Fault.RestartBeforePayment ? host : null);
    var teams = new MirrorTeamOptions[]
    {
        new() { Name = "disabled", Enabled = false },
        new() { Name = "hard", Mode = MirrorTeamMode.Hard },
        new() { Name = "A", GameTeamNumber = 1 }, new() { Name = "B", GameTeamNumber = 2 }
    };
    var saved = new List<string[]>();
    var saveAttempts = 0;
    Task Save(MirrorTeamOptions[] queue, CancellationToken token)
    {
        saveAttempts++;
        if (test.Fault == Fault.CancelBeforeSave) stop.Cancel();
        token.ThrowIfCancellationRequested();
        saved.Add(queue.Select(team => team.Name).ToArray());
        return Task.CompletedTask;
    }
    if (test.Fault == Fault.CancelBeforeRun) stop.Cancel();
    var result = await new MirrorRunner(session, new NoMap(), Save).RunAsync(new()
    {
        Runs = test.Runs, ClaimRewards = test.Fault != Fault.KeepRewards,
        WeeklyBonus = test.Weekly, Teams = teams
    }, stop.Token);
    var errors = new List<string>();
    void Check(bool condition, string rule) { if (!condition) errors.Add(rule); }
    var shouldFail = test.Fault is Fault.NoClear or Fault.NoReceipt or Fault.NoReceiptReturned or Fault.NoReturn
        or Fault.UnchangedSubmission or Fault.UnchangedWeekly;
    var shouldPay = test.Fault is not (Fault.KeepRewards or Fault.NoClear or Fault.UnchangedWeekly or Fault.CancelBeforeRun);
    if (shouldFail) Check(result.Outcome == RunOutcome.Failed, "IncompleteSettlementMustFail");
    else if (test.Fault is Fault.CancelBeforeRun or Fault.CancelBeforeSave)
        Check(result.Outcome == RunOutcome.Cancelled, "CancellationMustBeReported");
    else Check(result.Outcome == RunOutcome.Completed, "RoundMustComplete");
    Check(host.Payments <= test.Runs, "NoExtraModuleSubmission");
    Check(host.NewEntries <= Math.Max(test.Runs - 1, test.Fault == Fault.RestartBeforePayment ? 1 : 0), "NoUnplannedRound");
    if (!shouldPay) Check(host.Payments == 0, "NoPaymentWithoutPermissionAndClearEvidence");
    if (shouldFail || test.Fault is Fault.KeepRewards or Fault.CancelBeforeRun)
        Check(saved.Count == 0, "NoRotationWithoutVerifiedClaim");
    else Check(saved.Count == test.Runs, "ClaimedRoundMustSaveRotation");
    if (!shouldFail && shouldPay && test.Fault != Fault.CancelBeforeRun)
        Check(host.ReceiptsClosed == test.Runs, "OneClosedReceiptPerPlannedRound");
    if (saved.Count > 0)
        Check(saved[0].SequenceEqual(["disabled", "hard", "B", "A"]), "OnlyCompletedEligibleTeamMoves");
    if (test.Runs == 2)
    {
        Check(saved.Count == 2 && saved[1].SequenceEqual(["disabled", "hard", "A", "B"]), "SecondEligibleTeamMovesNext");
        Check(events.Where(e => e.Rule == "mirror.run.begin").Select(e => e.Detail ?? "")
            .SequenceEqual(["第 1/2 轮 · A · 游戏队伍 1", "第 2/2 轮 · B · 游戏队伍 2"]), "NextRunUsesRotatedQueue");
    }
    if (test.Bonuses > 0 && test.Fault != Fault.UnchangedWeekly)
    {
        var expected = test.Weekly switch { MirrorWeeklyBonus.None => 0, MirrorWeeklyBonus.One => 1, _ => test.Bonuses };
        Check(host.BonusesAtPayment.SequenceEqual([expected]), "WeeklyChoiceObservedBeforePayment");
    }
    Check(host.UnexpectedInputs.Count == 0, "OnlyExpectedInputs");
    if (test.Fault == Fault.UnchangedWeekly) Check(host.WeeklyClicks == 1, "NoRepeatedWeeklyWithoutObservedDecrease");
    if (errors.Count > 0) failures++;
    Console.WriteLine(JsonSerializer.Serialize(new
    {
        test = test.Name, pass = errors.Count == 0, errors, outcome = result.Outcome.ToString(),
        result.Reason, result.Observations, result.ElapsedMilliseconds,
        host.Payments, host.ReceiptsClosed, host.NewEntries, host.Restarts, host.Blocks, host.WeeklyClicks,
        saveAttempts, saved, host.BonusesAtPayment, host.UnexpectedInputs,
        actions = events.Where(e => e.Action is "Click" || e.Rule.StartsWith("mirror.") || e.Rule.StartsWith("game."))
            .Select(e => new { e.Rule, e.Action, e.Detail }).ToArray()
    }));
}

var queueCases = 0;
var queueErrors = 0;
foreach (var mode in new[] { MirrorMode.Normal, MirrorMode.Hard })
for (var bits = 0; bits < 256; bits++)
{
    var teams = Enumerable.Range(0, 4).Select(i => ((bits >> (i * 2)) & 3) switch
    {
        0 => new MirrorTeamOptions { Name = i.ToString(), Enabled = false },
        1 => new MirrorTeamOptions { Name = i.ToString(), Mode = MirrorTeamMode.Normal },
        2 => new MirrorTeamOptions { Name = i.ToString(), Mode = MirrorTeamMode.Hard },
        _ => new MirrorTeamOptions { Name = i.ToString(), Mode = MirrorTeamMode.Both }
    }).ToArray();
    var eligible = Array.FindIndex(teams, t => MirrorPlan.Eligible(t, mode));
    if (eligible < 0) continue;
    queueCases++;
    var rotated = MirrorPlan.Rotate(teams, eligible);
    var next = teams.Skip(eligible + 1).FirstOrDefault(t => MirrorPlan.Eligible(t, mode)) ?? teams[eligible];
    var stableOrder = true;
    for (var left = 0; left < teams.Length; left++)
    for (var right = left + 1; right < teams.Length; right++)
        if (left != eligible && right != eligible)
            stableOrder &= Array.IndexOf(rotated, teams[left]) < Array.IndexOf(rotated, teams[right]);
    if (rotated.Length != teams.Length || !stableOrder
        || !teams.All(team => rotated.Count(item => ReferenceEquals(item, team)) == 1)
        || !ReferenceEquals(rotated.Last(), teams[eligible])
        || !ReferenceEquals(rotated.First(t => MirrorPlan.Eligible(t, mode)), next)
        || !teams.Select(t => t.Name).SequenceEqual(["0", "1", "2", "3"])) queueErrors++;
}
Console.WriteLine(JsonSerializer.Serialize(new { test = "BoundedEligibleQueueRotation", pass = queueErrors == 0, cases = queueCases, errors = queueErrors }));
if (queueErrors > 0) failures++;
Console.WriteLine(JsonSerializer.Serialize(new { summary = true, checks = 18, failed = failures }));
return failures == 0 ? 0 : 1;

enum Fault { None, KeepRewards, NoClear, NoReceipt, NoReceiptReturned, NoReturn, UnchangedSubmission, UnchangedWeekly,
    RestartBeforePayment, RestartAfterReceipt, BlockReceipt, CancelBeforeSave, CancelBeforeRun }
sealed record Case(string Name, Fault Fault = Fault.None, int Runs = 1,
    MirrorWeeklyBonus Weekly = MirrorWeeklyBonus.None, int Bonuses = 0);

sealed class NoMap : IMirrorMapReader
{
    public MirrorMapSnapshot Read(PixelFrame frame, PixelPoint bus, CancellationToken cancellationToken) =>
        throw new InvalidOperationException("结算探针不应进入地图识别");
}

sealed class Host(Case test) : IGameVision, IGameInput, IRunClock, IGameRestarter
{
    private const string Receipt = "mirror/claim_reward/rewards_acquired_assets.png";
    private const string Entrance = "mirror/road_to_mir/enter_mirror_assets.png";
    private const string Enter = "mirror/road_to_mir/enter_assets.png";
    private string page = "settlement";
    private bool faultInjected;
    private bool restartPending = test.Fault == Fault.RestartBeforePayment;
    private int selected = test.Bonuses;
    private int observations;
    private GameFrame? latest;
    public TimeSpan Elapsed { get; private set; }
    public int Payments { get; private set; }
    public int ReceiptsClosed { get; private set; }
    public int NewEntries { get; private set; }
    public int Restarts { get; private set; }
    public int Blocks { get; private set; }
    public int WeeklyClicks { get; private set; }
    public List<int> BonusesAtPayment { get; } = [];
    public List<string> UnexpectedInputs { get; } = [];

    public ValueTask<GameFrame> ObserveAsync(IReadOnlyList<ImageQuery> queries, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        if (observations >= 500) throw new InvalidOperationException("探针观察超过 500 帧");
        List<string> assets = restartPending ? ["base/try_again.png"] : page switch
        {
            "settlement" => test.Fault == Fault.NoClear
                ? [MirrorSettlementFlow.Claim, MirrorSettlementFlow.UseModules]
                : [MirrorSettlementFlow.Clear, MirrorSettlementFlow.UseModules],
            "receipt" => [Receipt],
            "entrance" => [Entrance],
            "home" => ["home/drive_assets.png", "home/mail_assets.png"],
            "enter" => [Enter, "mirror/road_to_mir/infinity_mirror_locked.png"],
            _ => []
        };
        var hits = assets.Select((asset, i) => Hit(asset, 400 + 60 * i)).ToList();
        if (page == "settlement" && !restartPending)
            hits.AddRange(Enumerable.Range(0, selected).Select(i => Hit(MirrorSettlementFlow.Weekly, 900 + 200 * i)));
        latest = new(new(new(++observations, 2560, 1440, 1, 0), []),
            hits.Where(hit => queries.Any(query => query.Asset == hit.Asset)).ToArray());
        return ValueTask.FromResult(latest);
    }

    public ValueTask<IReadOnlyList<RecognizedText>> ReadTextAsync(GameFrame frame, CancellationToken ct,
        PixelRect? region = null, int scale = 1, TextPreprocessing preprocessing = TextPreprocessing.None)
    {
        ct.ThrowIfCancellationRequested();
        IReadOnlyList<RecognizedText> result = restartPending
            ? [new("游戏无法运行", 1, new(100, 100, 200, 30)), new("即将关闭游戏", 1, new(100, 140, 200, 30))] : [];
        return ValueTask.FromResult(result);
    }

    public ValueTask ClickAtAsync(PixelPoint target, FrameIdentity frame, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        if (latest?.Identity != frame) throw new InvalidOperationException("探针收到旧帧输入");
        var hit = latest.Targets.FirstOrDefault(h => h.Center == target);
        if (hit is null) throw new InvalidOperationException("探针收到非控件点击");
        switch (hit.Asset)
        {
            case MirrorSettlementFlow.Weekly:
                WeeklyClicks++;
                if (test.Fault != Fault.UnchangedWeekly) selected--;
                break;
            case MirrorSettlementFlow.UseModules:
                Payments++;
                BonusesAtPayment.Add(selected);
                if (test.Fault != Fault.UnchangedSubmission)
                    page = test.Fault switch { Fault.NoReceipt => "blank", Fault.NoReceiptReturned => "entrance", _ => "receipt" };
                break;
            case Receipt:
                if (test.Fault == Fault.BlockReceipt && Blocks == 0)
                {
                    Blocks++;
                    throw new GameInputBlockedException("探针模拟回执确认时光标移动被拒绝");
                }
                ReceiptsClosed++;
                page = test.Fault == Fault.NoReturn ? "blank" : "entrance";
                if (test.Fault == Fault.RestartAfterReceipt && !faultInjected)
                {
                    restartPending = true;
                    faultInjected = true;
                }
                break;
            case "home/drive_assets.png": page = "entrance"; break;
            case Entrance: page = "enter"; break;
            case Enter:
                NewEntries++;
                page = "settlement";
                break;
            default:
                UnexpectedInputs.Add(hit.Asset);
                throw new InvalidOperationException("探针收到额外输入 " + hit.Asset);
        }
        return ValueTask.CompletedTask;
    }

    public ValueTask RestartAsync(CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        Restarts++;
        restartPending = false;
        page = "home";
        return ValueTask.CompletedTask;
    }
    public ValueTask DelayAsync(TimeSpan duration, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        Elapsed += duration;
        return ValueTask.CompletedTask;
    }
    public ValueTask KeyPressAsync(GameKey key, FrameIdentity frame, CancellationToken ct) => throw new NotSupportedException();
    public ValueTask DragAsync(PixelPoint from, PixelPoint to, TimeSpan duration, FrameIdentity frame, CancellationToken ct) => throw new NotSupportedException();
    private static VisualTarget Hit(string asset, int x) => new(asset, new(x, 350), new(x - 20, 340, 40, 20), 1);
}
