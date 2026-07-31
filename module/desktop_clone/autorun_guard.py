"""Temporarily suppress explorer logon autoruns while the child session logs on.

Child sessions perform a full interactive logon, so their explorer replays every
Run-key autostart of the user and machine (single-instance apps then pop errors
or activate their main-session windows). The TS "initial program" path is
ignored for child sessions on client SKUs, so instead the root process sets the
per-user explorer policies DisableLocalMachineRun / DisableCurrentUserRun (and
the RunOnce variants) right before creating the child session and restores them
once the child AALC is ready. Explorer only reads these policies at shell
startup, so the already-running main session is unaffected. A marker file keeps
the original values so a crashed run can be healed later; while the marker
exists, repeated suppress calls never overwrite the original snapshot.
"""

from __future__ import annotations

import json
import os
import winreg
from contextlib import suppress
from pathlib import Path

from module.logger import log

_POLICY_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
_POLICY_VALUES = (
    "DisableLocalMachineRun",
    "DisableLocalMachineRunOnce",
    "DisableCurrentUserRun",
    "DisableCurrentUserRunOnce",
)


def _marker_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("无法取得 LOCALAPPDATA，不能记录自启动抑制状态")
    return Path(local_app_data) / "AALC" / "desktop-clone" / ".autorun-guard.json"


def _read_previous_values() -> dict[str, int | None]:
    previous: dict[str, int | None] = {}
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        _POLICY_SUBKEY,
        0,
        winreg.KEY_READ | winreg.KEY_WRITE,
    ) as key:
        for name in _POLICY_VALUES:
            try:
                value, value_type = winreg.QueryValueEx(key, name)
            except FileNotFoundError:
                previous[name] = None
                continue
            if value_type != winreg.REG_DWORD:
                raise RuntimeError(
                    f"Explorer Run 策略值 {name} 不是 DWORD，跳过自启动抑制"
                )
            previous[name] = int(value)
    return previous


def suppress_logon_autoruns() -> bool:
    """在子会话登录前抑制 Run 键自启动；已处于抑制状态时保持原始快照不变。"""
    marker = _marker_path()
    if marker.is_file():
        return True
    previous = _read_previous_values()
    marker.parent.mkdir(parents=True, exist_ok=True)
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps(previous), encoding="ascii")
    temporary.replace(marker)
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        _POLICY_SUBKEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        for name in _POLICY_VALUES:
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 1)
    return True


def restore_logon_autoruns() -> None:
    """恢复 Run 键策略到抑制前的原始值；没有抑制记录时不做任何事。"""
    marker = _marker_path()
    if not marker.is_file():
        return
    previous = json.loads(marker.read_text(encoding="ascii"))
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        _POLICY_SUBKEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        for name in _POLICY_VALUES:
            prior = previous.get(name)
            if prior is None:
                with suppress(FileNotFoundError, OSError):
                    winreg.DeleteValue(key, name)
            else:
                winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, int(prior))
    marker.unlink(missing_ok=True)
    log.info("已恢复登录自启动（Run 键策略）")
