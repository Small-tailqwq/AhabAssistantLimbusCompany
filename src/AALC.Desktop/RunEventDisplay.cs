using AALC.Runtime.Mail;

namespace AALC.Desktop;

/// <summary>运行记录里显示哪些事件。分身内进程用同一规则筛选，避免每帧观察都走管道。</summary>
internal static class RunEventDisplay
{
    public static bool IsShown(RunEvent item)
    {
        if (item.Rule is "mirror.route.map" or "mirror.route.scan") return false;
        if ((item.Rule.StartsWith("daily.", StringComparison.Ordinal) || item.Rule.StartsWith("mirror.", StringComparison.Ordinal)
            || item.Rule.StartsWith("battle.", StringComparison.Ordinal) || item.Rule.StartsWith("automation.", StringComparison.Ordinal)
            || item.Rule.StartsWith("team.", StringComparison.Ordinal)) &&
            (item.Action != "Progress" || string.IsNullOrWhiteSpace(item.Detail))) return false;
        return item.Action is not ("Sent" or "Complete");
    }
}
