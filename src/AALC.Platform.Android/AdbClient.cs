using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.Text;

namespace AALC.Platform.Android;

public sealed record AdbDevice(string Serial, long TransportId);

/// <summary>只使用用户已连接、已授权的 ADB transport；不扫描端口、不切换设备。</summary>
public sealed class AdbClient(string executable)
{
    public static AdbClient Local()
    {
        if (Environment.GetEnvironmentVariable("AALC_ADB") is { Length: > 0 } adb) return new(adb);
        var sdk = Environment.GetEnvironmentVariable("ANDROID_HOME") ??
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Library", "Android", "sdk");
        var candidates = new[] { Path.Combine(sdk, "platform-tools", "adb"), "/opt/homebrew/bin/adb", "/usr/local/bin/adb" };
        return new(candidates.FirstOrDefault(File.Exists) ?? "adb");
    }

    public async Task ConnectLocalAsync(int port, CancellationToken token)
    {
        if (port is < 1 or > 65535) throw new ArgumentOutOfRangeException(nameof(port), "ADB 端口须为 1–65535。");
        var endpoint = $"127.0.0.1:{port}";
        var reply = Encoding.UTF8.GetString(await RunAsync(["connect", endpoint], 65536, token)).Trim();
        if (reply != $"connected to {endpoint}" && reply != $"already connected to {endpoint}")
            throw new IOException($"无法连接模拟器：{reply}");
    }

    public async Task<IReadOnlyList<AdbDevice>> DevicesAsync(CancellationToken token)
    {
        var text = Encoding.UTF8.GetString(await RunAsync(["devices", "-l"], 1024 * 1024, token));
        var devices = new List<AdbDevice>();
        foreach (var line in text.Split('\n'))
        {
            var parts = line.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length < 3 || parts[1] != "device") continue;
            var id = parts.FirstOrDefault(p => p.StartsWith("transport_id:", StringComparison.Ordinal));
            if (id is not null && long.TryParse(id.AsSpan(13), NumberStyles.None, CultureInfo.InvariantCulture, out var transport)
                && transport > 0) devices.Add(new(parts[0], transport));
        }
        return devices;
    }

    public async Task<AdbGame> AttachAsync(AdbDevice target, CancellationToken token)
    {
        if (!(await DevicesAsync(token)).Contains(target))
            throw new InvalidOperationException("模拟器已断开或重新连接，请刷新并重新选择设备。");
        return new(this, target);
    }

    internal Task<byte[]> DeviceCommandAsync(AdbDevice device, string[] args, int limit, CancellationToken token) =>
        RunAsync(["-t", device.TransportId.ToString(CultureInfo.InvariantCulture), .. args], limit, token);

    private async Task<byte[]> RunAsync(string[] args, int limit, CancellationToken token)
    {
        token.ThrowIfCancellationRequested();
        var start = new ProcessStartInfo(executable)
        {
            UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true, CreateNoWindow = true
        };
        foreach (var argument in args) start.ArgumentList.Add(argument);
        using var process = new Process { StartInfo = start };
        try { process.Start(); }
        catch (Win32Exception e) { throw new InvalidOperationException("无法启动 adb。请安装 Android SDK Platform-Tools，或将 AALC_ADB 设为 adb 的绝对路径。", e); }
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(token);
        timeout.CancelAfter(TimeSpan.FromSeconds(15));
        try
        {
            var stderr = process.StandardError.ReadToEndAsync(timeout.Token);
            using var output = new MemoryStream();
            var buffer = new byte[81920];
            int read;
            while ((read = await process.StandardOutput.BaseStream.ReadAsync(buffer, timeout.Token)) > 0)
            {
                if (output.Length + read > limit) throw new InvalidDataException("ADB 返回数据超过大小限制。");
                output.Write(buffer, 0, read);
            }
            await process.WaitForExitAsync(timeout.Token);
            var error = await stderr;
            if (process.ExitCode != 0) throw new IOException($"ADB 操作失败：{error.Trim()}");
            return output.ToArray();
        }
        catch (OperationCanceledException) when (!token.IsCancellationRequested)
        { throw new TimeoutException("等待 ADB 超过 15 秒，请检查模拟器连接。"); }
        finally
        {
            if (!process.HasExited)
            {
                process.Kill();
                await process.WaitForExitAsync(CancellationToken.None);
            }
        }
    }
}
