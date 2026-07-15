"""HDR 检测工具 - 检测 Windows 10/11 是否开启了 HDR。

使用 DXGI IDXGIOutput6::GetDesc1() 查询每个显示器的 HDR 状态。
验证工具，用于测试检测方法在 Win10/11 上的准确性。

Usage:
    uv run python debug_tools/check_hdr.py
"""

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
