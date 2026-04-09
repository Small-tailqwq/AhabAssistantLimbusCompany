import atexit
import ctypes
import math
import os
import random
from time import sleep, time

import win32api

try:
    ctypes.windll.winmm.timeBeginPeriod(1)
    atexit.register(lambda: ctypes.windll.winmm.timeEndPeriod(1))
except Exception:
    pass

from app import mediator
from module.config import cfg
from module.logger import log
from utils.singletonmeta import SingletonMeta

from ...game_and_screen import screen
from ..human_kinematics import HumanKinematics
from .input import WinAbstractInput

BUTTON_RELEASED = 0
BUTTON_LEFT = 1
BUTTON_RIGHT = 2
BUTTON_MIDDLE = 4

KEY_NAME_ALIASES = {
    "return": "enter",
    "control": "ctrl",
    "back_space": "backspace",
    "del": "delete",
    "page_up": "pageup",
    "page_down": "pagedown",
    "lwin": "lwindows",
    "rwin": "rwindows_",
}


class LogitechInput(WinAbstractInput, metaclass=SingletonMeta):
    """基于可编译罗技驱动 DLL 的硬件级键鼠输入类。"""

    def __init__(self):
        super().__init__()
        self.dll_path = cfg.logitech_dll_path
        self.dll = None
        self.device_open_func = None
        self.device_close_func = None
        self.move_func = None
        self.move_with_button_func = None
        self.left_down_func = None
        self.right_down_func = None
        self.middle_down_func = None
        self.mouse_up_func = None
        self.wheel_up_func = None
        self.wheel_down_func = None
        self.press_key_func = None
        self.release_key_func = None
        self.release_key_all_func = None
        self._driver_ready = False
        self._cleanup_registered = False
        self._focus_waiting_notified = False

        log.info("罗技输入适配器已创建，DLL 将在首次实际键鼠操作时加载。")

    def _require_export(self, export_name: str):
        try:
            return getattr(self.dll, export_name)
        except AttributeError as e:
            message = (
                f"当前罗技驱动 DLL 缺少必需导出 `{export_name}`。"
                f"这通常表示你配置的仍是旧版 DLL，而不是新的 Logitech_driver-main 编译产物。"
            )
            raise RuntimeError(message) from e

    def _ensure_driver_ready(self):
        if self._driver_ready:
            return

        self.dll_path = cfg.logitech_dll_path
        if not self.dll_path or not os.path.exists(self.dll_path):
            message = f"罗技驱动 DLL 未找到：{self.dll_path}"
            log.error(f"无法使用实验室罗技驱动模拟：缺失 DLL 或路径错误 ({self.dll_path})。请在配置中提供正确路径。")
            raise FileNotFoundError(message)

        try:
            self.dll = ctypes.CDLL(self.dll_path)

            self.device_open_func = self._require_export("device_open")
            self.device_open_func.restype = ctypes.c_bool

            self.device_close_func = self._require_export("device_close")
            self.device_close_func.restype = None

            self.move_func = self._require_export("move")
            self.move_func.argtypes = [ctypes.c_byte, ctypes.c_byte]
            self.move_func.restype = ctypes.c_bool

            self.move_with_button_func = self._require_export("move_with_button")
            self.move_with_button_func.argtypes = [ctypes.c_byte, ctypes.c_byte, ctypes.c_int]
            self.move_with_button_func.restype = ctypes.c_bool

            self.left_down_func = self._require_export("lmbDown")
            self.left_down_func.restype = ctypes.c_bool

            self.right_down_func = self._require_export("rmbDown")
            self.right_down_func.restype = ctypes.c_bool

            self.middle_down_func = self._require_export("mmbDown")
            self.middle_down_func.restype = ctypes.c_bool

            self.mouse_up_func = self._require_export("mouseUp")
            self.mouse_up_func.restype = ctypes.c_bool

            self.wheel_up_func = self._require_export("wheelup")
            self.wheel_up_func.restype = ctypes.c_bool

            self.wheel_down_func = self._require_export("wheeldown")
            self.wheel_down_func.restype = ctypes.c_bool

            self.press_key_func = self._require_export("press_key")
            self.press_key_func.argtypes = [ctypes.c_char_p]
            self.press_key_func.restype = None

            self.release_key_func = self._require_export("release_key")
            self.release_key_func.argtypes = [ctypes.c_char_p]
            self.release_key_func.restype = None

            self.release_key_all_func = self._require_export("release_key_all")
            self.release_key_all_func.restype = None

            status = bool(self.device_open_func())
            if not status:
                log.error("罗技驱动 DLL 初始化设备失败(device_open=False)，请确认环境、驱动与 DLL 是否匹配。")
                raise RuntimeError("罗技驱动 DLL 设备开启失败。")

            self._driver_ready = True
            if not self._cleanup_registered:
                atexit.register(self._cleanup_driver_state)
                self._cleanup_registered = True

            log.info("成功加载罗技驱动 DLL，启用硬件级键鼠模拟保护。")
            log.info("罗技输入已切换为新 DLL 后端：驱动级鼠标移动/拖拽 + 驱动级键盘按键。")
        except Exception as e:
            msg = f"加载或初始化罗技驱动 DLL 失败: {e}"
            log.error(msg)
            raise RuntimeError(msg) from e

    def _cleanup_driver_state(self):
        if not self._driver_ready:
            return

        try:
            self.release_key_all_func()
        except Exception:
            pass

        try:
            self.mouse_up_func()
        except Exception:
            pass

        try:
            self.device_close_func()
        except Exception:
            pass
        finally:
            self._driver_ready = False

    @staticmethod
    def _normalize_key_name(key: str) -> str:
        normalized = str(key).strip().lower()
        return KEY_NAME_ALIASES.get(normalized, normalized)

    @staticmethod
    def _clamp_relative_delta(value: int, limit: int = 100) -> int:
        return max(-limit, min(limit, int(value)))

    def get_mouse_position(self) -> tuple[int, int]:
        return win32api.GetCursorPos()

    def _client_to_screen_target(self, x: int, y: int) -> tuple[int, int]:
        rect = screen.handle.rect(True)
        return rect[0] + int(x), rect[1] + int(y)

    def _ensure_input_focus(self):
        while not screen.ensure_direct_input_ready():
            if not self._focus_waiting_notified:
                message = "罗技模拟要求游戏窗口保持前台。请手动点回游戏窗口，脚本会在确认焦点后继续。"
                log.warning(message)
                mediator.warning.emit(message)
                self._focus_waiting_notified = True
            HumanKinematics.human_sleep(0.4, jitter=0.15, minimum=0.25, maximum=0.6)
        if self._focus_waiting_notified:
            log.info("已检测到游戏窗口重新获得焦点，继续执行罗技模拟输入。")
            mediator.warning_clear.emit()
            self._focus_waiting_notified = False

    def _resolve_move_duration(self, distance: float, duration: float) -> float:
        if duration > 0:
            return duration

        action_interval = float(getattr(cfg, "mouse_action_interval", 0.5) or 0.5)
        max_duration = max(0.06, min(0.18, action_interval * 0.4))
        return min(max_duration, max(0.03, distance / 8000))

    @staticmethod
    def _resolve_post_drag_pause(distance: float, drag_time: float) -> float:
        base_pause = min(0.16, max(0.03, drag_time * 0.08))
        if distance >= 800:
            base_pause += 0.02
        return HumanKinematics.sample_duration(base_pause, jitter=0.22, minimum=0.025, maximum=0.18)

    def _press_mouse_button(self, button: int = BUTTON_LEFT):
        self._ensure_driver_ready()
        if button == BUTTON_LEFT:
            result = self.left_down_func()
        elif button == BUTTON_RIGHT:
            result = self.right_down_func()
        elif button == BUTTON_MIDDLE:
            result = self.middle_down_func()
        else:
            raise ValueError(f"不支持的鼠标按键状态: {button}")

        if not result:
            raise RuntimeError(f"鼠标按下失败: button={button}")

    def _move_relative_chunked(self, dx: int, dy: int, button_state: int = BUTTON_RELEASED):
        self._ensure_driver_ready()
        remaining_x = int(dx)
        remaining_y = int(dy)

        while remaining_x != 0 or remaining_y != 0:
            step_x = self._clamp_relative_delta(remaining_x)
            step_y = self._clamp_relative_delta(remaining_y)

            if button_state != BUTTON_RELEASED:
                result = self.move_with_button_func(step_x, step_y, button_state)
            else:
                result = self.move_func(step_x, step_y)

            if not result:
                raise RuntimeError(
                    f"相对移动失败: dx={step_x}, dy={step_y}, button_state={button_state}",
                )

            remaining_x -= step_x
            remaining_y -= step_y

    def _mouse_move_to(self, x, y, duration: float = 0, button_state: int = BUTTON_RELEASED):
        x = int(x)
        y = int(y)

        start_x, start_y = self.get_mouse_position()
        distance = math.hypot(x - start_x, y - start_y)
        if distance == 0:
            return

        move_duration = self._resolve_move_duration(distance, duration)
        
        # 调用底层绝对仿生引擎 (Minimum Jerk + Perlin Noise)
        trajectory = HumanKinematics.generate_bionic_curve(
            start_x,
            start_y,
            x,
            y,
            target_width=25.0 if button_state == BUTTON_RELEASED else 10.0,
            duration=duration,
        )
        
        # 因为轨迹自身就是基于 100 FPS (10ms) 分切的！
        # 必须严格锁定为每帧 10ms，绝不可以由于外部 duration 极小而将帧间压缩到 1ms（这会击穿 sleep 精度阈值导致光速狂点发射）
        # 引入硬件状态观测器 (State Observer) 解决闭环积分发散和 Windows 加速漂移
        step_time = 0.01
        os_x, os_y = self.get_mouse_position()
        unack_dx, unack_dy = 0, 0

        for index, (current_target_x, current_target_y) in enumerate(trajectory):
            step_start = time()
            
            # 获取最新系统光标（若遭遇硬件延迟，坐标不会立即更新）
            current_x, current_y = self.get_mouse_position()
            if current_x != os_x or current_y != os_y:
                # 操作系统跟进了物理偏移，重置未确认缓冲堆栈
                os_x, os_y = current_x, current_y
                unack_dx, unack_dy = 0, 0
                
            # 推理游标必定到达的位置 (实际系统位置 + 已发送但还在底层路上堵着的相对差异)
            predicted_x = current_x + unack_dx
            predicted_y = current_y + unack_dy
            
            step_dx = int(current_target_x - predicted_x)
            step_dy = int(current_target_y - predicted_y)

            if step_dx != 0 or step_dy != 0:
                self._move_relative_chunked(step_dx, step_dy, button_state=button_state)
                unack_dx += step_dx
                unack_dy += step_dy

            elapsed = time() - step_start
            remaining = step_time - elapsed
            if remaining > 0.001:
                HumanKinematics.human_sleep(remaining, jitter=0.08, minimum=remaining)

        # 核心改进：轨迹已经发送完毕，给 Windows 操作系统 40 毫秒的时间清空所有的 WM_MOUSEMOVE 消息缓冲。
        # 不然有概率光标起飞
        sleep(0.04)

        final_x, final_y = self.get_mouse_position()
        final_dx = x - final_x
        final_dy = y - final_y
        if final_dx != 0 or final_dy != 0:
            self._move_relative_chunked(final_dx, final_dy, button_state=button_state)

    def _move_to_client(self, x: int, y: int, duration: float = 0, button_state: int = BUTTON_RELEASED):
        target_screen_x, target_screen_y = self._client_to_screen_target(x, y)
        self._mouse_move_to(target_screen_x, target_screen_y, duration=duration, button_state=button_state)

    def set_mouse_pos(self, x, y, duration: float = 0):
        x = int(x)
        y = int(y)
        current_x, current_y = self.get_mouse_position()
        target_screen_x, target_screen_y = self._client_to_screen_target(x, y)
        
        # 直接透传 duration，让底层 Fitts Law (如果 duration=0) 能够自己判断，而不是在这里用固定的 resolve_move_duration() 将其强制覆盖为 0.075s 之类
        # 仅为打印日志而临时计算展示用的 move_duration：
        dummy_move_duration = duration if duration > 0 else self._resolve_move_duration(
            math.hypot(target_screen_x - current_x, target_screen_y - current_y), duration
        )
        log.debug(
            f"新罗技驱动目标换算: 客户区({x},{y}) -> 屏幕({target_screen_x},{target_screen_y}), 当前鼠标({current_x},{current_y}), 日志估算时长{dummy_move_duration * 1000:.0f}ms",
            stacklevel=2,
        )
        
        self._move_to_client(x, y, duration=duration)

        final_x, final_y = self.get_mouse_position()
        err_x = target_screen_x - final_x
        err_y = target_screen_y - final_y
        log.debug(
            f"新罗技驱动实际落点: 屏幕({final_x},{final_y}), 与目标差值({err_x},{err_y})",
            stacklevel=2,
        )

    def mouse_down(self, x=None, y=None):
        if x is not None and y is not None:
            self.set_mouse_pos(x, y)
        self._press_mouse_button(BUTTON_LEFT)
        HumanKinematics.human_sleep(0.012, jitter=0.35, minimum=0.008, maximum=0.03)

    def mouse_up(self, x=None, y=None):
        if x is not None and y is not None:
            self.set_mouse_pos(x, y)
        self._ensure_driver_ready()
        if not self.mouse_up_func():
            raise RuntimeError("鼠标抬起失败")
        HumanKinematics.human_sleep(0.012, jitter=0.35, minimum=0.008, maximum=0.03)

    def mouse_click(self, x, y, times=1, move_back=False) -> bool:
        if move_back:
            current_mouse_position = self.get_mouse_position()

        log.debug(f"新罗技驱动点击位置:({x},{y})", stacklevel=2)

        for index in range(times):
            self._ensure_input_focus()
            self.set_mouse_pos(x, y)
            self.mouse_down()
            self.mouse_up()
            if index < times - 1:
                HumanKinematics.human_sleep(0.05, jitter=0.45, minimum=0.025, maximum=0.12)

        if move_back and current_mouse_position:
            self.mouse_move(current_mouse_position)

        self.wait_pause()
        return True

    def mouse_drag(self, x, y, drag_time=0.1, dx=0, dy=0, move_back=True) -> None:
        if move_back:
            current_mouse_position = self.get_mouse_position()

        drag_distance = math.hypot(dx, dy)
        self._ensure_input_focus()
        self.set_mouse_pos(x, y)
        self.mouse_down()
        self._move_to_client(x + dx, y + dy, duration=drag_time, button_state=BUTTON_LEFT)
        HumanKinematics.human_sleep(
            self._resolve_post_drag_pause(drag_distance, drag_time),
            jitter=0.05,
            minimum=0.02,
        )
        self.mouse_up()

        if move_back and current_mouse_position:
            self.mouse_move(current_mouse_position)

    def mouse_drag_down(self, x, y, reverse=1, move_back=True) -> None:
        if move_back:
            current_mouse_position = self.get_mouse_position()

        scale = cfg.set_win_size / 1080
        drag_distance = int(300 * scale * reverse)
        self._ensure_input_focus()
        self.set_mouse_pos(x, y)
        self.mouse_down()
        self._move_to_client(
            x,
            y + drag_distance,
            duration=HumanKinematics.sample_duration(0.28, jitter=0.18, minimum=0.2, maximum=0.36),
            button_state=BUTTON_LEFT,
        )
        HumanKinematics.human_sleep(
            self._resolve_post_drag_pause(abs(drag_distance), 0.28),
            jitter=0.05,
            minimum=0.02,
        )
        self.mouse_up()

        if move_back and current_mouse_position:
            self.mouse_move(current_mouse_position)

    def mouse_drag_link(self, position: list, drag_time=0.1, move_back=True) -> None:
        if move_back:
            current_mouse_position = self.get_mouse_position()

        self._ensure_input_focus()
        self.set_mouse_pos(position[0][0], position[0][1])
        self.mouse_down()
        for pos in position:
            self._move_to_client(pos[0], pos[1], duration=drag_time, button_state=BUTTON_LEFT)
        HumanKinematics.human_sleep(
            self._resolve_post_drag_pause(len(position) * 80, drag_time),
            jitter=0.05,
            minimum=0.02,
        )
        self.mouse_up()

        if move_back and current_mouse_position:
            self.mouse_move(current_mouse_position)

    def mouse_click_blank(self, coordinate=(1, 1), times=1, move_back=False) -> bool:
        if move_back:
            current_mouse_position = self.get_mouse_position()

        log.debug("新罗技驱动点击空白位置", stacklevel=2)
        x = coordinate[0] + random.randint(0, 10)
        y = coordinate[1] + random.randint(0, 10)
        for _ in range(times):
            self._ensure_input_focus()
            self.set_mouse_pos(x, y)
            self.mouse_down()
            self.mouse_up()

        if move_back and current_mouse_position:
            self.mouse_move(current_mouse_position)

        self.wait_pause()
        return True

    def mouse_to_blank(self, coordinate=(1, 1), move_back=False) -> None:
        if move_back:
            current_mouse_position = self.get_mouse_position()
            rect = screen.handle.rect(True)
            if current_mouse_position[0] > rect[2] or current_mouse_position[1] > rect[3]:
                return
            if current_mouse_position[0] < rect[0] or current_mouse_position[1] < rect[1]:
                return
        target_x = int(coordinate[0])
        target_y = int(coordinate[1])
        self.set_mouse_pos(target_x, target_y)
        log.debug(f"新罗技驱动鼠标移动到空白避免遮挡: 客户区({target_x},{target_y})", stacklevel=2)
        self.wait_pause()

    def mouse_scroll(self, direction: int = -3) -> bool:
        if direction == 0:
            return True

        self._ensure_input_focus()
        self._ensure_driver_ready()
        wheel_func = self.wheel_down_func if direction < 0 else self.wheel_up_func
        if not wheel_func():
            raise RuntimeError(f"滚轮事件发送失败: direction={direction}")
        return True

    def mouse_move(self, coordinate=(1, 1)) -> None:
        self._mouse_move_to(coordinate[0], coordinate[1])
        self.wait_pause()

    def set_active(self):
        self._ensure_input_focus()

    def key_down(self, key: str):
        self._ensure_driver_ready()
        normalized_key = self._normalize_key_name(key)
        try:
            self.press_key_func(normalized_key.encode("utf-8"))
        except Exception as e:
            log.error(f"新罗技驱动键盘按下异常: {normalized_key}, {e}")
            raise

    def key_up(self, key: str):
        self._ensure_driver_ready()
        normalized_key = self._normalize_key_name(key)
        try:
            self.release_key_func(normalized_key.encode("utf-8"))
        except Exception as e:
            log.error(f"新罗技驱动键盘抬起异常: {normalized_key}, {e}")
            raise

    def key_press(self, key):
        self._ensure_input_focus()
        self.key_down(key)
        HumanKinematics.human_sleep(0.018, jitter=0.35, minimum=0.012, maximum=0.045)
        self.key_up(key)
