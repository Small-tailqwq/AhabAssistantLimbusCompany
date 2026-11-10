using AALC.Runtime.Automation;
using System.Text.RegularExpressions;
using AALC.Core.Features.Mail;

namespace AALC.Runtime.Automation;

public sealed class BattleEvents
{
    public static bool HasNarration(GameFrame frame, IReadOnlyList<RecognizedText> entries) =>
        entries.Any(entry => Normalize(entry.Text).Equals("SKIP", StringComparison.OrdinalIgnoreCase)
            && Center(entry).X > frame.Identity.Width * .65 && Center(entry).Y > frame.Identity.Height * .75)
        && entries.Any(entry => entry.Bounds.Right < frame.Identity.Width * .55
            && Center(entry).Y > frame.Identity.Height * .3 && Normalize(entry.Text).Length >= 6);

    public static readonly ImageQuery[] Queries = [new("event/choices_assets.png"),
        new("event/select_first_option_assets.png"), new("event/perform_the_check_feature_assets.png"),
        new("event/continue_assets.png"), new("event/proceed_assets.png"), new("event/commence_assets.png"),
        new("event/skip_assets.png"), new("event/very_high.png"), new("event/high.png"),
        new("event/normal.png"), new("event/low.png"), new("event/very_low.png")];
    private int choiceAttempts;
    private int checkAttempts;
    private TimeSpan? participantRequestedAt;
    private string? narrationState;
    private TimeSpan narrationUnchangedSince;
    public TimeSpan NextObservationDelay { get; private set; } = TimeSpan.FromMilliseconds(500);

    public async Task<(bool Handled, bool Failed)> HandleAsync(IGameSession s, GameFrame frame,
        IReadOnlyList<RecognizedText> entries, CancellationToken ct)
    {
        NextObservationDelay = TimeSpan.FromMilliseconds(500);
        var header = entries.FirstOrDefault(entry => Normalize(entry.Text).ToLowerInvariant() is "选项" or "choices");
        if (header is not null || frame.Find("event/choices_assets.png") is not null)
        {
            narrationState = null;
            if (++choiceAttempts > 8)
            {
                s.Report("battle.event.stalled", "事件选项连续八次未推进，停止本批战斗");
                return (true, true);
            }
            s.Report("battle.event.choice", "处理战斗事件选项");
            // 原始槽位常量对应 900p，区别于其余锚点的 1440p 基准。
            var choiceScale = frame.Scale * 1.6;
            var first = header is null ? null : Choice(entries, header, 0, choiceScale);
            var second = header is null ? null : Choice(entries, header, 1, choiceScale);
            var spacing = first is not null && second is not null ? Center(second).Y - Center(first).Y
                : (int)Math.Round(124 * choiceScale);
            if (first is not null && IsDisabled(frame, Center(first), spacing))
            {
                if (second is not null)
                    await s.ClickAsync(frame, Center(second), "battle.event.next-enabled-choice", ct);
            }
            else if (frame.Find("event/select_first_option_assets.png") is { } template)
                await s.ClickAsync(frame, template.Center, "battle.event.first-choice-template", ct);
            else if (first is not null)
                await s.ClickAsync(frame, Center(first), "battle.event.first-choice-ocr", ct);
            await s.DelayAsync(TimeSpan.FromMilliseconds(750), ct);
            return (true, false);
        }
        var result = entries.Any(entry => Normalize(entry.Text).Contains("判定成功") || Normalize(entry.Text).Contains("判定失败"));
        var skip = entries.FirstOrDefault(entry => Normalize(entry.Text).Equals("SKIP", StringComparison.OrdinalIgnoreCase)
            && Center(entry).X > frame.Identity.Width * 0.65 && Center(entry).Y > frame.Identity.Height * 0.75);
        var narration = entries.FirstOrDefault(entry => entry.Bounds.Right < frame.Identity.Width * 0.55
            && Center(entry).Y > frame.Identity.Height * 0.3 && Normalize(entry.Text).Length >= 6);
        var checkButtons = entries.Where(entry => Center(entry).X > frame.Identity.Width * .55
            && Center(entry).Y > frame.Identity.Height * .55).ToArray();
        var perform = checkButtons.FirstOrDefault(entry => Normalize(entry.Text).ToLowerInvariant() is "进行判定" or "performthecheck");
        var probabilities = entries.Select(entry => (Entry: entry, Rank: ProbabilityRank(entry.Text)))
            .Where(value => value.Rank.HasValue && Center(value.Entry).Y > frame.Identity.Height * .8)
            .OrderBy(value => value.Rank).ThenBy(value => value.Entry.Bounds.X).ToArray();
        var probabilityTargets = new[] { "event/very_high.png", "event/high.png", "event/normal.png", "event/low.png", "event/very_low.png" }
            .Select(frame.Find).OfType<VisualTarget>().Where(target => target.Center.Y > frame.Identity.Height * .8).ToArray();
        var checkFeature = frame.Find("event/perform_the_check_feature_assets.png") is not null;
        if (checkFeature || probabilities.Length > 0 || probabilityTargets.Length > 0)
            perform ??= checkButtons.FirstOrDefault(entry => Normalize(entry.Text).Equals("commence", StringComparison.OrdinalIgnoreCase));
        var participantPrompt = entries.Any(entry => Normalize(entry.Text).Contains("罪人")
            && (Normalize(entry.Text).Contains("选择") || Normalize(entry.Text).Contains("挑选")));
        var checkPage = !result && (checkFeature
            || perform is not null
            || (probabilities.Length > 0 || probabilityTargets.Length > 0) && (participantPrompt || participantRequestedAt is not null));
        if (checkPage)
        {
            narrationState = null;
            choiceAttempts = 0;
            if (++checkAttempts > 8)
            {
                s.Report("battle.event.stalled", "事件判定连续八次未推进，停止本批战斗");
                return (true, true);
            }
            if (perform is not null)
            {
                s.Report("battle.event.check", "进行事件判定");
                await s.ClickAsync(frame, Center(perform), "battle.event.perform-check-ocr", ct);
                return (true, false);
            }
            if (participantRequestedAt is { } requestedAt
                && (!participantPrompt || s.Elapsed - requestedAt < TimeSpan.FromMilliseconds(1250)))
                return (true, false);
            if (probabilityTargets.FirstOrDefault() is { } target)
            {
                s.Report("battle.event.check", "选择事件判定罪人");
                await s.ClickAsync(frame, ParticipantPoint(frame, target.Bounds), "battle.event.select-probability", ct);
                participantRequestedAt = s.Elapsed;
                return (true, false);
            }
            if (probabilities.Length > 0)
            {
                s.Report("battle.event.check", "根据成功率选择事件判定罪人");
                await s.ClickAsync(frame, ParticipantPoint(frame, probabilities[0].Entry.Bounds), "battle.event.select-probability-ocr", ct);
                participantRequestedAt = s.Elapsed;
                return (true, false);
            }
            await s.DelayAsync(TimeSpan.FromMilliseconds(750), ct);
            return (true, false);
        }
        checkAttempts = 0;
        choiceAttempts = 0;
        if (result) participantRequestedAt = null;
        foreach (var asset in new[] { "event/continue_assets.png", "event/proceed_assets.png", "event/commence_assets.png", "event/skip_assets.png" })
            if (frame.Find(asset) is { } action)
            {
                narrationState = null;
                s.Report("battle.event.advance", "推进战斗事件");
                await s.ClickAsync(frame, action.Center, "battle.event.advance-template", ct);
                return (true, false);
            }
        var context = result || entries.Any(entry => !Normalize(entry.Text).Contains("进行判定") &&
            new[] { "事件", "判定", "选项" }.Any(word => Normalize(entry.Text).Contains(word)));
        var advance = context || skip is not null && narration is not null ? entries.FirstOrDefault(entry =>
            Center(entry).X > frame.Identity.Width * .65 && Center(entry).Y > frame.Identity.Height * .65
            && Normalize(entry.Text).ToLowerInvariant() is "继续" or "前进" or "开始" or "继续前进" or "开始战斗"
                or "continue" or "proceed" or "commence" or "start") : null;
        advance ??= context ? perform : null;
        if (advance is not null)
        {
            narrationState = null;
            s.Report("battle.event.advance", "识别并推进事件按钮");
            await s.ClickAsync(frame, Center(advance), "battle.event.advance-ocr", ct);
            return (true, false);
        }
        if (skip is not null && narration is not null)
        {
            var state = (result ? "result:" : "narration:") + string.Join("\n", entries.Where(entry =>
                entry.Bounds.Right < frame.Identity.Width * .55 && Center(entry).Y > frame.Identity.Height * .3)
                .OrderBy(entry => entry.Bounds.Y).ThenBy(entry => entry.Bounds.X).Select(entry => Normalize(entry.Text)));
            if (narrationState != state)
            {
                narrationState = state;
                narrationUnchangedSince = s.Elapsed;
            }
            else if (s.Elapsed - narrationUnchangedSince >= TimeSpan.FromSeconds(10))
            {
                s.Report("battle.event.stalled", "事件叙述十秒未推进，停止本批战斗");
                return (true, true);
            }
            s.Report(result ? "battle.event.result" : "battle.event.reveal", "按空格推进事件叙述");
            await s.KeyAsync(frame, GameKey.Space, "battle.event.advance-space", ct);
            participantRequestedAt = null;
            NextObservationDelay = TimeSpan.FromMilliseconds(150);
            return (true, false);
        }
        narrationState = null;
        if (result)
        {
            s.Report("battle.event.wait-result", "等待事件结果页面");
            await s.DelayAsync(TimeSpan.FromSeconds(1), ct);
            return (true, false);
        }
        return (false, false);
    }

    private static string Normalize(string value) => Regex.Replace(value, @"\s+", "");
    private static PixelPoint Center(RecognizedText value) => new(value.Bounds.X + value.Bounds.Width / 2,
        value.Bounds.Y + value.Bounds.Height / 2);

    private static PixelPoint ParticipantPoint(GameFrame frame, PixelRect probability) =>
        new(probability.X + probability.Width / 2, Math.Min(frame.Identity.Height - 1,
            probability.Bottom + (int)(60 * frame.Scale)));

    private static int? ProbabilityRank(string value) => Normalize(value).ToLowerInvariant() switch
    {
        "veryhigh" or "极高" or "非常高" or "很高" => 0,
        "high" or "高" => 1,
        "normal" or "一般" or "普通" or "中等" or "正常" => 2,
        "low" or "低" => 3,
        "verylow" or "极低" or "非常低" or "很低" => 4,
        _ => null
    };

    private static RecognizedText? Choice(IReadOnlyList<RecognizedText> entries, RecognizedText header, int slot, double scale)
    {
        var origin = Center(header);
        var expected = origin.Y + (105 + 124 * slot) * scale;
        return entries.Where(entry =>
            {
                var text = Normalize(entry.Text); var center = Center(entry);
                return text.Length > 0 && text.ToLowerInvariant() is not ("选项" or "choices" or "skip") && !Regex.IsMatch(text, @"^[\d:.：]+$")
                    && center.X >= origin.X - 100 * scale && center.X <= origin.X + 300 * scale
                    && Math.Abs(center.Y - expected) <= 50 * scale;
            }).OrderBy(entry => Math.Abs(Center(entry).Y - expected)).FirstOrDefault();
    }

    private static bool IsDisabled(GameFrame frame, PixelPoint center, int spacing)
    {
        if (spacing <= 0) return false;
        var scale = spacing / 124.0;
        var left = (int)Math.Round(center.X - 112 * scale); var right = (int)Math.Round(center.X + 490 * scale);
        var top = (int)Math.Round(center.Y - 38 * scale); var bottom = (int)Math.Round(center.Y + 62 * scale);
        if (left < 0 || top < 0 || right > frame.Identity.Width || bottom > frame.Identity.Height || left >= right || top >= bottom) return false;
        var visible = 0; var saturated = 0;
        for (var y = top; y < bottom; y++)
            for (var x = left; x < right; x++)
            {
                var offset = (y * frame.Identity.Width + x) * 4;
                var b = frame.Pixels.Bgra[offset]; var g = frame.Pixels.Bgra[offset + 1]; var r = frame.Pixels.Bgra[offset + 2];
                var high = Math.Max(r, Math.Max(g, b)); var low = Math.Min(r, Math.Min(g, b));
                if (high > 40) visible++;
                if (high > 0 && (high - low) * 255.0 / high > 30) saturated++;
            }
        var size = (right - left) * (bottom - top);
        return visible / (double)size >= 0.5 && saturated / (double)size < 0.15;
    }
}
