using AALC.Runtime.Automation;
using Xunit;

namespace AALC.Core.Tests;

public sealed class GameResolutionTests
{
    [Theory]
    [InlineData(852, 478)]
    [InlineData(1279, 720)]
    [InlineData(1280, 719)]
    public void WindowsBelow720pAreTooSmall(int width, int height) => Assert.True(GameResolution.IsTooSmall(width, height));

    [Theory]
    [InlineData(1280, 720)]
    [InlineData(1366, 768)]
    [InlineData(2560, 1440)]
    public void WindowsAtOrAbove720pAreKept(int width, int height) => Assert.False(GameResolution.IsTooSmall(width, height));
}
