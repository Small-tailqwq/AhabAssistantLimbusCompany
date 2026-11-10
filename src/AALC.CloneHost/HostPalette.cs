using System.Drawing;

namespace AALC.CloneHost
{
    /// <summary>与 AALC.Desktop/Styles/Tokens.axaml 同名令牌取值一致；宿主不依赖 Avalonia。</summary>
    internal static class HostPalette
    {
        internal static readonly Color SurfaceWindow = ColorTranslator.FromHtml("#20242B");
        internal static readonly Color SurfaceInset = ColorTranslator.FromHtml("#141B26");
        internal static readonly Color SurfaceCard = ColorTranslator.FromHtml("#1E2734");
        internal static readonly Color BorderSubtle = ColorTranslator.FromHtml("#2B3545");
        internal static readonly Color BorderDefault = ColorTranslator.FromHtml("#354152");
        internal static readonly Color TextPrimary = ColorTranslator.FromHtml("#E6EBF2");
        internal static readonly Color Accent = ColorTranslator.FromHtml("#8CABFF");
        internal static readonly Color AccentSubtle = ColorTranslator.FromHtml("#263552");
        internal static readonly Font BodyFont = new Font("Microsoft YaHei UI", 9f);
    }
}
