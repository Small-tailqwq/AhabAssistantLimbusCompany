using System.Text.Json;
using System.Text.RegularExpressions;
using AALC.Core.Features.Mirror;
using AALC.Runtime;
using Xunit;

namespace AALC.Core.Tests;

public sealed class MirrorThemeCatalogTests
{
    [Fact]
    public void EveryAliasResolvesToItsStableIdAndTheDefaultsForBothModes()
    {
        var normal = new MirrorThemeOptions();
        var hard = normal with { HardMode = true };
        foreach (var pack in MirrorThemeCatalog.All)
        {
            Assert.Equal(pack.Id, MirrorThemeCatalog.Match(pack.TitleZh)?.Id);
            foreach (var alias in pack.OcrAliases)
            {
                Assert.Equal(pack.Id, MirrorThemeCatalog.Match(alias)?.Id);
                Assert.Equal(pack.InNormal ? pack.DefaultNormalWeight : normal.UnknownWeight, normal.WeightFor(alias));
                Assert.Equal(pack.DefaultHardWeight, hard.WeightFor(alias));
            }
        }
    }

    [Fact]
    public void AllReferenceNamesImagesAndOcrAlternativesArePresent()
    {
        using var reference = JsonDocument.Parse(File.ReadAllText(
            Path.Combine(AppContext.BaseDirectory, "Fixtures", "mirror-theme-catalog.json")));
        foreach (var hard in new[] { false, true })
        {
            var mode = reference.RootElement.GetProperty(hard ? "hard" : "normal");
            var images = mode.GetProperty("images");
            foreach (var pair in mode.GetProperty("names").EnumerateObject())
            {
                var pack = MirrorThemeCatalog.Match(pair.Name);
                Assert.NotNull(pack);
                Assert.Contains(pair.Value.GetString(), pack.OcrAliases);
                Assert.Equal(pack.Id, MirrorThemeCatalog.Match(pair.Value.GetString()!)?.Id);
                Assert.Equal("assets/app/theme_packs/" + images.GetProperty(pair.Name).GetString(), hard ? pack.HardImage : pack.NormalImage);
            }
        }
        foreach (var pair in reference.RootElement.GetProperty("ocrAliases").EnumerateObject())
            Assert.Equal(MirrorThemeCatalog.Match(pair.Value.GetString()!)?.Id, MirrorThemeCatalog.Match(pair.Name)?.Id);
    }

    [Fact]
    public void EveryChineseAndEnglishExampleWeightHasTheSameCatalogDefault()
    {
        var path = Path.Combine(RepositoryRoot(), "assets/config/theme_pack_list.example.yaml");
        var hard = false;
        var checkedEntries = 0;
        foreach (var line in File.ReadLines(path))
        {
            if (line.StartsWith("theme_pack_list", StringComparison.Ordinal)) hard = line.Contains("_hard");
            var match = Regex.Match(line, @"^  ([^:#]+):\s*(-?\d+)");
            if (!match.Success) continue;
            var alias = match.Groups[1].Value.Trim();
            var pack = MirrorThemeCatalog.Match(alias);
            Assert.NotNull(pack);
            Assert.Contains(alias, pack.OcrAliases);
            Assert.Equal(int.Parse(match.Groups[2].Value), hard ? pack.DefaultHardWeight : pack.DefaultNormalWeight);
            checkedEntries++;
        }
        Assert.Equal(182, checkedEntries);
    }

    [Theory]
    [InlineData("forgot", "被遗忘者们")]
    [InlineData("lake", "湖的世界")]
    [InlineData("miracle", "20区的奇迹 复刻")]
    [InlineData("spring", "切磋琢春")]
    [InlineData("dolen", "待情感懒惰者")]
    [InlineData("heartb", "心意相悖")]
    [InlineData("corpses", "尸山血海")]
    [InlineData("s.e.a", "去·海·边")]
    public void DisplayNamesUseTheVerifiedCoverText(string id, string title)
    {
        Assert.Equal(title, MirrorThemeCatalog.All.Single(pack => pack.Id == id).TitleZh);
        Assert.Equal(id, MirrorThemeCatalog.Match(title)?.Id);
    }

    [Fact]
    public void CoversAreRepositoryRelativeAndTheCommonPacksAreAvailableInHardMode()
    {
        var root = RepositoryRoot();
        Assert.Equal(87, MirrorThemeCatalog.All.Count);
        Assert.Equal(53, MirrorThemeCatalog.All.Count(pack => pack.InNormal));
        Assert.Equal(87, MirrorThemeCatalog.All.Select(pack => pack.Id).Distinct().Count());
        foreach (var pack in MirrorThemeCatalog.All)
        {
            Assert.True(pack.InHard);
            Assert.False(Path.IsPathRooted(pack.NormalImage));
            Assert.True(File.Exists(Path.Combine(root, pack.NormalImage)), pack.NormalImage);
            if (pack.HardImage is { } hardImage) Assert.True(File.Exists(Path.Combine(root, hardImage)), hardImage);
            if (pack.InNormal) Assert.Equal(pack.DefaultNormalWeight, pack.DefaultHardWeight);
        }
    }

    [Fact]
    public void ModeOverridesRoundTripAsStableIdsAndApplyToBothLanguageAliases()
    {
        var options = new MirrorThemeOptions { NormalWeights = new() { ["sweep"] = 8 }, HardWeights = new() { ["sweep"] = 2 } };
        var copy = JsonSerializer.Deserialize<MirrorThemeOptions>(JsonSerializer.Serialize(options))!;
        Assert.Equal(8, copy.WeightFor("清扫"));
        Assert.Equal(8, copy.WeightFor("Nocturnal Sweeping"));
        Assert.Equal(2, (copy with { HardMode = true }).WeightFor("清扫"));
        Assert.Equal(2, (copy with { HardMode = true }).WeightFor("Nocturnal Sweeping"));
    }

    public static IEnumerable<object[]> InvalidThemes()
    {
        yield return [new MirrorThemeOptions { Floor = 0 }];
        yield return [new MirrorThemeOptions { Floor = 6 }];
        yield return [new MirrorThemeOptions { RefreshLimit = 11 }];
        yield return [new MirrorThemeOptions { PreferredThreshold = 11 }];
        yield return [new MirrorThemeOptions { UnknownWeight = -11 }];
        yield return [new MirrorThemeOptions { NormalWeights = null! }];
        yield return [new MirrorThemeOptions { HardWeights = null! }];
        yield return [new MirrorThemeOptions { NormalWeights = new() { ["theb"] = 1 } }];
        yield return [new MirrorThemeOptions { HardWeights = new() { ["missing"] = 1 } }];
        yield return [new MirrorThemeOptions { NormalWeights = new() { ["forgot"] = -11 } }];
        yield return [new MirrorThemeOptions { HardWeights = new() { ["forgot"] = 11 } }];
    }

    [Theory]
    [MemberData(nameof(InvalidThemes))]
    public void InvalidThemeConfigurationHasAReadableParameterError(MirrorThemeOptions theme)
    {
        var exception = Assert.Throws<ArgumentException>(() => MirrorPlan.ValidateConfiguration(new()
            { Teams = [new() { Theme = theme }] }));
        Assert.Contains("主题包", exception.Message);
    }

    private static string RepositoryRoot() => RepositoryPaths.Discover(AppContext.BaseDirectory)
        ?? throw new InvalidOperationException("未找到主题目录的仓库来源");

}
