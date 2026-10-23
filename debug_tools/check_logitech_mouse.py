"""检查罗技驱动 DLL 当前是否真的能移动鼠标（等价于 AALC「检测 DLL」的验证逻辑）。

用对照组把 DLL 的效果和用户手动移动鼠标的干扰分开：
  - 对照组：调用 move(0,0)（发同样一次 IOCTL，但不产生位移）
  - 测试组：调用 move(3,0)（应产生 +3px）
两组均值之差接近 +3 即说明 DLL 生效；若对照组也在乱跳，说明鼠标正被外力移动。

用法：
    uv run python debug_tools/check_logitech_mouse.py <dll_path>
退出码：0 = 判定生效；1 = 判定不生效或干扰过大；2 = DLL 缺失/设备打不开。
"""

import argparse
import ctypes
import os
import time

import win32api

SAMPLES = 8
WAIT = 0.05


def _sample(dll, dx: int, dy: int) -> list[tuple[int, int]]:
    deltas = []
    for _ in range(SAMPLES):
        before = win32api.GetCursorPos()
        dll.move(dx, dy)
        time.sleep(WAIT)
        after = win32api.GetCursorPos()
        deltas.append((after[0] - before[0], after[1] - before[1]))
    return deltas


def _dump(label: str, deltas: list[tuple[int, int]]) -> None:
    print(f"{label}: " + ", ".join(f"({dx:+d},{dy:+d})" for dx, dy in deltas))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dll_path", help="要检测的驱动 DLL 路径")
    dll_path = parser.parse_args().dll_path
    print(f"DLL: {dll_path}")
    if not os.path.exists(dll_path):
        print("结果: DLL 文件不存在")
        return 2

    dll = ctypes.CDLL(dll_path)
    dll.device_open.restype = ctypes.c_bool
    dll.device_close.restype = None
    dll.move.argtypes = [ctypes.c_byte, ctypes.c_byte]
    dll.move.restype = ctypes.c_bool

    try:
        if not bool(dll.device_open()):
            print("device_open: False -> 驱动设备不可用")
            return 2
        print("device_open: True")

        screen_w = win32api.GetSystemMetrics(0)
        screen_h = win32api.GetSystemMetrics(1)
        origin = (screen_w // 2, screen_h // 2)
        win32api.SetCursorPos(origin)
        time.sleep(0.2)
        print(f"已把光标移到屏幕中心 {origin}（避开屏幕边缘钳制）")

        control = _sample(dll, 0, 0)
        test = _sample(dll, 3, 0)

        _dump("对照 move(0,0) ", control)
        _dump("测试 move(3,0) ", test)

        mean_ctrl = sum(dx for dx, _ in control) / len(control)
        mean_test = sum(dx for dx, _ in test) / len(test)
        delta = mean_test - mean_ctrl
        exact_hits = sum(1 for d in test if d == (3, 0))
        noise = sum(1 for d in control if abs(d[0]) > 2 or abs(d[1]) > 2)

        print(f"对照 X 均值: {mean_ctrl:+.2f} | 测试 X 均值: {mean_test:+.2f} | 差值: {delta:+.2f}")
        print(f"测试组精确命中 +3px 次数: {exact_hits}/{SAMPLES} | 对照组明显位移次数: {noise}/{SAMPLES}")

        win32api.SetCursorPos(origin)
        if exact_hits >= 3 or (delta >= 2 and noise <= 1):
            print("结果: DLL 能移动鼠标（驱动级输入生效）")
            return 0
        if noise >= 3:
            print("结果: 结果不可信——鼠标正被手动移动，请静止几秒后重测")
            return 1
        print("结果: DLL 无法移动鼠标（IOCTL 被驱动吞掉）")
        return 1
    finally:
        dll.device_close()


if __name__ == "__main__":
    raise SystemExit(main())
