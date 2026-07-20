import os
import unittest
from unittest.mock import patch

import module.automation.input_handlers.simulator.mumu_control as mumu_control_module
from module.my_error.my_error import userStopError


class TestMumuIpcInputRetry(unittest.TestCase):
    def _make_start_control(self):
        control = mumu_control_module.MumuControl.__new__(mumu_control_module.MumuControl)
        control.exe_path = "MuMuManager.exe"
        control.install_path = "C:\\MuMu"
        control.multi_instance_number = 0
        control.connect_id = 0
        control.stop_checker = lambda: None
        return control

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

    def test_check_game_alive_initializes_adb_device_before_querying_package(self):
        control = mumu_control_module.MumuControl.__new__(mumu_control_module.MumuControl)
        control.device = None
        control.game_package_name = "com.ProjectMoon.LimbusCompany"
        control.stop_checker = lambda: None
        control.get_mumu_adb_port = lambda: "127.0.0.1:16384"

        class DeviceStub:
            def app_current(self):
                return type("CurrentApp", (), {"package": "com.ProjectMoon.LimbusCompany"})()

        with patch.object(mumu_control_module.adb, "device", return_value=DeviceStub()) as adb_device:
            self.assertTrue(control.check_game_alive())

        adb_device.assert_called_once_with("127.0.0.1:16384")

    def test_capture_nemu_ipc_uses_debug_for_startup_retry_output(self):
        messages = []

        class LoggerStub:
            def debug(self, message):
                messages.append(("debug", message))

            def error(self, message):
                messages.append(("error", message))

        capture = mumu_control_module.CaptureNemuIpc(LoggerStub(), log_level="debug")
        capture.stderr = b"nemu_connect instance_name: pending"
        capture.check_stderr()

        self.assertEqual(messages, [("debug", "NemuIpc stderr: b'nemu_connect instance_name: pending'")])

    def test_connect_forwards_startup_log_level_to_nemu_ipc(self):
        control = self._make_start_control()
        control.lib = type("LibStub", (), {"nemu_connect": object()})()

        with patch.object(control, "ev_run_sync", return_value=1) as ev_run_sync:
            control.connect(log_level="debug")

        self.assertEqual(ev_run_sync.call_args.kwargs, {"log_level": "debug"})

    def test_get_launch_status_records_container_android_version(self):
        control = self._make_start_control()
        control.android_version = None
        proc = type(
            "ProcStub",
            (),
            {"stdout": '{"android_version": "15.0", "is_process_started": true}'},
        )()

        with patch.object(mumu_control_module.subprocess, "run", return_value=proc):
            self.assertEqual(control.get_launch_status(), "start_finished")

        self.assertEqual(control.android_version, "15.0")

    def test_load_dll_prefers_current_container_android_version(self):
        for android_version in ("12.0", "15.0"):
            with self.subTest(android_version=android_version):
                control = self._make_start_control()
                control.install_path = os.path.join("C:\\MuMu", "nx_main")
                control.android_version = android_version
                control.mumu_version = 6
                expected = os.path.abspath(
                    os.path.join(
                        "C:\\MuMu",
                        "nx_device",
                        android_version,
                        "shell",
                        "sdk",
                        "external_renderer_ipc.dll",
                    )
                )

                with (
                    patch.object(mumu_control_module.os.path, "exists", return_value=True),
                    patch.object(mumu_control_module.os.path, "isdir", return_value=False),
                    patch.object(mumu_control_module.ctypes, "CDLL", return_value=object()) as load_dll,
                ):
                    control.load_dll()

                load_dll.assert_called_once_with(expected)

    def test_load_dll_keeps_legacy_fallback_without_android_version(self):
        control = self._make_start_control()
        control.install_path = os.path.join("C:\\MuMu", "nx_main")
        control.mumu_version = 6
        expected = os.path.abspath(
            os.path.join(
                "C:\\MuMu",
                "nx_device",
                "12.0",
                "shell",
                "sdk",
                "external_renderer_ipc.dll",
            )
        )

        with (
            patch.object(mumu_control_module.os.path, "exists", side_effect=lambda path: path == expected),
            patch.object(mumu_control_module.os.path, "isdir", return_value=False),
            patch.object(mumu_control_module.ctypes, "CDLL", return_value=object()) as load_dll,
        ):
            control.load_dll()

        load_dll.assert_called_once_with(expected)

    def test_start_retries_ipc_until_configured_timeout(self):
        control = self._make_start_control()
        clock = {"value": 0.0}

        def monotonic():
            return clock["value"]

        def sleep(seconds):
            clock["value"] += seconds

        connection_error = mumu_control_module.NemuIpcError("IPC 尚未就绪")
        connect_results = [connection_error] * 3 + [None]
        cfg_stub = type("CfgStub", (), {"start_emulator_timeout": 30})()

        with (
            patch.object(mumu_control_module, "cfg", cfg_stub),
            patch.object(mumu_control_module, "run_as_user") as launch,
            patch.object(control, "get_app_keptlive", return_value=False),
            patch.object(control, "load_dll") as load_dll,
            patch.object(control, "get_mumu_adb_port", return_value="127.0.0.1:16384"),
            patch.object(control, "get_launch_status", return_value="start_finished"),
            patch.object(control, "connect", side_effect=connect_results) as connect,
            patch.object(mumu_control_module.time, "monotonic", side_effect=monotonic),
            patch.object(mumu_control_module.time, "sleep", side_effect=sleep),
        ):
            control.start()

        launch.assert_called_once_with(["MuMuManager.exe", "control", "-v", "0", "launch"])
        load_dll.assert_called_once_with()
        self.assertEqual(connect.call_count, 4)
        self.assertTrue(all(call.kwargs == {"log_level": "debug"} for call in connect.call_args_list))

    def test_start_reports_timeout_after_ipc_deadline(self):
        control = self._make_start_control()
        clock = {"value": 0.0}

        def monotonic():
            return clock["value"]

        def sleep(seconds):
            clock["value"] += seconds

        connection_error = mumu_control_module.NemuIpcError("IPC 尚未就绪")
        cfg_stub = type("CfgStub", (), {"start_emulator_timeout": 3})()

        with (
            patch.object(mumu_control_module, "cfg", cfg_stub),
            patch.object(mumu_control_module, "run_as_user") as launch,
            patch.object(control, "get_app_keptlive", return_value=False),
            patch.object(control, "load_dll"),
            patch.object(control, "get_mumu_adb_port", return_value="127.0.0.1:16384"),
            patch.object(control, "get_launch_status", return_value="start_finished"),
            patch.object(control, "connect", side_effect=connection_error) as connect,
            patch.object(mumu_control_module.time, "monotonic", side_effect=monotonic),
            patch.object(mumu_control_module.time, "sleep", side_effect=sleep),
            self.assertRaisesRegex(RuntimeError, "启动超时（3秒），等待 Nemu IPC 就绪") as raised,
        ):
            control.start()

        launch.assert_called_once()
        self.assertEqual(connect.call_count, 3)
        self.assertIs(raised.exception.__cause__, connection_error)


if __name__ == "__main__":
    unittest.main()
