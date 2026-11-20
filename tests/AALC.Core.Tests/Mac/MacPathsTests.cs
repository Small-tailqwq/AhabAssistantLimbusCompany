using AALC.Runtime;
using AALC.Runtime.Replay;
using Xunit;

namespace AALC.Core.Tests;

public sealed class MacPathsTests
{
    [Fact]
    public void RelativeAndWindowsDrivePathsAreNotMacEvidenceRoots()
    {
        Assert.Throws<InvalidDataException>(() => EvidencePaths.RequireExternalPath("output"));
        Assert.Throws<InvalidDataException>(() => EvidencePaths.RequireExternalPath(@"D:\AALCData"));
    }

    [Fact]
    public void EvidenceResolvesSymlinksAndFixtureMustStayInsideRoot()
    {
        var parent = Directory.CreateTempSubdirectory();
        try
        {
            var root = parent.CreateSubdirectory("data").FullName;
            var target = parent.CreateSubdirectory("outside").FullName;
            Directory.CreateSymbolicLink(Path.Combine(root, "link"), target);
            Assert.Equal(EvidencePaths.RequireExternalPath(Path.Combine(target, "new", "a.png")),
                EvidencePaths.RequireExternalPath(Path.Combine(root, "link", "new", "a.png")));
            Assert.Throws<InvalidDataException>(() => ScreenshotTestset.ResolveDataPath(root, "link/a.png"));
            Assert.Throws<InvalidDataException>(() => ScreenshotTestset.ResolveDataPath(root, "../DATA/a.png"));
        }
        finally { parent.Delete(true); }
    }
}
