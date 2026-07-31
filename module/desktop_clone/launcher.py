"""Launch the child AALC into the active Windows Child Session."""

from __future__ import annotations

import getpass
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Callable

import pythoncom
import pywintypes
import win32api
import win32com.client

from module.desktop_clone.native import get_child_session_id
from module.logger import log

_TASK_ACTION_EXECUTE = 0
_TASK_CREATE = 2
_TASK_LOGON_INTERACTIVE_TOKEN = 3
_TASK_RUN_LEVEL_HIGHEST = 1
_TASK_RUN_USE_SESSION_ID = 0x4

_TASK_STATE_QUEUED = 2
_TASK_START_TIMEOUT_SECONDS = 15.0
_TASK_STATE_POLL_SECONDS = 0.2


def _wait_until_task_leaves_queue(running_task, ensure_not_cancelled) -> int | None:
    """Block until the task engine has actually acted on the queued run.

    ``RunEx`` only enqueues the run; the engine creates the process afterwards.
    Deleting the task definition while the run is still queued races that
    creation and can drop the launch entirely, with nothing written anywhere.
    """
    deadline = time.monotonic() + _TASK_START_TIMEOUT_SECONDS
    state = None
    while time.monotonic() < deadline:
        ensure_not_cancelled()
        try:
            state = int(running_task.State)
        except pywintypes.com_error as exc:
            # COM 层出错（调度器异常、RPC 中断）与“引擎已释放 run 对象”
            # 完全不是一回事；后者才是正常离开排队状态的信号。
            log.warning(
                "读取 Child Session 启动任务状态失败（HRESULT=%s），"
                "不能确认引擎已释放运行实例",
                getattr(exc, "hresult", None),
            )
            raise
        except Exception:
            # The engine releases the run object once the action has started.
            return state
        if state != _TASK_STATE_QUEUED:
            return state
        time.sleep(_TASK_STATE_POLL_SECONDS)
    return state


def _application_launch_command(
    expected_session_id: int,
    pipe_name: str,
    profile_dir: Path,
) -> tuple[Path, str, Path]:
    child_arguments = [
        "--aalc-instance",
        "child-session",
        "--expected-session-id",
        str(expected_session_id),
        "--desktop-clone-pipe",
        pipe_name,
        "--desktop-clone-profile",
        str(profile_dir),
    ]
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        arguments = subprocess.list2cmdline(child_arguments)
        return executable, arguments, executable.parent

    main_script = Path(__file__).resolve().parents[2] / "main.py"
    executable = Path(sys.executable).resolve()
    arguments = subprocess.list2cmdline([str(main_script), *child_arguments])
    return executable, arguments, main_script.parent


def _account_name() -> str:
    try:
        return win32api.GetUserNameEx(2)
    except Exception as exc:
        account = getpass.getuser()
        log.warning(
            "GetUserNameEx 失败，回退使用 %s 作为任务账号：%s",
            account,
            exc,
        )
        return account


def launch_child_aalc(
    child_session_id: int,
    pipe_name: str,
    profile_dir: Path,
    is_cancelled: Callable[[], bool] | None = None,
) -> None:
    def ensure_not_cancelled() -> None:
        if is_cancelled is not None and is_cancelled():
            raise RuntimeError("桌面分身启动已取消")

    ensure_not_cancelled()
    actual_session_id = get_child_session_id()
    if actual_session_id != child_session_id:
        raise RuntimeError(
            f"目标 Child Session 已变化：expected={child_session_id}, actual={actual_session_id}"
        )

    executable, arguments, working_directory = _application_launch_command(
        child_session_id,
        pipe_name,
        profile_dir,
    )
    if not executable.is_file():
        raise FileNotFoundError(f"AALC 启动程序不存在: {executable}")

    task_name = f"AALC-DesktopClone-Launch-{uuid.uuid4().hex}"
    account_name = _account_name()
    pythoncom.CoInitialize()
    root_folder = None
    task_registered = False
    try:
        ensure_not_cancelled()
        scheduler = win32com.client.Dispatch("Schedule.Service")
        scheduler.Connect()
        ensure_not_cancelled()
        root_folder = scheduler.GetFolder("\\")
        task_definition = scheduler.NewTask(0)
        task_definition.RegistrationInfo.Author = "AALC"
        task_definition.RegistrationInfo.Description = (
            f"临时启动 AALC 到 Windows Child Session {child_session_id}"
        )
        task_definition.Settings.Enabled = True
        task_definition.Settings.Hidden = True
        task_definition.Settings.AllowDemandStart = True
        task_definition.Settings.DisallowStartIfOnBatteries = False
        task_definition.Settings.StopIfGoingOnBatteries = False
        task_definition.Settings.ExecutionTimeLimit = "PT0S"
        task_definition.Principal.UserId = account_name
        task_definition.Principal.LogonType = _TASK_LOGON_INTERACTIVE_TOKEN
        task_definition.Principal.RunLevel = _TASK_RUN_LEVEL_HIGHEST

        action = task_definition.Actions.Create(_TASK_ACTION_EXECUTE)
        action.Path = str(executable)
        action.Arguments = arguments
        action.WorkingDirectory = str(working_directory)

        ensure_not_cancelled()
        registered_task = root_folder.RegisterTaskDefinition(
            task_name,
            task_definition,
            _TASK_CREATE,
            account_name,
            None,
            _TASK_LOGON_INTERACTIVE_TOKEN,
        )
        task_registered = True
        ensure_not_cancelled()
        log.info(
            "已注册 Child Session 启动任务 %s，目标会话 %s",
            task_name,
            child_session_id,
        )
        running_task = registered_task.RunEx(
            None,
            _TASK_RUN_USE_SESSION_ID,
            int(child_session_id),
            # user 必须传 ""：pywin32 会把 None 编组成 Task Scheduler 拒绝的
            # BSTR，RunEx 直接返回 E_INVALIDARG；"" 表示“未指定用户”，任务
            # 会以已登录目标 Child Session 的当前用户身份交互式启动。
            "",
        )
        if running_task is None:
            raise RuntimeError("任务计划程序没有返回 Child Session 运行实例")
        state = _wait_until_task_leaves_queue(running_task, ensure_not_cancelled)
        if state == _TASK_STATE_QUEUED:
            raise RuntimeError(
                f"Child Session 启动任务在 {_TASK_START_TIMEOUT_SECONDS:.0f} 秒内"
                "仍处于排队状态，任务计划程序未创建分身进程"
            )
        log.info(
            "Child Session 启动任务已离开排队状态（state=%s），分身进程创建中",
            state if state is not None else "released",
        )
    finally:
        if task_registered and root_folder is not None:
            try:
                root_folder.DeleteTask(task_name, 0)
            except Exception as exc:
                log.warning(
                    "清理 Child Session 启动任务失败（task=%s）：%s",
                    task_name,
                    exc,
                )
        pythoncom.CoUninitialize()
