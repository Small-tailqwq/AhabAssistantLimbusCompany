import unittest
from unittest.mock import patch

import module.automation.automation as automation_module
import module.automation.input_handlers.simulator.mumu_control as mumu_control_module
import tasks.base.script_task_scheme as script_task_scheme
from module.my_error.my_error import EmulatorCrashedError, userStopError


class TestEmulatorFailureLifecycle(unittest.TestCase):
    @staticmethod
    def _make_mumu_control():
        control = mumu_control_module.MumuControl.__new__(mumu_control_module.MumuControl)
        control.exe_path = "MuMuManager.exe"
        control.install_path = "C:\\MuMu"
        control.multi_instance_number = 0
        control.connect_id = 0
        control.stop_checker = lambda: None
        return control

    def test_start_times_out_when_launch_never_reaches_finished_state(self):
        control = self._make_mumu_control()
        clock = {"value": 0.0}

        def monotonic():
            return clock["value"]

        def sleep(seconds):
            clock["value"] += seconds

        cfg_stub = type("CfgStub", (), {"start_emulator_timeout": 3})()

        with (
            patch.object(mumu_control_module, "cfg", cfg_stub),
            patch.object(mumu_control_module, "run_as_user"),
            patch.object(control, "get_app_keptlive", return_value=False),
            patch.object(control, "load_dll"),
            patch.object(control, "get_mumu_adb_port", return_value="127.0.0.1:16384"),
            patch.object(control, "get_launch_status", return_value="launching") as launch_status,
            patch.object(control, "connect") as connect,
            patch.object(mumu_control_module.time, "monotonic", side_effect=monotonic),
            patch.object(mumu_control_module.time, "sleep", side_effect=sleep),
            self.assertRaisesRegex(RuntimeError, "启动超时（3秒），未检测到启动完成状态"),
        ):
            control.start()

        self.assertEqual(launch_status.call_count, 3)
        connect.assert_not_called()

    def test_stop_has_bounded_retries_when_shutdown_keeps_failing(self):
        control = self._make_mumu_control()

        with (
            patch.object(mumu_control_module.subprocess, "run", side_effect=OSError("boom")) as run,
            patch.object(control, "mumu_control_api_backend") as fallback,
            patch.object(mumu_control_module.time, "sleep") as sleep,
            patch.object(mumu_control_module.log, "warning") as warning,
        ):
            control.stop()

        self.assertEqual(run.call_count, 3)
        self.assertEqual(fallback.call_count, 2)
        self.assertEqual(sleep.call_count, 2)
        warning.assert_called_once()

    def test_screenshot_crash_becomes_cooperative_stop(self):
        automation = automation_module.Automation.__new__(automation_module.Automation)
        automation.last_screenshot_time = 0
        automation.last_click_time = 0
        automation._stop_requested = False
        automation._stop_reason = "用户主动终止程序"
        cfg_stub = type("CfgStub", (), {"screenshot_interval": 0})()
        crash = EmulatorCrashedError("模拟器进程已退出")

        with (
            patch.object(automation_module, "cfg", cfg_stub),
            patch.object(automation_module.ScreenShot, "take_screenshot", side_effect=crash),
            patch.object(automation_module.time, "sleep"),
            patch.object(automation_module.log, "error") as error,
            self.assertRaises(userStopError) as raised,
        ):
            automation.take_screenshot()

        self.assertEqual(str(raised.exception), "模拟器进程已退出")
        self.assertTrue(automation._stop_requested)
        error.assert_called_once_with("模拟器已崩溃：模拟器进程已退出")

    def test_script_thread_records_emulator_crash_and_always_cleans_up(self):
        calls = []
        task = script_task_scheme.my_script_task()
        crash = EmulatorCrashedError("模拟器进程已退出")
        task._run = lambda: (_ for _ in ()).throw(crash)
        auto_stub = type(
            "AutoStub",
            (),
            {"clear_stop_request": lambda self: calls.append("clear_stop")},
        )()
        mediator_stub = type(
            "MediatorStub",
            (),
            {
                "script_finished": type(
                    "SignalStub",
                    (),
                    {"emit": lambda self: calls.append("finished")},
                )()
            },
        )()

        with (
            patch.object(script_task_scheme, "auto", auto_stub),
            patch.object(script_task_scheme, "mediator", mediator_stub),
            patch.object(
                script_task_scheme,
                "disconnect_obs_capture",
                side_effect=lambda: calls.append("disconnect_obs"),
            ),
        ):
            task.run()

        self.assertIs(task.exception, crash)
        self.assertEqual(task.exc_traceback, "")
        self.assertEqual(calls, ["clear_stop", "disconnect_obs", "finished"])


if __name__ == "__main__":
    unittest.main()
