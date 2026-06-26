import unittest
from unittest.mock import patch

import module.automation.input_handlers.simulator.mumu_control as mumu_control_module
from module.my_error.my_error import userStopError


class TestMumuIpcInputRetry(unittest.TestCase):
    def _make_control(self, results):
        control = mumu_control_module.MumuControl.__new__(mumu_control_module.MumuControl)
        control.connect_id = 1
        control.display_id = 0
        control.height = 720
        control.width = 1280
        control.stop_checker = lambda: None
        calls = []

        class LibStub:
            def nemu_input_event_touch_down(self):
                raise AssertionError

        control.lib = LibStub()
        result_iter = iter(results)

        def fake_ev_run_sync(func, *args):
            calls.append((func.__name__, args))
            return next(result_iter)

        control.ev_run_sync = fake_ev_run_sync
        return control, calls

    def test_down_recovers_when_tenth_attempt_succeeds(self):
        control, calls = self._make_control([4] * 9 + [0])

        with (
            patch.object(mumu_control_module.log, "warning"),
            patch.object(mumu_control_module.time, "sleep"),
            patch.object(control, "reconnect"),
        ):
            control.down(12, 34)

        self.assertEqual(len(calls), 10)
        self.assertTrue(all(call[0] == "nemu_input_event_touch_down" for call in calls))

    def test_down_stops_after_ten_consecutive_failures(self):
        control, calls = self._make_control([4] * 10)

        with (
            patch.object(mumu_control_module.log, "warning") as warning,
            patch.object(mumu_control_module.time, "sleep"),
            patch.object(control, "reconnect"),
            self.assertRaises(userStopError) as raised,
        ):
            control.down(12, 34)

        self.assertEqual(len(calls), 10)
        self.assertIn("连续失败10次", str(raised.exception))
        warning.assert_called()

    def test_reconnect_is_attempted_after_five_failures(self):
        control, calls = self._make_control([4] * 6 + [0])

        with (
            patch.object(mumu_control_module.log, "warning"),
            patch.object(mumu_control_module.time, "sleep"),
            patch.object(control, "reconnect") as mock_reconnect,
        ):
            control.down(12, 34)

        self.assertEqual(len(calls), 7)
        mock_reconnect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
