import importlib
import unittest
from unittest.mock import patch

import module.automation.automation as automation_module
import tasks.base.script_task_scheme as script_task_scheme

screen_module = importlib.import_module("module.game_and_screen.screen")


class TestMacOSSupport(unittest.TestCase):
    def test_automation_uses_noop_input_on_non_windows_without_simulator(self):
        cfg_stub = type(
            "CfgStub",
            (),
            {
                "simulator": False,
                "simulator_type": 0,
                "win_input_type": "background",
                "lab_mouse_logitech": False,
                "memory_protection": False,
            },
        )()

        automation = automation_module.Automation.__new__(automation_module.Automation)
        automation.input_handler = None

        with (
            patch.object(automation_module, "_is_windows", False),
            patch.object(automation_module, "cfg", cfg_stub),
        ):
            automation_module.Automation.init_input(automation)

        self.assertEqual(type(automation.input_handler).__name__, "NoOpInput")

    def test_screen_set_win_returns_immediately_on_non_windows(self):
        screen = screen_module.Screen.__new__(screen_module.Screen)

        class HandleStub:
            isMinimized = False
            isActive = True

            @staticmethod
            def restore():
                return None

            @staticmethod
            def setForeground():
                return None

            @staticmethod
            def width(client=True):
                return 0

            @staticmethod
            def height(client=True):
                return 0

        cfg_stub = type(
            "CfgStub",
            (),
            {
                "background_click": True,
                "set_win_size": 1080,
                "set_win_position": "free",
                "set_windows": True,
            },
        )()

        object.__setattr__(screen, "handle", HandleStub())
        screen.check_win_size = lambda *_args, **_kwargs: None
        screen.reduce_miscontact = lambda *_args, **_kwargs: None
        screen.adjust_win_size = lambda *_args, **_kwargs: None
        screen.adjust_win_position = lambda *_args, **_kwargs: None

        with (
            patch.object(screen_module, "_is_windows", False),
            patch.object(screen_module, "cfg", cfg_stub),
            patch.object(screen_module, "sleep", side_effect=RuntimeError("set_win loop did not exit")),
        ):
            screen_module.Screen.set_win(screen)

    def test_init_game_raises_on_non_windows_without_simulator(self):
        cfg_stub = type(
            "CfgStub",
            (),
            {
                "simulator": False,
                "simulator_type": 0,
                "set_windows": True,
            },
        )()

        class AutoStub:
            @staticmethod
            def ensure_not_stopped():
                return None

            @staticmethod
            def init_input():
                return None

        class GameProcessStub:
            @staticmethod
            def start_game():
                return None

        class ScreenStub:
            @staticmethod
            def init_handle(stop_checker=None):
                return True

            @staticmethod
            def set_win():
                return None

        with (
            patch.object(script_task_scheme, "cfg", cfg_stub),
            patch.object(script_task_scheme, "auto", AutoStub()),
            patch.object(script_task_scheme, "game_process", GameProcessStub()),
            patch.object(script_task_scheme, "screen", ScreenStub()),
            patch.object(script_task_scheme.platform, "system", return_value="Darwin"),
        ):
            with self.assertRaises(script_task_scheme.cannotOperateGameError):
                script_task_scheme.init_game()

    def test_init_game_rejects_mumu_simulator_on_non_windows(self):
        cfg_stub = type(
            "CfgStub",
            (),
            {
                "simulator": True,
                "simulator_type": 0,
                "set_windows": True,
            },
        )()

        class AutoStub:
            @staticmethod
            def ensure_not_stopped():
                return None

            @staticmethod
            def init_input():
                return None

        with (
            patch.object(script_task_scheme, "cfg", cfg_stub),
            patch.object(script_task_scheme, "auto", AutoStub()),
            patch.object(script_task_scheme.platform, "system", return_value="Darwin"),
        ):
            with self.assertRaises(script_task_scheme.cannotOperateGameError):
                script_task_scheme.init_game()


if __name__ == "__main__":
    unittest.main()
