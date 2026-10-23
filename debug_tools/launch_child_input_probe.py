"""在活动 Child Session 启动输入通道诊断；无参数打开交互窗口。

构建：dotnet publish debug_tools/child_input_probe/ChildInputProbe.csproj -c Release
      -r win-x64 -o debug_tools/child_input_probe/publish
只读模式：--integrity / --gui；其他模式会向分身游戏发送测试输入。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pythoncom
import win32api
import win32com.client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from module.desktop_clone.native import get_child_session_id

TASK_ACTION_EXECUTE = 0
TASK_CREATE = 2
TASK_LOGON_INTERACTIVE_TOKEN = 3
TASK_RUN_LEVEL_HIGHEST = 1
TASK_RUN_USE_SESSION_ID = 0x4
TASK_STATE_QUEUED = 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--integrity", action="store_true")
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--gui", action="store_true")
    parser.add_argument("--route-zero", action="store_true")
    parser.add_argument("--route-mapped", action="store_true")
    parser.add_argument("--focused-route-zero", action="store_true")
    parser.add_argument("--focused-route-mapped", action="store_true")
    parser.add_argument("--focused-right-zero", action="store_true")
    parser.add_argument("--focused-right-mapped", action="store_true")
    parser.add_argument("--focused-sendinput-right", action="store_true")
    options = parser.parse_args()
    session_id = get_child_session_id()
    if session_id is None:
        message = "没有检测到活动的 AALC Child Session"
        raise RuntimeError(message)

    probe_root = Path(__file__).resolve().parent / "child_input_probe"
    executable = probe_root / "publish" / "ChildInputProbe.exe"
    probe_args = (
        ["--compare"]
        if options.compare
        else ["--integrity"]
        if options.integrity
        else ["--gui"]
        if options.gui
        else ["--route-zero"]
        if options.route_zero
        else ["--route-mapped"]
        if options.route_mapped
        else ["--focused-route-zero"]
        if options.focused_route_zero
        else ["--focused-route-mapped"]
        if options.focused_route_mapped
        else ["--focused-right-zero"]
        if options.focused_right_zero
        else ["--focused-right-mapped"]
        if options.focused_right_mapped
        else ["--focused-sendinput-right"]
        if options.focused_sendinput_right
        else []
    )
    arguments = subprocess.list2cmdline(probe_args)
    if not executable.is_file():
        raise FileNotFoundError(executable)

    task_name = f"AALC-ChildInputProbe-{uuid.uuid4().hex}"
    account_name = win32api.GetUserNameEx(2)
    pythoncom.CoInitialize()
    root_folder = None
    registered = False
    try:
        scheduler = win32com.client.Dispatch("Schedule.Service")
        scheduler.Connect()
        root_folder = scheduler.GetFolder("\\")
        definition = scheduler.NewTask(0)
        definition.RegistrationInfo.Author = "AALC debug probe"
        definition.RegistrationInfo.Description = (
            f"Temporary elevated input probe for Child Session {session_id}"
        )
        definition.Settings.Enabled = True
        definition.Settings.Hidden = True
        definition.Settings.AllowDemandStart = True
        definition.Settings.DisallowStartIfOnBatteries = False
        definition.Settings.StopIfGoingOnBatteries = False
        definition.Settings.ExecutionTimeLimit = "PT0S"
        definition.Principal.UserId = account_name
        definition.Principal.LogonType = TASK_LOGON_INTERACTIVE_TOKEN
        definition.Principal.RunLevel = TASK_RUN_LEVEL_HIGHEST

        action = definition.Actions.Create(TASK_ACTION_EXECUTE)
        action.Path = str(executable)
        action.Arguments = arguments
        action.WorkingDirectory = str(executable.parent)

        task = root_folder.RegisterTaskDefinition(
            task_name,
            definition,
            TASK_CREATE,
            account_name,
            None,
            TASK_LOGON_INTERACTIVE_TOKEN,
        )
        registered = True
        running = task.RunEx(None, TASK_RUN_USE_SESSION_ID, int(session_id), "")
        if running is None:
            message = "Task Scheduler 没有返回运行实例"
            raise RuntimeError(message)

        deadline = time.monotonic() + 15
        state = TASK_STATE_QUEUED
        while state == TASK_STATE_QUEUED and time.monotonic() < deadline:
            time.sleep(0.2)
            try:
                state = int(running.State)
            except Exception:
                state = -1
        if state == TASK_STATE_QUEUED:
            raise TimeoutError("探针启动任务仍处于排队状态")
        sys.stdout.write(f"Launched elevated probe in Child Session {session_id}; state={state}\n")
        return 0
    finally:
        if registered and root_folder is not None:
            root_folder.DeleteTask(task_name, 0)
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
