import unittest
from unittest.mock import patch

import module.automation.input_handlers.simulator.simulator_control as simulator_control_module
import tasks.base.back_init_menu as back_init_menu_module
import tasks.base.retry as retry_module


class TestSimulatorRecovery(unittest.TestCase):
    def _make_simulator_cfg(self):
        return type(
            "CfgStub",
            (),
            {
                "simulator": True,
                "simulator_type": 10,
                "config": type("ConfigStub", (), {"simulator": True})(),
            },
        )()

    def _make_simulator_connection_device(self, calls, pidof_output):
        class SimulatorDeviceStub:
            def shell(self, command):
                calls.append(("shell", command))
                return pidof_output

        class ConnectionDeviceStub:
            game_package_name = "com.ProjectMoon.LimbusCompany"
            simulator_device = SimulatorDeviceStub()

            def check_game_alive(self):
                calls.append("check_game_alive")
                return False

            def start_game(self):
                calls.append("start_game")

        return ConnectionDeviceStub()

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

    def test_click_title_screen_safely_allows_retry_after_five_seconds(self):
        clicks = []
        cfg_stub = type("CfgStub", (), {"simulator": True, "set_win_size": 1000})()
        auto_stub = type("AutoStub", (), {"mouse_click": lambda self, x, y: clicks.append((x, y))})()

        with (
            patch.object(retry_module, "cfg", cfg_stub),
            patch.object(retry_module, "auto", auto_stub),
            patch.object(retry_module, "_last_title_screen_tap_time", 20.0),
        ):
            with patch.object(retry_module.time, "time", return_value=24.9):
                retry_module.click_title_screen_safely()
            with patch.object(retry_module.time, "time", return_value=25.0):
                retry_module.click_title_screen_safely()

        self.assertEqual(clicks, [(1617, 580)])

    def test_ensure_simulator_game_started_restarts_inactive_game(self):
        calls = []

        with (
            patch.object(retry_module, "cfg", self._make_simulator_cfg()),
            patch.object(retry_module, "sleep", lambda *_: None),
            patch.object(retry_module.time, "time", return_value=100.0),
            patch.object(retry_module, "_last_simulator_alive_check_time", 0.0),
            patch.object(retry_module, "_pending_simulator_launch_probe", False, create=True),
            patch.object(
                simulator_control_module.SimulatorControl,
                "connection_device",
                self._make_simulator_connection_device(calls, pidof_output=""),
            ),
        ):
            result = retry_module.ensure_simulator_game_started()

        self.assertTrue(result)
        self.assertEqual(calls, ["check_game_alive", "start_game"])

    def test_should_wait_for_main_menu_after_simulator_start_detects_launch_state_once(self):
        calls = []

        class AutoStub:
            def ensure_not_stopped(self):
                calls.append("ensure_not_stopped")

            def take_screenshot(self):
                calls.append("take_screenshot")
                return object()

            def click_element(self, target, *_, **__):
                calls.append(("click_element", target))
                return False

            def find_element(self, target, *_, **__):
                calls.append(("find_element", target))
                return False

        time_values = iter([100.0, 100.0, 100.1])

        with (
            patch.object(retry_module, "auto", AutoStub()),
            patch.object(retry_module, "sleep", lambda *_: None),
            patch.object(retry_module, "_pending_simulator_launch_probe", True, create=True),
            patch.object(back_init_menu_module, "handle_launch_state_once", return_value=True),
            patch.object(
                retry_module,
                "time",
                type("TimeStub", (), {"time": staticmethod(lambda: next(time_values))})(),
            ),
        ):
            should_wait = retry_module.should_wait_for_main_menu_after_simulator_start()
            should_wait_after_consume = retry_module.should_wait_for_main_menu_after_simulator_start()

        self.assertTrue(should_wait)
        self.assertFalse(should_wait_after_consume)
        self.assertEqual(calls.count("take_screenshot"), 1)

    def test_should_wait_for_main_menu_after_simulator_start_returns_false_when_runtime_ui_visible(self):
        calls = []
        sleep_calls = []

        class AutoStub:
            def ensure_not_stopped(self):
                calls.append("ensure_not_stopped")

            def take_screenshot(self):
                calls.append("take_screenshot")
                return object()

            def click_element(self, target, *_, **__):
                calls.append(("click_element", target))
                return False

            def find_element(self, target, *_, **__):
                calls.append(("find_element", target))
                return target == "battle/setting_assets.png"

        time_values = iter([100.0, 100.0, 103.1])

        with (
            patch.object(retry_module, "auto", AutoStub()),
            patch.object(retry_module, "sleep", lambda *_: sleep_calls.append("sleep")),
            patch.object(retry_module, "_pending_simulator_launch_probe", True, create=True),
            patch.object(back_init_menu_module, "handle_launch_state_once", return_value=None),
            patch.object(
                retry_module,
                "time",
                type("TimeStub", (), {"time": staticmethod(lambda: next(time_values))})(),
            ),
        ):
            should_wait = retry_module.should_wait_for_main_menu_after_simulator_start()
            should_wait_after_consume = retry_module.should_wait_for_main_menu_after_simulator_start()

        self.assertFalse(should_wait)
        self.assertFalse(should_wait_after_consume)
        self.assertEqual(sleep_calls, [])
        self.assertIn(("find_element", "battle/setting_assets.png"), calls)

    def test_is_runtime_ui_visible_returns_true_for_story_cue(self):
        calls = []

        class AutoStub:
            def find_element(self, target, *_, **__):
                calls.append(target)
                return target == "scenes/story_skip_confirm_assets.png"

        with patch.object(retry_module, "auto", AutoStub()):
            result = retry_module._is_runtime_ui_visible()

        self.assertTrue(result)
        self.assertIn("scenes/story_skip_confirm_assets.png", calls)

    def test_is_runtime_ui_visible_returns_true_for_mirror_menu_cue(self):
        calls = []

        class AutoStub:
            def find_element(self, target, *_, **__):
                calls.append(target)
                return target == "mirror/road_in_mir/to_window_assets.png"

        with patch.object(retry_module, "auto", AutoStub()):
            result = retry_module._is_runtime_ui_visible()

        self.assertTrue(result)
        self.assertIn("mirror/road_in_mir/to_window_assets.png", calls)

    def test_is_runtime_ui_visible_returns_true_for_mirror_entrance_cue(self):
        calls = []

        class AutoStub:
            def find_element(self, target, *_, **__):
                calls.append(target)
                return target == "mirror/road_to_mir/enter_assets.png"

        with patch.object(retry_module, "auto", AutoStub()):
            result = retry_module._is_runtime_ui_visible()

        self.assertTrue(result)
        self.assertIn("mirror/road_to_mir/enter_assets.png", calls)

    def test_is_runtime_ui_visible_returns_true_for_maintenance_prompt_cue(self):
        calls = []

        class AutoStub:
            def find_element(self, target, *_, **__):
                calls.append(target)
                return target == "base/notification_close_assets.png"

        with patch.object(retry_module, "auto", AutoStub()):
            result = retry_module._is_runtime_ui_visible()

        self.assertTrue(result)
        self.assertIn("base/notification_close_assets.png", calls)

    def test_is_runtime_ui_visible_returns_true_for_retry_prompt_cue(self):
        calls = []

        class AutoStub:
            def find_element(self, target, *_, **__):
                calls.append(target)
                return target == "base/retry.png"

        with patch.object(retry_module, "auto", AutoStub()):
            result = retry_module._is_runtime_ui_visible()

        self.assertTrue(result)
        self.assertIn("base/retry.png", calls)

    def test_should_wait_for_main_menu_after_simulator_start_returns_true_when_probe_misses(self):
        calls = []

        class AutoStub:
            def ensure_not_stopped(self):
                calls.append("ensure_not_stopped")

            def take_screenshot(self):
                calls.append("take_screenshot")
                return object()

            def click_element(self, target, *_, **__):
                calls.append(("click_element", target))
                return False

            def find_element(self, target, *_, **__):
                calls.append(("find_element", target))
                return False

        time_values = iter([100.0, 100.0, 103.1])

        with (
            patch.object(retry_module, "auto", AutoStub()),
            patch.object(retry_module, "sleep", lambda *_: None),
            patch.object(retry_module, "_pending_simulator_launch_probe", True, create=True),
            patch.object(back_init_menu_module, "handle_launch_state_once", return_value=None),
            patch.object(
                retry_module,
                "time",
                type("TimeStub", (), {"time": staticmethod(lambda: next(time_values))})(),
            ),
        ):
            should_wait = retry_module.should_wait_for_main_menu_after_simulator_start()
            should_wait_after_consume = retry_module.should_wait_for_main_menu_after_simulator_start()

        self.assertTrue(should_wait)
        self.assertFalse(should_wait_after_consume)
        self.assertEqual(calls.count("take_screenshot"), 1)

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

    def test_retry_waits_for_main_menu_after_simulator_start_probe_detects_launch_chain(self):
        calls = []

        class AutoStub:
            def get_restore_time(self):
                return None

        ensure_call_count = {"value": 0}

        def ensure_started_once():
            ensure_call_count["value"] += 1
            if ensure_call_count["value"] > 1:
                raise AssertionError("retry() should switch to launch wait instead of restarting the loop")
            return True

        with (
            patch.object(retry_module, "cfg", self._make_simulator_cfg()),
            patch.object(retry_module, "auto", AutoStub()),
            patch.object(retry_module, "ensure_simulator_game_started", side_effect=ensure_started_once),
            patch.object(retry_module, "check_times", return_value=False),
            patch.object(retry_module, "sleep", lambda *_: None),
            patch.object(retry_module, "should_wait_for_main_menu_after_simulator_start", return_value=True),
            patch(
                "tasks.base.back_init_menu.wait_until_main_menu_after_launch",
                side_effect=lambda allow_restart=True: calls.append(("wait_main_menu", allow_restart)) or "main_menu",
            ),
        ):
            result = retry_module.retry()

        self.assertTrue(result)
        self.assertIn(("wait_main_menu", True), calls)
        self.assertEqual(ensure_call_count["value"], 1)

    def test_retry_returns_false_when_launch_wait_times_out(self):
        class AutoStub:
            def get_restore_time(self):
                return None

        with (
            patch.object(retry_module, "cfg", self._make_simulator_cfg()),
            patch.object(retry_module, "auto", AutoStub()),
            patch.object(retry_module, "ensure_simulator_game_started", return_value=True),
            patch.object(retry_module, "check_times", return_value=False),
            patch.object(retry_module, "sleep", lambda *_: None),
            patch.object(retry_module, "should_wait_for_main_menu_after_simulator_start", return_value=True),
            patch(
                "tasks.base.back_init_menu.wait_until_main_menu_after_launch",
                return_value="timeout",
            ),
        ):
            result = retry_module.retry()

        self.assertIs(result, False)

    def test_retry_continues_runtime_recovery_when_start_probe_detects_runtime_ui(self):
        calls = []

        class AutoStub:
            def get_restore_time(self):
                return None

            def take_screenshot(self):
                calls.append("take_screenshot")
                return object()

            def find_element(self, target, *_, **__):
                calls.append(("find_element", target))
                return False

            def click_element(self, target, *_, **__):
                calls.append(("click_element", target))
                return False

        ensure_call_count = {"value": 0}

        def ensure_started_once():
            ensure_call_count["value"] += 1
            if ensure_call_count["value"] > 1:
                raise AssertionError("retry() should continue the current recovery round")
            return True

        with (
            patch.object(retry_module, "cfg", self._make_simulator_cfg()),
            patch.object(retry_module, "auto", AutoStub()),
            patch.object(retry_module, "ensure_simulator_game_started", side_effect=ensure_started_once),
            patch.object(retry_module, "check_times", return_value=False),
            patch.object(retry_module, "sleep", lambda *_: None),
            patch.object(retry_module, "should_wait_for_main_menu_after_simulator_start", return_value=False),
        ):
            result = retry_module.retry()

        self.assertIsNone(result)
        self.assertEqual(ensure_call_count["value"], 1)
        self.assertEqual(calls.count("take_screenshot"), 1)

    def test_back_init_menu_waits_for_main_menu_after_simulator_start_probe_detects_launch_chain(self):
        calls = []

        class AutoStub:
            model = "clam"

            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

        ensure_call_count = {"value": 0}

        def ensure_started_once():
            ensure_call_count["value"] += 1
            if ensure_call_count["value"] > 1:
                raise AssertionError("back_init_menu() should switch to launch wait instead of restarting the loop")
            return True

        with (
            patch.object(back_init_menu_module, "auto", AutoStub()),
            patch.object(retry_module, "cfg", self._make_simulator_cfg()),
            patch.object(retry_module, "sleep", lambda *_: None),
            patch.object(back_init_menu_module, "ensure_simulator_game_started", side_effect=ensure_started_once),
            patch.object(back_init_menu_module, "should_wait_for_main_menu_after_simulator_start", return_value=True),
            patch.object(back_init_menu_module, "retry", return_value=False),
            patch.object(
                back_init_menu_module,
                "wait_until_main_menu_after_launch",
                side_effect=lambda allow_restart=True: calls.append(("wait_main_menu", allow_restart)) or "main_menu",
            ),
        ):
            result = back_init_menu_module.back_init_menu(allow_restart=False)

        self.assertIs(result, True)
        self.assertIn(("wait_main_menu", False), calls)
        self.assertEqual(ensure_call_count["value"], 1)

    def test_back_init_menu_continues_runtime_recovery_when_start_probe_detects_runtime_ui(self):
        calls = []

        class AutoStub:
            model = "clam"

            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

        ensure_call_count = {"value": 0}

        def ensure_started_once():
            ensure_call_count["value"] += 1
            if ensure_call_count["value"] > 1:
                raise AssertionError("back_init_menu() should continue the current recovery round")
            return True

        with (
            patch.object(back_init_menu_module, "auto", AutoStub()),
            patch.object(retry_module, "cfg", self._make_simulator_cfg()),
            patch.object(retry_module, "sleep", lambda *_: None),
            patch.object(back_init_menu_module, "ensure_simulator_game_started", side_effect=ensure_started_once),
            patch.object(back_init_menu_module, "should_wait_for_main_menu_after_simulator_start", return_value=False),
            patch.object(back_init_menu_module, "retry", side_effect=lambda: calls.append(("retry",)) or False),
            patch.object(
                back_init_menu_module,
                "wait_until_main_menu_after_launch",
                side_effect=lambda allow_restart=True: calls.append(("wait_main_menu", allow_restart)) or "main_menu",
            ),
        ):
            back_init_menu_module.back_init_menu(allow_restart=False)

        self.assertNotIn(("wait_main_menu", False), calls)
        self.assertIn(("retry",), calls)
        self.assertEqual(ensure_call_count["value"], 1)

    def test_restart_game_waits_for_main_menu_after_init_game(self):
        calls = []

        def wait_for_main_menu(*, allow_restart=True):
            calls.append(("wait_main_menu", allow_restart))
            return "main_menu"

        with (
            patch("tasks.base.script_task_scheme.init_game", lambda: calls.append(("init_game",))),
            patch(
                "tasks.base.back_init_menu.wait_until_main_menu_after_launch",
                wait_for_main_menu,
            ),
            patch.object(retry_module, "sleep", lambda *_: None),
        ):
            result = retry_module.restart_game()

        self.assertIs(result, True)
        self.assertEqual(calls, [("init_game",), ("wait_main_menu", True)])

    def test_restart_game_returns_false_when_main_menu_wait_times_out(self):
        calls = []

        def wait_for_main_menu(*, allow_restart=True):
            calls.append(("wait_main_menu", allow_restart))
            return "timeout"

        with (
            patch("tasks.base.script_task_scheme.init_game", lambda: calls.append(("init_game",))),
            patch(
                "tasks.base.back_init_menu.wait_until_main_menu_after_launch",
                wait_for_main_menu,
            ),
            patch.object(retry_module, "sleep", lambda *_: None),
        ):
            result = retry_module.restart_game()

        self.assertIs(result, False)
        self.assertEqual(calls, [("init_game",), ("wait_main_menu", True)])

    def test_back_init_menu_returns_bool_false_when_retry_fails(self):
        class AutoStub:
            model = "clam"

            def ensure_not_stopped(self):
                return None

        with (
            patch.object(back_init_menu_module, "auto", AutoStub()),
            patch.object(back_init_menu_module, "ensure_simulator_game_started", return_value=False),
            patch.object(back_init_menu_module, "retry", return_value=False),
        ):
            result = back_init_menu_module.back_init_menu(allow_restart=False)

        self.assertIs(result, False)

    def test_production_work_policy_uses_back_init_menu(self):
        import tasks.tools.production_module as production_module

        calls = []
        work = type("WorkStub", (), {"production_running": True, "_last_back_init_restart_time": 0.0})()
        cfg_stub = type("CfgStub", (), {"simulator": False})()
        auto_stub = type("AutoStub", (), {"ensure_not_stopped": lambda self: calls.append(("ensure_not_stopped",))})()

        def back_init_menu_stub(*, allow_restart=True):
            calls.append(("back_init_menu", allow_restart))
            return True

        with (
            patch.object(production_module, "cfg", cfg_stub),
            patch.object(production_module, "auto", auto_stub),
            patch.object(production_module, "back_init_menu", back_init_menu_stub),
        ):
            result = production_module.ProductionWork._back_init_menu_with_tool_policy(work)

        self.assertIs(result, True)
        self.assertEqual(calls, [("ensure_not_stopped",), ("back_init_menu", False)])


if __name__ == "__main__":
    unittest.main()
