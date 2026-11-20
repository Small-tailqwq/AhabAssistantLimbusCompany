using System.Runtime.InteropServices;

namespace AALC.Desktop.Mac;

internal static class MacDisplaySettings
{
    private const string ObjC = "/usr/lib/libobjc.A.dylib";
    [DllImport(ObjC)] private static extern nint objc_getClass(string name);
    [DllImport(ObjC)] private static extern nint sel_registerName(string selector);
    [DllImport(ObjC, EntryPoint = "objc_msgSend")] private static extern nint GetObject(nint receiver, nint selector);
    [DllImport(ObjC, EntryPoint = "objc_msgSend")] private static extern byte GetBool(nint receiver, nint selector);

    public static bool ReduceMotion
    {
        get
        {
            var workspace = GetObject(objc_getClass("NSWorkspace"), sel_registerName("sharedWorkspace"));
            return GetBool(workspace, sel_registerName("accessibilityDisplayShouldReduceMotion")) != 0;
        }
    }
}
