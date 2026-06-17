import unittest
from unittest import mock

from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme

from tasks.tools import ui_style
from tasks.tools.asset_manager import AssetManager
from tasks.tools.infinite_battle import InfiniteBattles
from tasks.tools.issue_replay import IssueReplay


class _DummyHotKeys:
    def __init__(self, *_args, **_kwargs):
        pass

    def start(self):
        pass

    def stop(self):
        pass


class TestToolStatusStyle(unittest.TestCase):
    def test_tool_window_theme_helper_updates_windows_titlebar_mode(self):
        class FakeWidget:
            def __init__(self):
                self.style = ""

            def setStyleSheet(self, style):
                self.style = style

        widget = FakeWidget()

        with (
            mock.patch.object(ui_style, "isDarkTheme", return_value=False),
            mock.patch.object(ui_style.os, "name", "nt"),
            mock.patch.object(ui_style, "_set_windows_title_bar_theme") as set_titlebar,
        ):
            ui_style.apply_tool_window_theme(widget, "FakeWidget")

        self.assertIn("background-color: #ffffff", widget.style.lower())
        set_titlebar.assert_called_once_with(widget, dark=False)

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

    def test_auto_battle_status_label_updates_when_theme_changes_to_light(self):
        app = QApplication.instance() or QApplication([])
        setTheme(Theme.DARK)

        with mock.patch("tasks.tools.infinite_battle.ExactGlobalHotKeys", _DummyHotKeys):
            window = InfiniteBattles()

        try:
            setTheme(Theme.LIGHT)
            app.processEvents()
            style = window.status_label.styleSheet().lower()

            self.assertIn("background-color: #f0f0f0", style)
            self.assertNotIn("background-color: #2b2b2b", style)
        finally:
            window.close()
            setTheme(Theme.LIGHT)
            app.processEvents()

    def test_auto_battle_window_updates_native_widgets_when_theme_changes_to_light(self):
        app = QApplication.instance() or QApplication([])
        setTheme(Theme.DARK)

        with mock.patch("tasks.tools.infinite_battle.ExactGlobalHotKeys", _DummyHotKeys):
            window = InfiniteBattles()

        try:
            setTheme(Theme.LIGHT)
            app.processEvents()
            style = window.styleSheet().lower()

            self.assertIn("infinitebattles", style)
            self.assertIn("qtextedit", style)
            self.assertIn("background-color: #ffffff", style)
            self.assertNotIn("background-color: #1f1f1f", style)
        finally:
            window.close()
            setTheme(Theme.LIGHT)
            app.processEvents()

    def test_auto_battle_clears_stop_request_on_finished(self):
        app = QApplication.instance() or QApplication([])

        with mock.patch("tasks.tools.infinite_battle.ExactGlobalHotKeys", _DummyHotKeys):
            window = InfiniteBattles()

        try:
            with (
                mock.patch.object(window, "log_text"),
                mock.patch("tasks.tools.infinite_battle.auto") as mock_auto,
            ):
                window.on_battle_finished()
                mock_auto.clear_stop_request.assert_called_once()
        finally:
            window.close()
            app.processEvents()

    def test_auto_battle_re_enables_checkboxes_on_finished(self):
        app = QApplication.instance() or QApplication([])

        with mock.patch("tasks.tools.infinite_battle.ExactGlobalHotKeys", _DummyHotKeys):
            window = InfiniteBattles()

        try:
            window.defense_box.setDisabled(True)
            window.defense_on_turn1_box.setDisabled(True)
            window.not_choose_event_box.setDisabled(True)
            window.main_story_mode_box.setDisabled(True)

            with (
                mock.patch("tasks.tools.infinite_battle.auto"),
                mock.patch.object(window, "log_text"),
            ):
                window.on_battle_finished()

            self.assertTrue(window.defense_box.isEnabled())
            self.assertTrue(window.defense_on_turn1_box.isEnabled())
            self.assertTrue(window.not_choose_event_box.isEnabled())
            self.assertTrue(window.main_story_mode_box.isEnabled())
        finally:
            window.close()
            app.processEvents()

    def test_auto_battle_clears_stop_request_before_start(self):
        app = QApplication.instance() or QApplication([])

        with mock.patch("tasks.tools.infinite_battle.ExactGlobalHotKeys", _DummyHotKeys):
            window = InfiniteBattles()

        try:
            worker = mock.MagicMock()
            worker.isRunning.return_value = False
            with (
                mock.patch("tasks.tools.infinite_battle.BattleWorker", return_value=worker),
                mock.patch("tasks.tools.infinite_battle.auto") as mock_auto,
            ):
                window.start_battle()
                mock_auto.clear_stop_request.assert_called_once()
                self.assertEqual(window.worker, worker)
        finally:
            window.close()
            app.processEvents()

    def test_asset_manager_uses_tool_window_light_theme(self):
        app = QApplication.instance() or QApplication([])
        setTheme(Theme.LIGHT)

        with mock.patch.object(AssetManager, "_start_scan"):
            window = AssetManager()

        try:
            style = window.styleSheet().lower()

            self.assertIn("assetmanager", style)
            self.assertIn("qtreewidget", style)
            self.assertIn("qsplitter::handle", style)
            self.assertIn("qcombobox qabstractitemview", style)
            self.assertIn("background-color: #ffffff", style)
            self.assertNotIn("background-color: #1f1f1f", style)
        finally:
            window.close()
            app.processEvents()

    def test_issue_replay_uses_tool_window_light_theme(self):
        app = QApplication.instance() or QApplication([])
        setTheme(Theme.LIGHT)

        with mock.patch.object(IssueReplay, "_refresh_issue_list"):
            window = IssueReplay()

        try:
            style = window.styleSheet().lower()

            self.assertIn("issuereplay", style)
            self.assertIn("qtablewidget", style)
            self.assertIn("qscrollbar:vertical", style)
            self.assertIn("background-color: #ffffff", style)
            self.assertNotIn("background-color: #1f1f1f", style)
            self.assertNotIn("palette(base)", window.issue_notes_edit.styleSheet().lower())
        finally:
            window.close()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
