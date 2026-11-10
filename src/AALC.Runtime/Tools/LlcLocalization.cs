using System.IO.Compression;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text.Json;

namespace AALC.Runtime.Tools;

public sealed record LlcRelease(string Tag, string Notes, Uri DownloadUrl, string? Digest);
public sealed record LlcInstallation(string Version, string? BackupDirectory);

public sealed class LlcLocalization(HttpClient client)
{
    public const string RepositoryUrl = "https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany";
    private const string PackagePrefix = "LimbusCompany_Data/Lang/LLC_zh-CN/";
    private const string VersionFile = ".llc_version";
    private const string FontDirectory = "Font";
    private const string FontFile = "ChineseFont.ttf";
    private const string FontUrl = "https://raw.githubusercontent.com/LocalizeLimbusCompany/LocalizeLimbusCompany/main/Fonts/ChineseFont.ttf";

    public static string InstalledVersion(string gameDirectory)
    {
        var directory = Path.Combine(GameInstallation.RequireDirectory(gameDirectory), "LimbusCompany_Data", "Lang", "LLC_zh-CN");
        var marker = Path.Combine(directory, VersionFile);
        if (File.Exists(marker)) return File.ReadAllText(marker).Trim();
        if (!Directory.Exists(directory)) return "未安装";
        // 其他工具安装的汉化没有版本文件；语言包自带的版本号与发布标签一致，补写后供后续更新判断。
        if (PackagedVersion(directory) is not { } version) return "未记录版本";
        File.WriteAllText(marker, version);
        return version;
    }

    public static bool HasFont(string gameDirectory) => ContainsFont(
        Path.Combine(GameInstallation.RequireDirectory(gameDirectory), "LimbusCompany_Data", "Lang", "LLC_zh-CN"));

    private static bool ContainsFont(string translation)
    {
        var fonts = Path.Combine(translation, FontDirectory);
        return Directory.Exists(fonts) && Directory.EnumerateFiles(fonts, "*", SearchOption.AllDirectories).Any();
    }

    private static string? PackagedVersion(string directory)
    {
        var file = Path.Combine(directory, "Info", "version.json");
        if (!File.Exists(file)) return null;
        try
        {
            using var document = JsonDocument.Parse(File.ReadAllText(file));
            return document.RootElement.TryGetProperty("version", out var version) ? version.ToString() : null;
        }
        catch (JsonException) { return null; }
    }

    public async Task<LlcRelease> CheckAsync(CancellationToken cancellationToken)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(15));
        using var request = new HttpRequestMessage(HttpMethod.Get,
            "https://api.github.com/repos/LocalizeLimbusCompany/LocalizeLimbusCompany/releases/latest");
        request.Headers.UserAgent.Add(new ProductInfoHeaderValue("AAALC", "1.0"));
        using var response = await client.SendAsync(request, timeout.Token);
        if (response.StatusCode is System.Net.HttpStatusCode.Forbidden or System.Net.HttpStatusCode.TooManyRequests)
            return await CheckWithoutApiAsync(timeout.Token);
        response.EnsureSuccessStatusCode();
        await using var content = await response.Content.ReadAsStreamAsync(timeout.Token);
        using var document = await JsonDocument.ParseAsync(content, cancellationToken: timeout.Token);
        var release = document.RootElement;
        var tag = release.GetProperty("tag_name").GetString() ?? throw new InvalidDataException("发布版本为空。");
        foreach (var asset in release.GetProperty("assets").EnumerateArray())
        {
            if (asset.GetProperty("name").GetString() != $"LimbusLocalize_{tag}.zip") continue;
            var url = new Uri(asset.GetProperty("browser_download_url").GetString()!);
            if (url.Scheme != "https" || url.Host != "github.com")
                throw new InvalidDataException("汉化附件地址不是 GitHub HTTPS 地址。");
            return new(tag, release.GetProperty("body").GetString() ?? "", url,
                asset.TryGetProperty("digest", out var digest) ? digest.GetString() : null);
        }
        throw new InvalidDataException("该版本没有 LimbusLocalize ZIP 附件。");
    }

    /// <summary>API 按 IP 限流，网页地址不受影响：latest 跳转到发布页可得版本号，附件地址可由版本号拼出；此时没有更新说明和摘要。</summary>
    private async Task<LlcRelease> CheckWithoutApiAsync(CancellationToken cancellationToken)
    {
        using var latest = await client.GetAsync(RepositoryUrl + "/releases/latest", HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        latest.EnsureSuccessStatusCode();
        var segments = latest.RequestMessage?.RequestUri?.Segments ?? [];
        if (segments.Length < 2 || segments[^2] != "tag/")
            throw new InvalidDataException("无法从发布页确定最新版本。");
        var tag = Uri.UnescapeDataString(segments[^1]);
        var escaped = Uri.EscapeDataString(tag);
        var url = new Uri($"{RepositoryUrl}/releases/download/{escaped}/LimbusLocalize_{escaped}.zip");
        using var asset = await client.GetAsync(url, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        if (asset.StatusCode == System.Net.HttpStatusCode.NotFound)
            throw new InvalidDataException("该版本没有 LimbusLocalize ZIP 附件。");
        asset.EnsureSuccessStatusCode();
        return new(tag, "", url, null);
    }

    public async Task<LlcInstallation> InstallAsync(string gameDirectory, LlcRelease release,
        IProgress<string> progress, CancellationToken cancellationToken)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromMinutes(10));
        cancellationToken = timeout.Token;
        var parent = Path.Combine(GameInstallation.RequireDirectory(gameDirectory), "LimbusCompany_Data", "Lang");
        var target = Path.Combine(parent, "LLC_zh-CN");
        var work = Path.Combine(parent, ".aaalc-llc-" + Guid.NewGuid().ToString("N"));
        var staged = Path.Combine(work, "translation");
        Directory.CreateDirectory(staged);
        try
        {
            if (InstalledVersion(gameDirectory) == release.Tag)
            {
                await DownloadFontAsync(staged, progress, cancellationToken);
                var relative = Path.Combine(FontDirectory, "Context", FontFile);
                Directory.CreateDirectory(Path.GetDirectoryName(Path.Combine(target, relative))!);
                Directory.CreateDirectory(Path.Combine(target, FontDirectory, "Title"));
                File.Move(Path.Combine(staged, relative), Path.Combine(target, relative), overwrite: true);
                return new(release.Tag, null);
            }
            progress.Report($"正在下载零协汉化 {release.Tag}…");
            var package = Path.Combine(work, "package.zip");
            using (var response = await client.GetAsync(release.DownloadUrl, HttpCompletionOption.ResponseHeadersRead, cancellationToken))
            {
                response.EnsureSuccessStatusCode();
                await using var source = await response.Content.ReadAsStreamAsync(cancellationToken);
                await using var destination = File.Create(package);
                await source.CopyToAsync(destination, cancellationToken);
            }
            if (release.Digest is not null && release.Digest.StartsWith("sha256:", StringComparison.Ordinal))
            {
                await using var stream = File.OpenRead(package);
                var hash = Convert.ToHexStringLower(await SHA256.HashDataAsync(stream, cancellationToken));
                if (!hash.Equals(release.Digest[7..], StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("汉化附件 SHA-256 校验失败，游戏文件未修改。");
            }
            progress.Report("正在检查并解压汉化文件…");
            using (var archive = ZipFile.OpenRead(package))
            {
                var count = 0;
                foreach (var entry in archive.Entries)
                {
                    cancellationToken.ThrowIfCancellationRequested();
                    var name = entry.FullName.Replace('\\', '/');
                    if (name.EndsWith('/') && PackagePrefix.StartsWith(name, StringComparison.Ordinal)) continue;
                    if (!name.StartsWith(PackagePrefix, StringComparison.Ordinal) || ((entry.ExternalAttributes >> 16) & 0xF000) == 0xA000)
                        throw new InvalidDataException($"汉化包包含目录之外的内容：{entry.FullName}");
                    var relative = name[PackagePrefix.Length..];
                    if (relative.Length == 0) continue;
                    if (relative.Split('/').Any(part => part is "." or ".." || part.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0))
                        throw new InvalidDataException($"汉化包路径无效：{entry.FullName}");
                    var path = Path.GetFullPath(Path.Combine(staged, relative));
                    if (!path.StartsWith(staged + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException($"汉化包路径越界：{entry.FullName}");
                    if (name.EndsWith('/')) { Directory.CreateDirectory(path); continue; }
                    Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                    await using var source = entry.Open();
                    await using var destination = new FileStream(path, FileMode.CreateNew);
                    await source.CopyToAsync(destination, cancellationToken);
                    count++;
                }
                if (count == 0) throw new InvalidDataException("汉化包中没有语言文件。");
            }
            await File.WriteAllTextAsync(Path.Combine(staged, VersionFile), release.Tag, cancellationToken);
            // 字体不在语言包内，由零协单独分发；整目录替换时要带上，否则游戏不显示汉化。
            var fonts = Path.Combine(target, FontDirectory);
            if (!ContainsFont(staged) && !ContainsFont(target))
                await DownloadFontAsync(staged, progress, cancellationToken);
            else if (!ContainsFont(staged))
            {
                foreach (var directory in Directory.EnumerateDirectories(fonts, "*", SearchOption.AllDirectories).Prepend(fonts))
                    Directory.CreateDirectory(Path.Combine(staged, FontDirectory, Path.GetRelativePath(fonts, directory)));
                foreach (var file in Directory.EnumerateFiles(fonts, "*", SearchOption.AllDirectories))
                {
                    cancellationToken.ThrowIfCancellationRequested();
                    File.Copy(file, Path.Combine(staged, FontDirectory, Path.GetRelativePath(fonts, file)));
                }
            }
            cancellationToken.ThrowIfCancellationRequested();
            progress.Report("正在安装汉化文件…");
            string? backup = null;
            if (Directory.Exists(target))
            {
                backup = target + ".backup-" + DateTime.Now.ToString("yyyyMMdd-HHmmss-fff") + "-" + Guid.NewGuid().ToString("N")[..8];
                Directory.Move(target, backup);
            }
            // 两次重命名之间完成提交或回滚，避免取消后留下缺失的语言目录。
            try { Directory.Move(staged, target); }
            catch
            {
                if (backup is not null) Directory.Move(backup, target);
                throw;
            }
            return new(release.Tag, backup);
        }
        finally { Directory.Delete(work, recursive: true); }
    }

    private async Task DownloadFontAsync(string translation, IProgress<string> progress, CancellationToken cancellationToken)
    {
        progress.Report("正在下载汉化字体…");
        var path = Path.Combine(translation, FontDirectory, "Context", FontFile);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        Directory.CreateDirectory(Path.Combine(translation, FontDirectory, "Title"));
        using var response = await client.GetAsync(FontUrl, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        response.EnsureSuccessStatusCode();
        await using (var source = await response.Content.ReadAsStreamAsync(cancellationToken))
        await using (var destination = File.Create(path))
            await source.CopyToAsync(destination, cancellationToken);
        var header = new byte[4];
        await using (var font = File.OpenRead(path))
            await font.ReadAtLeastAsync(header, 4, throwOnEndOfStream: false, cancellationToken);
        if (!header.AsSpan().SequenceEqual<byte>([0, 1, 0, 0]))
            throw new InvalidDataException("下载的字体文件无效，游戏文件未修改。");
    }
}
