# Agent Note: MuMu 启动以 Nemu IPC 连接成功为就绪条件

Status: implemented

## 问题

MuMuManager 报告 `start_finished` 时，external_renderer_ipc 的共享内存可能尚未可用。管理器状态等待超时后立即调用 Nemu IPC，`nemu_connect` 失败会进入回退路径；标准流捕获若替换了 Python 流对象，后续访问 `fileno` 会抛出 `AttributeError`，回退再递归重启模拟器，没有有界的恢复条件。

## 决策

[MumuControl.start()](../../../../module/automation/input_handlers/simulator/mumu_control.py) 在 `start_emulator_timeout` 的同一截止时间内轮询启动状态。只有状态为 `start_finished` 后才加载 DLL、读取 ADB 端口并尝试 `connect()`；`NemuIpcError` 和 `asyncio.TimeoutError` 视为 IPC 尚在预热，在截止前重试。连接成功才算启动完成。截止时抛出一个 `RuntimeError`，并区分“未检测到启动完成状态”和“等待 Nemu IPC 就绪”，后者保留最后一次连接错误作为原因；不递归重启。每轮检查停止请求，`userStopError` 直接传播。

`CaptureNemuIpc` 用 `os.dup2` 重定向并恢复底层文件描述符，退出时还原原有的 `sys.stdout`、`sys.stderr` 对象，IPC 失败输出诊断后 Python 流仍可用。启动期间的 IPC 重试输出记录为 debug 级，正常预热不作为应用错误上报。

该修复不改变 MuMu 安装检测、版本要求、启动超时配置、实例选择和游戏启动命令。

<!-- agent-note-format: alternatives-not-recorded (pre-format Agent Note) -->

## 后果

模拟器慢启动时，IPC 短暂不可用会在配置的超时内自动恢复；真正失败时只有一个带原因的错误，不会反复拉起模拟器。启动总时长受 `start_emulator_timeout` 约束，IPC 预热占用同一预算。

[test_mumu_ipc_retry.py](../../../../tests/test_mumu_ipc_retry.py) 覆盖截止前恢复、截止后保留原因和重试输出的日志级别。
