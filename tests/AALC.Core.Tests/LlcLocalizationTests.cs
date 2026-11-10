using System.IO.Compression;
using System.Net;
using AALC.Runtime.Tools;
using Xunit;

namespace AALC.Core.Tests;

public sealed class LlcLocalizationTests : IDisposable
{
    private const string PackagePrefix = "LimbusCompany_Data/Lang/LLC_zh-CN/";
    private static readonly LlcRelease Release = new("2026103002", "", new("https://github.com/llc/package.zip"), null);
    private readonly string game = Path.Combine(Path.GetTempPath(), "aaalc-llc-" + Guid.NewGuid().ToString("N"));
    private string Target => Path.Combine(game, "LimbusCompany_Data", "Lang", "LLC_zh-CN");

    public LlcLocalizationTests()
    {
        Directory.CreateDirectory(Path.Combine(game, "LimbusCompany_Data", "Lang"));
        File.WriteAllText(Path.Combine(game, GameInstallation.ExecutableName), "");
    }

    [Fact]
    public async Task ExistingFontsSurviveReinstall()
    {
        Directory.CreateDirectory(Path.Combine(Target, "Font", "Context"));
        File.WriteAllText(Path.Combine(Target, "Font", "Context", "ChineseFont.ttf"), "font");
        Directory.CreateDirectory(Path.Combine(Target, "Font", "Title"));
        File.WriteAllText(Path.Combine(Target, "Stale.json"), "old");

        var installed = await InstallCoreAsync(new PackageHandler([(PackagePrefix + "New.json", "new")], []));

        Assert.Equal("font", File.ReadAllText(Path.Combine(Target, "Font", "Context", "ChineseFont.ttf")));
        Assert.True(Directory.Exists(Path.Combine(Target, "Font", "Title")));
        Assert.Equal("new", File.ReadAllText(Path.Combine(Target, "New.json")));
        Assert.False(File.Exists(Path.Combine(Target, "Stale.json")));
        Assert.True(File.Exists(Path.Combine(installed.BackupDirectory!, "Font", "Context", "ChineseFont.ttf")));
    }

    [Fact]
    public async Task PackagedFontsReplaceExistingFonts()
    {
        Directory.CreateDirectory(Path.Combine(Target, "Font"));
        File.WriteAllText(Path.Combine(Target, "Font", "Old.ttf"), "old");

        await InstallAsync((PackagePrefix + "Font/New.ttf", "new"));

        Assert.True(File.Exists(Path.Combine(Target, "Font", "New.ttf")));
        Assert.False(File.Exists(Path.Combine(Target, "Font", "Old.ttf")));
    }

    [Fact]
    public async Task FirstInstallDownloadsFontAndRecordsVersion()
    {
        await InstallAsync((PackagePrefix + "New.json", "new"));

        Assert.True(LlcLocalization.HasFont(game));
        Assert.True(Directory.Exists(Path.Combine(Target, "Font", "Title")));
        Assert.Equal(Release.Tag, LlcLocalization.InstalledVersion(game));
    }

    [Fact]
    public async Task SameVersionWithoutFontOnlyDownloadsFont()
    {
        Directory.CreateDirectory(Target);
        File.WriteAllText(Path.Combine(Target, ".llc_version"), Release.Tag);
        File.WriteAllText(Path.Combine(Target, "Kept.json"), "kept");

        var requests = await InstallAsync();

        Assert.Equal("raw.githubusercontent.com", Assert.Single(requests).Host);
        Assert.True(LlcLocalization.HasFont(game));
        Assert.True(File.Exists(Path.Combine(Target, "Kept.json")));
    }

    [Fact]
    public async Task InvalidFontLeavesGameFilesUntouched()
    {
        await Assert.ThrowsAsync<InvalidDataException>(() => InstallCoreAsync(new PackageHandler([(PackagePrefix + "New.json", "new")], [60, 104, 116, 109])));

        Assert.False(Directory.Exists(Target));
    }

    [Fact]
    public void PackagedVersionIsRecordedForTranslationsInstalledElsewhere()
    {
        Directory.CreateDirectory(Path.Combine(Target, "Info"));
        File.WriteAllText(Path.Combine(Target, "Info", "version.json"), """{ "version": 2026103002, "notice": "" }""");

        Assert.Equal("2026103002", LlcLocalization.InstalledVersion(game));
        Assert.Equal("2026103002", File.ReadAllText(Path.Combine(Target, ".llc_version")));
    }

    [Fact]
    public void TranslationWithoutVersionInformationIsReported()
    {
        Directory.CreateDirectory(Target);

        Assert.Equal("未记录版本", LlcLocalization.InstalledVersion(game));
    }

    [Theory]
    [InlineData(HttpStatusCode.Forbidden)]
    [InlineData(HttpStatusCode.TooManyRequests)]
    public async Task RateLimitedCheckFallsBackToReleasePage(HttpStatusCode limited)
    {
        using var client = new HttpClient(new ReleasePageHandler(limited, "/LocalizeLimbusCompany/LocalizeLimbusCompany/releases/tag/2026103002", HttpStatusCode.OK));

        var release = await new LlcLocalization(client).CheckAsync(CancellationToken.None);

        Assert.Equal("2026103002", release.Tag);
        Assert.Equal("/LocalizeLimbusCompany/LocalizeLimbusCompany/releases/download/2026103002/LimbusLocalize_2026103002.zip", release.DownloadUrl.AbsolutePath);
        Assert.Equal("", release.Notes);
        Assert.Null(release.Digest);
    }

    [Fact]
    public async Task FallbackRejectsReleaseWithoutPackage()
    {
        using var client = new HttpClient(new ReleasePageHandler(HttpStatusCode.Forbidden, "/LocalizeLimbusCompany/LocalizeLimbusCompany/releases/tag/2026103002", HttpStatusCode.NotFound));

        await Assert.ThrowsAsync<InvalidDataException>(() => new LlcLocalization(client).CheckAsync(CancellationToken.None));
    }

    [Fact]
    public async Task FallbackRejectsRepositoryWithoutRelease()
    {
        using var client = new HttpClient(new ReleasePageHandler(HttpStatusCode.Forbidden, "/LocalizeLimbusCompany/LocalizeLimbusCompany/releases", HttpStatusCode.OK));

        await Assert.ThrowsAsync<InvalidDataException>(() => new LlcLocalization(client).CheckAsync(CancellationToken.None));
    }

    private async Task<IReadOnlyList<Uri>> InstallAsync(params (string Name, string Content)[] entries)
    {
        var handler = new PackageHandler(entries, [0, 1, 0, 0, 9]);
        await InstallCoreAsync(handler);
        return handler.Requests;
    }

    private async Task<LlcInstallation> InstallCoreAsync(PackageHandler handler)
    {
        using var client = new HttpClient(handler);
        return await new LlcLocalization(client).InstallAsync(game, Release, new Progress<string>(), CancellationToken.None);
    }

    public void Dispose() => Directory.Delete(game, recursive: true);

    private sealed class ReleasePageHandler(HttpStatusCode api, string latest, HttpStatusCode package) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            var uri = request.RequestUri!;
            if (uri.Host == "api.github.com") return Task.FromResult(new HttpResponseMessage(api));
            if (uri.AbsolutePath.EndsWith("/releases/latest", StringComparison.Ordinal))
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { RequestMessage = new(HttpMethod.Get, new Uri(uri, latest)) });
            return Task.FromResult(new HttpResponseMessage(package));
        }
    }

    private sealed class PackageHandler((string Name, string Content)[] entries, byte[] font) : HttpMessageHandler
    {
        public List<Uri> Requests { get; } = [];

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Requests.Add(request.RequestUri!);
            if (request.RequestUri!.Host == "raw.githubusercontent.com")
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(font) });
            using var package = new MemoryStream();
            using (var archive = new ZipArchive(package, ZipArchiveMode.Create, leaveOpen: true))
            {
                foreach (var (name, content) in entries)
                {
                    using var writer = new StreamWriter(archive.CreateEntry(name).Open());
                    writer.Write(content);
                }
            }
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(package.ToArray()) });
        }
    }
}
