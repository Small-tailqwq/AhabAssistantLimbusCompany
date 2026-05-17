import unittest
from unittest import mock

from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme

from tasks.tools.infinite_battle import InfiniteBattles


class _DummyHotKeys:
    def __init__(self, *_args, **_kwargs):
        pass

    def start(self):
        pass

    def stop(self):
        pass


class TestToolStatusStyle(unittest.TestCase):
    def test_auto_battle_status_label_uses_dark_background_in_dark_theme(self):
        app = QApplication.instance() or QApplication([])
        setTheme(Theme.DARK)

        with mock.patch("tasks.tools.infinite_battle.ExactGlobalHotKeys", _DummyHotKeys):
            window = InfiniteBattles()

        try:
            style = window.status_label.styleSheet().lower()

            self.assertNotIn("background-color: #f0f0f0", style)
            self.assertIn("background-color: #2b2b2b", style)
        finally:
            window.close()
            setTheme(Theme.LIGHT)
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
