using System.Diagnostics;
using AALC.Runtime;
using Xunit;

namespace AALC.Core.Tests;

[CollectionDefinition("Evidence paths", DisableParallelization = true)]
public sealed class EvidencePathsCollection;

[Collection("Evidence paths")]
public sealed class EvidencePathsTests
{
    [Theory]
    [InlineData(@"C:\AALCData\frame.png")]
    [InlineData(@"c:\evidence\..\frame.png")]
    [InlineData(@"\\?\C:\AALCData\frame.png")]
    public void CDrivePathsAreRejected(string path) =>
        Assert.Throws<InvalidDataException>(() => EvidencePaths.RequireExternalPath(path));

    [Fact]
    public void ApplicationDataDirectoryOnCDriveIsRejected()
    {
        var path = Path.Combine(AppContext.BaseDirectory, "data", "recordings", "events.jsonl");
        if (Path.GetPathRoot(path)!.Equals(@"C:\", StringComparison.OrdinalIgnoreCase))
            Assert.Throws<InvalidDataException>(() => EvidencePaths.RequireExternalPath(path));
    }

    [Theory]
    [InlineData(@"\\server\evidence\frame.png")]
    [InlineData(@"\\?\Volume{11111111-1111-1111-1111-111111111111}\frame.png")]
    public void PathsWithoutAVerifiableLocalDriveAreRejected(string path) =>
        Assert.Throws<InvalidDataException>(() => EvidencePaths.RequireExternalPath(path));

    [Fact]
    public void RelativePathsResolvingToCDriveAreRejected()
    {
        var previous = Environment.CurrentDirectory;
        try
        {
            Environment.CurrentDirectory = @"C:\";
            Assert.Throws<InvalidDataException>(() => EvidencePaths.RequireExternalPath(@"recordings\frame.png"));
        }
        finally { Environment.CurrentDirectory = previous; }
    }

    [Fact]
    public void DefaultRootIsExternalAndResolutionDoesNotCreateDirectories()
    {
        WithRoot(null, () => Assert.Equal(@"D:\AALCData", EvidencePaths.ResolveRoot(), ignoreCase: true));
        var path = Path.Combine(@"D:\AALCData", "path-tests", Guid.NewGuid().ToString("N"), "frames");
        Assert.Equal(path, EvidencePaths.RequireExternalPath(path), ignoreCase: true);
        Assert.False(Directory.Exists(path));
    }

    [Fact]
    public void EnvironmentRootIsNormalizedAndInvalidConfigurationNeverFallsBack()
    {
        WithRoot(@"D:\AALCData\uncreated\..\custom", () =>
            Assert.Equal(@"D:\AALCData\custom", EvidencePaths.ResolveRoot(), ignoreCase: true));
        WithRoot(@"C:\AALCData", () => Assert.Throws<InvalidDataException>(() => EvidencePaths.ResolveRoot()));
        WithRoot(" ", () => Assert.Throws<ArgumentException>(() => EvidencePaths.ResolveRoot()));
    }

    [Fact]
    public void DirectoryLinksAreResolvedBeforeReturningAnUncreatedOutputPath()
    {
        var directory = Path.Combine(@"D:\AALCData", "path-tests-" + Guid.NewGuid().ToString("N"));
        var target = Path.Combine(directory, "target");
        var link = Path.Combine(directory, "link");
        Directory.CreateDirectory(target);
        try
        {
            CreateJunction(link, target);
            Assert.Equal(Path.Combine(target, "new", "frame.png"),
                EvidencePaths.RequireExternalPath(Path.Combine(link, "new", "frame.png")), ignoreCase: true);
            Assert.False(File.Exists(Path.Combine(target, "new", "frame.png")));
        }
        finally
        {
            if (Directory.Exists(link)) Directory.Delete(link);
            Directory.Delete(target);
            Directory.Delete(directory);
        }
    }

    [Fact]
    public void JunctionsLeadingToCDriveAreRejectedBeforeWritingAnything()
    {
        var directory = Path.Combine(@"D:\AALCData", "path-tests-" + Guid.NewGuid().ToString("N"));
        var link = Path.Combine(directory, "link");
        Directory.CreateDirectory(directory);
        try
        {
            CreateJunction(link, @"C:\");
            Assert.Throws<InvalidDataException>(() => EvidencePaths.RequireExternalPath(Path.Combine(link, "frame.png")));
        }
        finally
        {
            if (Directory.Exists(link)) Directory.Delete(link);
            Directory.Delete(directory);
        }
    }

    private static void CreateJunction(string link, string target)
    {
        var start = new ProcessStartInfo("powershell.exe") { UseShellExecute = false, CreateNoWindow = true, RedirectStandardError = true };
        foreach (var argument in new[] { "-NoProfile", "-NonInteractive", "-Command",
            "New-Item -ItemType Junction -Path $env:AALC_TEST_LINK -Target $env:AALC_TEST_TARGET -ErrorAction Stop | Out-Null" })
            start.ArgumentList.Add(argument);
        start.Environment["AALC_TEST_LINK"] = link;
        start.Environment["AALC_TEST_TARGET"] = target;
        using var process = Process.Start(start)!;
        if (!process.WaitForExit(10000))
        {
            process.Kill(entireProcessTree: true);
            throw new TimeoutException("创建 D 盘测试 junction 超时");
        }
        Assert.True(process.ExitCode == 0, process.StandardError.ReadToEnd());
    }

    private static void WithRoot(string? root, Action action)
    {
        var previous = Environment.GetEnvironmentVariable("AALC_DATA_ROOT");
        try { Environment.SetEnvironmentVariable("AALC_DATA_ROOT", root); action(); }
        finally { Environment.SetEnvironmentVariable("AALC_DATA_ROOT", previous); }
    }
}
