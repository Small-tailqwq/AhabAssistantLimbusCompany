import unittest
from unittest import mock

from PySide6.QtWidgets import QApplication

from module.config import cfg
from module.game_and_screen import screen
from module.game_and_screen.screen import Handle
from tasks.tools.screenshot_module import QuickScreenshotGet, ScreenshotGet


class _DummyImage:
    def __init__(self):
        self.saved_path = None

    def save(self, path: str):
        self.saved_path = path


class TestScreenshotTool(unittest.TestCase):
    def test_screenshot_tool_restores_window_when_configured(self):
        QApplication.instance() or QApplication([])
        image = _DummyImage()
        tool = ScreenshotGet()

        with (
            mock.patch.object(cfg, "set_windows", True),
            mock.patch.object(cfg, "set_reduce_miscontact", True),
            mock.patch.object(cfg, "simulator", False),
            mock.patch("tasks.base.script_task_scheme.init_game") as init_game,
            mock.patch("tasks.tools.screenshot_module.auto.take_screenshot", return_value=image) as take_screenshot,
            mock.patch.object(screen, "reset_win") as reset_win,
            mock.patch("tasks.tools.screenshot_module.time.strftime", return_value="20260517_151500"),
        ):
            tool.run()

        init_game.assert_called_once_with()
        take_screenshot.assert_called_once_with(gray=False)
        self.assertEqual(image.saved_path, "screenshot_20260517_151500.png")
        reset_win.assert_called_once_with(activate=False)

    def test_screenshot_tool_preserves_window_when_restore_is_disabled(self):
        QApplication.instance() or QApplication([])
        image = _DummyImage()
        tool = ScreenshotGet()

        with (
            mock.patch.object(cfg, "set_windows", True),
            mock.patch.object(cfg, "set_reduce_miscontact", False),
            mock.patch.object(cfg, "simulator", False),
            mock.patch("tasks.base.script_task_scheme.init_game"),
            mock.patch("tasks.tools.screenshot_module.auto.take_screenshot", return_value=image),
            mock.patch.object(screen, "reset_win") as reset_win,
            mock.patch("tasks.tools.screenshot_module.time.strftime", return_value="20260517_151500"),
        ):
            tool.run()

        reset_win.assert_not_called()


class TestQuickScreenshotTool(unittest.TestCase):
    def test_pc_mode_success(self):
        QApplication.instance() or QApplication([])
        image = _DummyImage()
        tool = QuickScreenshotGet()

        with (
            mock.patch.object(cfg, "simulator", False),
            mock.patch.object(screen.handle, "init_handle") as init_handle,
            mock.patch.object(Handle, "hwnd", new_callable=mock.PropertyMock, return_value=12345),
            mock.patch.object(Handle, "isMinimized", new_callable=mock.PropertyMock, return_value=False),
            mock.patch("tasks.tools.screenshot_module.ScreenShot.take_screenshot", return_value=image) as take_screenshot,
            mock.patch("tasks.tools.screenshot_module.time.strftime", return_value="20260517_151500_123456"),
            mock.patch.object(tool, "on_saved_timestr") as mock_signal,
        ):
            tool.run()

        init_handle.assert_called_once_with()
        take_screenshot.assert_called_once_with(gray=False)
        self.assertEqual(image.saved_path, "quick_screenshot_20260517_151500_123456.png")
        mock_signal.emit.assert_called_once_with("20260517_151500_123456")

    def test_pc_mode_no_window(self):
        QApplication.instance() or QApplication([])
        tool = QuickScreenshotGet()

        with (
            mock.patch.object(cfg, "simulator", False),
            mock.patch.object(screen.handle, "init_handle"),
            mock.patch.object(Handle, "hwnd", new_callable=mock.PropertyMock, return_value=0),
            mock.patch.object(tool, "on_error") as mock_error,
        ):
            tool.run()

        mock_error.emit.assert_called_once()

    def test_pc_mode_minimized(self):
        QApplication.instance() or QApplication([])
        tool = QuickScreenshotGet()

        with (
            mock.patch.object(cfg, "simulator", False),
            mock.patch.object(screen.handle, "init_handle"),
            mock.patch.object(Handle, "hwnd", new_callable=mock.PropertyMock, return_value=12345),
            mock.patch.object(Handle, "isMinimized", new_callable=mock.PropertyMock, return_value=True),
            mock.patch.object(tool, "on_error") as mock_error,
        ):
            tool.run()

        mock_error.emit.assert_called_once()

    def test_mumu_mode_success(self):
        QApplication.instance() or QApplication([])
        image = _DummyImage()
        tool = QuickScreenshotGet()
        mock_connection = mock.MagicMock()

        with (
            mock.patch.object(cfg, "simulator", True),
            mock.patch.object(cfg, "simulator_type", 0),
            mock.patch("module.automation.input_handlers.simulator.mumu_control.MumuControl") as MockMumu,
            mock.patch("tasks.tools.screenshot_module.ScreenShot.mumu_screenshot", return_value=image) as mumu_screenshot,
            mock.patch("tasks.tools.screenshot_module.time.strftime", return_value="20260517_151500_123456"),
            mock.patch.object(tool, "on_saved_timestr") as mock_signal,
        ):
            MockMumu.connection_device = mock_connection
            tool.run()

        mumu_screenshot.assert_called_once_with(gray=False)
        self.assertEqual(image.saved_path, "quick_screenshot_20260517_151500_123456.png")
        mock_signal.emit.assert_called_once_with("20260517_151500_123456")

    def test_mumu_mode_not_connected(self):
        QApplication.instance() or QApplication([])
        tool = QuickScreenshotGet()

        with (
            mock.patch.object(cfg, "simulator", True),
            mock.patch.object(cfg, "simulator_type", 0),
            mock.patch("module.automation.input_handlers.simulator.mumu_control.MumuControl") as MockMumu,
            mock.patch.object(tool, "on_error") as mock_error,
        ):
            MockMumu.connection_device = None
            tool.run()

        mock_error.emit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
