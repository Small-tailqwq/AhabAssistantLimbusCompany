"""Steam launch path that preserves login state and verifies Windows Session ownership."""

from __future__ import annotations

import os
import subprocess
import winreg
from dataclasses import dataclass
from pathlib import Path

import psutil

from module.desktop_clone.messages import translate_message
from module.instance_context import get_process_session_id

STEAM_PROCESS_NAME = "steam.exe"
LIMBUS_STEAM_APP_ID = "1973530"


class SteamSessionConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class SteamProcessInfo:
    process_id: int
    session_id: int


def find_steam_executable() -> Path:
    candidates: list[Path] = []
    registry_values = (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamExe"),
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
    )
    for hive, key_path, value_name in registry_values:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                raw_value, _ = winreg.QueryValueEx(key, value_name)
        except OSError:
            continue
        value = Path(str(raw_value).replace("/", os.sep))
        candidates.append(value if value.suffix.casefold() == ".exe" else value / "steam.exe")

    program_files_x86 = os.environ.get("PROGRAMFILES(X86)")
    if program_files_x86:
        candidates.append(Path(program_files_x86) / "Steam" / "steam.exe")

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        translate_message("未找到 Steam.exe；桌面分身必须通过 Steam 完成账户验证")
    )


def steam_processes() -> list[SteamProcessInfo]:
    result: list[SteamProcessInfo] = []
    for process in psutil.process_iter(["name"]):
        try:
            if (process.info.get("name") or "").casefold() != STEAM_PROCESS_NAME:
                continue
            result.append(
                SteamProcessInfo(
                    process_id=process.pid,
                    session_id=get_process_session_id(process.pid),
                )
            )
        except (OSError, psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
    return result


def ensure_steam_available_in_session(expected_session_id: int) -> None:
    conflicts = [
        process
        for process in steam_processes()
        if process.session_id != expected_session_id
    ]
    if not conflicts:
        return
    conflict_text = ", ".join(
        f"PID {process.process_id}/Session {process.session_id}"
        for process in conflicts
    )
    raise SteamSessionConflictError(
        translate_message(
            "Steam 已在其他 Windows Session 运行，无法保证登录态和游戏进程进入桌面分身。"
            "请完全退出 Steam 后重试（{0}）。",
            conflict_text,
        )
    )


def launch_limbus_via_steam(expected_session_id: int) -> None:
    ensure_steam_available_in_session(expected_session_id)
    steam_executable = find_steam_executable()
    # 无论 Steam 是否已在目标 Session 中运行，都让 Steam 自己处理 -applaunch。
    # 这会复用同一 Windows 用户的 Steam 登录态，而不会绕过账户验证直接执行游戏 exe。
    subprocess.Popen(
        [str(steam_executable), "-applaunch", LIMBUS_STEAM_APP_ID],
        cwd=str(steam_executable.parent),
    )
