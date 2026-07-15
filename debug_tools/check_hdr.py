"""HDR 检测工具 - 检测 Windows 10/11 是否开启了 HDR。

使用 DXGI IDXGIOutput6::GetDesc1() 查询每个显示器的 HDR 状态。
验证工具，用于测试检测方法在 Win10/11 上的准确性。

Usage:
    uv run python debug_tools/check_hdr.py
"""

import ctypes
import os
import sys
from dataclasses import dataclass

# DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020
HDR_COLOR_SPACE = 16

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
    16: "RGB_FULL_G2084_NONE_P2020",
    17: "YCBCR_STUDIO_G2084_LEFT_P2020",
    18: "RGB_STUDIO_G2084_NONE_P2020",
    19: "YCBCR_STUDIO_G22_TOP_P709",
    20: "YCBCR_STUDIO_G22_TOP_P2020",
    21: "RGB_FULL_G22_NONE_P2020",
    22: "YCBCR_STUDIO_GHLG_TOP_P2020",
    23: "YCBCR_FULL_GHLG_TOP_P2020",
    24: "RGB_STUDIO_G24_NONE_P709",
    25: "RGB_STUDIO_G24_NONE_P2020",
    26: "YCBCR_STUDIO_G24_LEFT_P709",
    27: "YCBCR_STUDIO_G24_LEFT_P2020",
    28: "YCBCR_STUDIO_G24_TOP_P709",
    29: "YCBCR_STUDIO_G24_TOP_P2020",
}


def color_space_name(value: int) -> str:
    """返回 DXGI_COLOR_SPACE_TYPE 枚举值的人类可读名称。"""
    return _COLOR_SPACE_NAMES.get(value, f"UNKNOWN ({value})")


@dataclass
class MonitorInfo:
    """显示器信息容器。"""

    device_name: str = ""
    friendly_name: str = ""
    is_primary: bool = False
    desktop_rect: tuple[int, int, int, int] = (0, 0, 0, 0)
    attached_to_desktop: bool = False
    hdr_enabled: bool = False
    hdr_supported: bool = True
    bits_per_color: int = 0
    color_space: int = 0
    color_space_name: str = ""
    max_luminance: float = 0.0
    min_luminance: float = 0.0
    max_full_frame_luminance: float = 0.0


def format_monitor_info(info: MonitorInfo, index: int) -> str:
    """将 MonitorInfo 格式化为显示字符串。"""
    lines = [f"显示器 {index}:"]
    lines.append(f"  设备名: {info.device_name}")
    lines.append(f"  友好名: {info.friendly_name or '(未知)'}")
    lines.append(f"  主显示器: {'是' if info.is_primary else '否'}")
    left, top, right, bottom = info.desktop_rect
    lines.append(f"  桌面区域: ({left}, {top}) - ({right}, {bottom})")
    lines.append(f"  连接到桌面: {'是' if info.attached_to_desktop else '否'}")
    if info.hdr_supported:
        lines.append(f"  HDR 已开启: {'是' if info.hdr_enabled else '否'}")
        lines.append(f"  每通道位数: {info.bits_per_color}")
        lines.append(f"  色彩空间: {info.color_space_name} ({info.color_space})")
        lines.append(f"  最大亮度: {info.max_luminance:.1f} nits")
        lines.append(f"  最小亮度: {info.min_luminance:.1f} nits")
        lines.append(f"  最大全帧亮度: {info.max_full_frame_luminance:.1f} nits")
    else:
        lines.append("  HDR 已开启: 不支持 HDR 检测（需 Win10 1703+）")
    return "\n".join(lines)


# === COM 互操作层 ===

# 常量
COINIT_APARTMENTTHREADED = 0x2
S_OK = 0
S_FALSE = 1
RPC_E_CHANGED_MODE = 0x80010106
MONITORINFOF_PRIMARY = 0x00000001

_LPVOIDP = ctypes.POINTER(ctypes.c_void_p)


class GUID(ctypes.Structure):
    """Windows GUID/IID 结构体。"""

    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class RECT(ctypes.Structure):
    """Windows RECT 结构体。"""

    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class DXGI_OUTPUT_DESC1(ctypes.Structure):
    """IDXGIOutput6::GetDesc1 返回的显示器描述结构体。"""

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


# IID 常量
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

# COM 方法函数原型
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

# DLL 引用
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
    """按 vtable 索引获取 COM 方法可调用对象。

    com_ptr: COM 对象地址（整数）
    index: vtable 索引
    prototype: ctypes.WINFUNCTYPE 函数原型
    """
    vtable = ctypes.cast(com_ptr, _LPVOIDP).contents
    func_ptr = ctypes.cast(vtable, _LPVOIDP)[index]
    return prototype(func_ptr)


def com_release(ptr) -> None:
    """调用 IUnknown::Release。空指针安全。"""
    if not ptr:
        return
    release = _vtable_func(ptr, 2, _Release)
    release(ptr)


def _com_query_interface(com_ptr: int, iid: GUID) -> int | None:
    """QueryInterface 包装。返回新接口指针或 None。"""
    out = ctypes.c_void_p()
    qi = _vtable_func(com_ptr, 0, _QueryInterface)
    hr = qi(com_ptr, ctypes.byref(iid), ctypes.byref(out))
    if hr == S_OK:
        return out.value
    return None


# === DXGI 枚举层 ===


def _create_dxgi_factory() -> int | None:
    """创建 IDXGIFactory1 实例。返回指针或 None。"""
    factory = ctypes.c_void_p()
    hr = _dxgi.CreateDXGIFactory1(
        ctypes.byref(IID_IDXGIFactory1),
        ctypes.byref(factory),
    )
    if hr == S_OK:
        return factory.value
    return None


def _enumerate_monitors(factory_ptr: int) -> list[DXGI_OUTPUT_DESC1]:
    """枚举所有显示器的 DXGI_OUTPUT_DESC1。

    遍历 factory -> adapters -> outputs -> IDXGIOutput6 -> GetDesc1。
    QI 失败的 output 被跳过（IDXGIOutput6 不可用 = Win10 < 1703）。
    """
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


# === Win32 信息补充 ===


def _enrich_monitor_info(desc: DXGI_OUTPUT_DESC1) -> MonitorInfo:
    """从 DXGI_OUTPUT_DESC1 构建 MonitorInfo，用 Win32 API 补充友好名称等。"""
    import win32api

    info = MonitorInfo(
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
        color_space_name=color_space_name(desc.ColorSpace),
        max_luminance=desc.MaxLuminance,
        min_luminance=desc.MinLuminance,
        max_full_frame_luminance=desc.MaxFullFrameLuminance,
        hdr_enabled=(desc.ColorSpace == HDR_COLOR_SPACE),
        hdr_supported=True,
    )

    if not desc.Monitor:
        return info

    try:
        mon_info = win32api.GetMonitorInfo(desc.Monitor)
        info.is_primary = bool(mon_info.get("Flags", 0) & MONITORINFOF_PRIMARY)
        device = mon_info.get("Device", "")
        if "\\Monitor" in device:
            adapter_name = device.split("\\Monitor")[0]
            for i in range(5):
                try:
                    result = win32api.EnumDisplayDevices(adapter_name, i, 0)
                    if result[0] == device:
                        info.friendly_name = result[1]
                        break
                except Exception:
                    break
    except Exception:
        pass

    return info


# === 主函数 ===


def main() -> int:
    """主入口。返回退出码。"""
    hr = _ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    if hr == RPC_E_CHANGED_MODE:
        print("错误: COM 套间类型冲突（线程已初始化为 MTA）", file=sys.stderr)
        return 1

    try:
        factory_ptr = _create_dxgi_factory()
        if factory_ptr is None:
            print("错误: CreateDXGIFactory1 失败", file=sys.stderr)
            return 1

        try:
            descs = _enumerate_monitors(factory_ptr)
        finally:
            com_release(factory_ptr)

        if not descs:
            print("未检测到活动显示器")
            return 0

        monitors = [_enrich_monitor_info(desc) for desc in descs]

        print("HDR 检测报告")
        print("=" * 40)
        for i, info in enumerate(monitors, 1):
            print(format_monitor_info(info, i))
            print("-" * 40)
        print("=" * 40)

        hdr_count = sum(1 for m in monitors if m.hdr_enabled)
        print(f"汇总: 检测到 {len(monitors)} 台显示器，其中 {hdr_count} 台开启了 HDR")

        return 0
    finally:
        _ole32.CoUninitialize()


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
