---
name: verify-clone-lifecycle
description: 修改 AAALC 分身启动、就绪、任务互斥或注销逻辑时，核对 TLA+ 状态机并用生产 DesktopCloneController 重放等待与任务交错。
---

# 分身生命周期验证

承诺：注销完成后不遗留启动等待；同一分身只接收一个运行任务。破坏前者会卡住启动命令，破坏后者会丢失任务归属。

## 核对源码与模型

覆盖记录见 [coverage.json](coverage.json)。基准 HEAD 为 `cee28c37cc7e496759e2df786b03dd5027c8dede`，覆盖源码在验证时尚未提交；文件 SHA-256 才是本次工作树的精确基线，`sync_commit` 为空。

| 模型动作 | 生产方法及原子边界 |
| --- | --- |
| `Start` | `StartAsync` 在 `gate` 中创建 `ready`、记录状态和启动任务 |
| `RdpConnected` | `OnRdpConnected` 在锁内记录会话并启动 worker |
| `WorkerReady`、`DeliverReady` | `OnWorkerReady` 的锁内状态更新与锁外 `TrySetResult` 分别建模 |
| `Run`、`RunResult` | `RunAsync` 的第二次锁内检查与登记；`OnRunResult` 释放运行记录 |
| `BeginShutdown`、`CancelStarting`、`FinishShutdown` | `ShutdownAsync` 锁内取出启动信号、锁外 `TrySetCanceled`；`FinishAsync` 的锁内状态更新 |

`waiting` 指启动调用依赖的信号尚未完成；`readyRef` 是控制器字段；`readyDelivery` 是就绪处理在锁外完成的信号，`cancelDelivery` 是注销在锁外取消的信号。通知取消完成后才进入后续清理。

## 执行

在 Windows 仓库根目录运行（SDK 见 `global.json`）：

```powershell
dotnet run --project .agents/skills/verify-clone-lifecycle/scripts/Probe.csproj
```

随后加载 `/statechart`，按其当前说明在仓库外 scratch 中检查 [CloneLifecycle.tla](models/CloneLifecycle.tla) 与同目录 cfg，采用 [clone.view.mjs](models/clone.view.mjs) 输出图和最短反例。TLC 固定为 1.7.4，Java 至少 11；已验证组合为 TLC 1.7.4、Temurin 21.0.13+9。不要把模型检查通过代替生产类重放。

当前基线：`NoOrphanStartWaiter`、`SingleActiveRun` 均通过；生产探针确认同次启动的两个等待调用均取消，第二个运行请求被拒绝，退出 0。

## 边界与维护

- 范围是一次启动、一个 worker、最多两个运行登记，以及 Windows 确认注销成功的路径。错误清理、管道替换、真实 RDP、计时器竞争和 UI 调度不在模型内。
- 假系统只替代 OS 和传输；探针调用仓库中的生产控制器，不创建 Child Session、不修改系统设置。
- 变异验证只使用仓库外副本：撤回启动取消通知应使等待探针与 `NoOrphanStartWaiter` 失败；删除两处 `Ready` 检查应使 `runMessages=2`，并触发 `SingleActiveRun`。
- 覆盖文件变化后先重新核对原子边界、事件生产者与调用方；模型反例不能逐步重放时先修正模型。提交源码后，只有重新核对并运行过才填写或推进 `sync_commit` 和文件哈希。
- 合并后未执行本技能而产生的漂移，可使用 pstack `/maintain-formal-verification-skill` 检查；本技能的源码核对与运行步骤也可独立执行。
