from collections.abc import Mapping
from time import sleep, time

from module.logger import log

from .keys import KeyCode, UnsupportedKeyError, normalize_key, resolve_backend_key


class AbstractInput:
    """输入接口类，定义输入方法的抽象接口

    Tips: 有特殊需求写在对应方法描述中
    """

    def __init__(self) -> None:
        self.is_pause: bool = False
        self.restore_time: float | None = None

    KEY_BACKEND = "abstract"
    KEY_CODES: Mapping[str, KeyCode] | None = None
    KEY_PRESS_DURATION = 0.015

    def check_stop_requested(self) -> None:
        stop_checker = getattr(self, "stop_checker", None)
        if callable(stop_checker):
            stop_checker()

    def set_pause(self) -> None:
        """
        设置暂停状态
        """
        self.is_pause = not self.is_pause  # 设置暂停状态
        if self.is_pause:
            msg = "操作将在下一次点击时暂停"
        else:
            msg = "继续操作"
        log.info(msg)

    def wait_pause(self) -> None:
        """
        当处于暂停状态时堵塞的进行等待
        """
        pause_identity = False
        while self.is_pause:
            self.check_stop_requested()
            if pause_identity is not False:
                log.info("AALC 已暂停")
                pause_identity = True
            sleep(1)
            self.restore_time = time()

    def mouse_click(self, x, y, times=1, move_back=False) -> bool:
        """在指定坐标上执行点击操作

        Args:
            x (int): x坐标
            y (int): y坐标
            times (int): 点击次数
            move_back (bool): 是否在点击后将鼠标移动回原位置
        Returns:
            bool (True) : 总是返回True表示操作执行完毕
        ---
        Extra:<br>
            输出日志: "点击位置:(x,y)"
        """
        raise InterruptedError(f"未实现的输入方法 {self.__class__.__name__}.mouse_click")

    def mouse_click_blank(self, coordinate=(1, 1), times=1, move_back=False) -> bool:
        """在空白位置点击鼠标
        Args:
            coordinate (tuple): 坐标元组 (x, y)
            times (int): 点击次数
            move_back (bool): 是否在点击后将鼠标移动回原位置
        Returns:
            bool (True) : 总是返回True表示操作执行完毕
        ---
        Extra:<br>
            输出日志: "点击（1，1）空白位置"
        """
        raise InterruptedError(f"未实现的输入方法 {self.__class__.__name__}.mouse_click_blank")

    def mouse_drag(self, x, y, drag_time=0.1, dx=0, dy=0, move_back=True, drag_profile=None) -> None:
        """鼠标从指定位置拖动到另一个位置
        Args:
            x (int): 起始x坐标
            y (int): 起始y坐标
            drag_time (float): 拖动时间
            dx (int): x方向拖动距离
            dy (int): y方向拖动距离
            move_back (bool): 是否在拖动后将鼠标移动回原位置
        """
        raise InterruptedError(f"未实现的输入方法 {self.__class__.__name__}.mouse_drag")

    def mouse_drag_down(self, x, y, reverse=1, move_back=True) -> None:
        """鼠标从指定位置向下拖动

        Args:
            x (int): x坐标
            y (int): y坐标
            reverse (int): 拖动方向，1表示向下，-1表示向上
            move_back (bool): 是否在拖动后将鼠标移动回原位置
        """
        raise InterruptedError(f"未实现的输入方法 {self.__class__.__name__}.mouse_drag_down")

    def mouse_drag_link(self, position: list, drag_time=0.1, move_back=False, drag_profile=None) -> None:
        """鼠标从指定位置拖动到指定位置
        Args:
            x (int): 起始x坐标
            y (int): 起始y坐标
            position (list): 目标位置列表
            drag_time (float): 拖动时间
        """
        raise InterruptedError(f"未实现的输入方法 {self.__class__.__name__}.mouse_drag_link")

    def mouse_scroll(self, direction: int = -3) -> bool:
        """
        进行鼠标滚动操作
        Args:
            direction (int): 滚动方向，正值表示拉近，负值表示缩小
        Returns:
            bool (True) : 表示是否支持该操作
        ---
        Extra:<br>
            如果`direction`为负数, 输出日志: "鼠标滚动滚轮，远离界面"<br>
            如果`direction`为正数, 输出日志: "鼠标滚动滚轮，拉近界面"
        """
        raise InterruptedError(f"未实现的输入方法 {self.__class__.__name__}.mouse_scroll")

    def mouse_to_blank(self, coordinate=(1, 1), move_back=False) -> None:
        """鼠标移动到空白位置，避免遮挡
        Args:
            coordinate (tuple): 坐标元组 (x, y)
            move_back (bool): 是否在移动后将鼠标移动回原位置
        ---
        Extra:<br>
            输出日志: "鼠标移动到空白，避免遮挡"
        """
        raise InterruptedError(f"未实现的输入方法 {self.__class__.__name__}.mouse_to_blank")

    def _resolve_backend_key(self, key: str) -> KeyCode:
        if self.KEY_CODES is None:
            return key
        return resolve_backend_key(key, self.KEY_CODES, self.KEY_BACKEND)

    def _before_key_input(self, key: str) -> None:
        return

    def _key_down_impl(self, backend_key: KeyCode) -> None:
        raise InterruptedError(f"未实现的输入方法 {self.__class__.__name__}._key_down_impl")

    def _key_up_impl(self, backend_key: KeyCode) -> None:
        raise InterruptedError(f"未实现的输入方法 {self.__class__.__name__}._key_up_impl")

    def _key_press_impl(self, backend_key: KeyCode) -> None:
        self._key_down_impl(backend_key)
        sleep(self.KEY_PRESS_DURATION)
        self._key_up_impl(backend_key)

    def key_down(self, key: str) -> None:
        try:
            canonical_key = normalize_key(key)
            backend_key = self._resolve_backend_key(canonical_key)
        except UnsupportedKeyError as e:
            log.error(str(e))
            raise
        log.debug(f"按键按下: {canonical_key}")
        self._before_key_input(canonical_key)
        self._key_down_impl(backend_key)

    def key_up(self, key: str) -> None:
        try:
            canonical_key = normalize_key(key)
            backend_key = self._resolve_backend_key(canonical_key)
        except UnsupportedKeyError as e:
            log.error(str(e))
            raise
        log.debug(f"按键抬起: {canonical_key}")
        self._before_key_input(canonical_key)
        self._key_up_impl(backend_key)

    def key_press(self, key: str) -> None:
        try:
            canonical_key = normalize_key(key)
            backend_key = self._resolve_backend_key(canonical_key)
        except UnsupportedKeyError as e:
            log.error(str(e))
            raise
        log.debug(f"按下按键: {canonical_key}")
        self._before_key_input(canonical_key)
        self._key_press_impl(backend_key)
