from time import sleep

from module.automation import auto
from module.config import cfg
from module.logger import log

_CONTINUOUS_COMBAT_DEFAULT_COUNT = 1
_CONTINUOUS_COMBAT_MAX_COUNT = 10
_CONTINUOUS_COMBAT_SHOW_BOX_ASSET = "luxcavation/thread_continuous_combat_show_box_assets.png"
_CONTINUOUS_COMBAT_UP_BOX_ASSET = "luxcavation/continuous_combat_up_box_assets.png"
_THREAD_CONSUME_ASSET = "luxcavation/thread_consume.png"
_THREAD_CONSUME_THRESHOLD = 0.85
_THREAD_LEVEL_MULTI_TARGET_THRESHOLD = 0.8


def _is_thread_debug_enabled():
    return bool(cfg.get_value("debug_mode", False) and cfg.get_value("debug_thread_dungeon", False))


def _dump_thread_debug_frame(label: str):
    if not _is_thread_debug_enabled():
        return
    import time
    from pathlib import Path

    import cv2
    import numpy as np

    screenshot = auto.screenshot
    if screenshot is None:
        log.debug(f"纽本调试截图失败: {label}")
        return
    image = np.array(screenshot)
    if image.size == 0:
        log.debug(f"纽本调试截图为空: {label}")
        return
    if len(image.shape) == 3:
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    dump_dir = Path("logs") / "thread_dungeon_debug"
    dump_dir.mkdir(parents=True, exist_ok=True)
    now = time.time()
    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(now))
    ms = int((now % 1) * 1000)
    stem = f"{ts}_{ms:03d}_{label}"
    image_path = dump_dir / f"{stem}.png"
    if cv2.imwrite(str(image_path), image):
        log.info(f"纽本调试截图已保存: {image_path}")
    else:
        log.debug(f"纽本调试截图写入失败: {image_path}")


def _get_continuous_combat_up_clicks(combat_count: int) -> int:
    target_count = max(_CONTINUOUS_COMBAT_DEFAULT_COUNT, min(int(combat_count), _CONTINUOUS_COMBAT_MAX_COUNT))
    return target_count - _CONTINUOUS_COMBAT_DEFAULT_COUNT


def _open_continuous_combat_count_box(log_prefix: str, box_position: tuple[int, int] | None = None) -> bool:
    if box_position is not None:
        auto.mouse_click(box_position[0], box_position[1])
        sleep(0.1)
        return True

    if not (pos := auto.click_element(
        _CONTINUOUS_COMBAT_SHOW_BOX_ASSET,
        threshold=0.85,
        click=False,
        model="aggressive",
    )):
        log.debug(f"{log_prefix}未找到连续战斗设置入口")
        return False

    auto.mouse_click(pos[0], pos[1])
    sleep(0.1)
    return True


def _close_continuous_combat_count_box(log_prefix: str, box_position: tuple[int, int] | None = None) -> None:
    sleep(0.1)
    if box_position is not None:
        auto.mouse_click(box_position[0], box_position[1])
        sleep(0.1)
        return

    if auto.take_screenshot() is None:
        return
    if pos := auto.click_element(
        _CONTINUOUS_COMBAT_SHOW_BOX_ASSET,
        threshold=0.85,
        click=False,
        model="aggressive",
    ):
        auto.mouse_click(pos[0], pos[1])
        sleep(0.1)
    else:
        log.debug(f"{log_prefix}未找到连续战斗设置入口，无法收起次数面板")


def _set_continuous_combat_count(
    combat_count: int,
    log_prefix: str,
    box_position: tuple[int, int] | None = None,
) -> bool:
    up_clicks = _get_continuous_combat_up_clicks(combat_count)
    if up_clicks <= 0:
        return True

    up_button = None
    for attempt in range(2):
        sleep(0.4 if attempt == 0 else 0.2)
        if auto.take_screenshot() is None:
            return False
        if log_prefix.startswith("纽本"):
            _dump_thread_debug_frame(f"continuous_count_panel_{attempt + 1}")
        up_button = auto.click_element(
            _CONTINUOUS_COMBAT_UP_BOX_ASSET,
            threshold=0.85,
            click=False,
            model="aggressive",
        )
        if up_button:
            break

    if not up_button:
        if log_prefix.startswith("纽本"):
            _dump_thread_debug_frame("continuous_up_not_found")
        log.debug(f"{log_prefix}未找到连续战斗增加按钮")
        return False

    for _ in range(up_clicks):
        auto.mouse_click(up_button[0], up_button[1])
        sleep(0.1)

    log.debug(f"{log_prefix}连续战斗次数已设置为 {up_clicks + _CONTINUOUS_COMBAT_DEFAULT_COUNT} 次")
    _close_continuous_combat_count_box(log_prefix, box_position)
    return True


def _prepare_continuous_combat_count(
    combat_count: int,
    log_prefix: str,
    box_position: tuple[int, int] | None = None,
) -> bool:
    if combat_count <= _CONTINUOUS_COMBAT_DEFAULT_COUNT:
        return True
    return _open_continuous_combat_count_box(log_prefix, box_position) and _set_continuous_combat_count(
        combat_count,
        log_prefix,
        box_position,
    )


def _get_exp_continuous_combat_box_position(level: tuple[int, int], scale: float) -> tuple[int, int]:
    return (int(level[0] + 300 * scale), int(level[1] - 450 * scale))


def _filter_thread_level_targets(level: list[tuple[int, int]] | None, scale: float) -> list[tuple[int, int]]:
    if not level:
        return []

    min_x = 700 * scale
    min_row_gap = max(20, int(70 * scale))
    selected = []
    for x, y in level:
        point = (int(x), int(y))
        if point[0] < min_x:
            continue
        if any(abs(point[1] - kept[1]) < min_row_gap for kept in selected):
            continue
        selected.append(point)
    return sorted(selected, key=lambda point: point[1], reverse=True)


def EXP_luxcavation(combat_count: int = 1):
    loop_count = 30
    auto.model = "clam"
    while True:
        # 自动截图
        if auto.take_screenshot() is None:
            continue
        if auto.find_element("teams/identify_assets.png"):
            break
        if (
            auto.find_element("home/first_prompt_assets.png", model="clam")
            and auto.find_element("home/back_assets.png", model="normal")
            and not auto.find_element("luxcavation/exp_enter.png", threshold=0.85)
        ):
            auto.key_press("esc")
            continue
        if auto.find_element("luxcavation/exp_enter.png", threshold=0.85, take_screenshot=True):
            if level := auto.find_element("luxcavation/exp_enter.png", find_type="image_with_multiple_targets"):
                level = sorted(level, key=lambda x: x[0], reverse=True)
                scale = cfg.set_win_size / 1440
                log.debug(f"经验本检测到 {len(level)} 个关卡入口: {level}")
                for lv_idx, lv in enumerate(level):
                    if combat_count > _CONTINUOUS_COMBAT_DEFAULT_COUNT:
                        box_position = _get_exp_continuous_combat_box_position(lv, scale)
                        if not _prepare_continuous_combat_count(combat_count, "经验本", box_position):
                            log.debug(f"经验本第 {lv_idx + 1} 关连续战斗设置失败，降级尝试下一关")
                            continue

                    select_team = False
                    for _ in range(3):
                        auto.mouse_click(lv[0], lv[1])
                        sleep(1)
                        auto.mouse_to_blank()
                        for _ in range(3):
                            if auto.find_element("teams/identify_assets.png", take_screenshot=True) or auto.find_element(
                                "home/first_prompt_assets.png",
                                model="clam",
                                take_screenshot=True,
                            ):
                                select_team = True
                                break
                        if select_team:
                            break
                    if select_team:
                        break
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
    continuous_combat_ready = combat_count <= _CONTINUOUS_COMBAT_DEFAULT_COUNT
    auto.model = "clam"
    while True:
        # 自动截图
        if auto.take_screenshot() is None:
            continue
        if auto.find_element("teams/identify_assets.png"):
            break
        if (
            auto.find_element("home/first_prompt_assets.png", model="clam")
            and auto.find_element("home/back_assets.png", model="normal")
            and not auto.find_element("luxcavation/thread_enter_assets.png", threshold=0.78)
            and not auto.find_element(_THREAD_CONSUME_ASSET, threshold=_THREAD_CONSUME_THRESHOLD)
        ):
            auto.key_press("esc")
            continue
        if thread_enter := auto.click_element("luxcavation/thread_enter_assets.png", threshold=0.78, click=False):
            if not continuous_combat_ready:
                if not _prepare_continuous_combat_count(combat_count, "纽本"):
                    log.debug("纽本连续战斗设置失败，重新检测")
                    continue
                continuous_combat_ready = True
            auto.mouse_click(thread_enter[0], thread_enter[1])
            sleep(0.5)
            if auto.take_screenshot() is None:
                continue
            _dump_thread_debug_frame("enter_thread")
            if pos := auto.find_element(_THREAD_CONSUME_ASSET, threshold=_THREAD_CONSUME_THRESHOLD):
                _dump_thread_debug_frame("thread_consume_found")
                if scroll_bar := auto.find_element("luxcavation/thread_scroll_bar.png"):
                    auto.mouse_drag_down(scroll_bar[0], scroll_bar[1], reverse=2)
                else:
                    log.debug("未找到滚动条，通过滑动下滑")
                    auto.mouse_drag_down(pos[0], pos[1], reverse=-2)

                level = auto.find_element(
                    _THREAD_CONSUME_ASSET,
                    find_type="image_with_multiple_targets",
                    threshold=_THREAD_LEVEL_MULTI_TARGET_THRESHOLD,
                    take_screenshot=True,
                )
                scale = cfg.set_win_size / 1440
                level = _filter_thread_level_targets(level, scale)
                if level:
                    _dump_thread_debug_frame("before_level_click")
                    log.debug(f"纽本检测到 {len(level)} 个关卡入口: {level}")
                    for lv_idx, lv in enumerate(level):
                        select_team = False
                        for _ in range(3):
                            auto.mouse_click(lv[0], lv[1])
                            sleep(1)
                            auto.mouse_to_blank()
                            for _ in range(3):
                                if auto.find_element(
                                    "teams/identify_assets.png", take_screenshot=True
                                ) or auto.find_element(
                                    "home/first_prompt_assets.png",
                                    model="clam",
                                    take_screenshot=True,
                                ):
                                    select_team = True
                                    break
                            if select_team:
                                break
                        if select_team:
                            break
                else:
                    # 处理下方所有关卡未解锁的情况
                    level = None
                    slide_times = 0
                    x = int(1300 * scale)
                    y = int(960 * scale)
                    dy = int(200 * scale)

                    while not level:
                        auto.mouse_drag(x, y, drag_time=0.5, dy=dy)
                        level = auto.find_element(
                            _THREAD_CONSUME_ASSET,
                            find_type="image_with_multiple_targets",
                            threshold=_THREAD_LEVEL_MULTI_TARGET_THRESHOLD,
                            take_screenshot=True,
                        )
                        level = _filter_thread_level_targets(level, scale)
                        if level:
                            break
                        slide_times += 1
                        if slide_times > 10:
                            break
                    if not level:
                        continue

                    log.debug(f"纽本(滑动后)检测到 {len(level)} 个关卡入口: {level}")
                    for lv_idx, lv in enumerate(level):
                        success = False
                        for retry in range(3):
                            log.debug(f"纽本(滑动后)尝试第 {lv_idx + 1} 关 (x={lv[0]}, y={lv[1]}), 第 {retry + 1}/3 次")
                            auto.mouse_click(lv[0], lv[1])
                            sleep(1)
                            auto.mouse_to_blank()
                            if auto.find_element("teams/identify_assets.png", take_screenshot=True):
                                log.debug(f"纽本(滑动后)第 {lv_idx + 1} 关点击成功，已进入编队界面")
                                success = True
                                break
                        if success:
                            break

            continue
        if auto.click_element("luxcavation/thread_assets.png"):
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
