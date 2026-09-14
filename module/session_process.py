"""Process discovery constrained to one Windows Session."""

from __future__ import annotations

import os
from collections.abc import Iterator

import psutil

from module.instance_context import get_instance_context, get_process_session_id
from module.logger import log


def target_session_id() -> int:
    context = get_instance_context()
    return context.expected_session_id if context.is_child_session else context.current_session_id


def process_belongs_to_session(process_id: int, session_id: int | None = None) -> bool:
    if os.name != "nt":
        return True
    expected = target_session_id() if session_id is None else session_id
    try:
        return get_process_session_id(process_id) == expected
    except OSError:
        return False


def iter_processes_by_name(process_name: str, session_id: int | None = None) -> Iterator[psutil.Process]:
    expected_name = process_name.casefold()
    for process in psutil.process_iter(["name"]):
        try:
            actual_name = process.info.get("name") or ""
            if actual_name.casefold() != expected_name:
                continue
            if process_belongs_to_session(process.pid, session_id):
                yield process
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue


def process_sessions_by_name(process_name: str) -> list[tuple[int, int]]:
    expected_name = process_name.casefold()
    result: list[tuple[int, int]] = []
    for process in psutil.process_iter(["name"]):
        try:
            actual_name = process.info.get("name") or ""
            if actual_name.casefold() != expected_name:
                continue
            result.append((process.pid, get_process_session_id(process.pid)))
        except (OSError, psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
    return result


def process_is_running(process_name: str, session_id: int | None = None) -> bool:
    return next(iter_processes_by_name(process_name, session_id), None) is not None


def terminate_processes(process_name: str, session_id: int | None = None, timeout: float = 10.0) -> bool:
    processes = list(iter_processes_by_name(process_name, session_id))
    if not processes:
        return True
    for process in processes:
        try:
            process.terminate()
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess) as exc:
            log.warning(
                "终止进程 %s（pid=%s）失败：%s",
                process_name,
                process.pid,
                exc,
            )
    _, alive = psutil.wait_procs(processes, timeout=timeout)
    for process in alive:
        try:
            process.kill()
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess) as exc:
            log.warning(
                "强制结束进程 %s（pid=%s）失败：%s",
                process_name,
                process.pid,
                exc,
            )
    _, alive = psutil.wait_procs(alive, timeout=min(timeout, 5.0))
    if alive:
        log.warning(
            "进程 %s 仍有 %s 个未退出（session=%s）",
            process_name,
            len(alive),
            session_id if session_id is not None else target_session_id(),
        )
    return not alive
