import os
import re
import platform
import time
from time import sleep
from dataclasses import dataclass

import cv2
import numpy as np

import win32process

from module.automation import auto
from module.config import cfg
from module.game_and_screen import screen
from module.logger import log
from utils.utils import check_game_running

_last_title_screen_tap_time = 0.0
_last_simulator_alive_check_time = 0.0
_pending_simulator_launch_probe = False

_last_server_error_retry_time = 0.0
_server_error_disabled_since: float | None = None

SERVER_ERROR_RETRY_INTERVAL = 5.0
SERVER_ERROR_DISABLED_TIMEOUT = 15.0


@dataclass(frozen=True)
class ServerErrorDialog:
    close_position: tuple[int, int]
    close_bounds: tuple[int, int, int, int]
    retry_position: tuple[int, int]
    retry_bounds: tuple[int, int, int, int]


def _entry_with_text(
    entries: list[tuple[str, tuple[int, int, int, int]]], target: str
) -> tuple[str, tuple[int, int, int, int]] | None:
    return next((entry for entry in entries if target in entry[0]), None)


def find_server_error_dialog(
    entries: list[tuple[str, tuple[int, int, int, int]]],
) -> ServerErrorDialog | None:
    """从当前帧 OCR 结果中识别新版中文服务器错误弹窗。"""
    error = _entry_with_text(entries, "服务器发生错误")
    later = _entry_with_text(entries, "请稍后再试")
    close = _entry_with_text(entries, "关闭")
    retry = _entry_with_text(entries, "重试")
    if not all((error, later, close, retry)):
        return None

    _, error_bounds = error
    _, later_bounds = later
    _, close_bounds = close
    _, retry_bounds = retry
    close_position = ((close_bounds[0] + close_bounds[2]) // 2, (close_bounds[1] + close_bounds[3]) // 2)
    retry_position = ((retry_bounds[0] + retry_bounds[2]) // 2, (retry_bounds[1] + retry_bounds[3]) // 2)
    message_bottom = max(error_bounds[3], later_bounds[3])
    if retry_position[0] <= close_position[0] or min(close_position[1], retry_position[1]) <= message_bottom:
        return None

    return ServerErrorDialog(close_position, close_bounds, retry_position, retry_bounds)


def is_retry_button_enabled(image: np.ndarray, bounds: tuple[int, int, int, int]) -> bool:
    """根据新版按钮金色文字的饱和度判断“重试”是否仍可点击。"""
    x1, y1, x2, y2 = bounds
    height, width = image.shape[:2]
    crop = image[max(0, y1 - 4) : min(height, y2 + 4), max(0, x1 - 4) : min(width, x2 + 4)]
    if crop.size == 0:
        return False

    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    gold_pixels = (hsv[:, :, 1] > 20) & (hsv[:, :, 2] > 100)
    return int(gold_pixels.sum()) >= 8


def _is_server_error_retry_countdown(entries: list[tuple[str, tuple[int, int, int, int]]]) -> bool:
    return any("重试" in text and re.search(r"重试\s*\d+", text) for text, _ in entries)


def handle_server_error_dialog(now: float | None = None) -> bool | None:
    """处理服务器错误：True 为已拦截重试，False 为关闭重启，None 为非目标弹窗。"""
    global _last_server_error_retry_time, _server_error_disabled_since

    entries = auto.get_ocr_entries()
    dialog = find_server_error_dialog(entries)
    if dialog is None:
        _server_error_disabled_since = None
        return None

    now = time.time() if now is None else now
    if _is_server_error_retry_countdown(entries):
        _server_error_disabled_since = None
        log.info("服务器错误弹窗的重试正在游戏倒计时中，等待按钮恢复可点击")
        return True

    color_screenshot = auto.screenshot_rgb
    if color_screenshot is None:
        log.warning("检测到服务器错误弹窗，但当前帧缺少彩色截图，等待下一帧后再处理")
        return True

    image = np.asarray(color_screenshot)
    if is_retry_button_enabled(image, dialog.retry_bounds):
        _server_error_disabled_since = None
        if now - _last_server_error_retry_time >= SERVER_ERROR_RETRY_INTERVAL:
            log.info("检测到服务器错误弹窗，点击重试")
            auto.mouse_click(*dialog.retry_position)
            _last_server_error_retry_time = now
        else:
            log.debug("服务器错误弹窗的重试仍在 AALC 5 秒节流窗口内")
        return True

    if _server_error_disabled_since is None:
        _server_error_disabled_since = now
        log.info("服务器错误弹窗的重试暂不可用，等待其恢复")
        return True
    if now - _server_error_disabled_since < SERVER_ERROR_DISABLED_TIMEOUT:
        log.debug("服务器错误弹窗的重试仍不可用，继续等待")
        return True

    log.warning("服务器错误弹窗的重试长时间不可用，关闭弹窗并重启游戏")
    auto.mouse_click(*dialog.close_position)
    _server_error_disabled_since = None
    kill_game()
    restart_game()
    return False




def _get_simulator_connection_device():
    if cfg.simulator_type == 0:
        from module.automation.input_handlers.simulator.mumu_control import MumuControl

        return MumuControl.connection_device

    from module.automation.input_handlers.simulator.simulator_control import SimulatorControl

    return SimulatorControl.connection_device


def _is_main_menu_visible(automation=None) -> bool:
    automation = automation or auto
    has_home_navigation = bool(
        automation.find_element("home/window_assets.png")
        or automation.find_element("home/drive_assets.png", model="normal")
    )
    return bool(has_home_navigation and automation.find_element("home/mail_assets.png", model="normal"))


def _is_runtime_ui_visible() -> bool:
    return bool(
        auto.find_element("battle/setting_assets.png")
        or auto.find_element("battle/battle_finish_confirm_assets.png")
        or auto.find_element("base/retry_countdown.png")
        or auto.find_element("base/retry.png")
        or auto.find_element("base/try_again.png")
        or auto.find_element("home/back_assets.png", model="normal")
        or auto.find_element("base/back_assets.png", model="normal", threshold=0.6)
        or auto.find_element("base/notification_close_assets.png")
        or auto.find_element("scenes/story_skip_confirm_assets.png")
        or auto.find_element("scenes/story_skip_assets.png")
        or auto.find_element("scenes/story_meun_assets.png")
        or auto.find_element("home/close_anniversary_event_assets.png")
        or auto.find_element("mirror/road_in_mir/towindow&forfeit_confirm_assets.png", threshold=0.75)
        or auto.find_element("mirror/road_in_mir/to_window_assets.png", threshold=0.75)
        or auto.find_element("mirror/road_in_mir/select_encounter_reward_card_assets.png")
        or auto.find_element("mirror/road_in_mir/legend_assets.png")
        or auto.find_element("mirror/road_to_mir/enter_assets.png")
    )


def should_wait_for_main_menu_after_simulator_start() -> bool:
    global _pending_simulator_launch_probe

    if not _pending_simulator_launch_probe:
        return False
    _pending_simulator_launch_probe = False

    from tasks.base.back_init_menu import handle_launch_state_once

    deadline = time.time() + 3
    had_model = hasattr(auto, "model")
    previous_model = getattr(auto, "model", None)
    auto.model = "clam"
    try:
        while time.time() <= deadline:
            auto.ensure_not_stopped()
            if auto.take_screenshot() is None:
                continue
            if _is_main_menu_visible():
                return True
            if handle_launch_state_once():
                return True
            if _is_runtime_ui_visible():
                return False
            sleep(0.5)
    finally:
        if had_model:
            auto.model = previous_model

    return True


def ensure_simulator_game_started() -> bool:
    """模拟器模式下确认游戏仍在前台，不在时尝试拉起游戏。"""
    global _last_simulator_alive_check_time, _pending_simulator_launch_probe

    _pending_simulator_launch_probe = False
    if not cfg.simulator:
        return False

    now = time.time()
    if now - _last_simulator_alive_check_time < 5:
        return False
    _last_simulator_alive_check_time = now

    connection_device = _get_simulator_connection_device()
    if connection_device is None:
        return False

    if connection_device.check_game_alive():
        return False

    log.info("检测到游戏未运行或不在前台，尝试自动启动游戏")
    connection_device.start_game()
    _pending_simulator_launch_probe = True
    sleep(3)
    return True


def click_title_screen_safely() -> None:
    """标题页点击入口，避开账号、清缓存和中间弹窗区域。"""
    global _last_title_screen_tap_time
    if not cfg.simulator:
        auto.mouse_click_blank()
        return

    now = time.time()
    if now - _last_title_screen_tap_time < 5:
        return
    _last_title_screen_tap_time = now

    height = int(cfg.set_win_size or 1080)
    width = int(height * 16 / 9)
    tap_points = ((0.86, 0.80), (0.74, 0.83), (0.91, 0.58))
    index = int(now // 10) % len(tap_points)
    x_ratio, y_ratio = tap_points[index]
    auto.mouse_click(int(width * x_ratio), int(height * y_ratio))


def kill_game():
    """关闭游戏"""
    if cfg.simulator:
        if cfg.simulator_type == 0:
            from module.automation.input_handlers.simulator.mumu_control import (
                MumuControl,
            )

            MumuControl.connection_device.close_current_app()
        else:
            from module.automation.input_handlers.simulator.simulator_control import (
                SimulatorControl,
            )

            SimulatorControl.connection_device.close_current_app()
        return
    if platform.system() == "Windows":
        from module.session_process import process_belongs_to_session, terminate_processes

        _, pid = win32process.GetWindowThreadProcessId(screen.handle.hwnd)
        if process_belongs_to_session(pid):
            os.system(f"taskkill /F /PID {pid}")
        else:
            log.error(f"拒绝终止其他 Windows Session 的游戏进程：PID {pid}")
            terminate_processes(cfg.game_process_name)
    sleep(10)
    wait_start = time.time()
    while True:
        from module.session_process import process_is_running

        game_running = process_is_running(cfg.game_process_name)
        if not game_running:
            break
        if time.time() - wait_start > 30:
            log.warning("等待游戏进程退出超时(30s)，继续后续流程")
            break
        sleep(1)


def check_times(start_time, timeout=90, logs=True):
    """检查是否卡死超时，若是则尝试关闭重启游戏"""
    now_time = time.time()
    if logs and int(now_time - start_time) > 9 and int(now_time - start_time) % 10 == 0:
        log.info(f"初始时间为{time.strftime('%H:%M:%S', time.localtime(start_time))}，此刻时间为{time.strftime('%H:%M:%S', time.localtime(now_time))}，已卡死{int(now_time - start_time)}秒")
        sleep(1)
    if now_time - start_time > timeout:
        log.info(f"已卡死超过{timeout}秒，尝试关闭重启游戏")
        kill_game()
        restart_game()
        return True
    else:
        return False


def retry():
    """重试连接。

    为保证稳定性，retry 内循环始终刷新截图，避免复用旧帧导致误判。
    """
    start_time = time.time()
    is_windows = not cfg.config.simulator
    if is_windows:
        saved_hwnd = screen.handle.hwnd
    while True:
        if is_windows and screen.handle.hwnd != saved_hwnd:
            # 句柄发生变化则重置初始时间, 以免误判卡死
            saved_hwnd = screen.handle.hwnd
            start_time = time.time()
        if auto.get_restore_time() is not None:
            start_time = max(start_time, auto.get_restore_time())
        if check_times(start_time):
            return False
        if auto.take_screenshot() is None:
            continue
        server_error_result = handle_server_error_dialog()
        if server_error_result is not None:
            if server_error_result is False:
                return False
            continue
        if auto.find_element("base/connecting_assets.png"):
            continue
        if position := auto.find_element("base/retry_countdown.png"):
            sleep(5)
            auto.mouse_click(position[0], position[1], times=3)
            continue
        if auto.click_element("base/retry.png", threshold=0.9):
            auto.mouse_to_blank()
            continue
        if (
            auto.find_element("base/retry_countdown.png")
            or auto.find_element("base/retry.png")
            or auto.find_element("base/try_again.png")
        ):
            auto.click_element("base/retry.png", threshold=0.9)
            continue
        if auto.find_element("base/clear_all_caches_assets.png", model="clam"):
            if auto.click_element("base/update_confirm_assets.png"):
                continue
            click_title_screen_safely()
            continue
        if auto.click_element("base/only_option_assets.png", model="clam"):
            sleep(5)
            if not check_game_running():
                log.debug("检测到游戏未运行，调用 init_game() 重新初始化")
                from tasks.base.script_task_scheme import init_game

                init_game()
            continue
        break


def restart_game() -> bool:
    """重启游戏"""
    from tasks.base.back_init_menu import wait_until_main_menu_after_launch
    from tasks.base.script_task_scheme import init_game

    init_game()
    sleep(3)
    return wait_until_main_menu_after_launch() == "main_menu"
