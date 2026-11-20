using AALC.Platform.Android;
using AALC.Runtime.Automation;

namespace AALC.Cli;

internal static class PlatformDevice
{
    public const string Identifier = "ADB设备序列号";
    public const string Commands = "devices";

    public static async Task<IAttachedGame> AttachAsync(string serial, CancellationToken token)
    {
        var adb = AdbClient.Local();
        var target = (await adb.DevicesAsync(token)).SingleOrDefault(d => d.Serial == serial)
            ?? throw new InvalidOperationException("未找到已授权的模拟器，请先用 devices 查看设备序列号。");
        return await adb.AttachAsync(target, token);
    }
}
