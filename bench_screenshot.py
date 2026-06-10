import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from module.automation.input_handlers.simulator.mumu_control import MumuControl
from module.config import cfg
from module.logger import log


def determine_instance():
    instance = 0
    if cfg.simulator_port == 0 and cfg.mumu_instance_number == -1:
        instance = 0
    elif cfg.simulator_port != 0:
        if cfg.simulator_port == 16384 or (cfg.simulator_port - 16384) % 32 == 0:
            instance = 0 if cfg.simulator_port == 16384 else (cfg.simulator_port - 16384) // 32
    elif cfg.mumu_instance_number != -1:
        instance = cfg.mumu_instance_number
    return instance

def main():
    instance = determine_instance()
    log.info(f"检测到 Mumu 实例编号: {instance}")

    # 创建 MumuControl 但跳过 start() —— 模拟器已运行
    mc = MumuControl.__new__(MumuControl)
    mc.multi_instance_number = instance
    mc.display_id = 0
    mc._ev = asyncio.new_event_loop()
    mc.connect_id = 0
    mc.width = 0
    mc.height = 0
    mc.lib = None
    mc.stop_checker = None

    # 查找安装路径并加载 DLL
    mc.mumu_control_api_backend()
    log.info(f"exe_path={mc.exe_path}")
    mc.load_dll()

    # 直接连接已运行的模拟器（不启动）
    mc.connect()
    log.info("Mumu IPC 连接成功")

    import cv2

    sample_count = 30

    # 1. Mumu IPC 原生截图延迟
    times_raw = []
    for i in range(sample_count):
        t0 = time.perf_counter()
        img = mc.screenshot()
        cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        elapsed = (time.perf_counter() - t0) * 1000
        times_raw.append(elapsed)
    times_raw.sort()
    log.info(f"=== Mumu IPC 原生截图({sample_count}次) ===")
    log.info(f"avg={sum(times_raw)/len(times_raw):.1f}ms  min={times_raw[0]:.0f}  median={times_raw[15]:.0f}  max={times_raw[-1]:.0f}")

    # 2. 完整管线: IPC截图 + cvtColor + PIL + 灰度
    from module.automation.screenshot import ScreenShot
    times_full = []
    for i in range(sample_count):
        t0 = time.perf_counter()
        ScreenShot.mumu_screenshot(gray=True)
        elapsed = (time.perf_counter() - t0) * 1000
        times_full.append(elapsed)
    times_full.sort()
    log.info(f"=== 完整截图管线({sample_count}次) ===")
    log.info(f"avg={sum(times_full)/len(times_full):.1f}ms  min={times_full[0]:.0f}  median={times_full[15]:.0f}  max={times_full[-1]:.0f}")

    # 3. auto.take_screenshot 全链路
    from module.automation import auto
    auto.input_handler = mc
    auto.last_click_time = 0
    times_auto = []
    for i in range(sample_count):
        auto.screenshot = None
        t0 = time.perf_counter()
        auto.take_screenshot()
        elapsed = (time.perf_counter() - t0) * 1000
        times_auto.append(elapsed)
    times_auto.sort()
    log.info(f"=== auto.take_screenshot 全链路({sample_count}次) ===")
    log.info(f"avg={sum(times_auto)/len(times_auto):.1f}ms  min={times_auto[0]:.0f}  median={times_auto[15]:.0f}  max={times_auto[-1]:.0f}")

    mc.disconnect()

if __name__ == "__main__":
    main()
