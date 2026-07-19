# ruff: noqa: T201

"""Print a report of the current Windows HDR display state."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from module.game_and_screen.hdr import (  # noqa: E402
    HdrDisplayInfo,
    enumerate_hdr_displays,
)


def format_monitor_info(info: HdrDisplayInfo, index: int) -> str:
    lines = [f"显示器 {index}:"]
    lines.append(f"  设备名: {info.device_name}")
    lines.append(f"  友好名: {info.friendly_name or '(未知)'}")
    lines.append(f"  主显示器: {'是' if info.is_primary else '否'}")
    left, top, right, bottom = info.desktop_rect
    lines.append(f"  桌面区域: ({left}, {top}) - ({right}, {bottom})")
    lines.append(f"  连接到桌面: {'是' if info.attached_to_desktop else '否'}")
    lines.append(f"  HDR 已开启: {'是' if info.hdr_enabled else '否'}")
    lines.append(f"  每通道位数: {info.bits_per_color}")
    lines.append(f"  色彩空间: {info.color_space_name} ({info.color_space})")
    lines.append(f"  最大亮度: {info.max_luminance:.1f} nits")
    lines.append(f"  最小亮度: {info.min_luminance:.1f} nits")
    lines.append(f"  最大全帧亮度: {info.max_full_frame_luminance:.1f} nits")
    return "\n".join(lines)


def main() -> int:
    monitors = enumerate_hdr_displays()
    if not monitors:
        print("未检测到活动显示器")
        return 0

    print("HDR 检测报告")
    print("=" * 40)
    for index, info in enumerate(monitors, 1):
        print(format_monitor_info(info, index))
        print("-" * 40)
    print("=" * 40)

    hdr_count = sum(1 for monitor in monitors if monitor.hdr_enabled)
    print(f"汇总: 检测到 {len(monitors)} 台显示器，其中 {hdr_count} 台开启了 HDR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
