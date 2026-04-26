import time
from pathlib import Path
from time import sleep

import cv2
import numpy as np

from module.automation import auto
from module.config import cfg
from module.logger import log


def _is_thread_debug_enabled():
    return bool(cfg.get_value("debug_mode", False) and cfg.get_value("debug_thread_dungeon", False))


def _dump_thread_debug_frame(label: str):
    if not _is_thread_debug_enabled():
        return
    screenshot = auto.screenshot
    if screenshot is None:
        log.debug(f"纽本调试截图失败: {label}")
        return
    image = np.array(screenshot)
    if len(image.shape) == 3:
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    dump_dir = Path("logs") / "thread_dungeon_debug"
    dump_dir.mkdir(parents=True, exist_ok=True)
    now = time.time()
    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(now))
    ms = int((now % 1) * 1000)
    stem = f"{ts}_{ms:03d}_{label}"
    image_path = dump_dir / f"{stem}.png"
    cv2.imwrite(str(image_path), image)
    log.info(f"纽本调试截图已保存: {image_path}")


def EXP_luxcavation(combat_count: int = 1):
    loop_count = 30
    auto.model = "clam"
    while True:
        # 自动截图
        if auto.take_screenshot() is None:
            continue
        if auto.find_element("battle/teams_assets.png"):
            break
        if auto.find_element("home/first_prompt_assets.png", model="clam") and auto.find_element(
            "home/back_assets.png", model="normal"
        ):
            auto.click_element("home/back_assets.png")
            continue
        if auto.find_element("luxcavation/exp_enter.png", threshold=0.85, take_screenshot=True):
            if level := auto.find_element("luxcavation/exp_enter.png", find_type="image_with_multiple_targets"):
                level = sorted(level, key=lambda x: x[0], reverse=True)
                scale = cfg.set_win_size / 1440
                log.debug(f"经验本检测到 {len(level)} 个关卡入口: {level}")
                for lv_idx, lv in enumerate(level):
                    success = False
                    for retry in range(3):
                        if combat_count > 1 and retry == 0:
                            auto.mouse_click(lv[0] + 300 * scale, lv[1] - 450 * scale)
                            sleep(0.1)
                            if slide_bar := auto.find_element("luxcavation/continuous_combat.png", take_screenshot=True):
                                auto.mouse_drag(slide_bar[0], slide_bar[1], dx=30 * scale * (combat_count - 1))
                        log.debug(f"经验本尝试第 {lv_idx + 1} 关 (x={lv[0]}, y={lv[1]}), 第 {retry + 1}/3 次")
                        auto.mouse_click(lv[0], lv[1])
                        sleep(1)
                        auto.mouse_to_blank()
                        if auto.find_element("battle/teams_assets.png", take_screenshot=True) or auto.find_element(
                            "home/first_prompt_assets.png",
                            model="clam",
                            take_screenshot=True,
                        ):
                            log.debug(f"经验本第 {lv_idx + 1} 关点击成功，已进入编队界面")
                            success = True
                            break
                    if success:
                        break
                    log.debug(f"经验本第 {lv_idx + 1} 关 3 次尝试均未进入编队，降级尝试下一关")
        if auto.click_element("home/luxcavation_assets.png"):
            continue
        if auto.find_element("home/inferno_bus_assets.png") and not auto.find_element("home/luxcavation_assets.png"):
            sleep(1)
            if not auto.find_element("home/luxcavation_assets.png"):
                auto.click_element("home/window_assets.png")
                continue
        if auto.find_element("base/renew_confirm_assets.png", model="clam") and auto.find_element(
            "home/drive_assets.png", model="normal"
        ):
            auto.click_element("base/renew_confirm_assets.png")
            from tasks.base.back_init_menu import back_init_menu

            back_init_menu()
            continue
        if auto.click_element("home/drive_assets.png"):
            sleep(0.5)
            continue
        auto.mouse_to_blank()

        loop_count -= 1
        if loop_count < 20:
            auto.model = "normal"
        if loop_count < 10:
            auto.model = "aggressive"
        if loop_count < 0:
            log.error("无法进入经验本,不能进行下一步,此次经验本无效")
            break


def thread_luxcavation(combat_count: int = 1):
    loop_count = 30
    auto.model = "clam"
    while True:
        # 自动截图
        if auto.take_screenshot() is None:
            continue
        if auto.find_element("battle/teams_assets.png"):
            break
        if auto.find_element("home/first_prompt_assets.png", model="clam") and auto.find_element(
            "home/back_assets.png", model="normal"
        ):
            auto.click_element("home/back_assets.png")
            continue
        if auto.click_element("luxcavation/thread_enter_assets.png", threshold=0.78):
            sleep(0.5)
            _dump_thread_debug_frame("enter_thread")
            if pos := auto.find_element("luxcavation/thread_consume.png", threshold=0.85, take_screenshot=True):
                _dump_thread_debug_frame("thread_consume_found")
                if scroll_bar := auto.find_element("luxcavation/thread_scroll_bar.png"):
                    _dump_thread_debug_frame("scroll_bar_found")
                    auto.mouse_drag_down(scroll_bar[0], scroll_bar[1], reverse=2)
                else:
                    log.debug("未找到滚动条，通过滑动下滑")
                    auto.mouse_drag_down(pos[0], pos[1], reverse=-2)

                level = auto.find_element(
                    "luxcavation/thread_consume.png",
                    find_type="image_with_multiple_targets",
                    take_screenshot=True,
                )
                _dump_thread_debug_frame("level_detection")
                scale = cfg.set_win_size / 1440
                if level:
                    level = [(x, y) for x, y in level if x >= 700 * scale]
                if level:
                    _dump_thread_debug_frame("before_level_click")
                    level = sorted(level, key=lambda y: y[1], reverse=True)
                    log.debug(f"纽本检测到 {len(level)} 个关卡入口: {level}")
                    if combat_count > 1 and auto.click_element(
                        "luxcavation/thread_continuous_combat_show_box_assets.png"
                    ):
                        scale = cfg.set_win_size / 1440
                        sleep(0.1)
                        if slide_bar := auto.find_element(
                            "luxcavation/continuous_combat.png", threshold=0.78, take_screenshot=True
                        ):
                            auto.mouse_drag(slide_bar[0], slide_bar[1], dx=32 * scale * (combat_count - 1))
                            log.debug(f"纽本连续战斗滑块已拖至 {combat_count} 次")
                    for lv_idx, lv in enumerate(level):
                        success = False
                        for retry in range(3):
                            log.debug(f"纽本尝试第 {lv_idx + 1} 关 (x={lv[0]}, y={lv[1]}), 第 {retry + 1}/3 次")
                            auto.mouse_click(lv[0], lv[1])
                            sleep(1)
                            auto.mouse_to_blank()
                            if auto.find_element("battle/teams_assets.png", take_screenshot=True):
                                log.debug(f"纽本第 {lv_idx + 1} 关点击成功，已进入编队界面")
                                success = True
                                break
                        if success:
                            break
                        log.debug(f"纽本第 {lv_idx + 1} 关 3 次尝试均未进入编队，降级尝试下一关")
                else:
                    # 处理下方所有关卡未解锁的情况
                    _dump_thread_debug_frame("unaccessed_levels")
                    level = None
                    slide_times = 0
                    x = int(1300 * scale)
                    y = int(960 * scale)
                    dy = int(200 * scale)

                    while not level:
                        auto.mouse_drag(x, y, drag_time=0.5, dy=dy)
                        level = auto.find_element(
                            "luxcavation/thread_consume.png",
                            find_type="image_with_multiple_targets",
                            take_screenshot=True,
                        )
                        if level:
                            level = [(x, y) for x, y in level if x >= 700 * scale]
                        if level:
                            break
                        slide_times += 1
                        if slide_times > 10:
                            break
                    if not level:
                        continue

                    level = sorted(level, key=lambda y: y[1], reverse=True)
                    log.debug(f"纽本(滑动后)检测到 {len(level)} 个关卡入口: {level}")
                    if combat_count > 1 and auto.click_element(
                        "luxcavation/thread_continuous_combat_show_box_assets.png"
                    ):
                        scale = cfg.set_win_size / 1440
                        sleep(0.1)
                        if slide_bar := auto.find_element(
                            "luxcavation/continuous_combat.png", threshold=0.78, take_screenshot=True
                        ):
                            auto.mouse_drag(slide_bar[0], slide_bar[1], dx=32 * scale * (combat_count - 1))
                            log.debug(f"纽本连续战斗滑块已拖至 {combat_count} 次")
                    for lv_idx, lv in enumerate(level):
                        success = False
                        for retry in range(3):
                            log.debug(f"纽本(滑动后)尝试第 {lv_idx + 1} 关 (x={lv[0]}, y={lv[1]}), 第 {retry + 1}/3 次")
                            auto.mouse_click(lv[0], lv[1])
                            sleep(1)
                            auto.mouse_to_blank()
                            if auto.find_element("battle/teams_assets.png", take_screenshot=True):
                                log.debug(f"纽本(滑动后)第 {lv_idx + 1} 关点击成功，已进入编队界面")
                                success = True
                                break
                        if success:
                            break
                        log.debug(f"纽本(滑动后)第 {lv_idx + 1} 关 3 次尝试均未进入编队，降级尝试下一关")

            else:
                _dump_thread_debug_frame("thread_consume_not_found")
            continue
        if auto.click_element("luxcavation/thread_assets.png"):
            sleep(0.5)
            continue
        if auto.click_element("home/luxcavation_assets.png"):
            continue
        if auto.find_element("home/inferno_bus_assets.png") and not auto.find_element("home/luxcavation_assets.png"):
            sleep(1)
            if not auto.find_element("home/luxcavation_assets.png"):
                auto.click_element("home/window_assets.png")
                continue
        if auto.find_element("base/renew_confirm_assets.png", model="clam") and auto.find_element(
            "home/drive_assets.png", model="normal"
        ):
            auto.click_element("base/renew_confirm_assets.png")
            from tasks.base.back_init_menu import back_init_menu

            back_init_menu()
            continue
        if auto.click_element("home/drive_assets.png"):
            sleep(0.5)
            continue
        auto.mouse_to_blank()
        loop_count -= 1
        if loop_count < 20:
            auto.model = "normal"
        if loop_count < 10:
            auto.model = "aggressive"
        if loop_count < 0:
            log.error("无法进入纽本,不能进行下一步,此次纽本无效")
            break
