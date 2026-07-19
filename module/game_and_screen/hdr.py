"""Windows HDR display detection through DXGI."""

import ctypes
from dataclasses import dataclass

from module.logger import log

# DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020
HDR_COLOR_SPACE = 12

_COLOR_SPACE_NAMES: dict[int, str] = {
    0: "RGB_FULL_G22_NONE_P709",
    1: "RGB_FULL_G10_NONE_P709",
    2: "RGB_STUDIO_G22_NONE_P709",
    3: "RGB_STUDIO_G22_NONE_P2020",
    4: "RESERVED",
    5: "YCBCR_FULL_G22_NONE_P709_X601",
    6: "YCBCR_STUDIO_G22_LEFT_P601",
    7: "YCBCR_FULL_G22_LEFT_P601",
    8: "YCBCR_STUDIO_G22_LEFT_P709",
    9: "YCBCR_FULL_G22_LEFT_P709",
    10: "YCBCR_STUDIO_G22_LEFT_P2020",
    11: "YCBCR_FULL_G22_LEFT_P2020",
    12: "RGB_FULL_G2084_NONE_P2020",
    13: "YCBCR_STUDIO_G2084_LEFT_P2020",
    14: "RGB_STUDIO_G2084_NONE_P2020",
    15: "YCBCR_STUDIO_G22_TOPLEFT_P2020",
    16: "YCBCR_STUDIO_G2084_TOPLEFT_P2020",
    17: "RGB_FULL_G22_NONE_P2020",
    18: "YCBCR_STUDIO_GHLG_TOPLEFT_P2020",
    19: "YCBCR_FULL_GHLG_TOPLEFT_P2020",
    20: "RGB_STUDIO_G24_NONE_P709",
    21: "RGB_STUDIO_G24_NONE_P2020",
    22: "YCBCR_STUDIO_G24_LEFT_P709",
    23: "YCBCR_STUDIO_G24_LEFT_P2020",
    24: "YCBCR_STUDIO_G24_TOPLEFT_P2020",
    25: "RGB_FULL_G10_NONE_P2020",
    -1: "CUSTOM",
}

COINIT_APARTMENTTHREADED = 0x2
S_OK = 0
S_FALSE = 1
MONITORINFOF_PRIMARY = 0x00000001

_LPVOIDP = ctypes.POINTER(ctypes.c_void_p)


def color_space_name(value: int) -> str:
    """Return the human-readable name of a DXGI color space value."""
    return _COLOR_SPACE_NAMES.get(value, f"UNKNOWN ({value})")


@dataclass
class HdrDisplayInfo:
    monitor_handle: int
    device_name: str
    friendly_name: str = ""
    is_primary: bool = False
    desktop_rect: tuple[int, int, int, int] = (0, 0, 0, 0)
    attached_to_desktop: bool = False
    bits_per_color: int = 0
    color_space: int = 0
    max_luminance: float = 0.0
    min_luminance: float = 0.0
    max_full_frame_luminance: float = 0.0

    @property
    def hdr_enabled(self) -> bool:
        return self.color_space == HDR_COLOR_SPACE

    @property
    def color_space_name(self) -> str:
        return color_space_name(self.color_space)


class GUID(ctypes.Structure):
    """Windows GUID/IID structure."""

    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class RECT(ctypes.Structure):
    """Windows RECT structure."""

    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class DXGI_OUTPUT_DESC1(ctypes.Structure):
    """Display description returned by IDXGIOutput6::GetDesc1."""

    _fields_ = [
        ("DeviceName", ctypes.c_wchar * 32),
        ("DesktopCoordinates", RECT),
        ("AttachedToDesktop", ctypes.c_int),
        ("Rotation", ctypes.c_uint),
        ("Monitor", ctypes.c_void_p),
        ("BitsPerColor", ctypes.c_uint),
        ("ColorSpace", ctypes.c_int),
        ("RedPrimary", ctypes.c_float * 2),
        ("GreenPrimary", ctypes.c_float * 2),
        ("BluePrimary", ctypes.c_float * 2),
        ("WhitePoint", ctypes.c_float * 2),
        ("MinLuminance", ctypes.c_float),
        ("MaxLuminance", ctypes.c_float),
        ("MaxFullFrameLuminance", ctypes.c_float),
    ]


IID_IDXGIFactory1 = GUID(
    0x770AAE78,
    0xF26F,
    0x4DBA,
    (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87),
)

IID_IDXGIOutput6 = GUID(
    0x068346E8,
    0xAAEC,
    0x4B84,
    (ctypes.c_ubyte * 8)(0xAD, 0xD7, 0x13, 0x7F, 0x51, 0x3F, 0x77, 0xA1),
)

_QueryInterface = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_void_p,
    ctypes.POINTER(GUID),
    ctypes.POINTER(ctypes.c_void_p),
)

_Release = ctypes.WINFUNCTYPE(
    ctypes.c_ulong,
    ctypes.c_void_p,
)

_EnumAdapters1 = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_void_p,
    ctypes.c_uint,
    ctypes.POINTER(ctypes.c_void_p),
)

_EnumOutputs = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_void_p,
    ctypes.c_uint,
    ctypes.POINTER(ctypes.c_void_p),
)

_GetDesc1 = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_void_p,
    ctypes.POINTER(DXGI_OUTPUT_DESC1),
)

_ole32 = ctypes.windll.ole32
_ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
_ole32.CoInitializeEx.restype = ctypes.c_long
_ole32.CoUninitialize.argtypes = []
_ole32.CoUninitialize.restype = None

_dxgi = ctypes.windll.dxgi
_dxgi.CreateDXGIFactory1.argtypes = [
    ctypes.POINTER(GUID),
    ctypes.POINTER(ctypes.c_void_p),
]
_dxgi.CreateDXGIFactory1.restype = ctypes.c_long


def _vtable_func(com_ptr: int, index: int, prototype):
    """Return a callable COM method at a vtable index."""
    vtable = ctypes.cast(com_ptr, _LPVOIDP).contents
    func_ptr = ctypes.cast(vtable, _LPVOIDP)[index]
    return prototype(func_ptr)


def com_release(ptr) -> None:
    """Call IUnknown::Release, accepting null pointers."""
    if not ptr:
        return
    release = _vtable_func(ptr, 2, _Release)
    release(ptr)


def _com_query_interface(com_ptr: int, iid: GUID) -> int | None:
    """Return a queried COM interface pointer, or None on failure."""
    out = ctypes.c_void_p()
    query_interface = _vtable_func(com_ptr, 0, _QueryInterface)
    hr = query_interface(com_ptr, ctypes.byref(iid), ctypes.byref(out))
    if hr == S_OK:
        return out.value
    return None


def _create_dxgi_factory() -> int | None:
    """Create an IDXGIFactory1 instance."""
    factory = ctypes.c_void_p()
    hr = _dxgi.CreateDXGIFactory1(
        ctypes.byref(IID_IDXGIFactory1),
        ctypes.byref(factory),
    )
    if hr == S_OK:
        return factory.value
    return None


def _enumerate_output_descs(factory_ptr: int) -> list[DXGI_OUTPUT_DESC1]:
    """Enumerate DXGI_OUTPUT_DESC1 values from all adapters and outputs."""
    results: list[DXGI_OUTPUT_DESC1] = []
    enum_adapters1 = _vtable_func(factory_ptr, 12, _EnumAdapters1)

    adapter_index = 0
    while True:
        adapter = ctypes.c_void_p()
        hr = enum_adapters1(factory_ptr, adapter_index, ctypes.byref(adapter))
        if hr != S_OK:
            break

        try:
            enum_outputs = _vtable_func(adapter.value, 7, _EnumOutputs)
            output_index = 0
            while True:
                output = ctypes.c_void_p()
                hr = enum_outputs(
                    adapter.value, output_index, ctypes.byref(output)
                )
                if hr != S_OK:
                    break

                try:
                    output6_ptr = _com_query_interface(
                        output.value, IID_IDXGIOutput6
                    )
                    if output6_ptr is not None:
                        try:
                            desc = DXGI_OUTPUT_DESC1()
                            get_desc1 = _vtable_func(output6_ptr, 27, _GetDesc1)
                            hr = get_desc1(output6_ptr, ctypes.byref(desc))
                            if hr == S_OK:
                                results.append(desc)
                        finally:
                            com_release(output6_ptr)
                finally:
                    com_release(output.value)
                output_index += 1
        finally:
            com_release(adapter.value)
        adapter_index += 1

    return results


def _build_display_info(desc: DXGI_OUTPUT_DESC1) -> HdrDisplayInfo:
    """Build display information and enrich it with Win32 monitor details."""
    import win32api

    info = HdrDisplayInfo(
        monitor_handle=int(desc.Monitor or 0),
        device_name=desc.DeviceName,
        desktop_rect=(
            desc.DesktopCoordinates.left,
            desc.DesktopCoordinates.top,
            desc.DesktopCoordinates.right,
            desc.DesktopCoordinates.bottom,
        ),
        attached_to_desktop=bool(desc.AttachedToDesktop),
        bits_per_color=desc.BitsPerColor,
        color_space=desc.ColorSpace,
        max_luminance=desc.MaxLuminance,
        min_luminance=desc.MinLuminance,
        max_full_frame_luminance=desc.MaxFullFrameLuminance,
    )

    if not desc.Monitor:
        return info

    try:
        mon_info = win32api.GetMonitorInfo(desc.Monitor)
        info.is_primary = bool(mon_info.get("Flags", 0) & MONITORINFOF_PRIMARY)
        display_device = win32api.EnumDisplayDevices(desc.DeviceName, 0, 0)
        info.friendly_name = display_device.DeviceString
    except Exception:
        pass

    return info


def enumerate_hdr_displays() -> list[HdrDisplayInfo]:
    """用新建的 DXGI factory 返回当前所有输出；失败时记录日志并返回空列表。"""
    hr = _ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    if hr not in (S_OK, S_FALSE):
        log.warning(f"COM 初始化失败，跳过 HDR 检测: 0x{hr & 0xFFFFFFFF:08X}")
        return []

    try:
        factory_ptr = _create_dxgi_factory()
        if factory_ptr is None:
            log.warning("CreateDXGIFactory1 失败，跳过 HDR 检测")
            return []
        try:
            descs = _enumerate_output_descs(factory_ptr)
        finally:
            com_release(factory_ptr)
    except Exception as exc:
        log.warning(f"查询显示器 HDR 状态失败: {exc}")
        return []
    finally:
        _ole32.CoUninitialize()

    return [_build_display_info(desc) for desc in descs]


def get_monitor_hdr_info(hmonitor: int) -> HdrDisplayInfo | None:
    """返回指定 HMONITOR 的当前 HDR 信息。"""
    return next(
        (
            info
            for info in enumerate_hdr_displays()
            if info.monitor_handle == int(hmonitor)
        ),
        None,
    )
