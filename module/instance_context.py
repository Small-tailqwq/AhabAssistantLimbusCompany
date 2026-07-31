"""Process-role and Windows Session context resolved before project singletons load."""

from __future__ import annotations

import ctypes
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT_ROLE = "root"
CHILD_SESSION_ROLE = "child-session"

_ROLE_ARGUMENT = "--aalc-instance"
_SESSION_ARGUMENT = "--expected-session-id"
_PIPE_ARGUMENT = "--desktop-clone-pipe"
_PROFILE_ARGUMENT = "--desktop-clone-profile"


def _argument_value(argv: Sequence[str], name: str) -> str | None:
    try:
        index = argv.index(name)
    except ValueError:
        return None
    if index + 1 >= len(argv):
        return None
    return argv[index + 1]


def get_process_session_id(process_id: int | None = None) -> int:
    """Return the Windows Session ID for a process."""
    if os.name != "nt":
        return 0

    session_id = ctypes.c_uint32()
    target_pid = os.getpid() if process_id is None else int(process_id)
    if not ctypes.windll.kernel32.ProcessIdToSessionId(target_pid, ctypes.byref(session_id)):
        raise ctypes.WinError()
    return int(session_id.value)


@dataclass(frozen=True)
class InstanceContext:
    role: str
    current_session_id: int
    expected_session_id: int | None = None
    pipe_name: str | None = None
    profile_dir: Path | None = None

    @property
    def is_root(self) -> bool:
        return self.role == ROOT_ROLE

    @property
    def is_child_session(self) -> bool:
        return self.role == CHILD_SESSION_ROLE

    def validate(self) -> None:
        if self.role not in {ROOT_ROLE, CHILD_SESSION_ROLE}:
            raise ValueError(f"未知 AALC 实例角色: {self.role}")
        if not self.is_child_session:
            return
        if self.expected_session_id is None:
            raise ValueError("Child Session 实例缺少 --expected-session-id")
        if self.pipe_name is None:
            raise ValueError("Child Session 实例缺少 --desktop-clone-pipe")
        if self.profile_dir is None:
            raise ValueError("Child Session 实例缺少 --desktop-clone-profile")
        if self.current_session_id != self.expected_session_id:
            raise RuntimeError(
                f"Child Session 实例启动到了错误会话："
                f"expected={self.expected_session_id}, actual={self.current_session_id}"
            )


def parse_instance_context(argv: Sequence[str] | None = None) -> InstanceContext:
    args = list(sys.argv if argv is None else argv)
    role = _argument_value(args, _ROLE_ARGUMENT) or ROOT_ROLE
    expected_raw = _argument_value(args, _SESSION_ARGUMENT)
    if expected_raw is not None:
        try:
            expected_session_id = int(expected_raw)
        except ValueError as exc:
            raise ValueError(
                f"非法 --expected-session-id: {expected_raw!r}"
            ) from exc
    else:
        expected_session_id = None
    pipe_name = _argument_value(args, _PIPE_ARGUMENT)
    profile_raw = _argument_value(args, _PROFILE_ARGUMENT)
    profile_dir = Path(profile_raw).expanduser().resolve() if profile_raw else None
    return InstanceContext(
        role=role,
        current_session_id=get_process_session_id(),
        expected_session_id=expected_session_id,
        pipe_name=pipe_name,
        profile_dir=profile_dir,
    )


_instance_context = parse_instance_context()


def get_instance_context() -> InstanceContext:
    return _instance_context
