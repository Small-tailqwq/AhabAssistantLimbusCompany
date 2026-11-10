# 桌面分身

桌面分身在 Windows Child Session 里运行 Steam、游戏和任务，主桌面的鼠标不受影响。入口是侧栏“桌面分身”页；打开“任务在分身内运行”后，日常和镜牢的开始按钮都交给分身执行，进度和预览仍显示在“运行监控”页。邮件和截图工具只操作主桌面窗口。

## 进程

| 进程 | 会话与权限 | 责任 |
|---|---|---|
| `AAALC.exe` | 主会话，管理员 | 环境检查、生命周期、配置写入、界面 |
| `clone-host/AAALC.CloneHost.exe` | 主会话，继承管理员 | RDP ActiveX、分身窗口、音频静音，net48 WinForms |
| `AAALC.exe --clone-worker` | Child Session，受限令牌 | 拉起 Steam 与游戏、运行任务，无窗口 |

生命周期在 `src/AALC.Runtime/DesktopClone/DesktopCloneController.cs`，系统调用经 `ICloneSystem`、`ICloneTransport` 接入，单元测试用假实现驱动。Windows 实现在 `src/AALC.Platform.Windows/DesktopClone/`，分身内进程在 `src/AALC.Desktop/CloneWorker.cs`，它和主窗口共用 `GameTasks.cs` 的任务组装。

## 前置条件

检查结果显示在页面“环境”卡片，启动时再次执行，任一项失败都不会启动宿主。

- 非 Home 版 Windows，已开启远程桌面且本机 RDP 端口在监听。远程桌面未开启时页面提供开启入口，确认后通过 WMI 开启并添加防火墙例外。
- AAALC 以管理员身份运行。页面提供“以管理员身份重启”。普通权限连接会被断开（code=2，extended=12，系统日志 0x8007139F），并留下僵尸会话：`WTSGetChildSessionId` 一直返回已消失的 ID，`WTSLogoffSession` 报错误 2，只有注销 Windows 才能清除。
- 没有其他 Child Session。不属于本程序的会话不接管也不注销；`WTSQuerySessionInformation` 查不到的 ID 判定为僵尸会话，提示注销 Windows。
- Child Session 已启用，且不是在本次登录内启用的。首次启动时启用，然后要求注销 Windows 并重新登录一次，使免凭据登录生效。
- 主桌面没有游戏，分身以外没有 Steam。分身内由 `steam.exe -applaunch 1973530` 启动游戏，Steam 复用同一 Windows 用户的登录态。

ToDesk、UU 远程、MuMu 远程的交互进程只作风险提示：Child Session 会成为新的活动桌面，远程控制画面可能被切换到分身。启动前询问一次，可在页面上关闭提示。

## 启动

1. 启动命名管道，管道只授权当前用户 SID 并拒绝网络登录。
2. 在 HKLM 和 HKCU 设置 Explorer 的 `DisableLocalMachineRun`、`DisableCurrentUserRun` 及其 RunOnce 策略，抑制分身登录时重放自启动项。build 26300 上只有 HKLM 的值生效，它同时拦住 Run 项和打包应用的启动任务；HKCU 的值与既有抑制标记保持一致。主会话的 explorer 只在启动时读取这些策略。登录触发的计划任务不走 explorer，例如 PowerToys，所以同时临时禁用 `\Microsoft` 以外、对当前用户或所有用户生效的登录任务（`LogonTaskGuard.cs`）。服务账户任务运行在会话 0，不进入分身，不处理。禁用只阻止新实例，主桌面已在运行的实例不受影响；窗口期内这些任务的其他触发器也不会触发。服务拉起的进程不受抑制。
3. 启动宿主。宿主 `rdp-connected` 上报会话 ID 后，主程序核对 `WTSGetChildSessionId` 的返回值，不一致时清理并报错。
4. 180 秒后恢复策略：explorer 在登录后约 10 秒才处理启动项，最后一项在约 45 秒时启动，不能在分身就绪时恢复。恢复动作幂等。HKCU 的标记文件为 `.autorun-guard.json`，HKLM 的标记文件是 `.autorun-guard-machine.json`，被禁用的任务记录在 `.autorun-guard-tasks.json`。崩溃遗留的抑制由下一次启动恢复；HKLM 和任务部分要等下一次以管理员身份运行，在此之前重新登录 Windows 时主桌面的自启动项和登录任务不会运行。
5. 通过临时任务计划的 `RunEx`（`TASK_RUN_USE_SESSION_ID`）把分身内进程投递到目标会话，等运行实例离开排队后删除任务定义。
6. 分身内进程用短静音打开 RDP 的重定向音频端点，然后上报 `ready`。

连接时限 120 秒。首次连接失败时宿主自动重试三次。

## 任务

任务配置写入 `<数据根>/clone/requests/`，管道只传路径。分身内进程读取后删除；任务计划启动的进程不继承环境变量，数据根通过 `--data-root` 显式传入，证据路径规则与主桌面相同。

分身内进程回报四类消息：筛选后的运行事件、约每秒一帧的缩小 JPEG 预览（宽 800，放不进消息上限时丢弃）、队伍轮换、任务结果。发送走有界队列，队列满时丢弃最旧的消息，任务流程不等待管道。完整事件和帧保存在分身内进程写入的 `recordings/`。队伍轮换由主程序写回配置，配置只有一个写入者。

## 停止与退出

停止按钮和 Esc 向分身内进程发送 `stop`，任务按主桌面的协作式规则结束并回报结果。30 秒内没有结果时界面解除运行状态并报错，控制器保持运行中，不接受新任务，可以“停止并注销”。启动阶段取消时直接注销本次创建的会话；注销会取消所有尚在等待该次启动就绪的调用。

“停止并注销”依次停止任务（3 秒）、退出分身内进程、通知宿主注销，然后轮询直到 `WTSGetChildSessionId` 不再返回会话，时限 30 秒。Windows 未确认注销时保持错误状态并保留宿主，确认后才结束宿主并回到空闲。

关闭主窗口时走同一路径，总时长不超过 5 秒。超时后主程序直接退出；管道断开后，宿主自行注销，分身内进程取消任务并退出。

## 分身窗口

宿主窗口使用 AAALC 图标，标题栏和工具栏的颜色取自 `Styles/Tokens.axaml` 的同名令牌（`src/AALC.CloneHost/HostPalette.cs`）。标题栏底色只有 Windows 11 支持，旧系统退回深色标题栏。工具栏的“关闭声音”“关闭输入”与页面开关双向同步，开启后按钮文字同时改变。关闭窗口只隐藏，不注销；隐藏时自动静音。RDP 客户端忽略子会话程序产生的鼠标位置更新；关闭时等待已缓冲音频停止，再恢复宿主音量。

主程序到宿主的命令为 `show`、`hide`、`tool-set <mute|input> <0|1>`、`logoff`。协议为制表符分隔的文本行，自由文本用 Base64，单条上限 64 KB，版本 1。连接与命令处理实现在 `src/AALC.CloneHost/`。

## 文件

| 路径 | 内容 |
|---|---|
| `<数据根>/clone/logs/root-日期.log` | 主程序状态变化、宿主诊断 |
| `<数据根>/clone/logs/worker-日期.log` | 分身内进程的启动与异常 |
| `<数据根>/clone/logs/host-startup-error.txt` | 宿主构造期崩溃 |
| `%LOCALAPPDATA%/AALC/desktop-clone/` | 启用标记、自启动抑制记录 |

设置保存在 `settings.json` 的 `DesktopClone` 字段。

## 验证范围

`tests/AALC.Core.Tests/DesktopCloneTests.cs` 用假实现覆盖状态机、拒绝错误会话、取消、断连、注销未确认与僵尸会话，并用真实命名管道验证分帧和对端身份。ActiveX 连接、任务计划投递、WMI 开启远程桌面和音频只能实机验证。

实机验证用无窗口入口，在管理员终端运行：

```powershell
dotnet run --project src/AALC.Cli -- clone-verify <AAALC.exe 路径> --run
```

`clone-verify` 隐藏启动宿主，不激活窗口，核对静音和输入开关的回显。`--run` 再运行一次只返回主界面的日常，然后运行第二次并在首个事件后停止，最后注销并确认没有残留会话。结果写入 `<数据根>/clone/logs/verify-时间.log`。窗口外观与显示切换不在这个入口的覆盖范围内。

连续镜牢用同样无窗口的入口，同样需要管理员终端：

```powershell
dotnet run --project src/AALC.Cli -- clone-mirror <AAALC.exe 路径> <轮数>
```

`clone-mirror` 使用已保存的镜牢配置并强制领取结算奖励，不写回配置，队伍轮换只记入日志。进度写入 `<数据根>/clone/logs/mirror-时间.log`，最新一帧写入同目录的 `mirror-latest.jpg`。在该目录创建 `stop-mirror` 文件即协作式停止，之后注销。游戏停在上一次未领取的结算页时，领取这份奖励算作第 1 轮。
