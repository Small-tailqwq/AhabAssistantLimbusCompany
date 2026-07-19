import unittest
from pathlib import Path
from typing import get_type_hints
from unittest import mock

from PySide6.QtWidgets import QApplication

import app.base_combination as base_combination_module
import app.my_app as my_app_module
import module.config.config_typing as config_typing_module
from app.setting_interface import SettingInterface


class EventStub:
    def __init__(self):
        self.was_set = False

    def set(self):
        self.was_set = True


class TestHdrWarningUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_hdr_warning_sets_event_after_dialog_closes(self):
        event = EventStub()
        dialog = mock.Mock()
        generic_dialog = mock.Mock()
        window = my_app_module.MainWindow.__new__(my_app_module.MainWindow)
        window.tr = lambda text: text
        window._current_warning_box = generic_dialog

        with mock.patch.object(my_app_module, "MessageBoxWarning", return_value=dialog):
            my_app_module.MainWindow.show_hdr_warning(window, event)

        dialog.exec.assert_called_once_with()
        self.assertTrue(event.was_set)
        self.assertIsNone(window._current_hdr_warning_box)
        self.assertIs(window._current_warning_box, generic_dialog)

    def test_hdr_warning_sets_event_when_dialog_raises(self):
        event = EventStub()
        dialog = mock.Mock()
        dialog.exec.side_effect = RuntimeError("dialog failed")
        window = my_app_module.MainWindow.__new__(my_app_module.MainWindow)
        window.tr = lambda text: text

        with mock.patch.object(my_app_module, "MessageBoxWarning", return_value=dialog):
            my_app_module.MainWindow.show_hdr_warning(window, event)

        self.assertTrue(event.was_set)
        self.assertIsNone(window._current_hdr_warning_box)

    def test_hdr_warning_clear_closes_only_matching_hdr_dialog(self):
        current_event = EventStub()
        generic_dialog = mock.Mock()
        hdr_dialog = mock.Mock()
        window = my_app_module.MainWindow.__new__(my_app_module.MainWindow)
        window._current_hdr_warning_event = current_event
        window._current_hdr_warning_box = hdr_dialog
        window._current_warning_box = generic_dialog

        my_app_module.MainWindow.clear_hdr_warning(window, current_event)

        hdr_dialog.accept.assert_called_once_with()
        generic_dialog.accept.assert_not_called()

    def test_hdr_warning_clear_with_other_event_closes_neither_dialog(self):
        current_event = EventStub()
        other_event = EventStub()
        generic_dialog = mock.Mock()
        hdr_dialog = mock.Mock()
        window = my_app_module.MainWindow.__new__(my_app_module.MainWindow)
        window._current_hdr_warning_event = current_event
        window._current_hdr_warning_box = hdr_dialog
        window._current_warning_box = generic_dialog

        my_app_module.MainWindow.clear_hdr_warning(window, other_event)

        hdr_dialog.accept.assert_not_called()
        generic_dialog.accept.assert_not_called()

    def test_hdr_warning_finally_preserves_later_hdr_dialog_and_event(self):
        event = EventStub()
        later_event = EventStub()
        dialog = mock.Mock()
        later_dialog = mock.Mock()
        generic_dialog = mock.Mock()
        window = my_app_module.MainWindow.__new__(my_app_module.MainWindow)
        window.tr = lambda text: text
        window._current_warning_box = generic_dialog

        def replace_current_hdr_warning():
            window._current_hdr_warning_event = later_event
            window._current_hdr_warning_box = later_dialog

        dialog.exec.side_effect = replace_current_hdr_warning

        with mock.patch.object(my_app_module, "MessageBoxWarning", return_value=dialog):
            my_app_module.MainWindow.show_hdr_warning(window, event)

        self.assertTrue(event.was_set)
        self.assertIs(window._current_hdr_warning_event, later_event)
        self.assertIs(window._current_hdr_warning_box, later_dialog)
        self.assertIs(window._current_warning_box, generic_dialog)

    def test_config_declares_default_enabled_hdr_warning(self):
        hints = get_type_hints(config_typing_module.ConfigModel)
        self.assertIs(hints["experimental_hdr_warning"], bool)

        content = (
            Path(__file__).resolve().parents[1]
            / "assets/config/config.example.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("experimental_hdr_warning: True", content)

    def test_setting_interface_adds_hdr_warning_to_experimental_group(self):
        original_get_value = base_combination_module.cfg.get_value

        def get_value(key, *args, **kwargs):
            if key == "experimental_hdr_warning":
                return True
            return original_get_value(key, *args, **kwargs)

        with mock.patch.object(
            base_combination_module.cfg,
            "get_value",
            side_effect=get_value,
        ):
            interface = SettingInterface()
        try:
            widgets = interface.experimental_group.cardLayout._ExpandLayout__widgets
            self.assertIn(interface.hdr_warning_card, widgets)
            self.assertTrue(interface.hdr_warning_card.switchButton.checked)
        finally:
            interface.close()
            self.app.processEvents()

    def test_setting_interface_retranslates_hdr_warning_card(self):
        interface = SettingInterface()
        try:
            with mock.patch.object(
                interface.hdr_warning_card, "retranslateUi"
            ) as retranslate:
                interface.retranslateUi()

            retranslate.assert_called_once_with()
        finally:
            interface.close()
            self.app.processEvents()
