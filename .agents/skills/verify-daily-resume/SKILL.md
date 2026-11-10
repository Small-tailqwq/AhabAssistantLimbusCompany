---
name: verify-daily-resume
description: 修改 AAALC 日常采光批次、游戏重启恢复、完成记录或返回主页逻辑时，检查已胜利批次是否会再次开战，并用生产运行器重放。
---

# 日常重启续跑验证

承诺：一批已胜利的采光不会因重启再次执行，已经写入的批次完成记录在重启后保留。重复开战会超出配置的场数并额外消耗资源。

## 核对源码与模型

覆盖记录见 [coverage.json](coverage.json)。基准 HEAD 为 `cee28c37cc7e496759e2df786b03dd5027c8dede`；覆盖源码尚未提交，工作树 SHA-256 是验证基线，`sync_commit` 为空。

| 模型动作 | 生产行为 |
| --- | --- |
| `EnterBatch`、`StartBattle` | `DailyRunner.RunStepsAsync` 检查 `RunProgress.Done`，记录 `PendingBatch` 后调用 `LuxcavationFlow`，由 `BattleFlow.StartAsync` 开战 |
| `BattleWon` | 游戏进入胜利结算，独立于本地是否记录完成 |
| `RestartBeforeCheckpoint` | `GameSession.ObserveCoreAsync` 重启并抛出 `GameRestartedException`，`DailyRunner.RunAsync` 捕获 |
| `ObserveRecoveredSettlement`、`DismissRecoveredSettlement`、`ObserveHomeAfterRecovery` | `DailyNavigation.ReturnHomeAsync` 观察、确认残留结算、再观察主页 |
| `RecordRecoveredCheckpoint` | 返回主页确认结算后调用 `RunProgress.CompleteBatch`，写入当前批次完成记录并清空待完成身份 |
| `ConfirmBattleSettlement`、`RecordCheckpoint` | `BattleFlow.ContinueAsync` 确认结算并返回；`RunStepsAsync` 随后调用 `CompleteBatch` |
| `RestartAfterCheckpoint`、`ReturnHome`、`Complete` | 完成记录写入后的重启、返回主页与跳过批次 |

## 执行

在 Windows 仓库根目录运行：

```powershell
dotnet run --project .agents/skills/verify-daily-resume/scripts/Probe.csproj -- .
```

加载 `/statechart`，按其当前说明在仓库外 scratch 检查 [DailyResume.tla](models/DailyResume.tla) 与同目录 cfg，采用 [daily.view.mjs](models/daily.view.mjs) 解释全部结果。使用 TLC 1.7.4、Java 至少 11；本次用 Temurin 21.0.13+9。

当前基线：`NoRepeatedBatch`、`KeepCompletedCheckpoint` 均通过。生产探针覆盖完成记录前后重启、继续下一批经验本、继续纺锤本；实际开战批数等于计划批数，退出 0。

## 边界与维护

- 有限模型只含一批、一次重启、至多两次开战。假定重启成功后仍可见胜利结算；不验证游戏服务端扣费、奖励发放、视觉识别或跨进程持久化。
- 探针以现有 `daily-exp-thread-three` 合成场景为基础，通过 `IGameSession` 在观察边界注入重启异常；`DailyRunner`、采光、战斗、返回主页均运行生产实现。后继场景允许观察重复开战，再以开战次数判错。
- 两个注入点分别位于胜利结算观察时，以及 `CompleteBatch` 后返回主页的观察时；不能在源码没有观察调用的位置随意注入重启。模型是一批，后续批次和类型对应由生产探针检查。
- 仓库外变异：撤回返回主页时的完成通知，应使 `NoRepeatBeforeCheckpoint` 与 `NoRepeatedBatch` 失败；在重启 catch 清空 `Done` 应使 `KeepCompletedCheckpoint` 失败。
- 源码改变后先核对恢复位置和完成记录的写入时刻；每个反例都重放。修复代码后按事实更新模型，保留“一批只执行一次”的承诺。提交后重新核对并运行，才更新 `sync_commit` 与哈希。
- 未及时重验的合并可交给 pstack `/maintain-formal-verification-skill`；本文件也包含独立执行所需的源码映射、命令与范围。
