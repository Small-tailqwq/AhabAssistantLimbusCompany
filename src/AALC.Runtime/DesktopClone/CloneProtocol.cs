using System.Text;

namespace AALC.Runtime.DesktopClone;

/// <summary>主程序、RDP 宿主与分身内进程共用的行协议：制表符分隔字段，换行结束一条消息，自由文本用 Base64。</summary>
public static class CloneProtocol
{
    public const string Version = "1";
    public const int MaxMessageBytes = 64 * 1024;
    public const string HostRole = "rdp-host";
    public const string WorkerRole = "child-session";
    public const string WorkerFlag = "--clone-worker";

    public static string WorkerArguments(CloneWorkerStart start, string dataRoot) =>
        $"{WorkerFlag} --clone-pipe \"{start.PipeName}\" --expected-session-id {start.SessionId} --data-root \"{dataRoot}\"";

    public static string Encode(string value) => Convert.ToBase64String(Encoding.UTF8.GetBytes(value));

    public static string Decode(string value)
    {
        try { return Encoding.UTF8.GetString(Convert.FromBase64String(value)); }
        catch (FormatException) { return "无法解码远端消息"; }
    }

    public static byte[] Serialize(params string[] parts)
    {
        if (parts.Length == 0 || parts.Any(part => part.AsSpan().IndexOfAny('\t', '\r', '\n') >= 0))
            throw new ArgumentException("桌面分身消息包含非法字段", nameof(parts));
        var payload = Encoding.UTF8.GetBytes(string.Join('\t', parts) + "\n");
        if (payload.Length > MaxMessageBytes) throw new ArgumentException("桌面分身消息超过长度上限", nameof(parts));
        return payload;
    }

    public static string[] Parse(ReadOnlySpan<byte> line)
    {
        if (line.Length > MaxMessageBytes) throw new InvalidDataException("桌面分身消息超过长度上限");
        var text = Encoding.UTF8.GetString(line).TrimEnd('\r', '\n');
        if (text.Length == 0) throw new InvalidDataException("桌面分身消息为空");
        return text.Split('\t');
    }
}
