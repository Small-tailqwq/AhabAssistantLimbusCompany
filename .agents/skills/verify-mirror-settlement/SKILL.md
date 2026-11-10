---
name: verify-mirror-settlement
description: 修改 AAALC 镜牢奖励结算、周奖励选择、队伍轮换或重启恢复时，核对结算与恢复模型，并用生产 GameSession 和 MirrorRunner 重放中断边界。
---

# 镜牢结算与恢复验证

承诺：模块确认需要通关证据和领取授权；同一次待确认结算不重复提交。领取回执处理后重启不能多开一轮；短暂拒绝输入后仍能处理已提交的回执；领取已完成时停止不能丢失队伍轮换。

## 核对源码与模型

覆盖记录见 [coverage.json](coverage.json)。基准 HEAD 为 `cee28c37cc7e496759e2df786b03dd5027c8dede`；源码尚未提交，工作树 SHA-256 是验证基线，`sync_commit` 为空。

| 模型动作 | 生产行为 |
| --- | --- |
| `ObserveCompletion`、`KeepRewards`、`SubmitModules` | `MirrorSettlementFlow.RunAsync` 观察通关标记、检查领取配置、发送模块确认并记录 `submitted` |
| `RequestWeeklyChange`、`ObserveWeeklyDecrease`、`WeeklyUnchanged` | 取消最右侧周奖励；下一帧必须观察数量下降，否则等待至上限停止 |
| `ObserveReceipt`、`AcknowledgeReceipt`、`ObserveEntrance` | 发送回执确认，再观察返回入口，形成 `MirrorSettlementResult` |
| `ObserveFatalPage`、`RestartGame`、`ObserveHomeAfterRestart` | `GameSession.ObserveCoreAsync` 识别致命提示并重启；`MirrorRunner.RunAsync` 捕获 `GameRestartedException`，返回主页并重新观察确认 |
| `NavigateFromHome`、`NavigateToEntry`、`EnterAnotherDungeon` | `MirrorEntryFlow.RunAsync` 从主页经过入口进入新的镜牢；本地轮数尚未增加 |
| `InputBlocked`、`WaitForInputRecovery`、`EntryCannotRecognizeReceipt` | 回执点击抛出 `GameInputBlockedException`，运行器等待后重新走入口；入口查询和 `Inside` 没有领取回执 |
| `RotateQueue`、`SaveQueue`、`CancelBeforeSave`、`RejectCanceledSave` | `MirrorRunner.RunAsync` 先轮换内存数组，再把任务令牌传给保存回调；停止令牌取消后桌面回调在保存前拒绝执行 |

结算模型覆盖单次调用内的安全条件；恢复模型覆盖调用退出后丢失结算状态、当前轮计数与队列保存之间的顺序。队伍筛选和数组轮换另用生产 `MirrorPlan` 检查，避免复制一份 C# 算法充当证明。

## 执行

在 Windows 仓库根目录运行：

```powershell
dotnet run --project .agents/skills/verify-mirror-settlement/scripts/Probe.csproj -c Release
```

加载 `/statechart`，按其当前说明在仓库外 scratch 检查以下两组文件；使用 TLC 1.7.4、Java 至少 11，本次使用 Temurin 21.0.13+9。

- [MirrorSettlement.tla](models/MirrorSettlement.tla)、[cfg](models/MirrorSettlement.cfg)、[视图](models/settlement.view.mjs)。
- [MirrorRecovery.tla](models/MirrorRecovery.tla)、[cfg](models/MirrorRecovery.cfg)、[视图](models/recovery.view.mjs)。

当前基线：结算模型全部通过；恢复模型的 `NoUnplannedRound`、`NoExtraPayment`、`TransientBlockKeepsReceiptRecoverable`、`CompletedClaimKeepsRotation` 失败。探针共 18 项检查，含 480 组队列排列；以下三项失败，其余通过。退出 1 表示复现了当前问题。

| 探针 | 当前生产行为 |
| --- | --- |
| `RestartAfterReceiptCannotStartAnotherRound` | 计划一轮，回执确认后下一次观察触发重启；额外进入镜牢一次、模块确认两次，最终仍报告完成一轮 |
| `BlockedReceiptCanResume` | 已提交模块，第一次回执点击被拒绝；输入恢复后入口无法识别回执，最终失败，队列未保存 |
| `CancelAfterClaimKeepsRotation` | 已确认回执并返回入口；保存回调开始时令牌取消，领取完成但队列未保存 |

不要为消除失败而放宽承诺。修改产品行为需要用户授权；本技能负责验证和报告。

## 边界与维护

- 探针直接运行生产 `GameSession`、`MirrorRunner`、入口、结算、返回主页与 `MirrorPlan`。替身只实现视觉、设备输入、时钟和游戏重启端口；保存回调执行与桌面回调相同的取消检查，再记录队列。
- 致命提示使用生产识别条件触发真实的重启异常；拒绝输入在底层输入发送前抛出，符合“输入未生效”的契约。取消在回执和入口已确认后、保存回调第一步之前发生。
- 页面为合成状态，按实际查询过滤资源键；进入新镜牢后省略战斗，直接给出下一轮通关页。假定回执关闭后重启会回到主页，已领取的镜牢已结束；不验证游戏服务端、真实画面识别和战斗。
- 拒绝输入分支不提供重启器，与 CLI 的 `GameSession` 组合一致；不把该分支的最终失败外推到带重启器的桌面组合。
- 结算模型含 11 种固定响应、最多 3 个周奖励；稳定页面等待折叠到观察上限。恢复模型含一轮计划、一次重启或拒绝输入或取消，至多一次额外进入，不组合多个故障。
- 每项探针最多观察 500 帧。队列枚举为 4 个不同名称、每项禁用或三种适用难度、两种运行难度，共 480 个存在可用队伍的配置；检查稳定顺序、原数组不变和下一支可用队伍。
- 在仓库外复制 Core、Runtime、公共构建文件及本技能，再变异生产源码：去掉提交标记检查、去掉通关检查、破坏周奖励等待条件、改错周奖励目标数量、去掉回执确认条件；探针应新增失败。变异只在副本中进行，随后恢复到仅有上述三项失败的基线。
- 覆盖源码改变后核对所有观察、输入、异常和保存边界，再重放每个反例；有意修复时同步修改模型的动作，保留承诺。重新运行并核对提交内容后才能更新 `sync_commit` 和哈希。
- 未及时重验的合并可交给 pstack `/maintain-formal-verification-skill`；本文件包含独立执行所需的映射、命令与边界。
