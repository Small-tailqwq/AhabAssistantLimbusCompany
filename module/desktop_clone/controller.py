"""Root-process lifecycle controller for the Windows Child Session."""

from __future__ import annotations

import subprocess
import threading
import time
from contextlib import suppress
from enum import Enum

from PySide6.QtCore import QObject, Signal
from qfluentwidgets import isDarkTheme, qconfig

from module.config import cfg
from module.desktop_clone.autorun_guard import (
    restore_logon_autoruns,
    suppress_logon_autoruns,
)
from module.desktop_clone.host_build import get_desktop_clone_host_executable
from module.desktop_clone.ipc import PipeConnection, PipeServer, build_pipe_name
from module.desktop_clone.launcher import launch_child_aalc
from module.desktop_clone.messages import translate_message, translate_remote_message
from module.desktop_clone.native import (
    build_remote_control_warning,
    check_compatibility,
    child_sessions_enabled_during_current_logon,
    clear_child_sessions_enabled_for_current_logon,
    enable_child_sessions,
    get_child_session_id,
    get_configured_rdp_port,
    is_child_sessions_enabled,
    logoff_child_session,
    mark_child_sessions_enabled_for_current_logon,
)
from module.desktop_clone.profile import prepare_child_profile
from module.desktop_clone.protocol import (
    PROTOCOL_VERSION,
    ROLE_CHILD_SESSION,
    ROLE_RDP_HOST,
    decode_text,
    encode_text,
)
from module.desktop_clone.state_sync import apply_child_state_delta
from module.instance_context import get_instance_context
from module.logger import log

_CONNECTION_TIMEOUT_SECONDS = 120.0
_TOOL_IDS = ("mute", "input")


class DesktopCloneState(str, Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    LAUNCHING_CHILD = "launching-child"
    READY = "ready"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class DesktopCloneController(QObject):
    state_changed = Signal(str, str)
    error_occurred = Signal(str)
    script_started = Signal()
    script_finished = Signal(str, str)
    pause_changed = Signal(bool)
    visibility_changed = Signal(bool)
    tool_state_changed = Signal(str, bool)

    def __init__(self):
        super().__init__()
        context = get_instance_context()
        if not context.is_root:
            raise RuntimeError("DesktopCloneController 只能在 root AALC 中创建")

        self.pipe_name = build_pipe_name()
        self.state = DesktopCloneState.IDLE
        self._status_source = "桌面分身尚未启动"
        self._status_args: tuple[object, ...] = ()
        self.child_session_id: int | None = None
        self._server: PipeServer | None = None
        self._helper_process: subprocess.Popen | None = None
        self._helper_connection: PipeConnection | None = None
        self._child_connection: PipeConnection | None = None
        self._pending_task_start = False
        self._task_completion_pending = False
        self._expected_child_shutdown = False
        self._expected_helper_shutdown = False
        self._operation_lock = threading.RLock()
        self._shutdown_lock = threading.Lock()
        self._child_ready_event = threading.Event()
        self._helper_launch_idle_event = threading.Event()
        self._helper_launch_idle_event.set()
        self._child_launch_idle_event = threading.Event()
        self._child_launch_idle_event.set()
        self._script_idle_event = threading.Event()
        self._script_idle_event.set()
        self._child_disconnected_event = threading.Event()
        self._helper_logged_off_event = threading.Event()
        self._connection_timer: threading.Timer | None = None
        self._autorun_restore_timer: threading.Timer | None = None
        self._cancel_requested = threading.Event()
        qconfig.themeChanged.connect(self._sync_host_theme)
        # 修复上次运行崩溃遗留的自启动抑制（有标记文件才会动注册表）。
        self._restore_autoruns_quietly()

    @property
    def is_session_active(self) -> bool:
        return (
            self.child_session_id is not None
            or self._helper_connection is not None
            or self._child_connection is not None
            or self._helper_process is not None
        )

    @property
    def is_lifecycle_active(self) -> bool:
        return self.is_session_active or self.state in {
            DesktopCloneState.CONNECTING,
            DesktopCloneState.LAUNCHING_CHILD,
            DesktopCloneState.READY,
            DesktopCloneState.RUNNING,
            DesktopCloneState.STOPPING,
        }

    @property
    def is_task_active(self) -> bool:
        return (
            self._pending_task_start
            and self.state
            in {
                DesktopCloneState.CONNECTING,
                DesktopCloneState.LAUNCHING_CHILD,
            }
        ) or self.state in {
            DesktopCloneState.RUNNING,
            DesktopCloneState.STOPPING,
        }

    @property
    def status_text(self) -> str:
        return translate_message(self._status_source, *self._status_args)

    def _set_state(
        self,
        state: DesktopCloneState,
        source: str,
        *args: object,
    ) -> None:
        self.state = state
        self._status_source = source
        self._status_args = args
        text = self.status_text
        log.info(text)
        self.state_changed.emit(state.value, text)

    def _fail(self, source: str, *args: object) -> None:
        with self._operation_lock:
            self._cancel_connection_timer()
            self._pending_task_start = False
            self._task_completion_pending = False
            self._set_state(DesktopCloneState.ERROR, source, *args)
            text = self.status_text
        log.error("桌面分身进入错误状态：%s", text)
        self.error_occurred.emit(text)

    def _task_start_block_reason(self) -> str | None:
        """Return a user-facing reason while holding ``_operation_lock``."""
        if (
            self.state == DesktopCloneState.STOPPING
            or self._expected_child_shutdown
            or self._expected_helper_shutdown
        ):
            self._pending_task_start = False
            self._cancel_requested.set()
            return translate_message(
                "桌面分身正在停止，请等待注销完成后重试"
            )
        if self.state == DesktopCloneState.ERROR:
            if self.is_session_active:
                self._pending_task_start = False
                self._cancel_requested.set()
                return translate_message(
                    "桌面分身仍有残留会话，请先执行“停止任务并注销分身”"
                )
        return None

    def remote_control_warning(self) -> str | None:
        """Pre-start risk notice, or ``None`` when the user opted out of it."""
        if bool(cfg.get_value("desktop_clone_ignore_remote_control_warning", False)):
            return None
        return build_remote_control_warning()

    def compatibility_details(self) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
        result = check_compatibility()
        details = list(result.details)
        warnings = result.warnings
        if result.supported:
            existing_session_id = get_child_session_id()
            if (
                existing_session_id is not None
                and existing_session_id != self.child_session_id
            ):
                details.append(
                    translate_message(
                        "检测到非 AALC 管理的 Child Session {0}，"
                        "为避免注销其中的程序，AALC 不会接管。",
                        existing_session_id,
                    )
                )
                return False, tuple(details), warnings
            try:
                helper = get_desktop_clone_host_executable()
                details.append(translate_message("RDP 宿主可用：{0}。", helper.name))
            except Exception as exc:
                details.append(translate_message("RDP 宿主不可用：{0}", exc))
                return False, tuple(details), warnings
            try:
                from module.game_and_screen.steam import find_steam_executable

                steam = find_steam_executable()
                details.append(translate_message("Steam 可用：{0}。", steam))
            except Exception as exc:
                details.append(translate_message("Steam 不可用：{0}", exc))
                return False, tuple(details), warnings
        return result.supported, tuple(details), warnings

    def _ensure_server(self) -> None:
        if self._server is None:
            self._server = PipeServer(
                self.pipe_name,
                self._on_pipe_message,
                self._on_pipe_disconnect,
            )
        self._server.start()

    def start_session(self) -> None:
        with self._operation_lock:
            if self.is_session_active and self.state == DesktopCloneState.ERROR:
                self.error_occurred.emit(
                    translate_message(
                        "桌面分身仍有残留会话，请先执行“停止任务并注销分身”"
                    )
                )
                return
            if self.state in {
                DesktopCloneState.CONNECTING,
                DesktopCloneState.LAUNCHING_CHILD,
                DesktopCloneState.READY,
                DesktopCloneState.RUNNING,
                DesktopCloneState.STOPPING,
            }:
                return
            self._helper_logged_off_event.clear()
            self._child_disconnected_event.clear()
            self._child_ready_event.clear()
            self._cancel_requested.clear()
            # 预期退出标记属于单次会话。取消启动的路径会置位但不一定走到
            # _shutdown_session_owner 的收尾，残留的 True 会让下一次真正的
            # 宿主崩溃被 _monitor_helper 当成正常退出吞掉。
            self._expected_child_shutdown = False
            self._expected_helper_shutdown = False
            self._set_state(DesktopCloneState.CONNECTING, "正在创建 Windows Child Session")
            self._cancel_connection_timer()
            self._connection_timer = threading.Timer(
                _CONNECTION_TIMEOUT_SECONDS,
                self._connection_timeout,
            )
            self._connection_timer.daemon = True
            self._connection_timer.start()
            threading.Thread(
                target=self._start_session_worker,
                name="DesktopCloneStart",
                daemon=True,
            ).start()

    def _connection_timeout(self) -> None:
        if not self._child_ready_event.is_set() and self.state in {
            DesktopCloneState.CONNECTING,
            DesktopCloneState.LAUNCHING_CHILD,
        }:
            tail = self._child_startup_error_tail()
            source = (
                "桌面分身在 {0} 秒内未完成登录，已终止 RDP 宿主并清理 Child Session。"
                "若出现凭据窗口，请注销 Windows 后重新登录再试"
            )
            if tail:
                source += "；分身启动崩溃记录：\n{1}"
                args = (int(_CONNECTION_TIMEOUT_SECONDS), tail)
            else:
                args = (int(_CONNECTION_TIMEOUT_SECONDS),)
            self._fail_connection_and_cleanup(source, *args)

    @staticmethod
    def _child_startup_error_tail() -> str:
        """返回 Child AALC 启动崩溃记录（child-startup-error.txt）的最后几行。

        帮助区分“分身尚未连接”与“分身启动即崩溃”，否则超时报障只能靠
        用户手动翻文件。文件不存在或不可读时返回空字符串。
        """
        try:
            from module.desktop_clone.profile import child_profile_dir

            error_file = child_profile_dir() / "logs" / "child-startup-error.txt"
            if not error_file.is_file():
                return ""
            content = error_file.read_text(encoding="utf-8", errors="replace")
            return "\n".join(content.splitlines()[-8:])
        except Exception:
            return ""

    def _fail_connection_and_cleanup(self, source: str, *args: object) -> None:
        with self._operation_lock:
            if self.state in {
                DesktopCloneState.IDLE,
                DesktopCloneState.STOPPING,
            }:
                return
            if self.state == DesktopCloneState.ERROR and self._cancel_requested.is_set():
                return
            self._cancel_requested.set()
            self._fail(source, *args)
        threading.Thread(
            target=self._cleanup_failed_connection,
            args=(source, args),
            name="DesktopCloneFailureCleanup",
            daemon=True,
        ).start()

    def _cleanup_failed_connection(
        self,
        source: str,
        args: tuple[object, ...],
    ) -> None:
        if not self.shutdown_session(timeout=5.0):
            return
        with self._operation_lock:
            if self.state == DesktopCloneState.IDLE and not self.is_session_active:
                self._set_state(DesktopCloneState.ERROR, source, *args)

    def _cancel_connection_timer(self) -> None:
        timer = self._connection_timer
        self._connection_timer = None
        if timer is not None:
            timer.cancel()

    def _restore_autoruns_quietly(self) -> None:
        try:
            restore_logon_autoruns()
        except Exception as exc:
            log.warning(f"恢复登录自启动策略失败：{exc}")

    def _schedule_autorun_restore(self) -> None:
        """子会话登录后延时恢复 Run 键策略。

        explorer 在登录后约 10 秒才延迟处理启动项，恢复不能挂在子进程
        ready 上（热缓存下 6 秒就绪，实测撤销早于该窗口导致抑制失效）；
        与收尾、自愈路径幂等，先到先执行。
        """
        timer = self._autorun_restore_timer
        if timer is not None:
            timer.cancel()
        timer = threading.Timer(180.0, self._restore_autoruns_quietly)
        timer.daemon = True
        timer.name = "DesktopCloneAutorunRestore"
        self._autorun_restore_timer = timer
        timer.start()

    @staticmethod
    def _configured_toolbar_items() -> tuple[str, ...]:
        configured = cfg.get_value(
            "desktop_clone_toolbar_items",
            list(_TOOL_IDS),
        )
        if not isinstance(configured, list):
            configured = list(_TOOL_IDS)
        return tuple(tool_id for tool_id in _TOOL_IDS if tool_id in configured)

    def _start_session_worker(self) -> None:
        helper_process = None
        monitor_started = False
        self._helper_launch_idle_event.clear()
        try:
            compatible, details, warnings = self.compatibility_details()
            if not compatible:
                raise RuntimeError("；".join(details))
            for warning in warnings:
                log.warning(warning)
            self._ensure_server()
            if self._cancel_requested.is_set():
                return
            if get_child_session_id() is not None:
                raise RuntimeError(
                    "检测到已有 Child Session；"
                    "AALC 不会接管或注销其他程序创建的会话"
                )
            if child_sessions_enabled_during_current_logon():
                raise RuntimeError(
                    translate_message(
                        "Windows Child Session 已在本次登录后启用。"
                        "请注销 Windows 并重新登录后再启动桌面分身；"
                        "不要在凭据窗口中输入密码。"
                    )
                )
            if not is_child_sessions_enabled():
                # Persist the same-logon safety gate first. If enabling fails,
                # a false-positive relogon requirement is safer than launching
                # against a parent logon created before Child Sessions started.
                # 但 API 真正失败（如 Win32 调用出错）时应回滚标记，否则本次
                # 登录内后续启动都会被误判为"已启用"而要求无意义的重登。
                mark_child_sessions_enabled_for_current_logon()
                try:
                    enable_child_sessions()
                except Exception:
                    clear_child_sessions_enabled_for_current_logon()
                    raise
                raise RuntimeError(
                    translate_message(
                        "Windows Child Session 已成功启用。"
                        "请注销 Windows 并重新登录一次，使免凭据登录生效；"
                        "重新登录后无需再次设置。"
                    )
                )
            helper = get_desktop_clone_host_executable()
            show_on_start = bool(
                cfg.get_value("desktop_clone_show_on_start", True)
            )
            visible_toolbar_items = ",".join(
                self._configured_toolbar_items()
            )
            command = [
                str(helper),
                "--pipe-name",
                self.pipe_name,
                "--width",
                "1920",
                "--height",
                "1080",
                "--rdp-port",
                str(get_configured_rdp_port()),
                "--show",
                str(show_on_start).lower(),
                "--dark",
                str(isDarkTheme()).lower(),
                "--visible-tools",
                visible_toolbar_items,
                "--window-title",
                translate_message("AALC 桌面分身"),
                "--mute-text",
                translate_message("关闭声音"),
                "--input-text",
                translate_message("关闭输入"),
                "--connecting-text",
                translate_message("正在创建 AALC 桌面分身..."),
                "--disconnected-text",
                translate_message("AALC 桌面分身已断开"),
            ]
            if bool(cfg.get_value("desktop_clone_suppress_autoruns", True)):
                # 子会话是完整交互登录，explorer 会重放全部 Run 键自启动；
                # TS 初始程序对 Child Session 无效（客户端 SKU 实测被忽略），
                # 改为登录窗口期临时抑制 Run 键策略，连接后延时恢复。
                try:
                    stale_timer = self._autorun_restore_timer
                    if stale_timer is not None:
                        stale_timer.cancel()
                    suppress_logon_autoruns()
                    log.info(
                        "已临时抑制登录自启动（Run 键策略），连接后延时自动恢复"
                    )
                except Exception as exc:
                    self._restore_autoruns_quietly()
                    log.warning(
                        "抑制登录自启动失败，子会话将带自启动运行：%s",
                        exc,
                    )
            if self._cancel_requested.is_set():
                self._restore_autoruns_quietly()
                return
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            helper_process = subprocess.Popen(
                command,
                cwd=str(helper.parent),
                creationflags=creation_flags,
            )
            with self._operation_lock:
                self._helper_process = helper_process
            threading.Thread(
                target=self._monitor_helper,
                args=(helper_process,),
                name="DesktopCloneHostMonitor",
                daemon=True,
            ).start()
            monitor_started = True
            if self._cancel_requested.is_set():
                self._restore_autoruns_quietly()
                # 取消发生在 Popen 之后：宿主已注册但无人回收，必须由生成方
                # 终止，否则留下孤儿 Child Session 宿主。先标记预期退出，避免
                # _monitor_helper 把这次主动终止当成意外退出而进入错误态。
                self._expected_helper_shutdown = True
                with suppress(Exception):
                    helper_process.terminate()
        except Exception as exc:
            self._restore_autoruns_quietly()
            if helper_process is not None and not monitor_started:
                with suppress(Exception):
                    helper_process.terminate()
            if self._cancel_requested.is_set():
                log.info("已取消启动桌面分身")
                return
            log.exception("启动桌面分身失败")
            self._fail("启动桌面分身失败：{0}", exc)
        finally:
            self._helper_launch_idle_event.set()

    def _monitor_helper(self, process: subprocess.Popen) -> None:
        return_code = process.wait()
        if self._helper_process is not process:
            return
        self._helper_process = None
        if not self._expected_helper_shutdown and self.state not in {
            DesktopCloneState.IDLE,
            DesktopCloneState.ERROR,
        }:
            self._fail_connection_and_cleanup(
                "RDP 桌面分身宿主意外退出（exit={0}）",
                return_code,
            )

    def request_task_start(self) -> None:
        with self._operation_lock:
            blocked_reason = self._task_start_block_reason()
            if self.state == DesktopCloneState.RUNNING or self._pending_task_start:
                return
        if blocked_reason is not None:
            self.error_occurred.emit(blocked_reason)
            return
        if bool(cfg.get_value("simulator", False)):
            self._fail("模拟器模式不需要且不支持桌面分身")
            return
        try:
            from module.game_and_screen.steam import ensure_steam_available_in_session
            from module.session_process import process_is_running

            expected_steam_session = (
                self.child_session_id
                if self.child_session_id is not None
                else -1
            )
            ensure_steam_available_in_session(expected_steam_session)
            if process_is_running(
                cfg.get_value("game_process_name", "LimbusCompany.exe"),
                get_instance_context().current_session_id,
            ):
                raise RuntimeError(
                    translate_message(
                        "《边狱公司》已在主桌面运行，请先退出游戏后再启动桌面分身。"
                    )
                )
        except Exception as exc:
            self._fail(str(exc))
            return
        with self._operation_lock:
            blocked_reason = self._task_start_block_reason()
            if self.state == DesktopCloneState.RUNNING or self._pending_task_start:
                return
            if blocked_reason is not None:
                self.error_occurred.emit(blocked_reason)
                return
            self._pending_task_start = True
            self._task_completion_pending = True
            self._cancel_requested.clear()
            self._script_idle_event.clear()
            if self.state == DesktopCloneState.READY and self._child_connection is not None:
                self._set_state(
                    DesktopCloneState.LAUNCHING_CHILD,
                    "正在同步配置并启动分身任务",
                )
                threading.Thread(
                    target=self._refresh_profile_and_start,
                    name="DesktopCloneTaskStart",
                    daemon=True,
                ).start()
                return
            self.start_session()

    def _refresh_profile_and_start(self) -> None:
        try:
            if self._cancel_requested.is_set():
                return
            prepare_child_profile()
            with self._operation_lock:
                if (
                    self._cancel_requested.is_set()
                    or not self._pending_task_start
                ):
                    return
                connection = self._child_connection
                if connection is None:
                    raise RuntimeError(translate_message("Child AALC 尚未连接"))
            connection.send_with_timeout(1.0, "reload-start")
        except Exception as exc:
            if self._cancel_requested.is_set():
                log.info("取消桌面分身启动时忽略配置同步异常")
                return
            log.exception("同步桌面分身配置失败")
            self._fail_connection_and_cleanup(
                "同步桌面分身配置失败：{0}",
                exc,
            )

    def request_task_stop(self) -> None:
        cancel_pending_start = False
        with self._operation_lock:
            if self._pending_task_start:
                self._pending_task_start = False
                self._cancel_requested.set()
                self._set_state(
                    DesktopCloneState.STOPPING,
                    "正在取消分身启动",
                )
                cancel_pending_start = True
        if cancel_pending_start:
            threading.Thread(
                target=self._cancel_pending_task_worker,
                name="DesktopCloneTaskCancel",
                daemon=True,
            ).start()
            return
        connection = self._child_connection
        if connection is None:
            self._fail("Child AALC 尚未连接，无法停止任务")
            return
        try:
            self._pending_task_start = False
            self._set_state(DesktopCloneState.STOPPING, "正在请求分身任务安全停止")
            connection.send_with_timeout(1.0, "stop")
        except Exception as exc:
            self._fail("请求分身任务停止失败：{0}", exc)

    def _cancel_pending_task_worker(self) -> None:
        stopped = self.shutdown_session(timeout=5.0)
        if not stopped:
            self._fail("取消分身启动时未能确认 Child Session 已注销")

    def request_pause_toggle(self) -> None:
        connection = self._child_connection
        if connection is None or self.state != DesktopCloneState.RUNNING:
            return
        try:
            connection.send_with_timeout(1.0, "toggle-pause")
        except Exception as exc:
            self._fail("切换分身任务暂停状态失败：{0}", exc)

    def show_desktop(self) -> None:
        if self._helper_connection is None:
            self.start_session()
            return
        self._send_helper_command("show")

    def hide_desktop(self) -> None:
        self._send_helper_command("hide")

    def set_toolbar_tool_visible(self, tool_id: str, visible: bool) -> None:
        if tool_id not in _TOOL_IDS:
            raise ValueError(f"未知桌面分身快捷工具：{tool_id}")
        self._send_helper_command(
            "tool-visible",
            tool_id,
            "1" if visible else "0",
        )

    def _sync_host_theme(self, *_args) -> None:
        self._send_helper_command(
            "theme",
            "dark" if isDarkTheme() else "light",
        )

    def _sync_host_texts(self) -> None:
        self._send_helper_command(
            "ui-text",
            encode_text(translate_message("AALC 桌面分身")),
            encode_text(translate_message("关闭声音")),
            encode_text(translate_message("关闭输入")),
            encode_text(
                translate_message("正在创建 AALC 桌面分身...")
            ),
            encode_text(translate_message("AALC 桌面分身已断开")),
        )

    def retranslateUi(self) -> None:
        self._sync_host_texts()

    def _send_helper_command(self, *parts: str) -> bool:
        connection = self._helper_connection
        if connection is None:
            return False
        try:
            connection.send(*parts)
        except Exception as exc:
            log.warning("向桌面分身窗口发送 %s 失败：%s", parts[0], exc)
            return False
        return True

    def shutdown_session(self, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + max(0.0, timeout)
        acquired = self._shutdown_lock.acquire(
            timeout=max(0.0, deadline - time.monotonic())
        )
        if not acquired:
            log.error(
                "获取桌面分身停止锁超时（%.2fs），本次注销中止",
                timeout,
            )
            return False
        try:
            self._cancel_requested.set()
            acquired = self._operation_lock.acquire(
                timeout=max(0.0, deadline - time.monotonic())
            )
            if not acquired:
                log.error(
                    "获取桌面分身操作锁超时（%.2fs），本次注销中止",
                    timeout,
                )
                return False
            try:
                if self.state == DesktopCloneState.IDLE and not self.is_session_active:
                    return True
            finally:
                self._operation_lock.release()
            return self._shutdown_session_owner(deadline)
        finally:
            self._shutdown_lock.release()

    def _shutdown_session_owner(self, deadline: float) -> bool:
        def remaining(limit: float | None = None) -> float:
            duration = max(0.0, deadline - time.monotonic())
            return duration if limit is None else min(duration, limit)

        def send_for_shutdown(
            connection: PipeConnection,
            *parts: str,
        ) -> bool:
            timeout = remaining(0.5)
            if timeout <= 0:
                return False
            try:
                connection.send_with_timeout(timeout, *parts)
            except Exception as exc:
                log.warning(
                    "桌面分身停止时发送 %s 失败：%s",
                    parts[0],
                    exc,
                )
                with suppress(Exception):
                    connection.close()
                return False
            return True

        acquired = self._operation_lock.acquire(timeout=remaining())
        if not acquired:
            return False
        try:
            should_stop_script = not self._script_idle_event.is_set()
            self._cancel_connection_timer()
            self._pending_task_start = False
            self._cancel_requested.set()
            self._expected_child_shutdown = True
            self._expected_helper_shutdown = True
            self._set_state(
                DesktopCloneState.STOPPING,
                "正在请求分身任务安全停止",
            )
        finally:
            self._operation_lock.release()
        # 先等启动线程走完：它在 finally 里置位，届时 _helper_process 必已注册
        # （或已自行回收）。不等待就读取会拿到尚未写入的 None，导致宿主残留。
        # 同样要早于恢复 Run 键，避免恢复跑在抑制之前而让抑制泄漏到下次登录。
        def wait_with_log(event: threading.Event, timeout: float, stage: str) -> None:
            if not event.wait(timeout=max(0.0, timeout)):
                log.warning("停止桌面分身：等待%s超时（%.2fs）", stage, timeout)

        wait_with_log(
            self._helper_launch_idle_event,
            remaining(0.75),
            "RDP 宿主启动线程结束",
        )
        # 无论后续收尾是否超时，先恢复 Run 键策略（幂等，无标记时不动注册表）。
        self._restore_autoruns_quietly()
        try:
            notify_task_stopped = False
            wait_with_log(
                self._child_launch_idle_event,
                remaining(0.75),
                "Child AALC 启动线程结束",
            )
            child_connection = self._child_connection
            if child_connection is not None:
                if should_stop_script:
                    send_for_shutdown(child_connection, "stop")
                    wait_with_log(
                        self._script_idle_event,
                        remaining(3.0),
                        "Child AALC 任务停止",
                    )
                send_for_shutdown(child_connection, "shutdown")
                wait_with_log(
                    self._child_disconnected_event,
                    remaining(0.75),
                    "Child AALC 断开",
                )

            helper_connection = self._helper_connection
            if helper_connection is not None:
                send_for_shutdown(helper_connection, "logoff")
                wait_with_log(
                    self._helper_logged_off_event,
                    remaining(0.5),
                    "RDP 宿主确认注销",
                )

            actual_session_id = get_child_session_id()
            if (
                self.child_session_id is not None
                and actual_session_id == self.child_session_id
            ):
                try:
                    logoff_child_session(self.child_session_id, wait=False)
                except Exception as exc:
                    log.warning(
                        "注销 Child Session %s 失败：%s",
                        self.child_session_id,
                        exc,
                    )
            logoff_failure_logged = False
            while remaining() > 0:
                actual_session_id = get_child_session_id()
                if actual_session_id is None:
                    break
                if (
                        self.child_session_id is not None
                        and actual_session_id == self.child_session_id
                    ):
                        try:
                            logoff_child_session(
                                self.child_session_id,
                                wait=False,
                            )
                        except Exception as exc:
                            if not logoff_failure_logged:
                                logoff_failure_logged = True
                                log.warning(
                                    "注销 Child Session %s 持续失败：%s",
                                    self.child_session_id,
                                    exc,
                                )
                time.sleep(min(0.1, remaining()))

            actual_session_id = get_child_session_id()
            stopped = actual_session_id is None
            helper_process = self._helper_process
            if helper_process is not None:
                if helper_process.poll() is None:
                    if stopped:
                        helper_process.terminate()
                        with suppress(subprocess.TimeoutExpired):
                            helper_process.wait(timeout=remaining(0.75))
                    else:
                        log.warning(
                            "注销 Child Session 失败，RDP 宿主进程保持运行（pid=%s）",
                            helper_process.pid,
                        )
                if helper_process.poll() is None:
                    stopped = False
                else:
                    self._helper_process = None
        except Exception:
            log.exception("清理桌面分身会话失败")
            stopped = False

        acquired = self._operation_lock.acquire(timeout=remaining())
        if not acquired:
            log.error("获取桌面分身操作锁超时，注销收尾中止")
            return False
        try:
            if stopped:
                notify_task_stopped = self._task_completion_pending
                self._task_completion_pending = False
                self._helper_connection = None
                self._child_connection = None
                self.child_session_id = None
                self._child_ready_event.clear()
                self._script_idle_event.set()
                self._set_state(DesktopCloneState.IDLE, "桌面分身已停止")
            else:
                # 若此前已进入 ERROR，保留原始诊断（如 RDP 登录失败的具体
                # stage/code），不要被笼统的清理超时文本覆盖。
                if self.state != DesktopCloneState.ERROR:
                    self._set_state(
                        DesktopCloneState.ERROR,
                        "桌面分身尚未确认注销",
                    )
            self._expected_child_shutdown = False
            self._expected_helper_shutdown = False
        finally:
            self._operation_lock.release()
        if stopped and notify_task_stopped:
            self.script_finished.emit("stopped", "")
        return stopped

    def stop_transport(self) -> None:
        if self._server is not None:
            self._server.stop()
            self._server = None

    def _on_pipe_message(self, connection: PipeConnection, message: list[str]) -> None:
        if connection.role is None:
            self._handle_hello(connection, message)
            return
        if connection.role == ROLE_RDP_HOST:
            if connection is not self._helper_connection:
                log.info("忽略已替换的 RDP 宿主管道消息")
                return
            self._handle_helper_message(message)
        elif connection.role == ROLE_CHILD_SESSION:
            if connection is not self._child_connection:
                log.info("忽略已替换的 Child AALC 管道消息")
                return
            self._handle_child_message(message, connection)

    def _handle_hello(self, connection: PipeConnection, message: list[str]) -> None:
        if len(message) != 3 or message[0] != "hello" or message[2] != PROTOCOL_VERSION:
            log.warning(
                "拒绝桌面分身管道 hello（协议不匹配）："
                "peer_pid=%s，peer_session=%s，消息=%s",
                connection.peer_process_id,
                connection.peer_session_id,
                message,
            )
            connection.close()
            return
        role = message[1]
        if role == ROLE_RDP_HOST:
            if connection.peer_session_id != get_instance_context().current_session_id:
                log.warning(
                    "拒绝 RDP 宿主管道 hello：peer_session=%s 与主会话 %s 不符",
                    connection.peer_session_id,
                    get_instance_context().current_session_id,
                )
                connection.close()
                return
            old_connection = self._helper_connection
            self._helper_connection = connection
        elif role == ROLE_CHILD_SESSION:
            if (
                self.child_session_id is None
                or connection.peer_session_id != self.child_session_id
            ):
                log.warning(
                    "拒绝 Child AALC 管道 hello：peer_session=%s，期望 %s，"
                    "peer_pid=%s",
                    connection.peer_session_id,
                    self.child_session_id,
                    connection.peer_process_id,
                )
                connection.close()
                return
            old_connection = self._child_connection
            self._child_connection = connection
            self._child_disconnected_event.clear()
        else:
            log.warning(
                "拒绝桌面分身管道 hello（未知角色）：%s，peer_pid=%s",
                role,
                connection.peer_process_id,
            )
            connection.close()
            return
        connection.role = role
        log.info(
            "桌面分身管道已连接：role=%s, peer_pid=%s, peer_session=%s",
            role,
            connection.peer_process_id,
            connection.peer_session_id,
        )
        if old_connection is not None and old_connection is not connection:
            old_connection.close()
        if role == ROLE_RDP_HOST:
            self._sync_host_theme()
            self._sync_host_texts()
            visible_tools = set(self._configured_toolbar_items())
            for tool_id in _TOOL_IDS:
                self.set_toolbar_tool_visible(
                    tool_id,
                    tool_id in visible_tools,
                )

    def _handle_helper_message(self, message: list[str]) -> None:
        command = message[0]
        if command in {
            "rdp-retrying",
            "rdp-failed",
            "rdp-disconnected",
            "error",
        } and (
            self._cancel_requested.is_set()
            or self._expected_helper_shutdown
            or self.state == DesktopCloneState.STOPPING
        ):
            log.info("桌面分身停止期间忽略 RDP 宿主消息：%s", command)
            return
        if command == "rdp-connected" and len(message) == 2:
            try:
                reported_session_id = int(message[1])
            except ValueError:
                self._fail_connection_and_cleanup(
                    "RDP 宿主上报了无效的 Child Session ID：{0}",
                    message[1],
                )
                return
            actual_session_id = get_child_session_id()
            if (
                self._cancel_requested.is_set()
                or self._expected_helper_shutdown
                or self.state == DesktopCloneState.STOPPING
            ):
                if actual_session_id == reported_session_id:
                    self.child_session_id = reported_session_id
                if self._helper_connection is not None:
                    with suppress(Exception):
                        self._helper_connection.send("logoff")
                return
            if actual_session_id != reported_session_id:
                self._fail_connection_and_cleanup(
                    "RDP 宿主上报了错误 Child Session：reported={0}, actual={1}",
                    reported_session_id,
                    actual_session_id,
                )
                return
            self.child_session_id = reported_session_id
            self._set_state(
                DesktopCloneState.LAUNCHING_CHILD,
                "Child Session {0} 已连接，正在启动 AALC",
                reported_session_id,
            )
            self._schedule_autorun_restore()
            threading.Thread(
                target=self._launch_child_worker,
                name="DesktopCloneChildLaunch",
                daemon=True,
            ).start()
        elif command == "shown":
            self.visibility_changed.emit(True)
        elif command == "hidden":
            self.visibility_changed.emit(False)
        elif (
            command == "tool-state"
            and len(message) == 3
            and message[1] in _TOOL_IDS
            and message[2] in {"0", "1"}
        ):
            self.tool_state_changed.emit(message[1], message[2] == "1")
        elif command == "logged-off":
            self._helper_logged_off_event.set()
        elif command == "rdp-diagnostic" and len(message) >= 3:
            log.info(
                "RDP 宿主诊断：%s=%s",
                message[1],
                message[2],
            )
        elif command == "rdp-transport-connected":
            if (
                self.state == DesktopCloneState.CONNECTING
                and not self._cancel_requested.is_set()
            ):
                self._set_state(
                    DesktopCloneState.CONNECTING,
                    "RDP 已连接，正在等待 Windows 完成 Child Session 登录",
                )
        elif command == "rdp-login-complete":
            log.info("RDP ActiveX 已完成 Child Session 登录")
        elif command == "rdp-retrying" and len(message) >= 7:
            retry_number = message[1]
            delay_seconds = message[2]
            stage = message[3]
            error_code = message[4]
            extended_error_code = message[5]
            description = translate_remote_message(decode_text(message[6]))
            log.warning(
                "RDP Child Session 首次连接失败，%s 秒后重试"
                "（%s/3，stage=%s，code=%s，extended=%s）：%s",
                delay_seconds,
                retry_number,
                stage,
                error_code,
                extended_error_code,
                description,
            )
            self._set_state(
                DesktopCloneState.CONNECTING,
                "桌面分身首次初始化尚未完成，{0} 秒后自动重试（{1}/3）",
                delay_seconds,
                retry_number,
            )
        elif command == "rdp-failed" and len(message) >= 5:
            stage = message[1]
            error_code = message[2]
            extended_error_code = message[3]
            description = translate_remote_message(decode_text(message[4]))
            self._fail_connection_and_cleanup(
                "RDP Child Session 连接失败"
                "（stage={0}, code={1}, extended={2}）：{3}",
                stage,
                error_code,
                extended_error_code,
                description,
            )
        elif command == "rdp-disconnected":
            if not self._expected_helper_shutdown:
                reason = message[1] if len(message) > 1 else "unknown"
                self._fail_connection_and_cleanup(
                    "RDP 桌面分身意外断开（reason={0}）",
                    reason,
                )
        elif command == "error" and len(message) == 2:
            self._fail_connection_and_cleanup(
                translate_remote_message(decode_text(message[1]))
            )

    def _launch_child_worker(self) -> None:
        launch_slot_acquired = False
        try:
            if self._cancel_requested.is_set():
                return
            child_session_id = self.child_session_id
            if child_session_id is None:
                raise RuntimeError(
                    translate_message("Windows 未返回 Child Session ID")
                )
            # 重开分身时保留分身内配置；root 发起任务的两条路径都会经
            # _refresh_profile_and_start 强制刷新快照，显式同步不受影响。
            profile = prepare_child_profile(refresh_config=False)
            with self._operation_lock:
                if self._cancel_requested.is_set():
                    return
                self._child_launch_idle_event.clear()
                launch_slot_acquired = True
            launch_child_aalc(
                child_session_id,
                self.pipe_name,
                profile,
                self._cancel_requested.is_set,
            )
        except Exception as exc:
            if self._cancel_requested.is_set():
                log.info("已取消在 Child Session 启动 AALC")
                return
            log.exception("在 Child Session 启动 AALC 失败")
            self._fail_connection_and_cleanup(
                "在 Child Session 启动 AALC 失败：{0}",
                exc,
            )
        finally:
            if launch_slot_acquired:
                self._child_launch_idle_event.set()

    def _handle_child_message(
        self,
        message: list[str],
        connection: PipeConnection | None = None,
    ) -> None:
        command = message[0]
        if command == "log" and len(message) == 2:
            forwarded = decode_text(message[1])
            if bool(cfg.get_value("desktop_clone_sync_logs", True)):
                from module.logger.my_log import ui_log_dispatcher

                ui_log_dispatcher.append_line(
                    translate_message("[分身] {0}", forwarded)
                )
            # 同时以 DEBUG 级写入 root 文件日志（不进 UI 环形缓冲），
            # 避免用户重启 root 或日志被挤出缓冲后 child 侧证据丢失。
            log.debug("[分身] %s", forwarded)
        elif command == "audio-prime" and len(message) == 3:
            detail = decode_text(message[2])
            if message[1] == "ready":
                log.info("Child Session 音频端点预热完成（%s）", detail)
            elif message[1] == "failed":
                log.warning("Child Session 音频端点预热失败（%s）", detail)
        elif command == "ready":
            with self._operation_lock:
                self._cancel_connection_timer()
                self._child_ready_event.set()
                if (
                    self.state in {
                        DesktopCloneState.ERROR,
                        DesktopCloneState.STOPPING,
                    }
                    or self._expected_child_shutdown
                    or self._expected_helper_shutdown
                    or self._cancel_requested.is_set()
                ):
                    log.info(
                        "忽略迟到的分身就绪消息（state=%s, peer_pid=%s）",
                        self.state.value,
                        connection.peer_process_id
                        if connection is not None
                        else "unknown",
                    )
                    return
                self._set_state(DesktopCloneState.READY, "分身 AALC 已就绪")
                if self._pending_task_start:
                    self._set_state(
                        DesktopCloneState.LAUNCHING_CHILD,
                        "正在同步配置并启动分身任务",
                    )
                    threading.Thread(
                        target=self._refresh_profile_and_start,
                        name="DesktopClonePendingTaskStart",
                        daemon=True,
                    ).start()
        elif command == "script-started":
            if (
                self._cancel_requested.is_set()
                or self._expected_child_shutdown
                or self.state == DesktopCloneState.STOPPING
            ):
                log.info("桌面分身停止期间忽略迟到的任务启动消息")
                return
            self._pending_task_start = False
            self._script_idle_event.clear()
            self._set_state(DesktopCloneState.RUNNING, "分身任务运行中")
            self.script_started.emit()
        elif command == "script-result":
            outcome = message[1] if len(message) > 1 else "failed"
            if outcome not in {"success", "stopped", "failed"}:
                outcome = "failed"
            detail = decode_text(message[2]) if len(message) > 2 else ""
            # 陈旧性检查必须先于状态增量应用：被替换连接的消息不得写入
            # root 持久配置（apply_child_state_delta 会 set_value）。
            with self._operation_lock:
                if (
                    connection is not None
                    and connection is not self._child_connection
                ):
                    log.info("忽略已替换 Child AALC 的迟到任务结果")
                    return
            try:
                if len(message) < 4:
                    raise ValueError(
                        translate_message("分身任务结果缺少状态增量")
                    )
                apply_child_state_delta(decode_text(message[3]))
            except Exception as exc:
                with self._operation_lock:
                    stopping_session = (
                        self._cancel_requested.is_set()
                        or self._expected_child_shutdown
                        or self._expected_helper_shutdown
                        or self.state
                        in {
                            DesktopCloneState.IDLE,
                            DesktopCloneState.ERROR,
                        }
                    )
                    self._script_idle_event.set()
                if stopping_session:
                    log.exception("停止桌面分身时同步任务状态失败")
                    return
                self._fail_connection_and_cleanup(
                    "同步分身任务状态失败：{0}",
                    exc,
                )
                return
            with self._operation_lock:
                self._pending_task_start = False
                self._script_idle_event.set()
                if (
                    self._cancel_requested.is_set()
                    or self._expected_child_shutdown
                    or self._expected_helper_shutdown
                    or self.state
                    in {
                        DesktopCloneState.IDLE,
                        DesktopCloneState.ERROR,
                    }
                ):
                    log.info("桌面分身注销期间只接收任务状态增量")
                    return
                if self.state not in {
                    DesktopCloneState.RUNNING,
                    DesktopCloneState.LAUNCHING_CHILD,
                    DesktopCloneState.STOPPING,
                }:
                    log.info(
                        "在状态 %s 忽略无对应任务的结果",
                        self.state.value,
                    )
                    return
                self._set_state(
                    DesktopCloneState.READY,
                    "分身任务已停止"
                    if outcome == "stopped"
                    else "分身任务已完成"
                    if outcome == "success"
                    else "分身任务已结束：{0}",
                    *(() if outcome != "failed" else (detail,)),
                )
                self._task_completion_pending = False
            self.script_finished.emit(outcome, detail)
        elif command == "pause-state" and len(message) == 2:
            self.pause_changed.emit(message[1] == "1")
        elif command == "error" and len(message) == 2:
            if (
                self._cancel_requested.is_set()
                or self._expected_child_shutdown
                or self.state == DesktopCloneState.STOPPING
            ):
                log.info("桌面分身停止期间忽略 Child AALC 错误消息")
                return
            self._fail_connection_and_cleanup(
                translate_remote_message(decode_text(message[1]))
            )
        elif command == "toast" and len(message) == 4:
            template_name = message[1]
            title = decode_text(message[2])
            content = decode_text(message[3])
            if template_name not in {"normal", "test"}:
                log.debug("忽略未知通知模板：%s", template_name)
                return
            try:
                from app.windows_toast import TemplateToast, send_toast

                template = (
                    TemplateToast.NormalTemplate
                    if template_name == "normal"
                    else TemplateToast.TestTemplate
                )
                send_toast(title, content, template=template)
            except Exception:
                log.exception("展示 Child Session 透传通知失败")

    def _on_pipe_disconnect(self, connection: PipeConnection) -> None:
        if connection is self._child_connection:
            self._child_connection = None
            self._child_disconnected_event.set()
            log.info(
                "Child AALC 管道断开（peer_pid=%s, expected=%s）",
                connection.peer_process_id,
                self._expected_child_shutdown,
            )
            if not self._expected_child_shutdown and self.state not in {
                DesktopCloneState.IDLE,
                DesktopCloneState.ERROR,
            }:
                tail = self._child_startup_error_tail()
                source = "Child AALC 意外断开（peer_pid={0}）"
                args: tuple[object, ...] = (connection.peer_process_id,)
                if tail:
                    source += "；分身启动崩溃记录：\n{1}"
                    args = (connection.peer_process_id, tail)
                self._fail_connection_and_cleanup(source, *args)
        elif connection is self._helper_connection:
            self._helper_connection = None
            log.info(
                "RDP 宿主管道断开（peer_pid=%s, expected=%s）",
                connection.peer_process_id,
                self._expected_helper_shutdown,
            )
            if not self._expected_helper_shutdown and self.state not in {
                DesktopCloneState.IDLE,
                DesktopCloneState.ERROR,
            }:
                self._fail_connection_and_cleanup(
                    "RDP 桌面分身宿主连接已断开"
                )


_controller: DesktopCloneController | None = None
_controller_lock = threading.Lock()


def get_desktop_clone_controller() -> DesktopCloneController:
    global _controller
    with _controller_lock:
        if _controller is None:
            _controller = DesktopCloneController()
            from app.language_manager import LanguageManager

            LanguageManager().register_component(_controller)
        return _controller
