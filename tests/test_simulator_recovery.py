import unittest
from unittest.mock import patch

import module.automation.input_handlers.simulator.simulator_control as simulator_control_module
import tasks.base.retry as retry_module


class TestSimulatorRecovery(unittest.TestCase):
    def test_call_with_reconnect_retries_recoverable_error(self):
        control = simulator_control_module.SimulatorControl.__new__(simulator_control_module.SimulatorControl)
        control.stop_checker = lambda: None
        reconnect_reasons = []

        def fake_reconnect(reason):
            reconnect_reasons.append(reason)
            return True

        control.reconnect = fake_reconnect
        call_count = {"value": 0}

        def flaky_call():
            call_count["value"] += 1
            if call_count["value"] == 1:
                raise RuntimeError("Broken pipe")
            return "ok"

        result = simulator_control_module.SimulatorControl._call_with_reconnect(control, "截图", flaky_call)

        self.assertEqual(result, "ok")
        self.assertEqual(call_count["value"], 2)
        self.assertEqual(len(reconnect_reasons), 1)
        self.assertIn("Broken pipe", reconnect_reasons[0])

    def test_click_title_screen_safely_uses_simulator_safe_region(self):
        clicks = []
        cfg_stub = type("CfgStub", (), {"simulator": True, "set_win_size": 1000})()
        auto_stub = type("AutoStub", (), {"mouse_click": lambda self, x, y: clicks.append((x, y))})()

        with (
            patch.object(retry_module, "cfg", cfg_stub),
            patch.object(retry_module, "auto", auto_stub),
            patch.object(retry_module.time, "time", return_value=20.0),
            patch.object(retry_module, "_last_title_screen_tap_time", 0.0),
        ):
            retry_module.click_title_screen_safely()

        self.assertEqual(clicks, [(1617, 580)])

    def test_ensure_simulator_game_started_restarts_inactive_game(self):
        calls = []

        class ConnectionDeviceStub:
            def check_game_alive(self):
                calls.append("check_game_alive")
                return False

            def start_game(self):
                calls.append("start_game")

        cfg_stub = type("CfgStub", (), {"simulator": True, "simulator_type": 10})()

        with (
            patch.object(retry_module, "cfg", cfg_stub),
            patch.object(retry_module, "sleep", lambda *_: None),
            patch.object(retry_module.time, "time", return_value=100.0),
            patch.object(retry_module, "_last_simulator_alive_check_time", 0.0),
            patch.object(simulator_control_module.SimulatorControl, "connection_device", ConnectionDeviceStub()),
        ):
            result = retry_module.ensure_simulator_game_started()

        self.assertTrue(result)
        self.assertEqual(calls, ["check_game_alive", "start_game"])

    def test_retry_uses_safe_title_screen_click_for_simulator_cache_prompt(self):
        calls = []

        class AutoStub:
            def __init__(self):
                self.screenshot_calls = 0

            def get_restore_time(self):
                return None

            def take_screenshot(self):
                self.screenshot_calls += 1
                return object()

            def find_element(self, target, *_, **__):
                if target == "base/clear_all_caches_assets.png":
                    return self.screenshot_calls == 1
                return False

            def click_element(self, target, *_, **__):
                if target == "base/update_confirm_assets.png":
                    return False
                return False

            def mouse_to_blank(self):
                calls.append("mouse_to_blank")

        cfg_stub = type("CfgStub", (), {"config": type("ConfigStub", (), {"simulator": True})()})()

        with (
            patch.object(retry_module, "cfg", cfg_stub),
            patch.object(retry_module, "auto", AutoStub()),
            patch.object(retry_module, "ensure_simulator_game_started", return_value=False),
            patch.object(retry_module, "check_times", return_value=False),
            patch.object(retry_module, "click_title_screen_safely", side_effect=lambda: calls.append("safe_click")),
        ):
            retry_module.retry()

        self.assertEqual(calls, ["safe_click"])


if __name__ == "__main__":
    unittest.main()
