import ctypes
import math
import os
import random
from time import sleep, time

import win32api
import win32con
import win32gui

from module.config import cfg
from module.logger import log
from utils.singletonmeta import SingletonMeta

from ...game_and_screen import screen
from ..human_kinematics import HumanKinematics
from .input import WinAbstractInput


class LogitechInput(WinAbstractInput, metaclass=SingletonMeta):
    """基于罗技 G HUB (logitech.driver.dll) 的鼠标硬件级输入类
    用于规避游戏级的 mouseSynthetic 虚拟检测，并提供坐标插值
    """

    def __init__(self):
        super().__init__()
        self.dll_path = cfg.logitech_dll_path
        if not self.dll_path or not os.path.exists(self.dll_path):
            log.error(f"无法使用实验室鼠标仿真功能：缺失 logitech.driver.dll 或路径错误 ({self.dll_path})。请在配置中提供正确路径。")
            raise FileNotFoundError(f"logitech.driver.dll 未找到：{self.dll_path}")

        try:
            self.dll = ctypes.CDLL(self.dll_path)
            try:
                open_func = getattr(self.dll, "device_open")
                status = open_func()
                if status != 1:
                    log.error(f"罗技驱动 DLL 初始化设备失败(device_open={status})，请确认环境或是否有驱动！")
                    raise RuntimeError("罗技驱动 DLL 设备开启失败。")
            except AttributeError:
                # 若无 device_open 接口则跳过
                pass
            self.move_func = getattr(self.dll, "moveR")
            self.move_func.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
            self.down_func = getattr(self.dll, "mouse_down")
            self.down_func.argtypes = [ctypes.c_int]
            self.up_func = getattr(self.dll, "mouse_up")
            self.up_func.argtypes = [ctypes.c_int]

            log.info("成功加载罗技鼠标驱动 DLL，启用硬件级模拟保护！")
            log.info("罗技鼠标已启用混合模式：系统绝对定位 + DLL 硬件点击。")
        except Exception as e:
            msg = f"加载或初始化罗技 DLL 失败: {e}"
            log.error(msg)
            raise RuntimeError(msg) from e

    def get_mouse_position(self) -> tuple[int, int]:
        return win32api.GetCursorPos()

    def _client_to_screen_target(self, x: int, y: int) -> tuple[int, int]:
        """将窗口客户区相对坐标转换为屏幕绝对坐标。"""
        rect = screen.handle.rect(True)
        return rect[0] + int(x), rect[1] + int(y)

    def _set_cursor_pos_absolute(self, x: int, y: int):
        """使用会发出鼠标移动事件的绝对坐标移动，确保 PowerToys 等覆盖层同步更新。"""
        self._mouse_event_move_to(int(x), int(y))

    def _resolve_move_duration(self, distance: float, duration: float) -> float:
        """为普通鼠标移动补一个可见轨迹，避免看起来像触控瞬移。"""
        if duration > 0:
            return duration

        action_interval = float(getattr(cfg, "mouse_action_interval", 0.5) or 0.5)
        max_duration = max(0.06, min(0.18, action_interval * 0.4))
        return min(max_duration, max(0.03, distance / 8000))

    @staticmethod
    def _ease_out_cubic(progress: float) -> float:
        return 1 - pow(1 - progress, 3)

    def _mouse_move_to(self, x, y, duration: float = 0):
        """绝对于屏幕的插值计算移动"""
        x = int(x)
        y = int(y)

        current_x, current_y = self.get_mouse_position()

        dx = x - current_x
        dy = y - current_y

        if dx == 0 and dy == 0:
            return

        move_duration = self._resolve_move_duration(math.hypot(dx, dy), duration)
        self._move_relative_smooth(dx, dy, duration=move_duration)

    def _is_mouse_button_down(self) -> bool:
        """检测是否有鼠标按键处于按下状态"""
        return (win32api.GetAsyncKeyState(0x01) < 0) or \
               (win32api.GetAsyncKeyState(0x02) < 0) or \
               (win32api.GetAsyncKeyState(0x04) < 0)

    def _mouse_event_move_to(self, x: int, y: int):
        """使用 mouse_event 的绝对坐标移动鼠标，并发出系统可观测的移动事件。"""
        virtual_left = ctypes.windll.user32.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
        virtual_top = ctypes.windll.user32.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
        virtual_width = max(1, ctypes.windll.user32.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN))
        virtual_height = max(1, ctypes.windll.user32.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN))
        norm_x = int(round((int(x) - virtual_left) * 65535 / max(virtual_width - 1, 1)))
        norm_y = int(round((int(y) - virtual_top) * 65535 / max(virtual_height - 1, 1)))
        ctypes.windll.user32.mouse_event(
            win32con.MOUSEEVENTF_MOVE | win32con.MOUSEEVENTF_ABSOLUTE | win32con.MOUSEEVENTF_VIRTUALDESK,
            norm_x, norm_y, 0, 0
        )

    def _move_relative_smooth(self, target_dx: int, target_dy: int, duration: float = 0):
        """使用系统绝对坐标平滑移动，拖拽时用 mouse_event 保持按键状态。"""
        # 标准物理刷新率约 125Hz - 1000Hz, 取 8ms 间隔 (大约 125Hz)
        refresh_rate = 0.008

        distance = math.hypot(target_dx, target_dy)
        if distance == 0:
            return

        start_x, start_y = self.get_mouse_position()
        target_x = start_x + target_dx
        target_y = start_y + target_dy

        if duration <= 0:
            self._set_cursor_pos_absolute(target_x, target_y)
            return

        button_down = self._is_mouse_button_down()
        steps = max(2, int(duration / refresh_rate))
        trajectory = HumanKinematics.generate_human_curve(
            start_x,
            start_y,
            target_x,
            target_y,
            num_points=steps,
            allow_overshoot=not button_down,
            allow_micro_jitter=not button_down,
        )
        step_interval = duration / max(len(trajectory), 1)

        for current_target_x, current_target_y in trajectory:
            step_start = time()

            # 当前物理位置
            current_x, current_y = self.get_mouse_position()

            # 本步真实的 dx, dy
            step_dx = int(current_target_x - current_x)
            step_dy = int(current_target_y - current_y)

            if step_dx != 0 or step_dy != 0:
                self._set_cursor_pos_absolute(current_target_x, current_target_y)

            elapsed = time() - step_start
            remaining = step_interval - elapsed
            if remaining > 0.001:
                HumanKinematics.human_sleep(remaining, jitter=0.08, minimum=remaining)

        # 终点位置误差校验 (确保一定会到达目的地)
        final_x, final_y = self.get_mouse_position()
        final_dx = target_x - final_x
        final_dy = target_y - final_y
        if final_dx != 0 or final_dy != 0:
            self._set_cursor_pos_absolute(target_x, target_y)

    def _set_mouse_pos(self, x: int, y: int):
        self._mouse_move_to(x, y)

    def set_mouse_pos(self, x, y, duration: float = 0):
        """基于游戏窗口左上角的内部相对坐标系移动"""
        x = int(x)
        y = int(y)
        target_screen_x, target_screen_y = self._client_to_screen_target(x, y)
        current_x, current_y = self.get_mouse_position()
        move_duration = self._resolve_move_duration(
            math.hypot(target_screen_x - current_x, target_screen_y - current_y),
            duration,
        )
        log.debug(
            f"硬件鼠标目标换算: 客户区({x},{y}) -> 屏幕({target_screen_x},{target_screen_y}), 当前鼠标({current_x},{current_y}), 规划移动{move_duration * 1000:.0f}ms",
            stacklevel=2,
        )
        self._mouse_move_to(target_screen_x, target_screen_y, duration=move_duration)

        final_x, final_y = self.get_mouse_position()
        err_x = target_screen_x - final_x
        err_y = target_screen_y - final_y
        log.debug(
            f"硬件鼠标实际落点: 屏幕({final_x},{final_y}), 与目标差值({err_x},{err_y})",
            stacklevel=2,
        )

    def mouse_down(self, x=None, y=None):
        """鼠标左键按下（支持传入或不传入坐标，如果传入则先移动到对应位置）"""
        if x is not None and y is not None:
            self.set_mouse_pos(x, y)
        self.down_func(1)
        HumanKinematics.human_sleep(0.012, jitter=0.35, minimum=0.008, maximum=0.03)

    def mouse_up(self, x=None, y=None):
        """鼠标左键抬起"""
        if x is not None and y is not None:
            self.set_mouse_pos(x, y)
        self.up_func(1)
        HumanKinematics.human_sleep(0.012, jitter=0.35, minimum=0.008, maximum=0.03)

    def mouse_click(self, x, y, times=1, move_back=False) -> bool:
        if move_back:
            current_mouse_position = self.get_mouse_position()

        msg = f"硬件级点击位置:({x},{y})"
        log.debug(msg, stacklevel=2)
        
        for i in range(times):
            self.set_mouse_pos(x, y)
            self.set_active()
            before_down = self.get_mouse_position()
            log.debug(f"硬件点击前鼠标位置: {before_down}", stacklevel=2)
            self.mouse_down()
            self.mouse_up()
            if i < times - 1:
                HumanKinematics.human_sleep(0.05, jitter=0.45, minimum=0.025, maximum=0.12)

        if move_back and current_mouse_position:
            self.mouse_move(current_mouse_position)

        self.wait_pause()
        return True

    def mouse_drag(self, x, y, drag_time=0.1, dx=0, dy=0, move_back=True) -> None:
        if move_back:
            current_mouse_position = self.get_mouse_position()
            
        self.set_mouse_pos(x, y)
        self.set_active()
        self.mouse_down()
        
        # 使用 duration 提供平滑拖拽
        self.set_mouse_pos(x + dx, y + dy, duration=drag_time)
        hold_time = max(drag_time * 0.3, 0.5)
        HumanKinematics.human_sleep(hold_time, jitter=0.12, minimum=hold_time)
             
        self.mouse_up()

        if move_back and current_mouse_position:
            self.mouse_move(current_mouse_position)

    def mouse_drag_down(self, x, y, reverse=1, move_back=True) -> None:
        if move_back:
            current_mouse_position = self.get_mouse_position()

        scale = cfg.set_win_size / 1080
        self.set_active()
        self.set_mouse_pos(x, y)
        self.mouse_down()
        self.set_mouse_pos(x, y + int(300 * scale * reverse), duration=0.4)
        self.mouse_up()

        if move_back and current_mouse_position:
            self.mouse_move(current_mouse_position)
            
    def mouse_drag_link(self, position: list, drag_time=0.1, move_back=True) -> None:
        if move_back:
            current_mouse_position = self.get_mouse_position()

        self.set_mouse_pos(position[0][0], position[0][1])
        self.set_active()
        self.mouse_down()
        for pos in position:
            self.set_mouse_pos(pos[0], pos[1], duration=drag_time)
        self.mouse_up()

        if move_back and current_mouse_position:
            self.mouse_move(current_mouse_position)

    def mouse_click_blank(self, coordinate=(1, 1), times=1, move_back=False) -> bool:
        if move_back:
            current_mouse_position = self.get_mouse_position()

        msg = "硬件点击（1，1）空白位置"
        log.debug(msg, stacklevel=2)
        x = coordinate[0] + random.randint(0, 10)
        y = coordinate[1] + random.randint(0, 10)
        for i in range(times):
            self.set_mouse_pos(x, y)
            self.set_active()
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
            elif current_mouse_position[0] < rect[0] or current_mouse_position[1] < rect[1]:
                return
        target_x = int(coordinate[0])
        target_y = int(coordinate[1])
        self.set_mouse_pos(target_x, target_y)
        log.debug(f"硬件鼠标移动到空白避免遮挡: 客户区({target_x},{target_y})", stacklevel=2)
        self.wait_pause()

    def mouse_scroll(self, direction: int = -3) -> bool:
        # 如需可通过罗技控制滚轮（如果存在），一般可不提供此支持（由于游戏中用不到或是可以用拖拽替代）
        return False

    def mouse_move(self, coordinate=(1, 1)) -> None:
        """鼠标移动到指定绝对坐标"""
        self._mouse_move_to(coordinate[0], coordinate[1])
        self.wait_pause()

    def set_active(self):
        """将游戏窗口设置为输入焦点以让 Unity 接受输入事件"""
        hwnd = screen.handle.hwnd
        if hwnd:
            if screen.handle.isMinimized:
                screen.handle.set_window_transparent()
                screen.handle.restore()
                sleep(0.5)
            win32gui.SendMessage(hwnd, win32con.WM_ACTIVATE, win32con.WA_ACTIVE, 0)
        else:
            log.error("未初始化hwnd")

    def key_down(self, key: str):
        # 键盘仍旧使用原本WinAPI的方法，部分DLL支持keybd_event但这里先用Win32
        hwnd = screen.handle.hwnd
        lparam = 0x00000001
        try:
            win32api.SendMessage(hwnd, win32con.WM_KEYDOWN, self._get_key_code(key), lparam)
        except Exception as e:
            log.error(f"键盘按下异常: {e}")

    def key_up(self, key: str):
        hwnd = screen.handle.hwnd
        lparam = 0xC0000001
        try:
            win32api.SendMessage(hwnd, win32con.WM_KEYUP, self._get_key_code(key), lparam)
        except Exception as e:
            log.error(f"键盘抬起异常: {e}")

    def key_press(self, key):
        self.set_active()
        self.key_down(key)
        HumanKinematics.human_sleep(0.018, jitter=0.35, minimum=0.012, maximum=0.045)
        self.key_up(key)

    def _get_key_code(self, key: str) -> int:
        from .input import key_list
        return key_list[key.lower()]
