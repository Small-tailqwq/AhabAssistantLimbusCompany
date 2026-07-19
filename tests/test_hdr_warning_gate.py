import unittest
from types import SimpleNamespace
from unittest import mock

import tasks.base.script_task_scheme as scheme
from module.game_and_screen.hdr import HdrDisplayInfo
from module.my_error.my_error import userStopError


class ImmediateSignal:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)
        event.set()


class TestHdrWarningGate(unittest.TestCase):
    def test_simulator_mode_skips_hdr_query(self):
        cfg_stub = SimpleNamespace(simulator=True)
        with (
            mock.patch.object(scheme, "cfg", cfg_stub),
            mock.patch.object(scheme, "get_monitor_hdr_info") as query,
        ):
            scheme._warn_if_game_monitor_hdr_enabled()

        query.assert_not_called()

    def test_disabled_setting_skips_hdr_query(self):
        cfg_stub = SimpleNamespace(
            simulator=False,
            get_value=lambda key, default=None: False,
        )
        with (
            mock.patch.object(scheme, "cfg", cfg_stub),
            mock.patch.object(scheme, "get_monitor_hdr_info") as query,
        ):
            scheme._warn_if_game_monitor_hdr_enabled()

        query.assert_not_called()

    def test_hdr_display_emits_warning_and_waits_for_acknowledgement(self):
        signal = ImmediateSignal()
        cfg_stub = SimpleNamespace(
            simulator=False,
            get_value=lambda key, default=None: True,
        )
        mediator_stub = SimpleNamespace(
            hdr_warning=signal,
            hdr_warning_clear=SimpleNamespace(emit=mock.Mock()),
        )
        screen_stub = SimpleNamespace(handle=SimpleNamespace(hwnd=123))
        info = HdrDisplayInfo(
            monitor_handle=456,
            device_name=r"\\.\DISPLAY1",
            color_space=12,
        )
        with (
            mock.patch.object(scheme, "cfg", cfg_stub),
            mock.patch.object(scheme, "mediator", mediator_stub),
            mock.patch.object(scheme, "screen", screen_stub),
            mock.patch.object(scheme.win32api, "MonitorFromWindow", return_value=456),
            mock.patch.object(scheme, "get_monitor_hdr_info", return_value=info),
            mock.patch.object(scheme.auto, "ensure_not_stopped") as stop_check,
        ):
            scheme._warn_if_game_monitor_hdr_enabled()

        self.assertEqual(len(signal.events), 1)
        stop_check.assert_called_once_with()

    def test_stop_wins_when_acknowledgement_is_already_set(self):
        signal = ImmediateSignal()
        cfg_stub = SimpleNamespace(
            simulator=False,
            get_value=lambda key, default=None: True,
        )
        clear = mock.Mock()
        mediator_stub = SimpleNamespace(
            hdr_warning=signal,
            hdr_warning_clear=SimpleNamespace(emit=clear),
        )
        screen_stub = SimpleNamespace(handle=SimpleNamespace(hwnd=123))
        info = HdrDisplayInfo(456, r"\\.\DISPLAY1", color_space=12)
        with (
            mock.patch.object(scheme, "cfg", cfg_stub),
            mock.patch.object(scheme, "mediator", mediator_stub),
            mock.patch.object(scheme, "screen", screen_stub),
            mock.patch.object(scheme.win32api, "MonitorFromWindow", return_value=456),
            mock.patch.object(scheme, "get_monitor_hdr_info", return_value=info),
            mock.patch.object(
                scheme.auto,
                "ensure_not_stopped",
                side_effect=userStopError("stop"),
            ),
            self.assertRaises(userStopError),
        ):
            scheme._warn_if_game_monitor_hdr_enabled()

        clear.assert_not_called()

    def test_stop_during_warning_closes_dialog_and_propagates(self):
        event = mock.Mock()
        event.wait.return_value = False
        event.is_set.return_value = False
        cfg_stub = SimpleNamespace(
            simulator=False,
            get_value=lambda key, default=None: True,
        )
        clear = mock.Mock()
        mediator_stub = SimpleNamespace(
            hdr_warning=SimpleNamespace(emit=mock.Mock()),
            hdr_warning_clear=SimpleNamespace(emit=clear),
        )
        screen_stub = SimpleNamespace(handle=SimpleNamespace(hwnd=123))
        info = HdrDisplayInfo(456, r"\\.\DISPLAY1", color_space=12)
        with (
            mock.patch.object(scheme, "cfg", cfg_stub),
            mock.patch.object(scheme, "mediator", mediator_stub),
            mock.patch.object(scheme, "screen", screen_stub),
            mock.patch.object(scheme.win32api, "MonitorFromWindow", return_value=456),
            mock.patch.object(scheme, "get_monitor_hdr_info", return_value=info),
            mock.patch.object(scheme, "Event", return_value=event),
            mock.patch.object(
                scheme.auto,
                "ensure_not_stopped",
                side_effect=userStopError("stop"),
            ),
            self.assertRaises(userStopError),
        ):
            scheme._warn_if_game_monitor_hdr_enabled()

        clear.assert_called_once_with(event)
