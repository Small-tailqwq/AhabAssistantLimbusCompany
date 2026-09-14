"""Current-user-only named-pipe transport for desktop-clone processes."""

from __future__ import annotations

import _winapi
import ctypes
import os
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from ctypes import wintypes

import pywintypes
import win32api
import win32con
import win32event
import win32file
import win32pipe
import win32security

from module.desktop_clone.messages import translate_message
from module.desktop_clone.protocol import MAX_MESSAGE_BYTES, parse_message, serialize_message
from module.instance_context import get_process_session_id
from module.logger import log

_ERROR_PIPE_CONNECTED = 535
_ERROR_NOT_FOUND = 1168
_ERROR_OPERATION_ABORTED = 995
_SDDL_REVISION_1 = 1
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CancelIoEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
_kernel32.CancelIoEx.restype = wintypes.BOOL


def begin_pipe_read(handle, size: int = 4096):
    operation, _ = _winapi.ReadFile(int(handle), size, overlapped=True)
    return operation


def finish_pipe_read(operation) -> bytes:
    transferred, error = operation.GetOverlappedResult(True)
    if error:
        raise ctypes.WinError(error)
    return bytes(operation.getbuffer()[:transferred])


def read_pipe(handle, size: int = 4096) -> bytes:
    return finish_pipe_read(begin_pipe_read(handle, size))


def begin_pipe_write(handle, payload: bytes):
    operation, _ = _winapi.WriteFile(int(handle), payload, overlapped=True)
    return operation


def finish_pipe_write(
    operation,
    expected_size: int,
    timeout: float | None = None,
) -> None:
    if timeout is not None:
        wait_result = win32event.WaitForSingleObject(
            operation.event,
            max(0, int(timeout * 1000)),
        )
        if wait_result != win32con.WAIT_OBJECT_0:
            with suppress(OSError):
                operation.cancel()
            operation.GetOverlappedResult(True)
            if wait_result == win32con.WAIT_TIMEOUT:
                raise TimeoutError("桌面分身 IPC 写入超时")
            raise OSError(f"等待桌面分身 IPC 写入失败：{wait_result}")
    transferred, error = operation.GetOverlappedResult(True)
    if error:
        raise ctypes.WinError(error)
    if transferred != expected_size:
        raise OSError(
            translate_message(
                "桌面分身 IPC 写入不完整：{0}/{1}",
                transferred,
                expected_size,
            )
        )


def write_pipe(handle, payload: bytes) -> None:
    finish_pipe_write(begin_pipe_write(handle, payload), len(payload))


def cancel_pipe_io(handle) -> None:
    if _kernel32.CancelIoEx(int(handle), None):
        return
    error = ctypes.get_last_error()
    if error != _ERROR_NOT_FOUND:
        raise ctypes.WinError(error)


def current_user_sid_string() -> str:
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        sid, _ = win32security.GetTokenInformation(token, win32security.TokenUser)
        return win32security.ConvertSidToStringSid(sid)
    finally:
        token.Close()


def build_pipe_name() -> str:
    return f"AALC.v1.user-{current_user_sid_string()}.root"


def pipe_path(pipe_name: str) -> str:
    return rf"\\.\pipe\{pipe_name}"


def _security_attributes() -> pywintypes.SECURITY_ATTRIBUTES:
    sid = current_user_sid_string()
    descriptor = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
        f"D:P(D;;GA;;;NU)(A;;GA;;;{sid})",
        _SDDL_REVISION_1,
    )
    attributes = pywintypes.SECURITY_ATTRIBUTES()
    attributes.SECURITY_DESCRIPTOR = descriptor
    return attributes


def _named_pipe_client_pid(handle) -> int:
    pid = wintypes.ULONG()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetNamedPipeClientProcessId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
    kernel32.GetNamedPipeClientProcessId.restype = wintypes.BOOL
    if not kernel32.GetNamedPipeClientProcessId(int(handle), ctypes.byref(pid)):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(pid.value)


class PipeConnection:
    def __init__(self, handle):
        self.handle = handle
        self.peer_process_id = _named_pipe_client_pid(handle)
        self.peer_session_id = get_process_session_id(self.peer_process_id)
        self.role: str | None = None
        self._write_lock = threading.Lock()
        self._close_lock = threading.Lock()
        self._closed = threading.Event()

    @property
    def is_closed(self) -> bool:
        return self._closed.is_set()

    def send(self, *parts: str) -> None:
        payload = serialize_message(parts)
        with self._write_lock:
            with self._close_lock:
                if self._closed.is_set():
                    raise BrokenPipeError("桌面分身 IPC 已断开")
                operation = begin_pipe_write(self.handle, payload)
            finish_pipe_write(operation, len(payload))

    def send_with_timeout(self, timeout: float, *parts: str) -> None:
        payload = serialize_message(parts)
        deadline = time.monotonic() + max(0.0, timeout)
        acquired = self._write_lock.acquire(
            timeout=max(0.0, deadline - time.monotonic())
        )
        if not acquired:
            raise TimeoutError("等待桌面分身 IPC 写锁超时")
        try:
            with self._close_lock:
                if self._closed.is_set():
                    raise BrokenPipeError("桌面分身 IPC 已断开")
                operation = begin_pipe_write(self.handle, payload)
            finish_pipe_write(
                operation,
                len(payload),
                timeout=max(0.0, deadline - time.monotonic()),
            )
        finally:
            self._write_lock.release()

    def read(self, size: int = 4096) -> bytes:
        with self._close_lock:
            if self._closed.is_set():
                return b""
            operation = begin_pipe_read(self.handle, size)
        return finish_pipe_read(operation)

    def close(self) -> None:
        with self._close_lock:
            if self._closed.is_set():
                return
            self._closed.set()
            with suppress(OSError):
                cancel_pipe_io(self.handle)
            with suppress(pywintypes.error):
                win32pipe.DisconnectNamedPipe(self.handle)
            with suppress(pywintypes.error):
                win32file.CloseHandle(self.handle)


class PipeServer:
    def __init__(
        self,
        pipe_name: str,
        on_message: Callable[[PipeConnection, list[str]], None],
        on_disconnect: Callable[[PipeConnection], None],
    ):
        self.pipe_name = pipe_name
        self._on_message = on_message
        self._on_disconnect = on_disconnect
        self._stop_event = threading.Event()
        self._accept_thread: threading.Thread | None = None
        self._connections: set[PipeConnection] = set()
        self._connections_lock = threading.Lock()

    def start(self) -> None:
        if self._accept_thread and self._accept_thread.is_alive():
            return
        self._stop_event.clear()
        self._accept_thread = threading.Thread(
            target=self._accept_loop,
            name="DesktopClonePipeServer",
            daemon=True,
        )
        self._accept_thread.start()

    def _accept_loop(self) -> None:
        while not self._stop_event.is_set():
            handle = None
            try:
                handle = win32pipe.CreateNamedPipe(
                    pipe_path(self.pipe_name),
                    win32pipe.PIPE_ACCESS_DUPLEX | win32file.FILE_FLAG_OVERLAPPED,
                    win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
                    win32pipe.PIPE_UNLIMITED_INSTANCES,
                    MAX_MESSAGE_BYTES,
                    MAX_MESSAGE_BYTES,
                    5000,
                    _security_attributes(),
                )
                if self._stop_event.is_set():
                    win32file.CloseHandle(handle)
                    handle = None
                    break
                try:
                    operation = _winapi.ConnectNamedPipe(int(handle), overlapped=True)
                    _, error = operation.GetOverlappedResult(True)
                    if error:
                        raise ctypes.WinError(error)
                except OSError as exc:
                    if exc.winerror != _ERROR_PIPE_CONNECTED:
                        raise
                if self._stop_event.is_set():
                    win32file.CloseHandle(handle)
                    break
                connection = PipeConnection(handle)
                handle = None
                with self._connections_lock:
                    self._connections.add(connection)
                threading.Thread(
                    target=self._read_connection,
                    args=(connection,),
                    name=f"DesktopClonePipeClient-{connection.peer_process_id}",
                    daemon=True,
                ).start()
            except Exception:
                if not self._stop_event.is_set():
                    log.exception(
                        "桌面分身命名管道监听失败（%s）",
                        self.pipe_name,
                    )
                    # 持续失败（同名管道被占用、SDDL 异常）时退避重试，
                    # 避免 log.exception 刷屏与 100% CPU 忙循环。
                    time.sleep(1)
            finally:
                if handle is not None:
                    with suppress(pywintypes.error):
                        win32file.CloseHandle(handle)

    def _read_connection(self, connection: PipeConnection) -> None:
        pending = bytearray()
        try:
            while not self._stop_event.is_set() and not connection.is_closed:
                chunk = connection.read()
                if not chunk:
                    break
                pending.extend(chunk)
                if len(pending) > MAX_MESSAGE_BYTES:
                    raise ValueError("桌面分身 IPC 缓冲区超过长度上限")
                while b"\n" in pending:
                    raw_line, _, remainder = pending.partition(b"\n")
                    pending = bytearray(remainder)
                    if raw_line:
                        self._on_message(connection, parse_message(bytes(raw_line)))
        except OSError as exc:
            if getattr(exc, "winerror", None) not in (None, _ERROR_OPERATION_ABORTED):
                log.debug(
                    "桌面分身 IPC 读取异常：peer_pid=%s, winerror=%s, %s",
                    connection.peer_process_id,
                    getattr(exc, "winerror", None),
                    exc,
                )
        except Exception:
            log.exception(f"读取桌面分身 IPC 失败，peer_pid={connection.peer_process_id}")
        finally:
            connection.close()
            with self._connections_lock:
                self._connections.discard(connection)
            self._on_disconnect(connection)

    def stop(self) -> None:
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        try:
            handle = win32file.CreateFile(
                pipe_path(self.pipe_name),
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0,
                None,
                win32file.OPEN_EXISTING,
                0,
                None,
            )
            win32file.CloseHandle(handle)
        except pywintypes.error:
            pass
        with self._connections_lock:
            connections = list(self._connections)
        for connection in connections:
            connection.close()


def connect_pipe(
    pipe_name: str,
    timeout_ms: int = 10000,
    cancelled: Callable[[], bool] | None = None,
):
    if os.name != "nt":
        raise RuntimeError("桌面分身命名管道仅支持 Windows")
    path = pipe_path(pipe_name)
    deadline = time.monotonic() + timeout_ms / 1000
    last_error = None
    while time.monotonic() < deadline:
        if cancelled is not None and cancelled():
            raise InterruptedError("等待桌面分身命名管道已取消")
        try:
            remaining_ms = max(
                1,
                int((deadline - time.monotonic()) * 1000),
            )
            wait_slice_ms = 250 if cancelled is not None else 1000
            win32pipe.WaitNamedPipe(
                path,
                min(wait_slice_ms, remaining_ms, timeout_ms),
            )
            return win32file.CreateFile(
                path,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0,
                None,
                win32file.OPEN_EXISTING,
                win32file.FILE_FLAG_OVERLAPPED,
                None,
            )
        except pywintypes.error as exc:
            last_error = exc
            if cancelled is not None and cancelled():
                raise InterruptedError(
                    "等待桌面分身命名管道已取消"
                ) from exc
            time.sleep(0.05)
    if last_error is not None:
        raise last_error
    raise TimeoutError(f"等待桌面分身命名管道超时: {pipe_name}")
