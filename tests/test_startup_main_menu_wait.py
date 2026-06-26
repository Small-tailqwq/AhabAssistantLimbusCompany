import sys
import types
import unittest
from contextlib import suppress
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

import module.config.config_typing as config_typing_module
import tasks.base.back_init_menu as back_init_menu_module
from app.setting_interface import SettingInterface


class TimeSequence:
    def __init__(self, *values):
        self._values = iter(values)
        self._last = values[-1]

    def time(self):
        with suppress(StopIteration):
            self._last = next(self._values)
        return self._last


class TestStartupMainMenuWait(unittest.TestCase):
    def test_get_startup_wait_timeout_seconds_uses_simulator_value(self):
        cfg_stub = type(
            "CfgStub",
            (),
            {
                "simulator": True,
                "get_value": lambda self, key, default=None: {"startup_wait_timeout_simulator": 180}.get(key, default),
            },
        )()

        with patch.object(back_init_menu_module, "cfg", cfg_stub):
            self.assertEqual(back_init_menu_module.get_startup_wait_timeout_seconds(), 180)

    def test_get_startup_wait_timeout_seconds_uses_pc_value(self):
        cfg_stub = type(
            "CfgStub",
            (),
            {
                "simulator": False,
                "get_value": lambda self, key, default=None: {"startup_wait_timeout_pc": 120}.get(key, default),
            },
        )()

        with patch.object(back_init_menu_module, "cfg", cfg_stub):
            self.assertEqual(back_init_menu_module.get_startup_wait_timeout_seconds(), 120)

    def test_handle_launch_state_once_uses_safe_title_click_for_cache_prompt(self):
        calls = []

        class AutoStub:
            def find_element(self, target, *_, **__):
                return target == "base/clear_all_caches_assets.png"

            def click_element(self, target, *_, **__):
                calls.append(("click_element", target))
                return False

        with (
            patch.object(back_init_menu_module, "auto", AutoStub()),
            patch.object(back_init_menu_module, "click_title_screen_safely", lambda: calls.append(("safe_click",))),
        ):
            result = back_init_menu_module.handle_launch_state_once()

        self.assertTrue(result)
        self.assertIn(("safe_click",), calls)

    def test_wait_until_main_menu_after_launch_uses_deadline_not_loop_count(self):
        calls = []

        class AutoStub:
            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

            def take_screenshot(self):
                return object()

            def click_element(self, *args, **kwargs):
                return False

            def find_element(self, *args, **kwargs):
                return False

        with (
            patch.object(back_init_menu_module, "auto", AutoStub()),
            patch.object(back_init_menu_module, "ensure_simulator_game_started", return_value=False),
            patch.object(back_init_menu_module, "handle_launch_state_once", return_value=True),
            patch.object(back_init_menu_module, "get_startup_wait_timeout_seconds", return_value=3),
            patch.object(back_init_menu_module, "sleep", lambda *_: None),
            patch.object(back_init_menu_module, "time", TimeSequence(0.0, 0.0, 1.0, 2.0, 3.1)),
        ):
            result = back_init_menu_module.wait_until_main_menu_after_launch(allow_restart=False)

        self.assertEqual(result, "timeout")
        self.assertGreaterEqual(len(calls), 3)

    def test_wait_until_main_menu_after_launch_sets_clam_model_before_launch_checks(self):
        seen_models = []

        class AutoStub:
            def __init__(self):
                self.model = "aggressive"

            def ensure_not_stopped(self):
                return None

            def take_screenshot(self):
                return object()

            def click_element(self, target, *args, **kwargs):
                return target == "home/window_assets.png"

            def find_element(self, target, *args, **kwargs):
                return target == "home/mail_assets.png"

        auto_stub = AutoStub()

        def handle_launch_state_once_stub():
            seen_models.append(auto_stub.model)
            return None

        with (
            patch.object(back_init_menu_module, "auto", auto_stub),
            patch.object(back_init_menu_module, "ensure_simulator_game_started", return_value=False),
            patch.object(back_init_menu_module, "handle_launch_state_once", side_effect=handle_launch_state_once_stub),
            patch.object(back_init_menu_module, "_is_runtime_ui_visible", return_value=False),
            patch.object(back_init_menu_module, "get_startup_wait_timeout_seconds", return_value=3),
        ):
            result = back_init_menu_module.wait_until_main_menu_after_launch(allow_restart=False)

        self.assertTrue(result)
        self.assertEqual(seen_models, ["clam"])
        self.assertEqual(auto_stub.model, "clam")

    def test_wait_until_main_menu_after_launch_takes_screenshot_each_loop(self):
        calls = []
        screenshot_results = iter([None, object()])
        handle_calls = []

        class AutoStub:
            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

            def take_screenshot(self):
                calls.append(("take_screenshot",))
                return next(screenshot_results)

            def click_element(self, target, *args, **kwargs):
                calls.append(("click_element", target))
                return target == "home/window_assets.png"

            def find_element(self, target, *args, **kwargs):
                calls.append(("find_element", target))
                return target == "home/mail_assets.png"

        with (
            patch.object(back_init_menu_module, "auto", AutoStub()),
            patch.object(back_init_menu_module, "ensure_simulator_game_started", return_value=False),
            patch.object(
                back_init_menu_module,
                "handle_launch_state_once",
                side_effect=lambda: handle_calls.append("handle") or None,
            ),
            patch.object(back_init_menu_module, "_is_runtime_ui_visible", return_value=False),
            patch.object(back_init_menu_module, "get_startup_wait_timeout_seconds", return_value=1),
            patch.object(back_init_menu_module, "sleep", lambda *_: None),
            patch.object(back_init_menu_module, "time", TimeSequence(0.0, 0.0, 0.5, 1.0)),
        ):
            result = back_init_menu_module.wait_until_main_menu_after_launch(allow_restart=False)

        self.assertTrue(result)
        self.assertEqual(calls.count(("take_screenshot",)), 2)
        self.assertEqual(handle_calls, ["handle"])

    def test_wait_until_main_menu_after_launch_returns_runtime_ui_when_runtime_screen_restored(self):
        actions = []

        class AutoStub:
            def ensure_not_stopped(self):
                actions.append(("ensure_not_stopped",))

            def take_screenshot(self):
                actions.append(("take_screenshot",))
                return object()

            def click_element(self, *args, **kwargs):
                actions.append(("click_element",))
                return False

            def find_element(self, *args, **kwargs):
                actions.append(("find_element",))
                return False

        with (
            patch.object(back_init_menu_module, "auto", AutoStub()),
            patch.object(back_init_menu_module, "ensure_simulator_game_started", return_value=True),
            patch.object(back_init_menu_module, "should_wait_for_main_menu_after_simulator_start", return_value=False),
            patch.object(back_init_menu_module, "get_startup_wait_timeout_seconds", return_value=1),
            patch.object(back_init_menu_module, "sleep", lambda *_: actions.append(("sleep",))),
            patch.object(back_init_menu_module, "time", TimeSequence(0.0, 0.0, 0.5, 2.0)),
        ):
            result = back_init_menu_module.wait_until_main_menu_after_launch(allow_restart=False)

        self.assertEqual(result, "runtime_ui")
        self.assertEqual(actions, [("ensure_not_stopped",)])

    def test_wait_until_main_menu_after_launch_returns_runtime_ui_when_runtime_ui_visible(self):
        calls = []

        class AutoStub:
            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

            def take_screenshot(self):
                calls.append(("take_screenshot",))
                return object()

            def click_element(self, target, *args, **kwargs):
                calls.append(("click_element", target))
                return False

            def find_element(self, target, *args, **kwargs):
                calls.append(("find_element", target))
                return False

        with (
            patch.object(back_init_menu_module, "auto", AutoStub()),
            patch.object(back_init_menu_module, "ensure_simulator_game_started", return_value=False),
            patch.object(back_init_menu_module, "handle_launch_state_once", return_value=None),
            patch.object(back_init_menu_module, "_is_runtime_ui_visible", return_value=True),
            patch.object(back_init_menu_module, "get_startup_wait_timeout_seconds", return_value=1),
        ):
            result = back_init_menu_module.wait_until_main_menu_after_launch(allow_restart=False)

        self.assertEqual(result, "runtime_ui")
        self.assertNotIn(("click_element", "home/window_assets.png"), calls)

    def test_wait_until_main_menu_after_launch_presses_esc_when_frozen_unknown_screen(self):
        calls = []

        class FrozenScreenshot:
            def tobytes(self):
                return b"same-frame"

        class AutoStub:
            def __init__(self):
                self.screenshot = FrozenScreenshot()

            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

            def take_screenshot(self):
                calls.append(("take_screenshot",))
                return self.screenshot

            def click_element(self, target, *args, **kwargs):
                calls.append(("click_element", target))
                return False

            def find_element(self, target, *args, **kwargs):
                calls.append(("find_element", target))
                return False

            def key_press(self, key):
                calls.append(("key_press", key))

        with (
            patch.object(back_init_menu_module, "auto", AutoStub()),
            patch.object(back_init_menu_module, "ensure_simulator_game_started", return_value=False),
            patch.object(back_init_menu_module, "handle_launch_state_once", return_value=None),
            patch.object(back_init_menu_module, "_is_runtime_ui_visible", return_value=False),
            patch.object(back_init_menu_module, "get_startup_wait_timeout_seconds", return_value=1),
            patch.object(back_init_menu_module, "sleep", lambda *_: None),
            patch.object(back_init_menu_module, "time", TimeSequence(0.0, 0.0, 0.1, 0.2, 0.3, 1.1)),
        ):
            result = back_init_menu_module.wait_until_main_menu_after_launch(allow_restart=False)

        self.assertEqual(result, "timeout")
        self.assertIn(("key_press", "esc"), calls)

    def test_wait_until_main_menu_after_launch_logs_halfway_once_and_timeout(self):
        log_messages = []

        class AutoStub:
            def ensure_not_stopped(self):
                return None

            def take_screenshot(self):
                return object()

            def click_element(self, *args, **kwargs):
                return False

            def find_element(self, *args, **kwargs):
                return False

        class LogStub:
            def info(self, message):
                log_messages.append(("info", message))

            def error(self, message):
                log_messages.append(("error", message))

        with (
            patch.object(back_init_menu_module, "auto", AutoStub()),
            patch.object(back_init_menu_module, "log", LogStub()),
            patch.object(back_init_menu_module, "ensure_simulator_game_started", return_value=False),
            patch.object(back_init_menu_module, "handle_launch_state_once", return_value=True),
            patch.object(back_init_menu_module, "get_startup_wait_timeout_seconds", return_value=30),
            patch.object(back_init_menu_module, "sleep", lambda *_: None),
            patch.object(back_init_menu_module, "time", TimeSequence(0.0, 16.0, 20.0, 30.1)),
        ):
            result = back_init_menu_module.wait_until_main_menu_after_launch(allow_restart=False)

        self.assertEqual(result, "timeout")
        self.assertEqual(
            [message for level, message in log_messages if level == "info" and "仍在等待进入主界面" in message],
            [message for level, message in log_messages if level == "info" and "仍在等待进入主界面" in message][:1],
        )
        self.assertEqual(
            len([message for level, message in log_messages if level == "info" and "仍在等待进入主界面" in message]),
            1,
        )
        self.assertTrue(
            any(level == "error" and "启动等待主界面超时" in message for level, message in log_messages)
        )

    def test_wait_until_main_menu_after_launch_allow_restart_has_no_fixed_restart_limit(self):
        actions = []
        timeout_values = iter([0, 0, 0, 0, 5])
        script_task_scheme_stub = types.ModuleType("tasks.base.script_task_scheme")

        class AutoStub:
            def ensure_not_stopped(self):
                actions.append(("ensure_not_stopped",))

            def take_screenshot(self):
                actions.append(("take_screenshot",))
                return object()

            def click_element(self, target, *args, **kwargs):
                actions.append(("click_element", target))
                return target == "home/window_assets.png"

            def find_element(self, target, *args, **kwargs):
                actions.append(("find_element", target))
                return target == "home/mail_assets.png"

        script_task_scheme_stub.init_game = lambda: actions.append(("init_game",))

        with (
            patch.object(back_init_menu_module, "auto", AutoStub()),
            patch.object(back_init_menu_module, "ensure_simulator_game_started", return_value=False),
            patch.object(back_init_menu_module, "handle_launch_state_once", return_value=None),
            patch.object(back_init_menu_module, "_is_runtime_ui_visible", return_value=False),
            patch.object(
                back_init_menu_module,
                "get_startup_wait_timeout_seconds",
                side_effect=lambda: next(timeout_values),
            ),
            patch.object(back_init_menu_module, "sleep", lambda *_: None),
            patch.object(
                back_init_menu_module,
                "time",
                TimeSequence(0.0, 0.1, 1.0, 1.1, 2.0, 2.1, 3.0, 3.1, 4.0, 4.0),
            ),
            patch("tasks.base.retry.kill_game", side_effect=lambda: actions.append(("kill_game",))),
            patch("tasks.base.retry.restart_game", side_effect=lambda: actions.append(("restart_game",))),
            patch.dict(sys.modules, {"tasks.base.script_task_scheme": script_task_scheme_stub}),
        ):
            result = back_init_menu_module.wait_until_main_menu_after_launch(allow_restart=True)

        self.assertEqual(result, "main_menu")
        self.assertEqual(actions.count(("kill_game",)), 4)
        self.assertEqual(actions.count(("init_game",)), 4)
        self.assertNotIn(("restart_game",), actions)
        self.assertLess(actions.index(("kill_game",)), actions.index(("init_game",)))


class TestStartupMainMenuWaitTask4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_config_model_exposes_startup_wait_timeouts(self):
        model = config_typing_module.ConfigModel()

        self.assertEqual(model.startup_wait_timeout_pc, 120)
        self.assertEqual(model.startup_wait_timeout_simulator, 180)

    def test_config_example_contains_startup_wait_timeouts(self):
        config_example = (
            Path(__file__).resolve().parents[1] / "assets" / "config" / "config.example.yaml"
        )
        content = config_example.read_text(encoding="utf-8")

        self.assertIn("startup_wait_timeout_simulator: 180", content)
        self.assertIn("startup_wait_timeout_pc: 120", content)

    def test_setting_interface_adds_startup_wait_timeout_cards_to_expected_groups(self):
        interface = SettingInterface()

        try:
            self.assertIn(
                interface.startup_wait_timeout_simulator_card,
                interface.simulator_setting_group.cardLayout._ExpandLayout__widgets,
            )
            self.assertIn(
                interface.startup_wait_timeout_pc_card,
                interface.game_path_group.cardLayout._ExpandLayout__widgets,
            )
        finally:
            interface.close()
            self.app.processEvents()

    def test_setting_interface_retranslateUi_updates_startup_wait_timeout_cards(self):
        interface = SettingInterface()

        try:
            with (
                patch.object(
                    interface.startup_wait_timeout_simulator_card,
                    "retranslateUi",
                ) as simulator_retranslate,
                patch.object(
                    interface.startup_wait_timeout_pc_card,
                    "retranslateUi",
                ) as pc_retranslate,
            ):
                interface.retranslateUi()

            simulator_retranslate.assert_called_once_with()
            pc_retranslate.assert_called_once_with()
        finally:
            interface.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
