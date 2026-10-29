using System.Text.Json;
using AALC.Runtime.Automation;
using AALC.Runtime.Replay;
using Xunit;

namespace AALC.Core.Tests;

public sealed class ScreenshotTestsetTests
{
    private static ScreenshotCase Sample() => new("map", "地图", "mirror/images/map.png", new('0', 64), 1280, 720,
        Pages: new(Combat: false));

    [Fact]
    public void EmptyOrUnassertedCasesCannotPass()
    {
        Assert.Throws<InvalidDataException>(() => new ScreenshotTestset(1, [], []).Validate());
        Assert.Throws<InvalidDataException>(() => new ScreenshotTestset(1, [Sample() with { Pages = new() }], []).Validate());
        Assert.Throws<InvalidDataException>(() => new ScreenshotTestset(1, [Sample(), Sample()], []).Validate());
    }

    [Fact]
    public void AssertionsRequireOriginalDimensionsAndImageIdentity()
    {
        Assert.Throws<InvalidDataException>(() => new ScreenshotTestset(1, [Sample() with { Sha256 = "" }], []).Validate());
        Assert.Throws<InvalidDataException>(() => new ScreenshotTestset(1, [Sample() with
        {
            Text = [new(new(1200, 700, 100, 30), Exact: "0/1")]
        }], []).Validate());
        new ScreenshotTestset(1, [Sample() with { Text = [new(new(1180, 550, 60, 60), Exact: "")] }], []).Validate();
    }

    [Theory]
    [InlineData(@"..\outside.png")]
    [InlineData(@"C:\screenshots\map.png")]
    [InlineData(@"D:\elsewhere\map.png")]
    public void FixtureReferencesStayInsideExternalDataRoot(string reference)
    {
        Assert.Throws<InvalidDataException>(() => ScreenshotTestset.ResolveDataPath(@"D:\AALCData\testsets", reference));
    }

    [Fact]
    public void MisspelledAssertionsAreRejected()
    {
        var json = JsonSerializer.Serialize(new ScreenshotTestset(1, [Sample()], []), ScreenshotTestset.Json)
            .Replace("\"combat\"", "\"combta\"");
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<ScreenshotTestset>(json, ScreenshotTestset.Json));
    }

    [Fact]
    public void ReplayRequiresPinnedActionsOptionsAndResult()
    {
        Assert.Throws<InvalidDataException>(() => new ScreenshotTestset(1, [],
            [new("settlement", "结算", "mirror/runs/example", new())]).Validate());
    }
}
