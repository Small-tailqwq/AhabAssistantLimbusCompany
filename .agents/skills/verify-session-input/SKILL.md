---
name: verify-session-input
description: 修改 AAALC GameSession 的输入边界、帧校验、运行时限或事件发布时，检查事件处理后是否仍可能发送超时输入，并重放四种输入契约。
---

# 会话输入边界验证

承诺：使用旧画面或已到运行时限时不向输入设备发送动作。事件发布属于输入前的执行时间，不能忽略。

## 核对源码与模型

覆盖记录见 [coverage.json](coverage.json)。基准 HEAD 为 `cee28c37cc7e496759e2df786b03dd5027c8dede`；覆盖代码尚未提交，工作树哈希是精确基线，`sync_commit` 为空。

| 模型动作 | 生产方法 |
| --- | --- |
| `NewObservation` | `ObserveCoreAsync` 替换 `latest`，使旧帧失效；包括事件回调内再次观察 |
| `ExpireBeforeCheck` | 运行时钟在调用前到达任务总时限 |
| `CheckAccepted`、`CheckRejected` | `CheckFrame` 调用 `Check` 并比较 `latest.Identity` |
| `PublishQuickly`、`PublishAtDeadline` | 输入方法在 `Emit` 中同步调用 `publish`，事件处理可能耗时 |
| `RecheckRejected`、`SendInput`、`PostInputCheck` | 四种输入在 `Emit` 返回后再次 `CheckFrame`，通过才调用 `IGameInput`，随后再次 `Check` |

## 执行

在 Windows 仓库根目录运行：

```powershell
dotnet run --project .agents/skills/verify-session-input/scripts/Probe.csproj
```

加载 `/statechart`，按其当前说明在仓库外 scratch 检查 [SessionInput.tla](models/SessionInput.tla) 与同目录 cfg，采用 [input.view.mjs](models/input.view.mjs)。TLC 固定 1.7.4、Java 至少 11；已验证 Temurin 21.0.13+9。

当前基线：`NoInputAfterDeadline`、`NoStaleFrameInput` 均通过；生产探针四种输入在调用前超时、使用旧帧、事件处理耗尽时限或替换画面时均输出 `sends=0`，退出 0。

## 边界与维护

- 模型是一次输入、一个旧/新帧标志、到期前/已到期两类时间；不把检查和发布或发送合并为原子步骤。
- 探针运行生产 `GameSession`，替身实现 `IGameVision`、`IGameInput` 与虚拟时钟，不发送真实键鼠消息。输入设备仍检查取消；这里验证任务总时限，与取消令牌不同。
- `GameWindow.ValidateFrame` 的五秒画面期限不能代替会话剩余时限。模型不验证原生消息交付、按键释放、窗口租约或真实系统调度。
- 仓库外变异：删除 `Emit` 后的 `CheckFrame` 应使发布期间超时或换帧探针失败；删除帧 Identity 检查应使旧帧探针失败。对应模型检查必须能触发相应不变量。
- 修改覆盖文件后重新核对回调的同步性与每次 `await`；反例先用生产探针确认。修复后按源码更新模型，不能仅改规则求通过。提交并重新核对后才推进 `sync_commit` 与哈希。
- 合并造成的验证漂移可使用 pstack `/maintain-formal-verification-skill`；本文件也能独立指导核对和重放。
