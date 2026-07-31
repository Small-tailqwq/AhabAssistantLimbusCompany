"""Narrow Windows APIs used by the desktop-clone lifecycle."""

from __future__ import annotations

import ctypes
import os
import platform
import socket
import winreg
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

import psutil

from module.desktop_clone.messages import translate_message
from module.logger import log

_ERROR_NOT_FOUND = 1168
_NO_CHILD_SESSION_ID = 0xFFFFFFFF
_DEFAULT_RDP_PORT = 3389
_TERMINAL_SERVER_REGISTRY_PATH = (
    r"SYSTEM\CurrentControlSet\Control\Terminal Server"
)
_RDP_REGISTRY_PATH = r"SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp"
_TOKEN_QUERY = 0x0008
_TOKEN_STATISTICS_INFORMATION_CLASS = 10
# 只有能主动抢占活动桌面的交互式进程才提示。常驻后台服务由
# _REMOTE_CONTROL_SERVICE_PROCESS_LABELS 处理，用户通常无法彻底退出。
_REMOTE_CONTROL_PROCESS_LABELS = {
    "todesk.exe": "ToDesk",
    "gameviewer.exe": "UU远程",
    "gameviewerserver.exe": "UU远程",
    "mumuremotebackend.exe": "MuMu远程",
}
_REMOTE_CONTROL_SERVICE_PROCESS_LABELS = {
    "todesk_service.exe": "ToDesk",
    "gameviewerservice.exe": "UU远程",
    "mumuremotehealthd.exe": "MuMu远程",
    "mumuremoteservice.exe": "MuMu远程",
}


class _Luid(ctypes.Structure):
    _fields_ = [
        ("low_part", wintypes.DWORD),
        ("high_part", wintypes.LONG),
    ]


class _TokenStatistics(ctypes.Structure):
    _fields_ = [
        ("token_id", _Luid),
        ("authentication_id", _Luid),
        ("expiration_time", ctypes.c_longlong),
        ("token_type", ctypes.c_int),
        ("impersonation_level", ctypes.c_int),
        ("dynamic_charged", wintypes.DWORD),
        ("dynamic_available", wintypes.DWORD),
        ("group_count", wintypes.DWORD),
        ("privilege_count", wintypes.DWORD),
        ("modified_id", _Luid),
    ]


class DesktopCloneNativeError(OSError):
    pass


def _require_windows() -> None:
    if os.name != "nt":
        raise RuntimeError("桌面分身仅支持 Windows。")


def _wts_api():
    _require_windows()
    api = ctypes.WinDLL("wtsapi32", use_last_error=True)
    api.WTSEnableChildSessions.argtypes = [wintypes.BOOL]
    api.WTSEnableChildSessions.restype = wintypes.BOOL
    api.WTSIsChildSessionsEnabled.argtypes = [ctypes.POINTER(wintypes.BOOL)]
    api.WTSIsChildSessionsEnabled.restype = wintypes.BOOL
    api.WTSGetChildSessionId.argtypes = [ctypes.POINTER(wintypes.DWORD)]
    api.WTSGetChildSessionId.restype = wintypes.BOOL
    api.WTSLogoffSession.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL]
    api.WTSLogoffSession.restype = wintypes.BOOL
    return api


def _last_error(operation: str) -> DesktopCloneNativeError:
    error = ctypes.get_last_error()
    return DesktopCloneNativeError(
        error,
        translate_message(
            "{0}（Win32 错误 {1}）",
            translate_message(operation),
            error,
        ),
    )


def set_child_sessions_enabled(enabled: bool) -> None:
    if not _wts_api().WTSEnableChildSessions(enabled):
        operation = (
            "无法启用 Windows Child Session"
            if enabled
            else "无法禁用 Windows Child Session"
        )
        raise _last_error(operation)


def enable_child_sessions() -> None:
    set_child_sessions_enabled(True)


def disable_child_sessions() -> None:
    set_child_sessions_enabled(False)


def is_child_sessions_enabled() -> bool:
    enabled = wintypes.BOOL()
    if not _wts_api().WTSIsChildSessionsEnabled(ctypes.byref(enabled)):
        raise _last_error("无法读取 Windows Child Session 状态")
    return bool(enabled.value)


def get_child_session_id() -> int | None:
    session_id = wintypes.DWORD()
    if not _wts_api().WTSGetChildSessionId(ctypes.byref(session_id)):
        error = ctypes.get_last_error()
        if error == _ERROR_NOT_FOUND:
            return None
        raise _last_error("无法取得 Windows Child Session ID")
    if session_id.value == _NO_CHILD_SESSION_ID:
        return None
    return int(session_id.value)


def logoff_child_session(session_id: int, wait: bool = False) -> int:
    if not _wts_api().WTSLogoffSession(None, session_id, wait):
        raise _last_error(
            translate_message("无法注销 Child Session {0}", session_id)
        )
    return session_id


def get_configured_rdp_port() -> int:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _RDP_REGISTRY_PATH) as key:
            port, _ = winreg.QueryValueEx(key, "PortNumber")
            port = int(port)
            if 0 < port <= 65535:
                return port
    except (OSError, TypeError, ValueError) as exc:
        # 注册表不可读（权限/值异常）与“未配置”不能混为一谈：
        # 前者应提示用户查权限，而不是误导去改 RDP 设置。
        log.warning("读取 RDP 注册表端口失败，回退默认 %s：%s", _DEFAULT_RDP_PORT, exc)
    return _DEFAULT_RDP_PORT


def is_rdp_connections_enabled() -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            _TERMINAL_SERVER_REGISTRY_PATH,
        ) as key:
            disabled, _ = winreg.QueryValueEx(key, "fDenyTSConnections")
            return int(disabled) == 0
    except (OSError, TypeError, ValueError) as exc:
        log.warning("读取远程桌面启用状态失败：%s", exc)
        return False


def is_local_rdp_listener_available(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def get_current_logon_id() -> str:
    _require_windows()
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL

    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(
        kernel.GetCurrentProcess(),
        _TOKEN_QUERY,
        ctypes.byref(token),
    ):
        raise _last_error("无法读取当前 Windows 登录标识")
    try:
        statistics = _TokenStatistics()
        returned_length = wintypes.DWORD()
        if not advapi.GetTokenInformation(
            token,
            _TOKEN_STATISTICS_INFORMATION_CLASS,
            ctypes.byref(statistics),
            ctypes.sizeof(statistics),
            ctypes.byref(returned_length),
        ):
            raise _last_error("无法读取当前 Windows 登录标识")
        authentication_id = statistics.authentication_id
        return (
            f"{int(authentication_id.high_part) & 0xFFFFFFFF:08x}"
            f"{int(authentication_id.low_part):08x}"
        )
    finally:
        kernel.CloseHandle(token)


def _child_sessions_setup_marker_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError(
            translate_message(
                "无法取得 LOCALAPPDATA，不能记录 Child Session 初始化状态"
            )
        )
    return (
        Path(local_app_data)
        / "AALC"
        / "desktop-clone"
        / ".child-sessions-enabled-logon"
    )


def mark_child_sessions_enabled_for_current_logon() -> None:
    marker = _child_sessions_setup_marker_path()
    marker.parent.mkdir(parents=True, exist_ok=True)
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(get_current_logon_id(), encoding="ascii")
    temporary.replace(marker)


def clear_child_sessions_enabled_for_current_logon() -> None:
    """清除本次登录的 Child Session 启用标记（启用失败时回滚）。"""
    marker = _child_sessions_setup_marker_path()
    try:
        marker.unlink()
    except OSError:
        pass


def child_sessions_enabled_during_current_logon() -> bool:
    try:
        recorded_logon_id = _child_sessions_setup_marker_path().read_text(
            encoding="ascii"
        )
    except OSError:
        return False
    return recorded_logon_id.strip() == get_current_logon_id()


def get_windows_edition() -> str:
    try:
        return platform.win32_edition()
    except Exception:
        return ""


def is_home_edition() -> bool:
    return "home" in get_windows_edition().casefold()


def is_process_elevated() -> bool:
    _require_windows()
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _find_running_process_labels(labels: dict[str, str]) -> tuple[str, ...]:
    found: set[str] = set()
    for process in psutil.process_iter(["name"]):
        try:
            name = (process.info["name"] or "").casefold()
            label = labels.get(name)
            if label is not None:
                found.add(label)
        except (
            OSError,
            psutil.AccessDenied,
            psutil.NoSuchProcess,
            psutil.ZombieProcess,
        ):
            continue
    return tuple(sorted(found))


def find_running_remote_control_conflicts() -> tuple[str, ...]:
    """Interactive remote-control processes that can steal the active desktop."""
    return _find_running_process_labels(_REMOTE_CONTROL_PROCESS_LABELS)


def find_running_remote_control_services() -> tuple[str, ...]:
    """Background remote-control services; reported but never blocking."""
    return _find_running_process_labels(_REMOTE_CONTROL_SERVICE_PROCESS_LABELS)


def build_remote_control_warning() -> str | None:
    """User-facing risk notice, or ``None`` when nothing interactive is running."""
    conflicts = find_running_remote_control_conflicts()
    if not conflicts:
        return None
    return translate_message(
        "检测到正在运行的远程控制软件：{0}。"
        "Child Session 会成为新的活动桌面，远程控制画面可能被切换到分身；"
        "确认风险后可以继续启动。",
        translate_message("、").join(
            translate_message(label) for label in conflicts
        ),
    )


@dataclass(frozen=True)
class CompatibilityResult:
    supported: bool
    details: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def check_compatibility() -> CompatibilityResult:
    details: list[str] = []
    if os.name != "nt":
        return CompatibilityResult(
            False,
            (translate_message("桌面分身仅支持 Windows。"),),
        )

    release = platform.release()
    details.append(f"Windows {release} {get_windows_edition() or 'Unknown Edition'}")
    if is_home_edition():
        details.append(translate_message("Windows Home 未列入首发支持范围。"))
        return CompatibilityResult(False, tuple(details))
    if not is_process_elevated():
        details.append(
            translate_message("当前进程没有管理员权限，无法启用 Child Session。")
        )
        return CompatibilityResult(False, tuple(details))

    try:
        enabled = is_child_sessions_enabled()
        details.append(
            translate_message(
                "Child Session API 可用，当前状态：{0}。",
                translate_message("已启用" if enabled else "未启用"),
            )
        )
    except Exception as exc:
        details.append(translate_message("Child Session API 不可用：{0}", exc))
        return CompatibilityResult(False, tuple(details))

    if not is_rdp_connections_enabled():
        details.append(
            translate_message(
                "Windows 远程桌面连接未启用，无法创建本机 Child Session。"
            )
        )
        return CompatibilityResult(False, tuple(details))

    rdp_port = get_configured_rdp_port()
    details.append(
        translate_message("RDP 端口：{0}。", rdp_port)
    )
    if not is_local_rdp_listener_available(rdp_port):
        details.append(
            translate_message(
                "RDP 本机端口 {0} 未监听，请检查 Remote Desktop Services。",
                rdp_port,
            )
        )
        return CompatibilityResult(False, tuple(details))

    remote_control_services = find_running_remote_control_services()
    if remote_control_services:
        details.append(
            translate_message(
                "检测到远程控制后台服务：{0}。"
                "这类服务通常常驻且难以彻底退出，不会阻止桌面分身启动。",
                translate_message("、").join(
                    translate_message(label) for label in remote_control_services
                ),
            )
        )

    # 远程控制软件只是风险提示，不再阻止启动：用户可能正坐在本机操作。
    warnings: list[str] = []
    remote_control_warning = build_remote_control_warning()
    if remote_control_warning is not None:
        warnings.append(remote_control_warning)
    return CompatibilityResult(True, tuple(details), tuple(warnings))
