"""Child AALC named-pipe client and Qt command bridge."""

from __future__ import annotations

import queue
import threading
from contextlib import suppress

import pywintypes
import win32file
from PySide6.QtCore import Qt, QThread, Signal

from module.desktop_clone.audio import prime_remote_audio
from module.desktop_clone.ipc import (
    begin_pipe_read,
    begin_pipe_write,
    cancel_pipe_io,
    connect_pipe,
    finish_pipe_read,
    finish_pipe_write,
)
from module.desktop_clone.messages import translate_message
from module.desktop_clone.protocol import (
    MAX_MESSAGE_BYTES,
    PROTOCOL_VERSION,
    ROLE_CHILD_SESSION,
    encode_text,
    parse_message,
    serialize_message,
)
from module.desktop_clone.state_sync import serialize_child_state_delta
from module.instance_context import get_instance_context
from module.logger import log
from module.my_error.my_error import userStopError

_LOG_QUEUE_LIMIT = 1000
_MAX_FORWARDED_LOG_BYTES = 24 * 1024


class DesktopCloneClient(QThread):
    command_received = Signal(str)
    root_connected = Signal()
    root_disconnected = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        context = get_instance_context()
        if not context.is_child_session or context.pipe_name is None:
            raise RuntimeError("DesktopCloneClient 只能在 Child Session AALC 中创建")
        self.pipe_name = context.pipe_name
        self.session_id = context.current_session_id
        self._handle = None
        self._handle_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._connected_event = threading.Event()
        self._log_queue: queue.Queue[str] = queue.Queue(
            maxsize=_LOG_QUEUE_LIMIT
        )
        self._log_drop_lock = threading.Lock()
        self._dropped_log_lines = 0
        self._log_dispatcher = None
        self._log_sender_thread: threading.Thread | None = None
        self._audio_primed = False
        self._last_connect_error: str | None = None
        self._lost_log_lines = 0
        self._lost_log_lock = threading.Lock()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                handle = connect_pipe(
                    self.pipe_name,
                    timeout_ms=5000,
                    cancelled=self._stop_event.is_set,
                )
                with self._handle_lock:
                    self._handle = handle
                log.info("已连接 root AALC 桌面分身管道（%s）", self.pipe_name)
                self._last_connect_error = None
                self._send("hello", ROLE_CHILD_SESSION, PROTOCOL_VERSION)
                if not self._audio_primed:
                    primed, detail = prime_remote_audio()
                    self._audio_primed = primed
                    self._send(
                        "audio-prime",
                        "ready" if primed else "failed",
                        encode_text(detail),
                    )
                self._send("ready", str(self.session_id))
                self._connected_event.set()
                self.root_connected.emit()
                self._read_commands(handle)
            except (OSError, pywintypes.error) as exc:
                # 首次失败与错误类型变化时记录；持续失败只记一次，避免每秒刷屏。
                # pywintypes.error 不是 OSError 子类，必须显式捕获，
                # 否则 connect_pipe 最常见的“管道不存在”会落入下方刷屏路径。
                # 日志转发依赖同一条管道，连不上时 root 只能看到这条记录。
                message = f"{type(exc).__name__}: {exc}"
                if message != self._last_connect_error:
                    self._last_connect_error = message
                    log.warning(
                        "连接 root AALC 桌面分身管道失败（%s）：%s",
                        self.pipe_name,
                        message,
                    )
            except Exception:
                if not self._stop_event.is_set():
                    log.exception("连接 root AALC 桌面分身管道失败")
            finally:
                self._connected_event.clear()
                self._close_handle()
                self.root_disconnected.emit()
            if not self._stop_event.is_set():
                self.msleep(1000)

    def _read_commands(self, handle) -> None:
        pending = bytearray()
        while not self._stop_event.is_set():
            with self._handle_lock:
                if self._handle is not handle:
                    return
                operation = begin_pipe_read(handle)
            chunk = finish_pipe_read(operation)
            if not chunk:
                return
            pending.extend(chunk)
            if len(pending) > MAX_MESSAGE_BYTES:
                raise ValueError("root AALC 管道消息超过大小限制")
            while b"\n" in pending:
                raw_line, _, remainder = pending.partition(b"\n")
                pending = bytearray(remainder)
                if raw_line:
                    message = parse_message(bytes(raw_line))
                    self.command_received.emit(message[0])

    def _send(self, *parts: str) -> None:
        payload = serialize_message(parts)
        with self._write_lock:
            with self._handle_lock:
                handle = self._handle
                if handle is None:
                    raise BrokenPipeError("root AALC 尚未连接")
                operation = begin_pipe_write(handle, payload)
            finish_pipe_write(operation, len(payload))

    def send_script_started(self) -> None:
        try:
            self._send("script-started")
        except Exception as exc:
            log.warning("未能向 root AALC 上报任务开始：%s", exc)

    def send_script_result(self, exception: BaseException | None) -> None:
        if exception is None:
            outcome = "success"
            detail = ""
        elif isinstance(exception, userStopError):
            outcome = "stopped"
            detail = ""
        else:
            outcome = "failed"
            detail = str(exception)
        try:
            self._send(
                "script-result",
                outcome,
                encode_text(detail),
                encode_text(serialize_child_state_delta()),
            )
        except Exception as exc:
            log.warning("未能向 root AALC 上报任务结果：%s", exc)

    def send_stopped_before_start(self) -> None:
        try:
            self._send(
                "script-result",
                "stopped",
                encode_text(""),
                encode_text(serialize_child_state_delta()),
            )
        except Exception as exc:
            log.warning("未能向 root AALC 上报启动取消：%s", exc)

    def send_pause_state(self, paused: bool) -> None:
        try:
            self._send("pause-state", "1" if paused else "0")
        except Exception:
            log.debug("未能向 root AALC 上报暂停状态")

    def send_error(self, message: str) -> None:
        try:
            self._send("error", encode_text(message))
        except Exception:
            log.debug("未能向 root AALC 上报错误")

    def send_toast(self, template: str, title: str, msg_lines: list[str]) -> None:
        """把通知透传给 root AALC，在主会话展示 Windows Toast。

        Args:
            template: 通知模板名，取值 "normal" 或 "test"。
            title: 通知标题（已翻译）。
            msg_lines: 通知内容行（已翻译）。
        """
        try:
            self._send(
                "toast",
                template,
                encode_text(title),
                encode_text("\n".join(msg_lines)),
            )
        except Exception:
            log.debug("未能向 root AALC 转发通知")

    def install_log_forwarding(self, dispatcher) -> None:
        if self._log_dispatcher is dispatcher:
            return
        if self._log_dispatcher is not None:
            raise RuntimeError("桌面分身日志转发器已经安装")
        self._log_dispatcher = dispatcher
        dispatcher.new_lines.connect(
            self._enqueue_log_lines,
            Qt.ConnectionType.DirectConnection,
        )
        self._log_sender_thread = threading.Thread(
            target=self._forward_logs,
            name="DesktopCloneLogForwarder",
            daemon=True,
        )
        self._log_sender_thread.start()

    def _enqueue_log_lines(self, lines: list[str]) -> None:
        if self._stop_event.is_set():
            return
        for line in lines:
            normalized = self._truncate_log_line(str(line))
            try:
                self._log_queue.put_nowait(normalized)
            except queue.Full:
                with suppress(queue.Empty):
                    self._log_queue.get_nowait()
                with self._log_drop_lock:
                    self._dropped_log_lines += 1
                with suppress(queue.Full):
                    self._log_queue.put_nowait(normalized)

    @staticmethod
    def _truncate_log_line(line: str) -> str:
        encoded = line.encode("utf-8")
        if len(encoded) <= _MAX_FORWARDED_LOG_BYTES:
            return line
        truncated = encoded[:_MAX_FORWARDED_LOG_BYTES]
        return truncated.decode("utf-8", errors="ignore") + "…"

    def _forward_logs(self) -> None:
        while not self._stop_event.is_set():
            if not self._connected_event.wait(timeout=0.2):
                continue
            try:
                line = self._log_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            with self._log_drop_lock:
                dropped = self._dropped_log_lines
                self._dropped_log_lines = 0
            with self._lost_log_lock:
                lost = self._lost_log_lines
                self._lost_log_lines = 0
            try:
                if dropped:
                    self._send(
                        "log",
                        encode_text(
                            translate_message(
                                "[日志同步] 队列已丢弃较早的 {0} 条日志",
                                dropped,
                            )
                        ),
                    )
                if lost:
                    self._send(
                        "log",
                        encode_text(
                            translate_message(
                                "[日志同步] 管道断开期间丢失 {0} 条日志",
                                lost,
                            )
                        ),
                    )
                self._send("log", encode_text(line))
            except Exception:
                # 管道断开会由主客户端线程负责重连；日志转发不能反向写日志，
                # 否则可能形成自激循环。发送失败的行计入丢失计数，
                # 重连成功后再补发一条标记消息，避免 root 侧日志流出现
                # 无法解释的空洞。
                with self._lost_log_lock:
                    self._lost_log_lines += 1
                continue

    def stop_client(self) -> None:
        self._stop_event.set()
        self._connected_event.set()
        self._close_handle()
        dispatcher = self._log_dispatcher
        self._log_dispatcher = None
        if dispatcher is not None:
            with suppress(RuntimeError, TypeError):
                dispatcher.new_lines.disconnect(self._enqueue_log_lines)
        sender = self._log_sender_thread
        self._log_sender_thread = None
        if sender is not None and sender is not threading.current_thread():
            sender.join(timeout=1.0)

    def _close_handle(self) -> None:
        with self._handle_lock:
            handle = self._handle
            self._handle = None
        if handle is not None:
            with suppress(OSError):
                cancel_pipe_io(handle)
            with suppress(pywintypes.error):
                win32file.CloseHandle(handle)


_client_instance: DesktopCloneClient | None = None
_client_lock = threading.Lock()


def register_desktop_clone_client(client: DesktopCloneClient) -> None:
    """注册 Child Session AALC 的管道客户端单例。

    由 main.py 在创建客户端后调用；供 windows_toast 等非 UI 模块转发通知。
    """
    global _client_instance
    with _client_lock:
        _client_instance = client


def get_desktop_clone_client() -> DesktopCloneClient | None:
    with _client_lock:
        return _client_instance
