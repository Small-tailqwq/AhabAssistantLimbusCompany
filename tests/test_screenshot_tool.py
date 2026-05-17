import unittest
from unittest import mock

from PySide6.QtWidgets import QApplication

from module.config import cfg
from module.game_and_screen import screen
from tasks.tools.screenshot_module import ScreenshotGet


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


if __name__ == "__main__":
    unittest.main()
