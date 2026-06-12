import time

from PySide6.QtCore import QThread, Signal

from module.automation import auto
from module.automation.screenshot import ScreenShot
from module.config import cfg
from module.game_and_screen import screen
from module.logger import log


class ScreenshotGet(QThread):
    on_saved_timestr = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.finished.connect(self.deleteLater)

    def run(self):
        should_reset_window = False
        try:
            from tasks.base.script_task_scheme import init_game

            init_game()
            should_reset_window = cfg.set_windows and cfg.set_reduce_miscontact and not cfg.simulator
        except Exception as e:
            log.error(f"初始化游戏失败: {str(e)}")
            return
        try:
            img = auto.take_screenshot(gray=False)
            if img:
                timestr = time.strftime("%Y%m%d_%H%M%S", time.localtime())
                img.save(f"screenshot_{timestr}.png")
                log.info(f"图片保存为 AALC > screenshot_{timestr}.png")
                self.on_saved_timestr.emit(timestr)
            else:
                log.error("截图失败，请确认游戏是否处于启动状态")
        except Exception as e:
            log.error(f"截图错误: {str(e)}")
            return
        finally:
            if should_reset_window:
                screen.reset_win(activate=False)


class QuickScreenshotGet(QThread):
    on_saved_timestr = Signal(str)
    on_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.finished.connect(self.deleteLater)

    def run(self):
        try:
            if cfg.simulator:
                self._ensure_emulator_connected()
                if cfg.simulator_type == 0:
                    img = ScreenShot.mumu_screenshot(gray=False)
                elif cfg.simulator_type == 10:
                    img = ScreenShot.adb_screenshot(gray=False)
                else:
                    raise RuntimeError(f"未知的模拟器类型: {cfg.simulator_type}")
            else:
                screen.handle.init_handle()
                if screen.handle.hwnd == 0:
                    raise RuntimeError("未检测到游戏窗口")
                if screen.handle.isMinimized:
                    raise RuntimeError("游戏窗口已最小化，无法截图")
                img = ScreenShot.take_screenshot(gray=False)
            if img:
                timestr = time.strftime("%Y%m%d_%H%M%S_%f", time.localtime())
                img.save(f"quick_screenshot_{timestr}.png")
                log.info(f"快捷截图保存为 quick_screenshot_{timestr}.png")
                self.on_saved_timestr.emit(timestr)
            else:
                raise RuntimeError("截图返回为空")
        except Exception as e:
            log.error(f"快捷截图失败: {str(e)}")
            self.on_error.emit(str(e))

    def _ensure_emulator_connected(self):
        if cfg.simulator_type == 0:
            from module.automation.input_handlers.simulator.mumu_control import MumuControl

            if MumuControl.connection_device is None:
                raise ConnectionError("未连接到 MuMu 模拟器")
        elif cfg.simulator_type == 10:
            from module.automation.input_handlers.simulator.simulator_control import SimulatorControl

            if SimulatorControl.connection_device is None:
                raise ConnectionError("未连接到 ADB 设备")
        else:
            raise RuntimeError(f"未知的模拟器类型: {cfg.simulator_type}")
