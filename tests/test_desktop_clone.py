from __future__ import annotations

import _winapi
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import win32file
import win32pipe
from PySide6.QtCore import Qt
from ruamel.yaml import YAML

from module.desktop_clone.client import DesktopCloneClient
from module.desktop_clone.controller import DesktopCloneController, DesktopCloneState
from module.desktop_clone.host_build import compile_desktop_clone_host
from module.desktop_clone.ipc import (
    PipeConnection,
    PipeServer,
    begin_pipe_write,
    build_pipe_name,
    connect_pipe,
    pipe_path,
    read_pipe,
    write_pipe,
)
from module.desktop_clone.launcher import _application_launch_command
from module.desktop_clone.messages import translate_remote_message
from module.desktop_clone.native import (
    build_remote_control_warning,
    check_compatibility,
    child_sessions_enabled_during_current_logon,
    find_running_remote_control_conflicts,
    find_running_remote_control_services,
    mark_child_sessions_enabled_for_current_logon,
)
from module.desktop_clone.profile import prepare_child_profile
from module.desktop_clone.protocol import (
    decode_text,
    encode_text,
    parse_message,
    serialize_message,
)
from module.desktop_clone.state_sync import apply_child_state_delta
from module.game_and_screen.steam import (
    SteamProcessInfo,
    SteamSessionConflictError,
    ensure_steam_available_in_session,
)
from module.instance_context import CHILD_SESSION_ROLE, parse_instance_context


class InstanceContextTests(unittest.TestCase):
    @patch("module.instance_context.get_process_session_id", return_value=17)
    def test_child_session_arguments_are_parsed(self, _session_id):
        context = parse_instance_context(
            [
                "main.py",
                "--aalc-instance",
                CHILD_SESSION_ROLE,
                "--expected-session-id",
                "17",
                "--desktop-clone-pipe",
                "test-pipe",
                "--desktop-clone-profile",
                "C:/temp/aalc-child",
            ]
        )

        context.validate()
        self.assertTrue(context.is_child_session)
        self.assertEqual(context.expected_session_id, 17)
        self.assertEqual(context.pipe_name, "test-pipe")

    @patch("module.instance_context.get_process_session_id", return_value=18)
    def test_child_session_rejects_wrong_actual_session(self, _session_id):
        context = parse_instance_context(
            [
                "main.py",
                "--aalc-instance",
                CHILD_SESSION_ROLE,
                "--expected-session-id",
                "17",
                "--desktop-clone-pipe",
                "test-pipe",
                "--desktop-clone-profile",
                "C:/temp/aalc-child",
            ]
        )

        with self.assertRaises(RuntimeError):
            context.validate()


class ProtocolTests(unittest.TestCase):
    def test_protocol_round_trip(self):
        payload = serialize_message(("hello", "child-session", "1"))
        self.assertEqual(
            parse_message(payload),
            ["hello", "child-session", "1"],
        )

    def test_protocol_rejects_embedded_newline(self):
        with self.assertRaises(ValueError):
            serialize_message(("error", "bad\nmessage"))

    def test_remote_error_translates_nested_known_detail(self):
        translations = {
            "读取 RDP Child Session 状态失败：{0}": "Read failed: {0}",
            "RDP 已连接，但 Windows 未返回 Child Session ID。": "No Child Session ID.",
        }

        with patch(
            "module.desktop_clone.messages.translate_message",
            side_effect=lambda source, *args: translations[source].format(*args),
        ):
            translated = translate_remote_message(
                "读取 RDP Child Session 状态失败："
                "RDP 已连接，但 Windows 未返回 Child Session ID。"
            )

        self.assertEqual(translated, "Read failed: No Child Session ID.")

    def test_remote_rdp_authentication_detail_is_translated(self):
        source = "RDP 登录凭据无效；Child Session 未完成免凭据登录。"
        with patch(
            "module.desktop_clone.messages.translate_message",
            return_value="RDP credentials were rejected.",
        ) as translate:
            translated = translate_remote_message(source)

        self.assertEqual(translated, "RDP credentials were rejected.")
        translate.assert_called_once_with(source)


class NamedPipeTests(unittest.TestCase):
    def test_connect_pipe_wait_can_be_cancelled(self):
        cancelled = threading.Event()
        errors = []
        pipe_name = f"{build_pipe_name()}.missing-{uuid.uuid4().hex}"

        def connect():
            try:
                connect_pipe(
                    pipe_name,
                    timeout_ms=5000,
                    cancelled=cancelled.is_set,
                )
            except Exception as exc:
                errors.append(exc)

        worker = threading.Thread(target=connect)
        worker.start()
        time.sleep(0.1)
        cancelled.set()
        worker.join(1)

        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], InterruptedError)

    def test_server_observes_real_client_process_and_session(self):
        received = []
        ready = threading.Event()
        pipe_name = f"{build_pipe_name()}.test-{uuid.uuid4().hex}"
        server = PipeServer(
            pipe_name,
            lambda connection, message: (
                received.append((connection.peer_process_id, connection.peer_session_id, message)),
                ready.set(),
            ),
            lambda _connection: None,
        )
        server.start()
        handle = connect_pipe(pipe_name)
        try:
            write_pipe(handle, serialize_message(("hello", "test", "1")))
            self.assertTrue(ready.wait(3))
        finally:
            win32file.CloseHandle(handle)
            server.stop()

        self.assertEqual(received[0][2], ["hello", "test", "1"])
        self.assertGreater(received[0][0], 0)
        self.assertGreaterEqual(received[0][1], 0)

    def test_duplex_pipe_can_send_while_both_sides_are_waiting_for_input(self):
        server_connection = []
        server_received = threading.Event()
        client_received = []
        pipe_name = f"{build_pipe_name()}.test-{uuid.uuid4().hex}"

        def on_message(connection, message):
            server_connection.append(connection)
            server_received.set()

        server = PipeServer(pipe_name, on_message, lambda _connection: None)
        server.start()
        handle = connect_pipe(pipe_name)
        reader_started = threading.Event()

        def read_server_command():
            reader_started.set()
            client_received.append(parse_message(read_pipe(handle)))

        reader = threading.Thread(target=read_server_command, daemon=True)
        reader.start()
        self.assertTrue(reader_started.wait(1))
        time.sleep(0.1)
        try:
            write_pipe(handle, serialize_message(("hello", "test", "1")))
            self.assertTrue(server_received.wait(3))
            time.sleep(0.1)
            server_connection[0].send("stop")
            reader.join(3)
        finally:
            win32file.CloseHandle(handle)
            server.stop()

        self.assertFalse(reader.is_alive())
        self.assertEqual(client_received, [["stop"]])

    def test_connection_write_timeout_cancels_pending_operation(self):
        pipe_name = f"{build_pipe_name()}.test-{uuid.uuid4().hex}"
        server_handle = win32pipe.CreateNamedPipe(
            pipe_path(pipe_name),
            win32pipe.PIPE_ACCESS_DUPLEX | win32file.FILE_FLAG_OVERLAPPED,
            win32pipe.PIPE_TYPE_BYTE
            | win32pipe.PIPE_READMODE_BYTE
            | win32pipe.PIPE_WAIT,
            1,
            4096,
            4096,
            5000,
            None,
        )
        accept = _winapi.ConnectNamedPipe(
            int(server_handle),
            overlapped=True,
        )
        client_handle = connect_pipe(pipe_name)
        accept.GetOverlappedResult(True)
        connection = PipeConnection(server_handle)

        started = time.monotonic()
        try:
            with self.assertRaises(TimeoutError):
                connection.send_with_timeout(0.05, "x" * 60_000)
        finally:
            connection.close()
            win32file.CloseHandle(client_handle)

        self.assertLess(time.monotonic() - started, 0.5)

    def test_server_stop_cannot_miss_accept_created_after_wakeup(self):
        pipe_name = f"{build_pipe_name()}.test-{uuid.uuid4().hex}"
        create_entered = threading.Event()
        allow_create = threading.Event()
        real_create_named_pipe = win32pipe.CreateNamedPipe

        def delayed_create(*args, **kwargs):
            create_entered.set()
            allow_create.wait(3)
            return real_create_named_pipe(*args, **kwargs)

        server = PipeServer(pipe_name, lambda *_args: None, lambda _connection: None)
        with patch(
            "module.desktop_clone.ipc.win32pipe.CreateNamedPipe",
            side_effect=delayed_create,
        ):
            server.start()
            self.assertTrue(create_entered.wait(1))
            server.stop()
            allow_create.set()
            server._accept_thread.join(3)

        self.assertFalse(server._accept_thread.is_alive())

    @patch("module.desktop_clone.ipc.get_process_session_id", return_value=1)
    @patch("module.desktop_clone.ipc._named_pipe_client_pid", return_value=123)
    def test_connection_close_is_atomic(self, _client_pid, _session_id):
        connection = PipeConnection(456)
        disconnect_entered = threading.Event()
        allow_disconnect = threading.Event()

        def delayed_disconnect(_handle):
            disconnect_entered.set()
            allow_disconnect.wait(3)

        with (
            patch(
                "module.desktop_clone.ipc.win32pipe.DisconnectNamedPipe",
                side_effect=delayed_disconnect,
            ) as disconnect,
            patch("module.desktop_clone.ipc.win32file.CloseHandle") as close_handle,
        ):
            first = threading.Thread(target=connection.close)
            second = threading.Thread(target=connection.close)
            first.start()
            self.assertTrue(disconnect_entered.wait(1))
            second.start()
            allow_disconnect.set()
            first.join(3)
            second.join(3)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        disconnect.assert_called_once_with(456)
        close_handle.assert_called_once_with(456)

    @patch("module.desktop_clone.client.get_instance_context")
    def test_child_stop_does_not_wait_for_blocked_write(self, instance_context):
        instance_context.return_value = SimpleNamespace(
            is_child_session=True,
            pipe_name="test-pipe",
            current_session_id=1,
        )
        client = DesktopCloneClient()
        client._handle = 789
        write_entered = threading.Event()
        allow_write = threading.Event()
        stop_completed = threading.Event()

        def delayed_write(_handle, _payload):
            write_entered.set()
            allow_write.wait(3)

        with (
            patch(
                "module.desktop_clone.client.begin_pipe_write",
                return_value=object(),
            ),
            patch(
                "module.desktop_clone.client.finish_pipe_write",
                side_effect=delayed_write,
            ),
            patch("module.desktop_clone.client.win32file.CloseHandle") as close_handle,
        ):
            writer = threading.Thread(target=lambda: client._send("test"))
            stopper = threading.Thread(
                target=lambda: (client.stop_client(), stop_completed.set())
            )
            writer.start()
            self.assertTrue(write_entered.wait(1))
            stopper.start()
            completed_without_write = stop_completed.wait(0.5)
            allow_write.set()
            writer.join(3)
            stopper.join(3)

        self.assertTrue(completed_without_write)
        self.assertFalse(writer.is_alive())
        self.assertFalse(stopper.is_alive())
        close_handle.assert_called_once_with(789)

    @patch("module.desktop_clone.client.get_instance_context")
    def test_child_stop_serializes_cancel_with_io_start(self, instance_context):
        instance_context.return_value = SimpleNamespace(
            is_child_session=True,
            pipe_name="test-pipe",
            current_session_id=1,
        )
        pipe_name = f"{build_pipe_name()}.test-{uuid.uuid4().hex}"
        server_handle = win32pipe.CreateNamedPipe(
            pipe_path(pipe_name),
            win32pipe.PIPE_ACCESS_DUPLEX | win32file.FILE_FLAG_OVERLAPPED,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
            1,
            4096,
            4096,
            5000,
            None,
        )
        accept = _winapi.ConnectNamedPipe(int(server_handle), overlapped=True)
        client_handle = connect_pipe(pipe_name)
        accept.GetOverlappedResult(True)
        client = DesktopCloneClient()
        client._handle = client_handle
        begin_entered = threading.Event()
        allow_begin = threading.Event()
        write_finished = threading.Event()
        stop_finished = threading.Event()

        def delayed_begin(handle, payload):
            begin_entered.set()
            allow_begin.wait(3)
            return begin_pipe_write(handle, payload)

        def write_large_message():
            try:
                client._send("x" * 60_000)
            except OSError:
                pass
            finally:
                write_finished.set()

        def stop_client():
            client.stop_client()
            stop_finished.set()

        with patch(
            "module.desktop_clone.client.begin_pipe_write",
            side_effect=delayed_begin,
        ):
            writer = threading.Thread(target=write_large_message)
            stopper = threading.Thread(target=stop_client)
            writer.start()
            self.assertTrue(begin_entered.wait(1))
            stopper.start()
            time.sleep(0.1)
            stop_ran_before_io_start = stop_finished.is_set()
            allow_begin.set()
            cancelled_before_peer_close = write_finished.wait(2)
            stopped_before_peer_close = stop_finished.wait(2)

        try:
            writer.join(3)
            stopper.join(3)
        finally:
            win32file.CloseHandle(server_handle)

        self.assertFalse(stop_ran_before_io_start)
        self.assertTrue(cancelled_before_peer_close)
        self.assertTrue(stopped_before_peer_close)
        self.assertFalse(writer.is_alive())
        self.assertFalse(stopper.is_alive())

    @patch("module.desktop_clone.client.get_instance_context")
    def test_child_stop_cancels_pending_overlapped_write(self, instance_context):
        instance_context.return_value = SimpleNamespace(
            is_child_session=True,
            pipe_name="test-pipe",
            current_session_id=1,
        )
        pipe_name = f"{build_pipe_name()}.test-{uuid.uuid4().hex}"
        server_handle = win32pipe.CreateNamedPipe(
            pipe_path(pipe_name),
            win32pipe.PIPE_ACCESS_DUPLEX | win32file.FILE_FLAG_OVERLAPPED,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
            1,
            4096,
            4096,
            5000,
            None,
        )
        accept = _winapi.ConnectNamedPipe(int(server_handle), overlapped=True)
        client_handle = connect_pipe(pipe_name)
        accept.GetOverlappedResult(True)
        client = DesktopCloneClient()
        client._handle = client_handle
        write_started = threading.Event()
        write_finished = threading.Event()

        def write_large_message():
            write_started.set()
            try:
                client._send("x" * 60_000)
            except OSError:
                pass
            finally:
                write_finished.set()

        writer = threading.Thread(target=write_large_message)
        writer.start()
        self.assertTrue(write_started.wait(1))
        time.sleep(0.1)
        self.assertTrue(writer.is_alive())
        try:
            client.stop_client()
            cancelled_before_peer_close = write_finished.wait(2)
        finally:
            win32file.CloseHandle(server_handle)
            writer.join(3)

        self.assertTrue(cancelled_before_peer_close)
        self.assertFalse(writer.is_alive())

    @patch("module.desktop_clone.client.get_instance_context")
    def test_child_stop_cancels_pending_overlapped_read(self, instance_context):
        instance_context.return_value = SimpleNamespace(
            is_child_session=True,
            pipe_name="test-pipe",
            current_session_id=1,
        )
        pipe_name = f"{build_pipe_name()}.test-{uuid.uuid4().hex}"
        server_handle = win32pipe.CreateNamedPipe(
            pipe_path(pipe_name),
            win32pipe.PIPE_ACCESS_DUPLEX | win32file.FILE_FLAG_OVERLAPPED,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
            1,
            4096,
            4096,
            5000,
            None,
        )
        accept = _winapi.ConnectNamedPipe(int(server_handle), overlapped=True)
        client_handle = connect_pipe(pipe_name)
        accept.GetOverlappedResult(True)
        client = DesktopCloneClient()
        client._handle = client_handle
        read_started = threading.Event()
        read_finished = threading.Event()

        def wait_for_message():
            read_started.set()
            try:
                read_pipe(client_handle)
            except OSError:
                pass
            finally:
                read_finished.set()

        reader = threading.Thread(target=wait_for_message)
        reader.start()
        self.assertTrue(read_started.wait(1))
        time.sleep(0.1)
        self.assertTrue(reader.is_alive())
        try:
            client.stop_client()
            cancelled_before_peer_close = read_finished.wait(2)
        finally:
            win32file.CloseHandle(server_handle)
            reader.join(3)

        self.assertTrue(cancelled_before_peer_close)
        self.assertFalse(reader.is_alive())

    @patch("module.desktop_clone.ipc.get_process_session_id", return_value=1)
    @patch("module.desktop_clone.ipc._named_pipe_client_pid", return_value=123)
    def test_connection_close_serializes_with_io_start(
        self,
        _client_pid,
        _session_id,
    ):
        connection = PipeConnection(456)
        begin_entered = threading.Event()
        allow_begin = threading.Event()
        close_finished = threading.Event()

        def delayed_begin(_handle, _payload):
            begin_entered.set()
            allow_begin.wait(3)
            return object()

        def close_connection():
            connection.close()
            close_finished.set()

        with (
            patch(
                "module.desktop_clone.ipc.begin_pipe_write",
                side_effect=delayed_begin,
            ),
            patch("module.desktop_clone.ipc.finish_pipe_write"),
            patch("module.desktop_clone.ipc.cancel_pipe_io"),
            patch("module.desktop_clone.ipc.win32pipe.DisconnectNamedPipe"),
            patch("module.desktop_clone.ipc.win32file.CloseHandle"),
        ):
            sender = threading.Thread(target=lambda: connection.send("test"))
            closer = threading.Thread(target=close_connection)
            sender.start()
            self.assertTrue(begin_entered.wait(1))
            closer.start()
            time.sleep(0.1)
            close_ran_before_io_start = close_finished.is_set()
            allow_begin.set()
            sender.join(3)
            closer.join(3)

        self.assertFalse(close_ran_before_io_start)
        self.assertFalse(sender.is_alive())
        self.assertFalse(closer.is_alive())


class ChildLogForwardingTests(unittest.TestCase):
    @patch("module.desktop_clone.client.get_instance_context")
    def test_child_logs_are_forwarded_without_blocking_the_ui_dispatcher(
        self,
        instance_context,
    ):
        instance_context.return_value = SimpleNamespace(
            is_child_session=True,
            pipe_name="test-pipe",
            current_session_id=1,
        )
        client = DesktopCloneClient()
        dispatcher = SimpleNamespace(new_lines=MagicMock())
        forwarded = []
        forwarded_event = threading.Event()

        def capture(*parts):
            forwarded.append(parts)
            forwarded_event.set()

        with patch.object(client, "_send", side_effect=capture):
            client.install_log_forwarding(dispatcher)
            client._connected_event.set()
            client._enqueue_log_lines(["12:34:56 - test child log"])
            self.assertTrue(forwarded_event.wait(2))
            client.stop_client()

        dispatcher.new_lines.connect.assert_called_once_with(
            client._enqueue_log_lines,
            Qt.ConnectionType.DirectConnection,
        )
        dispatcher.new_lines.disconnect.assert_called_once()
        self.assertEqual(forwarded[0][0], "log")
        self.assertEqual(
            decode_text(forwarded[0][1]),
            "12:34:56 - test child log",
        )

    @patch("module.desktop_clone.client.get_instance_context")
    def test_child_log_queue_keeps_a_bounded_recent_window(
        self,
        instance_context,
    ):
        instance_context.return_value = SimpleNamespace(
            is_child_session=True,
            pipe_name="test-pipe",
            current_session_id=1,
        )
        client = DesktopCloneClient()

        client._enqueue_log_lines([str(index) for index in range(1005)])

        self.assertEqual(client._log_queue.qsize(), 1000)
        self.assertEqual(client._log_queue.get_nowait(), "5")
        client.stop_client()


class ChildToastForwardingTests(unittest.TestCase):
    @patch("module.desktop_clone.client.get_instance_context")
    def test_client_send_toast_serializes_template_title_and_lines(
        self,
        instance_context,
    ):
        instance_context.return_value = SimpleNamespace(
            is_child_session=True,
            pipe_name="test-pipe",
            current_session_id=1,
        )
        client = DesktopCloneClient()
        forwarded = []

        def capture(*parts):
            forwarded.append(parts)

        with patch.object(client, "_send", side_effect=capture):
            client.send_toast(
                "normal",
                "AALC 运行结束",
                ["所有任务已完成", "01:23:45"],
            )

        self.assertEqual(forwarded[0][0], "toast")
        self.assertEqual(forwarded[0][1], "normal")
        self.assertEqual(decode_text(forwarded[0][2]), "AALC 运行结束")
        self.assertEqual(
            decode_text(forwarded[0][3]),
            "所有任务已完成\n01:23:45",
        )

    @patch("module.desktop_clone.client.get_instance_context")
    def test_client_send_toast_swallows_pipe_failure(self, instance_context):
        instance_context.return_value = SimpleNamespace(
            is_child_session=True,
            pipe_name="test-pipe",
            current_session_id=1,
        )
        client = DesktopCloneClient()

        with patch.object(
            client,
            "_send",
            side_effect=BrokenPipeError("root AALC 尚未连接"),
        ):
            client.send_toast("normal", "标题", ["内容"])  # 不应抛异常

    def test_child_send_toast_forwards_to_root_client(self):
        from app.windows_toast import TemplateToast, send_toast

        root_client = MagicMock()
        context = SimpleNamespace(is_child_session=True)
        with (
            patch(
                "module.instance_context.get_instance_context",
                return_value=context,
            ),
            patch(
                "module.desktop_clone.client.get_desktop_clone_client",
                return_value=root_client,
            ),
        ):
            result = send_toast(
                "AALC 运行结束",
                ["所有任务已完成", "01:23:45"],
                template=TemplateToast.NormalTemplate,
            )

        self.assertTrue(result)
        root_client.send_toast.assert_called_once_with(
            "normal",
            "AALC 运行结束",
            ["所有任务已完成", "01:23:45"],
        )

    def test_child_send_toast_without_client_is_silently_skipped(self):
        from app.windows_toast import TemplateToast, send_toast

        context = SimpleNamespace(is_child_session=True)
        with (
            patch(
                "module.instance_context.get_instance_context",
                return_value=context,
            ),
            patch(
                "module.desktop_clone.client.get_desktop_clone_client",
                return_value=None,
            ),
        ):
            result = send_toast(
                "标题",
                "内容",
                template=TemplateToast.NormalTemplate,
            )

        self.assertTrue(result)

    def test_child_send_toast_forward_failure_does_not_raise(self):
        from app.windows_toast import TemplateToast, send_toast

        root_client = MagicMock()
        root_client.send_toast.side_effect = OSError("通知平台不可用")
        context = SimpleNamespace(is_child_session=True)
        with (
            patch(
                "module.instance_context.get_instance_context",
                return_value=context,
            ),
            patch(
                "module.desktop_clone.client.get_desktop_clone_client",
                return_value=root_client,
            ),
        ):
            result = send_toast(
                "标题",
                "内容",
                template=TemplateToast.NormalTemplate,
            )

        self.assertTrue(result)

    def test_root_send_toast_stays_local(self):
        from app.windows_toast import TemplateToast, send_toast

        context = SimpleNamespace(is_child_session=False)
        with (
            patch(
                "module.instance_context.get_instance_context",
                return_value=context,
            ),
            patch(
                "app.windows_toast._send_template_toast",
                return_value=True,
            ) as send_template,
        ):
            result = send_toast(
                "标题",
                "内容",
                template=TemplateToast.NormalTemplate,
            )

        self.assertTrue(result)
        send_template.assert_called_once()


class SteamSessionTests(unittest.TestCase):
    @patch(
        "module.game_and_screen.steam.steam_processes",
        return_value=[SteamProcessInfo(process_id=1234, session_id=1)],
    )
    def test_other_session_steam_is_rejected(self, _processes):
        with self.assertRaises(SteamSessionConflictError):
            ensure_steam_available_in_session(2)

    @patch(
        "module.game_and_screen.steam.steam_processes",
        return_value=[SteamProcessInfo(process_id=1234, session_id=2)],
    )
    def test_target_session_steam_is_allowed(self, _processes):
        ensure_steam_available_in_session(2)


class LauncherTests(unittest.TestCase):
    def test_development_launch_keeps_child_role_and_profile(self):
        executable, arguments, working_directory = _application_launch_command(
            42,
            "AALC.test.pipe",
            Path("C:/AALC Child"),
        )

        self.assertTrue(executable.is_file())
        self.assertIn("--aalc-instance child-session", arguments)
        self.assertIn("--expected-session-id 42", arguments)
        self.assertIn("--desktop-clone-pipe AALC.test.pipe", arguments)
        self.assertIn('"C:\\AALC Child"', arguments)
        self.assertTrue((working_directory / "main.py").is_file())


class ChildProfileTests(unittest.TestCase):
    def test_profile_is_isolated_and_sanitized(self):
        source_config = {
            "desktop_clone_enabled": True,
            "simulator": True,
            "background_click": True,
            "win_input_type": "background",
            "lab_mouse_logitech": True,
            "lab_mouse_razer": True,
            "lab_screenshot_obs": True,
            "obs_password": "do-not-copy",
            "mirrorchyan_cdk": "do-not-copy",
            "after_completion_actions": ["exit_game", "exit_aalc"],
            "after_completion_power_action": "lock",
            "keep_after_completion": False,
        }
        fake_cfg = MockConfig(source_config)
        fake_theme_list = MockThemeList()

        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profile"
            with (
                patch("module.desktop_clone.profile.child_profile_dir", return_value=profile),
                patch("module.desktop_clone.profile.cfg", fake_cfg),
                patch("module.desktop_clone.profile.theme_list", fake_theme_list),
            ):
                result = prepare_child_profile()

            with (result / "config.yaml").open("r", encoding="utf-8") as file:
                child_config = YAML().load(file)

        self.assertFalse(child_config["desktop_clone_enabled"])
        self.assertFalse(child_config["simulator"])
        self.assertFalse(child_config["background_click"])
        self.assertEqual(child_config["win_input_type"], "foreground")
        self.assertEqual(child_config["obs_password"], "")
        self.assertEqual(child_config["mirrorchyan_cdk"], "")
        self.assertEqual(child_config["after_completion_actions"], ["exit_game"])
        self.assertEqual(child_config["after_completion_power_action"], "lock")
        self.assertTrue(child_config["keep_after_completion"])

    def test_existing_config_preserved_without_refresh(self):
        fake_cfg = MockConfig({"win_input_type": "foreground"})
        fake_theme_list = MockThemeList()

        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profile"
            with (
                patch("module.desktop_clone.profile.child_profile_dir", return_value=profile),
                patch("module.desktop_clone.profile.cfg", fake_cfg),
                patch("module.desktop_clone.profile.theme_list", fake_theme_list),
            ):
                # 快照不存在时，即使不要求刷新也要首次生成。
                prepare_child_profile(refresh_config=False)
                config_path = profile / "config.yaml"
                self.assertTrue(config_path.is_file())

                # 模拟用户在分身 UI 里改过配置。
                edited = {"win_input_type": "foreground", "use_continuous_combat_select": 7}
                with config_path.open("w", encoding="utf-8") as file:
                    YAML().dump(edited, file)

                prepare_child_profile(refresh_config=False)
                with config_path.open("r", encoding="utf-8") as file:
                    preserved = YAML().load(file)
                self.assertEqual(preserved["use_continuous_combat_select"], 7)

                prepare_child_profile()
                with config_path.open("r", encoding="utf-8") as file:
                    refreshed = YAML().load(file)
                self.assertNotIn("use_continuous_combat_select", refreshed)


class FakeWinreg:
    HKEY_CURRENT_USER = object()
    REG_DWORD = 4
    REG_SZ = 1
    KEY_READ = 0x20019
    KEY_WRITE = 0x20006
    KEY_SET_VALUE = 0x2

    class _Key:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    def __init__(self, initial=None):
        self.values = dict(initial or {})

    def CreateKeyEx(self, _root, _subkey, _reserved, _access):
        return FakeWinreg._Key()

    def QueryValueEx(self, _key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name]

    def SetValueEx(self, _key, name, _reserved, value_type, value):
        self.values[name] = (value, value_type)

    def DeleteValue(self, _key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


class AutorunGuardTests(unittest.TestCase):
    def _run(self, fake_registry, marker):
        from module.desktop_clone import autorun_guard

        return (
            patch.object(autorun_guard, "winreg", fake_registry),
            patch.object(autorun_guard, "_marker_path", return_value=marker),
        )

    def test_suppress_and_restore_round_trip(self):
        from module.desktop_clone.autorun_guard import (
            restore_logon_autoruns,
            suppress_logon_autoruns,
        )

        fake = FakeWinreg({"DisableCurrentUserRun": (0, FakeWinreg.REG_DWORD)})
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / ".autorun-guard.json"
            registry_patch, marker_patch = self._run(fake, marker)
            with registry_patch, marker_patch:
                self.assertTrue(suppress_logon_autoruns())
                self.assertTrue(marker.is_file())
                for name in (
                    "DisableLocalMachineRun",
                    "DisableLocalMachineRunOnce",
                    "DisableCurrentUserRun",
                    "DisableCurrentUserRunOnce",
                ):
                    self.assertEqual(fake.values[name], (1, FakeWinreg.REG_DWORD))

                # 抑制期间重复调用不得覆盖原始快照。
                self.assertTrue(suppress_logon_autoruns())

                restore_logon_autoruns()
                self.assertFalse(marker.exists())
                self.assertEqual(
                    fake.values.get("DisableCurrentUserRun"),
                    (0, FakeWinreg.REG_DWORD),
                )
                self.assertNotIn("DisableLocalMachineRun", fake.values)

    def test_restore_without_marker_is_noop(self):
        from module.desktop_clone.autorun_guard import restore_logon_autoruns

        fake = FakeWinreg({"DisableLocalMachineRun": (1, FakeWinreg.REG_DWORD)})
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / ".autorun-guard.json"
            registry_patch, marker_patch = self._run(fake, marker)
            with registry_patch, marker_patch:
                restore_logon_autoruns()
            self.assertEqual(
                fake.values["DisableLocalMachineRun"],
                (1, FakeWinreg.REG_DWORD),
            )

    def test_non_dword_policy_aborts_suppression(self):
        from module.desktop_clone.autorun_guard import suppress_logon_autoruns

        fake = FakeWinreg({"DisableCurrentUserRun": ("odd", FakeWinreg.REG_SZ)})
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / ".autorun-guard.json"
            registry_patch, marker_patch = self._run(fake, marker)
            with registry_patch, marker_patch:
                with self.assertRaises(RuntimeError):
                    suppress_logon_autoruns()
                self.assertFalse(marker.exists())
                self.assertNotIn("DisableLocalMachineRun", fake.values)


class MockConfigModel:
    def __init__(self, data):
        self._data = data

    def model_dump(self):
        return dict(self._data)


class MockConfig:
    def __init__(self, data):
        self.config = MockConfigModel(data)


class MockThemeList:
    config = {}
    theme_pack_weight_path = "__missing_theme_pack_weight__"


class NativeHostBuildTests(unittest.TestCase):
    def test_rdp_host_source_compiles(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "AALC.DesktopCloneHost.exe"
            result = compile_desktop_clone_host(output=output, force=True)
            self.assertEqual(result, output)
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 0)


class NativeCompatibilityTests(unittest.TestCase):
    def test_remote_control_software_only_warns_and_never_blocks(self):
        with (
            patch(
                "module.desktop_clone.native.get_windows_edition",
                return_value="Professional",
            ),
            patch("module.desktop_clone.native.is_home_edition", return_value=False),
            patch(
                "module.desktop_clone.native.is_process_elevated",
                return_value=True,
            ),
            patch(
                "module.desktop_clone.native.is_child_sessions_enabled",
                return_value=True,
            ),
            patch(
                "module.desktop_clone.native.is_rdp_connections_enabled",
                return_value=True,
            ),
            patch(
                "module.desktop_clone.native.get_configured_rdp_port",
                return_value=3389,
            ),
            patch(
                "module.desktop_clone.native.is_local_rdp_listener_available",
                return_value=True,
            ),
            patch(
                "module.desktop_clone.native.find_running_remote_control_conflicts",
                return_value=("ToDesk", "UU远程"),
            ),
            patch(
                "module.desktop_clone.native.find_running_remote_control_services",
                return_value=("UU远程",),
            ),
        ):
            result = check_compatibility()

        self.assertTrue(result.supported)
        self.assertTrue(
            any("ToDesk、UU远程" in item for item in result.warnings)
        )
        self.assertTrue(any("切换到分身" in item for item in result.warnings))
        # 常驻后台服务只作为说明信息，不进入警告，也不阻止启动。
        self.assertTrue(any("远程控制后台服务" in item for item in result.details))
        self.assertFalse(
            any("远程控制后台服务" in item for item in result.warnings)
        )

    def test_background_remote_control_services_are_not_conflicts(self):
        class _Process:
            def __init__(self, name):
                self.info = {"name": name}

        with patch(
            "module.desktop_clone.native.psutil.process_iter",
            return_value=[
                _Process("GameViewerService.exe"),
                _Process("MuMuRemoteService.exe"),
            ],
        ):
            self.assertEqual(find_running_remote_control_conflicts(), ())
            self.assertEqual(
                find_running_remote_control_services(),
                ("MuMu远程", "UU远程"),
            )
            self.assertIsNone(build_remote_control_warning())

    def test_interactive_remote_control_process_builds_warning(self):
        class _Process:
            def __init__(self, name):
                self.info = {"name": name}

        with patch(
            "module.desktop_clone.native.psutil.process_iter",
            return_value=[_Process("GameViewer.exe")],
        ):
            self.assertEqual(find_running_remote_control_conflicts(), ("UU远程",))
            warning = build_remote_control_warning()

        self.assertIsNotNone(warning)
        self.assertIn("UU远程", warning)

    def test_child_session_setup_marker_is_scoped_to_windows_logon(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "setup-marker"
            with (
                patch(
                    "module.desktop_clone.native._child_sessions_setup_marker_path",
                    return_value=marker,
                ),
                patch(
                    "module.desktop_clone.native.get_current_logon_id",
                    return_value="logon-a",
                ),
            ):
                mark_child_sessions_enabled_for_current_logon()
                self.assertTrue(child_sessions_enabled_during_current_logon())

            with (
                patch(
                    "module.desktop_clone.native._child_sessions_setup_marker_path",
                    return_value=marker,
                ),
                patch(
                    "module.desktop_clone.native.get_current_logon_id",
                    return_value="logon-b",
                ),
            ):
                self.assertFalse(child_sessions_enabled_during_current_logon())

    def test_disabled_remote_desktop_is_rejected_before_listener_probe(self):
        with (
            patch(
                "module.desktop_clone.native.get_windows_edition",
                return_value="Professional",
            ),
            patch("module.desktop_clone.native.is_home_edition", return_value=False),
            patch(
                "module.desktop_clone.native.is_process_elevated",
                return_value=True,
            ),
            patch(
                "module.desktop_clone.native.is_child_sessions_enabled",
                return_value=False,
            ),
            patch(
                "module.desktop_clone.native.is_rdp_connections_enabled",
                return_value=False,
            ),
            patch(
                "module.desktop_clone.native.is_local_rdp_listener_available"
            ) as listener_probe,
        ):
            result = check_compatibility()

        self.assertFalse(result.supported)
        self.assertTrue(any("远程桌面连接未启用" in item for item in result.details))
        listener_probe.assert_not_called()

    def test_missing_local_rdp_listener_is_rejected(self):
        with (
            patch(
                "module.desktop_clone.native.get_windows_edition",
                return_value="Professional",
            ),
            patch("module.desktop_clone.native.is_home_edition", return_value=False),
            patch(
                "module.desktop_clone.native.is_process_elevated",
                return_value=True,
            ),
            patch(
                "module.desktop_clone.native.is_child_sessions_enabled",
                return_value=False,
            ),
            patch(
                "module.desktop_clone.native.is_rdp_connections_enabled",
                return_value=True,
            ),
            patch(
                "module.desktop_clone.native.get_configured_rdp_port",
                return_value=3390,
            ),
            patch(
                "module.desktop_clone.native.is_local_rdp_listener_available",
                return_value=False,
            ),
        ):
            result = check_compatibility()

        self.assertFalse(result.supported)
        self.assertTrue(any("3390 未监听" in item for item in result.details))


class ControllerLifecycleTests(unittest.TestCase):
    @patch("module.desktop_clone.controller.get_child_session_id", return_value=None)
    def test_first_start_enables_child_sessions_and_requires_windows_relogon(
        self,
        _get_child_session_id,
    ):
        controller = DesktopCloneController()
        with (
            patch.object(controller, "compatibility_details", return_value=(True, (), ())),
            patch.object(controller, "_ensure_server"),
            patch(
                "module.desktop_clone.controller."
                "child_sessions_enabled_during_current_logon",
                return_value=False,
            ),
            patch(
                "module.desktop_clone.controller.is_child_sessions_enabled",
                return_value=False,
            ),
            patch(
                "module.desktop_clone.controller.enable_child_sessions"
            ) as enable_child_sessions,
            patch(
                "module.desktop_clone.controller."
                "mark_child_sessions_enabled_for_current_logon"
            ) as mark_enabled,
            patch(
                "module.desktop_clone.controller.get_desktop_clone_host_executable"
            ) as get_helper,
        ):
            controller._start_session_worker()

        self.assertEqual(controller.state, DesktopCloneState.ERROR)
        self.assertIn("注销 Windows 并重新登录一次", controller.status_text)
        enable_child_sessions.assert_called_once_with()
        mark_enabled.assert_called_once_with()
        get_helper.assert_not_called()
        self.assertFalse(controller.is_session_active)

    @patch("module.desktop_clone.controller.get_child_session_id", return_value=None)
    def test_same_windows_logon_cannot_retry_after_enabling_child_sessions(
        self,
        _get_child_session_id,
    ):
        controller = DesktopCloneController()
        with (
            patch.object(controller, "compatibility_details", return_value=(True, (), ())),
            patch.object(controller, "_ensure_server"),
            patch(
                "module.desktop_clone.controller."
                "child_sessions_enabled_during_current_logon",
                return_value=True,
            ),
            patch(
                "module.desktop_clone.controller.is_child_sessions_enabled",
                return_value=True,
            ),
            patch(
                "module.desktop_clone.controller.get_desktop_clone_host_executable"
            ) as get_helper,
        ):
            controller._start_session_worker()

        self.assertEqual(controller.state, DesktopCloneState.ERROR)
        self.assertIn("本次登录后启用", controller.status_text)
        self.assertIn("不要在凭据窗口中输入密码", controller.status_text)
        get_helper.assert_not_called()

    @patch("module.desktop_clone.controller.get_child_session_id", return_value=None)
    def test_marker_write_failure_prevents_child_sessions_enable(
        self,
        _get_child_session_id,
    ):
        controller = DesktopCloneController()
        with (
            patch.object(controller, "compatibility_details", return_value=(True, (), ())),
            patch.object(controller, "_ensure_server"),
            patch(
                "module.desktop_clone.controller."
                "child_sessions_enabled_during_current_logon",
                return_value=False,
            ),
            patch(
                "module.desktop_clone.controller.is_child_sessions_enabled",
                return_value=False,
            ),
            patch(
                "module.desktop_clone.controller.enable_child_sessions"
            ) as enable_child_sessions,
            patch(
                "module.desktop_clone.controller."
                "mark_child_sessions_enabled_for_current_logon",
                side_effect=OSError("marker failed"),
            ),
            patch(
                "module.desktop_clone.controller.get_desktop_clone_host_executable"
            ) as get_helper,
        ):
            controller._start_session_worker()

        self.assertEqual(controller.state, DesktopCloneState.ERROR)
        enable_child_sessions.assert_not_called()
        get_helper.assert_not_called()

    @patch("module.desktop_clone.controller.get_child_session_id", return_value=None)
    def test_helper_launch_receives_theme_and_visible_toolbar_tools(
        self,
        _get_child_session_id,
    ):
        controller = DesktopCloneController()
        config_values = {
            "desktop_clone_show_on_start": False,
            "desktop_clone_toolbar_items": ["input"],
            "desktop_clone_suppress_autoruns": False,
        }

        with (
            patch.object(
                controller,
                "compatibility_details",
                return_value=(True, (), ()),
            ),
            patch.object(controller, "_ensure_server"),
            patch(
                "module.desktop_clone.controller."
                "child_sessions_enabled_during_current_logon",
                return_value=False,
            ),
            patch(
                "module.desktop_clone.controller.is_child_sessions_enabled",
                return_value=True,
            ),
            patch(
                "module.desktop_clone.controller."
                "get_desktop_clone_host_executable",
                return_value=Path("C:/AALC/AALC.DesktopCloneHost.exe"),
            ),
            patch(
                "module.desktop_clone.controller.get_configured_rdp_port",
                return_value=3390,
            ),
            patch(
                "module.desktop_clone.controller.cfg.get_value",
                side_effect=lambda key, default=None: config_values.get(
                    key,
                    default,
                ),
            ),
            patch(
                "module.desktop_clone.controller.isDarkTheme",
                return_value=True,
            ),
            patch(
                "module.desktop_clone.controller.subprocess.Popen"
            ) as popen,
            patch("module.desktop_clone.controller.threading.Thread"),
        ):
            controller._start_session_worker()

        command = popen.call_args.args[0]

        def argument(name):
            return command[command.index(name) + 1]

        self.assertEqual(argument("--show"), "false")
        self.assertEqual(argument("--dark"), "true")
        self.assertEqual(argument("--visible-tools"), "input")
        self.assertEqual(argument("--rdp-port"), "3390")
        self.assertEqual(argument("--mute-text"), "关闭声音")
        self.assertEqual(argument("--input-text"), "关闭输入")

    @patch("module.desktop_clone.controller.get_child_session_id", return_value=None)
    def test_helper_launch_failure_restores_suppressed_autoruns(
        self,
        _get_child_session_id,
    ):
        config_values = {
            "desktop_clone_show_on_start": True,
            "desktop_clone_toolbar_items": ["mute", "input"],
            "desktop_clone_suppress_autoruns": True,
        }
        with patch(
            "module.desktop_clone.controller.restore_logon_autoruns"
        ) as restore:
            controller = DesktopCloneController()
            restore.reset_mock()
            with (
                patch.object(
                    controller,
                    "compatibility_details",
                    return_value=(True, (), ()),
                ),
                patch.object(controller, "_ensure_server"),
                patch(
                    "module.desktop_clone.controller."
                    "child_sessions_enabled_during_current_logon",
                    return_value=False,
                ),
                patch(
                    "module.desktop_clone.controller."
                    "is_child_sessions_enabled",
                    return_value=True,
                ),
                patch(
                    "module.desktop_clone.controller."
                    "get_desktop_clone_host_executable",
                    return_value=Path(
                        "C:/AALC/AALC.DesktopCloneHost.exe"
                    ),
                ),
                patch(
                    "module.desktop_clone.controller."
                    "get_configured_rdp_port",
                    return_value=3389,
                ),
                patch(
                    "module.desktop_clone.controller.cfg.get_value",
                    side_effect=lambda key, default=None: config_values.get(
                        key,
                        default,
                    ),
                ),
                patch(
                    "module.desktop_clone.controller."
                    "suppress_logon_autoruns"
                ) as suppress_autoruns,
                patch(
                    "module.desktop_clone.controller.subprocess.Popen",
                    side_effect=OSError("launch failed"),
                ),
            ):
                controller._start_session_worker()

        suppress_autoruns.assert_called_once_with()
        restore.assert_called_once_with()
        self.assertEqual(controller.state, DesktopCloneState.ERROR)

    def test_connection_timeout_reports_error_and_schedules_cleanup(self):
        controller = DesktopCloneController()
        controller.state = DesktopCloneState.CONNECTING

        with patch("module.desktop_clone.controller.threading.Thread") as thread:
            controller._connection_timeout()

        self.assertEqual(controller.state, DesktopCloneState.ERROR)
        self.assertTrue(controller._cancel_requested.is_set())
        self.assertIn("已终止 RDP 宿主", controller.status_text)
        thread.return_value.start.assert_called_once_with()
        self.assertEqual(
            thread.call_args.kwargs["target"],
            controller._cleanup_failed_connection,
        )

    @patch("module.desktop_clone.controller.get_child_session_id", return_value=None)
    def test_failure_cleanup_stops_running_child_before_shutdown(
        self,
        _get_child_session_id,
    ):
        controller = DesktopCloneController()
        controller.state = DesktopCloneState.ERROR
        controller._script_idle_event.clear()
        connection = MagicMock()
        controller._child_connection = connection

        def acknowledge(_timeout, command):
            if command == "stop":
                controller._script_idle_event.set()
            elif command == "shutdown":
                controller._child_disconnected_event.set()

        connection.send_with_timeout.side_effect = acknowledge

        stopped = controller.shutdown_session(timeout=1.0)

        self.assertTrue(stopped)
        self.assertEqual(
            [
                call.args[1]
                for call in connection.send_with_timeout.call_args_list
            ],
            ["stop", "shutdown"],
        )

    def test_rdp_retry_message_preserves_connecting_state_and_diagnostics(self):
        controller = DesktopCloneController()
        controller.state = DesktopCloneState.CONNECTING

        controller._handle_helper_message(
            [
                "rdp-retrying",
                "1",
                "1",
                "logon",
                "0",
                "0",
                encode_text("Child Session 未完成免凭据登录"),
            ]
        )

        self.assertEqual(controller.state, DesktopCloneState.CONNECTING)
        self.assertIn("1 秒后自动重试（1/3）", controller.status_text)

    def test_transport_connection_waits_for_login_before_launch(self):
        controller = DesktopCloneController()
        controller.state = DesktopCloneState.CONNECTING

        controller._handle_helper_message(["rdp-transport-connected"])

        self.assertEqual(controller.state, DesktopCloneState.CONNECTING)
        self.assertIsNone(controller.child_session_id)
        self.assertIn("等待 Windows 完成", controller.status_text)

    def test_helper_toolbar_state_is_forwarded_to_qt(self):
        controller = DesktopCloneController()
        states = []
        controller.tool_state_changed.connect(
            lambda tool_id, enabled: states.append((tool_id, enabled))
        )

        controller._handle_helper_message(["tool-state", "mute", "1"])
        controller._handle_helper_message(["tool-state", "input", "0"])

        self.assertEqual(states, [("mute", True), ("input", False)])

    def test_helper_ui_command_pipe_race_is_non_fatal(self):
        controller = DesktopCloneController()
        controller._helper_connection = MagicMock()
        controller._helper_connection.send.side_effect = BrokenPipeError(
            "closed"
        )

        sent = controller._send_helper_command("hide")

        self.assertFalse(sent)

    def test_helper_hello_resynchronizes_current_theme_and_toolbar_config(self):
        context = SimpleNamespace(is_root=True, current_session_id=1)
        connection = MagicMock(peer_session_id=1, role=None)
        config_values = {"desktop_clone_toolbar_items": ["input"]}

        with (
            patch(
                "module.desktop_clone.controller.get_instance_context",
                return_value=context,
            ),
            patch(
                "module.desktop_clone.controller.cfg.get_value",
                side_effect=lambda key, default=None: config_values.get(
                    key,
                    default,
                ),
            ),
            patch(
                "module.desktop_clone.controller.isDarkTheme",
                return_value=True,
            ),
        ):
            controller = DesktopCloneController()
            controller._handle_hello(
                connection,
                ["hello", "rdp-host", "1"],
            )

        self.assertEqual(connection.role, "rdp-host")
        sent = connection.send.call_args_list
        self.assertEqual(sent[0], unittest.mock.call("theme", "dark"))
        # hello 后必须重放界面文案：宿主重连时若不补发，窗口会停在上一次
        # 语言的字符串上。只断言结构，不锁定 base64，避免改翻译就挂测试。
        self.assertEqual(sent[1].args[0], "ui-text")
        self.assertEqual(len(sent[1].args), 6)
        self.assertEqual(
            sent[2:],
            [
                unittest.mock.call("tool-visible", "mute", "0"),
                unittest.mock.call("tool-visible", "input", "1"),
            ],
        )

    def test_final_rdp_failure_schedules_cleanup_with_structured_error(self):
        controller = DesktopCloneController()
        controller.state = DesktopCloneState.CONNECTING

        with patch.object(controller, "_fail_connection_and_cleanup") as fail:
            controller._handle_helper_message(
                [
                    "rdp-failed",
                    "logon",
                    "0",
                    "0",
                    encode_text("Child Session 未完成免凭据登录"),
                ]
            )

        fail.assert_called_once_with(
            "RDP Child Session 连接失败"
            "（stage={0}, code={1}, extended={2}）：{3}",
            "logon",
            "0",
            "0",
            "Child Session 未完成免凭据登录",
        )

    @patch("module.desktop_clone.controller.get_child_session_id", return_value=88)
    def test_mismatched_rdp_session_schedules_cleanup(
        self,
        _get_child_session_id,
    ):
        controller = DesktopCloneController()
        controller.state = DesktopCloneState.CONNECTING

        with patch.object(controller, "_fail_connection_and_cleanup") as fail:
            controller._handle_helper_message(["rdp-connected", "77"])

        fail.assert_called_once_with(
            "RDP 宿主上报了错误 Child Session：reported={0}, actual={1}",
            77,
            88,
        )
        self.assertIsNone(controller.child_session_id)

    @patch("module.desktop_clone.controller.get_child_session_id", return_value=88)
    def test_late_mismatched_rdp_session_cannot_overwrite_stopping_state(
        self,
        _get_child_session_id,
    ):
        controller = DesktopCloneController()
        controller.state = DesktopCloneState.STOPPING
        controller._cancel_requested.set()
        controller._helper_connection = MagicMock()

        with patch.object(controller, "_fail_connection_and_cleanup") as fail:
            controller._handle_helper_message(["rdp-connected", "77"])

        self.assertEqual(controller.state, DesktopCloneState.STOPPING)
        self.assertIsNone(controller.child_session_id)
        controller._helper_connection.send.assert_called_once_with("logoff")
        fail.assert_not_called()

    def test_late_rdp_failures_are_ignored_while_stopping(self):
        controller = DesktopCloneController()
        controller.state = DesktopCloneState.STOPPING
        controller._cancel_requested.set()

        with patch.object(controller, "_fail_connection_and_cleanup") as fail:
            controller._handle_helper_message(
                [
                    "rdp-retrying",
                    "1",
                    "1",
                    "connect",
                    "516",
                    "0",
                    encode_text("RDP 连接失败。"),
                ]
            )
            controller._handle_helper_message(
                [
                    "rdp-failed",
                    "connect",
                    "516",
                    "0",
                    encode_text("RDP 连接失败。"),
                ]
            )
            controller._handle_helper_message(
                ["error", encode_text("RDP 连接失败。")]
            )

        self.assertEqual(controller.state, DesktopCloneState.STOPPING)
        fail.assert_not_called()

    def test_child_launch_failure_schedules_connection_cleanup(self):
        controller = DesktopCloneController()
        controller.child_session_id = 77
        with (
            patch(
                "module.desktop_clone.controller.prepare_child_profile",
                side_effect=RuntimeError("profile failed"),
            ),
            patch.object(controller, "_fail_connection_and_cleanup") as fail,
        ):
            controller._launch_child_worker()

        fail.assert_called_once()
        self.assertIn("在 Child Session 启动 AALC 失败", fail.call_args.args[0])

    def test_ready_task_profile_failure_schedules_connection_cleanup(self):
        controller = DesktopCloneController()
        controller.state = DesktopCloneState.LAUNCHING_CHILD
        controller._pending_task_start = True
        with (
            patch(
                "module.desktop_clone.controller.prepare_child_profile",
                side_effect=RuntimeError("profile failed"),
            ),
            patch.object(controller, "_fail_connection_and_cleanup") as fail,
        ):
            controller._refresh_profile_and_start()

        fail.assert_called_once()
        self.assertIn("同步桌面分身配置失败", fail.call_args.args[0])

    def test_child_error_schedules_connection_cleanup(self):
        controller = DesktopCloneController()
        controller.state = DesktopCloneState.LAUNCHING_CHILD

        with patch.object(controller, "_fail_connection_and_cleanup") as fail:
            controller._handle_child_message(
                ["error", encode_text("reload failed")]
            )

        fail.assert_called_once_with("reload failed")

    def test_child_log_is_prefixed_and_appended_to_root_ui_log(self):
        controller = DesktopCloneController()

        with (
            patch(
                "module.desktop_clone.controller.cfg.get_value",
                return_value=True,
            ),
            patch(
                "module.logger.my_log.ui_log_dispatcher.append_line"
            ) as append_line,
        ):
            controller._handle_child_message(
                ["log", encode_text("12:34:56 - child detail")]
            )

        append_line.assert_called_once_with(
            "[分身] 12:34:56 - child detail"
        )

    def test_child_log_sync_can_be_disabled(self):
        controller = DesktopCloneController()

        with (
            patch(
                "module.desktop_clone.controller.cfg.get_value",
                return_value=False,
            ),
            patch(
                "module.logger.my_log.ui_log_dispatcher.append_line"
            ) as append_line,
        ):
            controller._handle_child_message(
                ["log", encode_text("not forwarded")]
            )

        append_line.assert_not_called()

    def test_child_toast_is_displayed_by_root(self):
        from app.windows_toast import TemplateToast

        controller = DesktopCloneController()
        with patch("app.windows_toast.send_toast") as send_toast:
            controller._handle_child_message(
                [
                    "toast",
                    "normal",
                    encode_text("AALC 运行结束"),
                    encode_text("所有任务已完成\n01:23:45"),
                ]
            )

        send_toast.assert_called_once_with(
            "AALC 运行结束",
            "所有任务已完成\n01:23:45",
            template=TemplateToast.NormalTemplate,
        )

    def test_child_toast_unknown_template_is_ignored(self):
        controller = DesktopCloneController()
        with patch("app.windows_toast.send_toast") as send_toast:
            controller._handle_child_message(
                [
                    "toast",
                    "bogus",
                    encode_text("标题"),
                    encode_text("内容"),
                ]
            )

        send_toast.assert_not_called()

    def test_child_toast_malformed_message_is_ignored(self):
        controller = DesktopCloneController()
        with patch("app.windows_toast.send_toast") as send_toast:
            controller._handle_child_message(
                ["toast", "normal", encode_text("标题")]
            )

        send_toast.assert_not_called()

    def test_child_toast_display_failure_is_non_fatal(self):
        controller = DesktopCloneController()
        with patch(
            "app.windows_toast.send_toast",
            side_effect=OSError("通知平台不可用"),
        ):
            controller._handle_child_message(
                [
                    "toast",
                    "test",
                    encode_text("标题"),
                    encode_text("内容"),
                ]
            )  # 不应抛异常

    def test_unexpected_transport_disconnects_schedule_cleanup(self):
        controller = DesktopCloneController()
        controller.state = DesktopCloneState.READY
        child_connection = MagicMock()
        helper_connection = MagicMock()
        controller._child_connection = child_connection
        controller._helper_connection = helper_connection

        with patch.object(controller, "_fail_connection_and_cleanup") as fail:
            controller._on_pipe_disconnect(child_connection)
            controller._on_pipe_disconnect(helper_connection)

        self.assertEqual(
            [call.args[0] for call in fail.call_args_list],
            [
                "Child AALC 意外断开（peer_pid={0}）",
                "RDP 桌面分身宿主连接已断开",
            ],
        )

    def test_manual_stop_is_reported_without_failure_warning(self):
        controller = DesktopCloneController()
        # 任务结果只在会话真的在跑时才推进状态；IDLE 下的散落结果会被
        # 生命周期守卫忽略，所以先建立 RUNNING 前置条件再断言停止语义。
        controller.state = DesktopCloneState.RUNNING
        results = []
        controller.script_finished.connect(
            lambda outcome, detail: results.append((outcome, detail))
        )

        with patch("module.desktop_clone.controller.apply_child_state_delta"):
            controller._handle_child_message(
                [
                    "script-result",
                    "stopped",
                    encode_text(""),
                    encode_text("{}"),
                ]
            )

        self.assertEqual(controller.state, DesktopCloneState.READY)
        self.assertEqual(controller.status_text, "分身任务已停止")
        self.assertEqual(results, [("stopped", "")])

    @patch("module.desktop_clone.controller.get_child_session_id", return_value=44)
    def test_existing_child_session_is_rejected_before_helper_launch(
        self,
        _get_child_session_id,
    ):
        controller = DesktopCloneController()
        with (
            patch.object(controller, "compatibility_details", return_value=(True, (), ())),
            patch.object(controller, "_ensure_server"),
            patch("module.desktop_clone.controller.subprocess.Popen") as popen,
        ):
            controller._start_session_worker()

        self.assertEqual(controller.state, DesktopCloneState.ERROR)
        self.assertIn("已有 Child Session", controller.status_text)
        popen.assert_not_called()

    @patch("module.desktop_clone.controller.get_child_session_id", return_value=None)
    def test_cancelled_start_cannot_launch_helper_after_cleanup(
        self,
        _get_child_session_id,
    ):
        controller = DesktopCloneController()
        controller._cancel_requested.set()
        with (
            patch.object(controller, "compatibility_details", return_value=(True, (), ())),
            patch.object(controller, "_ensure_server"),
            patch("module.desktop_clone.controller.subprocess.Popen") as popen,
        ):
            controller._start_session_worker()

        popen.assert_not_called()

    def test_ready_session_enters_launching_state_before_profile_refresh(self):
        controller = DesktopCloneController()
        controller.state = DesktopCloneState.READY
        controller._child_connection = MagicMock()
        with (
            patch(
                "module.game_and_screen.steam.ensure_steam_available_in_session"
            ),
            patch(
                "module.session_process.process_is_running",
                return_value=False,
            ),
            patch("module.desktop_clone.controller.threading.Thread") as thread,
        ):
            controller.request_task_start()

        self.assertTrue(controller._pending_task_start)
        self.assertEqual(controller.state, DesktopCloneState.LAUNCHING_CHILD)
        thread.return_value.start.assert_called_once_with()

    def test_ready_session_cancel_cannot_send_reload_start_after_stop(self):
        controller = DesktopCloneController()
        controller.state = DesktopCloneState.LAUNCHING_CHILD
        controller._pending_task_start = True
        controller._child_connection = MagicMock()
        profile_entered = threading.Event()
        release_profile = threading.Event()

        def blocking_profile():
            profile_entered.set()
            self.assertTrue(release_profile.wait(2))

        worker = threading.Thread(target=controller._refresh_profile_and_start)
        with patch(
            "module.desktop_clone.controller.prepare_child_profile",
            side_effect=blocking_profile,
        ):
            worker.start()
            self.assertTrue(profile_entered.wait(2))
            with patch(
                "module.desktop_clone.controller.threading.Thread"
            ) as cancel_thread:
                controller.request_task_stop()
            release_profile.set()
            worker.join(2)

        self.assertFalse(worker.is_alive())
        self.assertTrue(controller._cancel_requested.is_set())
        controller._child_connection.send.assert_not_called()
        cancel_thread.return_value.start.assert_called_once_with()

    def test_cancelled_profile_exception_cannot_overwrite_stopping_state(self):
        controller = DesktopCloneController()
        controller.state = DesktopCloneState.LAUNCHING_CHILD
        controller._pending_task_start = True
        controller._child_connection = MagicMock()
        profile_entered = threading.Event()
        release_profile = threading.Event()

        def failing_profile():
            profile_entered.set()
            self.assertTrue(release_profile.wait(2))
            raise OSError("copy interrupted")

        worker = threading.Thread(target=controller._refresh_profile_and_start)
        with patch(
            "module.desktop_clone.controller.prepare_child_profile",
            side_effect=failing_profile,
        ):
            worker.start()
            self.assertTrue(profile_entered.wait(2))
            with patch("module.desktop_clone.controller.threading.Thread"):
                controller.request_task_stop()
            release_profile.set()
            worker.join(2)

        self.assertFalse(worker.is_alive())
        self.assertEqual(controller.state, DesktopCloneState.STOPPING)
        controller._child_connection.send.assert_not_called()

    def test_cancel_during_profile_copy_cannot_launch_child_aalc(self):
        controller = DesktopCloneController()
        controller.child_session_id = 77
        profile_entered = threading.Event()
        release_profile = threading.Event()

        def blocking_profile(refresh_config=True):
            # 重开分身的 launcher 路径必须保留分身内配置。
            self.assertFalse(refresh_config)
            profile_entered.set()
            self.assertTrue(release_profile.wait(2))
            return Path("C:/profile")

        with (
            patch(
                "module.desktop_clone.controller.prepare_child_profile",
                side_effect=blocking_profile,
            ),
            patch(
                "module.desktop_clone.controller.launch_child_aalc"
            ) as launch_child,
        ):
            worker = threading.Thread(target=controller._launch_child_worker)
            worker.start()
            self.assertTrue(profile_entered.wait(2))
            with controller._operation_lock:
                controller._cancel_requested.set()
            release_profile.set()
            worker.join(2)

        self.assertFalse(worker.is_alive())
        launch_child.assert_not_called()

    def test_error_with_residual_session_cannot_queue_or_restart_task(self):
        controller = DesktopCloneController()
        controller.state = DesktopCloneState.ERROR
        controller.child_session_id = 77
        controller._child_connection = MagicMock()
        errors = []
        controller.error_occurred.connect(errors.append)

        with patch(
            "module.game_and_screen.steam.ensure_steam_available_in_session"
        ) as ensure_steam:
            controller.request_task_start()
        controller._handle_child_message(["ready"])

        self.assertFalse(controller._pending_task_start)
        self.assertTrue(controller._cancel_requested.is_set())
        self.assertEqual(controller.state, DesktopCloneState.ERROR)
        self.assertEqual(len(errors), 1)
        ensure_steam.assert_not_called()
        controller._child_connection.send.assert_not_called()

    def test_error_without_residual_session_can_retry_preflight(self):
        controller = DesktopCloneController()
        controller.state = DesktopCloneState.ERROR
        controller._status_source = "模拟器模式不需要且不支持桌面分身"

        with (
            patch(
                "module.game_and_screen.steam.ensure_steam_available_in_session"
            ) as ensure_steam,
            patch(
                "module.session_process.process_is_running",
                return_value=False,
            ),
            patch.object(controller, "start_session") as start_session,
        ):
            controller.request_task_start()

        ensure_steam.assert_called_once_with(-1)
        start_session.assert_called_once_with()
        self.assertTrue(controller._pending_task_start)
        self.assertFalse(controller._cancel_requested.is_set())

    def test_shutdown_rejects_concurrent_task_start(self):
        controller = DesktopCloneController()
        controller.state = DesktopCloneState.READY
        controller.child_session_id = 77
        cleanup_entered = threading.Event()
        release_cleanup = threading.Event()

        def blocking_session_id():
            cleanup_entered.set()
            self.assertTrue(release_cleanup.wait(2))
            return None

        with patch(
            "module.desktop_clone.controller.get_child_session_id",
            side_effect=blocking_session_id,
        ):
            worker = threading.Thread(target=controller.shutdown_session)
            worker.start()
            self.assertTrue(cleanup_entered.wait(2))
            self.assertEqual(controller.state, DesktopCloneState.STOPPING)
            with patch(
                "module.game_and_screen.steam.ensure_steam_available_in_session"
            ) as ensure_steam:
                controller.request_task_start()
            release_cleanup.set()
            worker.join(2)

        self.assertFalse(worker.is_alive())
        self.assertFalse(controller._pending_task_start)
        self.assertEqual(controller.state, DesktopCloneState.IDLE)
        ensure_steam.assert_not_called()

    def test_child_launch_does_not_hold_operation_lock_during_task_scheduler_call(self):
        controller = DesktopCloneController()
        controller.child_session_id = 77
        launch_entered = threading.Event()
        release_launch = threading.Event()

        def blocking_launch(_session_id, _pipe_name, _profile, is_cancelled):
            launch_entered.set()
            self.assertTrue(release_launch.wait(2))
            self.assertTrue(is_cancelled())

        with (
            patch(
                "module.desktop_clone.controller.prepare_child_profile",
                return_value=Path("C:/profile"),
            ),
            patch(
                "module.desktop_clone.controller.launch_child_aalc",
                side_effect=blocking_launch,
            ),
            patch(
                "module.desktop_clone.controller.get_child_session_id",
                return_value=None,
            ),
        ):
            worker = threading.Thread(target=controller._launch_child_worker)
            worker.start()
            self.assertTrue(launch_entered.wait(2))
            started = time.monotonic()
            stopped = controller.shutdown_session(timeout=0.1)
            elapsed = time.monotonic() - started
            release_launch.set()
            worker.join(2)

        self.assertTrue(stopped)
        self.assertLess(elapsed, 0.5)
        self.assertFalse(worker.is_alive())

    def test_concurrent_shutdown_calls_share_one_cleanup_owner(self):
        controller = DesktopCloneController()
        controller.state = DesktopCloneState.READY
        controller.child_session_id = 77
        cleanup_entered = threading.Event()
        release_cleanup = threading.Event()
        call_count = 0
        call_count_lock = threading.Lock()

        def blocking_session_id():
            nonlocal call_count
            with call_count_lock:
                call_count += 1
            cleanup_entered.set()
            self.assertTrue(release_cleanup.wait(2))
            return None

        results = []
        with patch(
            "module.desktop_clone.controller.get_child_session_id",
            side_effect=blocking_session_id,
        ):
            first = threading.Thread(
                target=lambda: results.append(controller.shutdown_session(timeout=2))
            )
            second = threading.Thread(
                target=lambda: results.append(controller.shutdown_session(timeout=2))
            )
            first.start()
            self.assertTrue(cleanup_entered.wait(2))
            second.start()
            with patch(
                "module.game_and_screen.steam.ensure_steam_available_in_session"
            ) as ensure_steam:
                controller.request_task_start()
            release_cleanup.set()
            first.join(2)
            second.join(2)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(results, [True, True])
        self.assertEqual(call_count, 3)
        self.assertEqual(controller.state, DesktopCloneState.IDLE)
        self.assertFalse(controller._pending_task_start)
        ensure_steam.assert_not_called()

    @patch("module.desktop_clone.controller.logoff_child_session")
    @patch("module.desktop_clone.controller.get_child_session_id", return_value=88)
    def test_shutdown_never_logs_off_foreign_child_session(
        self,
        _get_child_session_id,
        logoff_child_session,
    ):
        controller = DesktopCloneController()
        controller.child_session_id = 77

        stopped = controller.shutdown_session(timeout=0)

        self.assertFalse(stopped)
        logoff_child_session.assert_not_called()

    @patch("module.desktop_clone.controller.logoff_child_session")
    @patch("module.desktop_clone.controller.get_child_session_id", return_value=77)
    def test_logoff_ack_does_not_override_windows_session_state(
        self,
        _get_child_session_id,
        logoff_child_session,
    ):
        controller = DesktopCloneController()
        controller.child_session_id = 77
        controller._helper_logged_off_event.set()

        stopped = controller.shutdown_session(timeout=0)

        self.assertFalse(stopped)
        self.assertEqual(controller.state, DesktopCloneState.ERROR)
        logoff_child_session.assert_called_once_with(77, wait=False)

    @patch("module.desktop_clone.controller.logoff_child_session")
    @patch(
        "module.desktop_clone.controller.get_child_session_id",
        side_effect=[77, 88],
    )
    def test_shutdown_logs_off_only_the_verified_session_id(
        self,
        _get_child_session_id,
        logoff_child_session,
    ):
        controller = DesktopCloneController()
        controller.child_session_id = 77

        stopped = controller.shutdown_session(timeout=0)

        self.assertFalse(stopped)
        logoff_child_session.assert_called_once_with(77, wait=False)


class ChildStateSyncTests(unittest.TestCase):
    def test_only_whitelisted_task_state_is_persisted(self):
        fake_cfg = MagicMock()
        with patch("module.desktop_clone.state_sync.cfg", fake_cfg):
            apply_child_state_delta(
                '{"teams_active_queue":[2,1],"last_auto_change":123.5,'
                '"hard_mirror_chance":2,"hard_mirror":true}'
            )

        fake_cfg.set_value.assert_any_call("teams_active_queue", [2, 1])
        fake_cfg.normalize_and_sync_team_state.assert_called_once_with(persist=True)
        fake_cfg.set_value.assert_any_call("last_auto_change", 123.5)
        fake_cfg.set_value.assert_any_call("hard_mirror_chance", 2)
        fake_cfg.set_value.assert_any_call("hard_mirror", True)

    def test_unknown_state_field_is_rejected(self):
        with self.assertRaises(ValueError):
            apply_child_state_delta(
                '{"teams_active_queue":[],"last_auto_change":0,'
                '"hard_mirror_chance":0,"hard_mirror":false,"unsafe":true}'
            )


class MainButtonOwnershipTests(unittest.TestCase):
    def test_manual_clone_start_is_adopted_by_main_button(self):
        from app.farming_interface import FarmingInterfaceLeft

        interface = SimpleNamespace(
            my_script=None,
            _desktop_clone_task_requested=False,
            _desktop_clone_task_started_from_root=False,
            _stop_in_progress=True,
            _disable_setting=MagicMock(),
            parent=MagicMock(return_value="parent"),
            link_start_button=SimpleNamespace(
                set_text=MagicMock(),
                button=SimpleNamespace(setEnabled=MagicMock()),
            ),
            pause_resume_button=SimpleNamespace(
                set_text=MagicMock(),
                setVisible=MagicMock(),
            ),
            tr=lambda text: text,
        )

        FarmingInterfaceLeft._handle_desktop_clone_script_started(interface)

        self.assertTrue(interface._desktop_clone_task_requested)
        self.assertFalse(interface._desktop_clone_task_started_from_root)
        self.assertFalse(interface._stop_in_progress)
        interface._disable_setting.assert_called_once_with("parent")
        interface.link_start_button.set_text.assert_called_once_with("S t o p !")
        interface.link_start_button.button.setEnabled.assert_called_once_with(True)
        interface.pause_resume_button.setVisible.assert_called_once_with(True)

    def test_clone_start_does_not_hijack_active_local_task(self):
        from app.farming_interface import FarmingInterfaceLeft

        interface = SimpleNamespace(
            my_script=object(),
            _desktop_clone_task_requested=False,
            link_start_button=MagicMock(),
        )

        FarmingInterfaceLeft._handle_desktop_clone_script_started(interface)

        self.assertFalse(interface._desktop_clone_task_requested)
        interface.link_start_button.set_text.assert_not_called()

    def test_root_requested_clone_start_keeps_root_origin(self):
        from app.farming_interface import FarmingInterfaceLeft

        interface = SimpleNamespace(
            my_script=None,
            _desktop_clone_task_requested=True,
            _desktop_clone_task_started_from_root=True,
            _stop_in_progress=False,
            _disable_setting=MagicMock(),
            link_start_button=SimpleNamespace(
                set_text=MagicMock(),
                button=SimpleNamespace(setEnabled=MagicMock()),
            ),
            pause_resume_button=SimpleNamespace(
                set_text=MagicMock(),
                setVisible=MagicMock(),
            ),
            tr=lambda text: text,
        )

        FarmingInterfaceLeft._handle_desktop_clone_script_started(interface)

        self.assertTrue(interface._desktop_clone_task_started_from_root)
        interface._disable_setting.assert_not_called()

    def test_active_clone_stop_ignores_changed_config_toggle(self):
        from app.farming_interface import FarmingInterfaceLeft

        controller = MagicMock()
        interface = SimpleNamespace(
            link_start_button=SimpleNamespace(
                get_text=lambda: "S t o p !",
                set_text=MagicMock(),
                button=SimpleNamespace(setEnabled=MagicMock()),
            ),
            _desktop_clone_task_requested=True,
            desktop_clone_controller=controller,
            _stop_in_progress=False,
            stop_script=MagicMock(),
            tr=lambda text: text,
        )

        FarmingInterfaceLeft.start_and_stop_tasks(interface)

        controller.request_task_stop.assert_called_once_with()
        interface.stop_script.assert_not_called()

    def test_active_local_stop_ignores_changed_config_toggle(self):
        from app.farming_interface import FarmingInterfaceLeft

        interface = SimpleNamespace(
            link_start_button=SimpleNamespace(get_text=lambda: "S t o p !"),
            _desktop_clone_task_requested=False,
            desktop_clone_controller=MagicMock(),
            _stop_in_progress=False,
            stop_script=MagicMock(),
        )

        FarmingInterfaceLeft.start_and_stop_tasks(interface)

        interface.stop_script.assert_called_once_with()
        interface.desktop_clone_controller.request_task_stop.assert_not_called()

    def test_manual_clone_stop_never_executes_exit_aalc_action(self):
        from app.farming_interface import FarmingInterfaceLeft

        controller = MagicMock()
        interface = SimpleNamespace(
            _desktop_clone_task_requested=True,
            _desktop_clone_task_started_from_root=False,
            desktop_clone_controller=controller,
            _restore_after_desktop_clone_task=MagicMock(),
            tr=lambda text: text,
        )
        with patch(
            "app.farming_interface.cfg.get_value",
            return_value=["exit_aalc"],
        ):
            FarmingInterfaceLeft._handle_desktop_clone_script_finished(
                interface,
                "stopped",
                "",
            )

        controller.shutdown_session.assert_not_called()


class ChildGameLaunchTests(unittest.TestCase):
    def test_child_steam_launch_error_propagates_to_task(self):
        from module.game_and_screen.game import Game
        from module.game_and_screen.steam import SteamSessionConflictError

        game = SimpleNamespace(
            check_game_alive=lambda: False,
            game_path=__file__,
            game_path_exists=True,
            process_name="LimbusCompany.exe",
            log=MagicMock(),
        )
        context = SimpleNamespace(is_child_session=True, current_session_id=77)
        with (
            patch("module.game_and_screen.game.get_instance_context", return_value=context),
            patch(
                "module.game_and_screen.steam.launch_limbus_via_steam",
                side_effect=SteamSessionConflictError("wrong session"),
            ),self.assertRaises(SteamSessionConflictError)
        ):
            Game.start_game(game)


if __name__ == "__main__":
    unittest.main()
