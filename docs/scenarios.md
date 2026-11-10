# 合成场景契约

`scenarios/` 保存邮件及日常的 `synthetic-contract`。观察内容由人工编写，来源为生产流程契约、现有单元测试或有界等待要求。场景调用生产流程并使用虚拟时钟，不启动游戏、不识别截图、不发送系统输入。验收比较运行结果、步骤观察与预期动作；画面匹配和实际 OCR 使用各自的视觉验证。

## 邮件

根目录的三份邮件场景使用生产 `MailRunner` 和 `MailFlow`。

| 场景 | 契约 | 预期结果与原因 |
|---|---|---|
| `mail-rewards` | 打开邮箱、领取、等待奖励确认、关闭、观察主页 | `Completed` / `mail.returned-home` |
| `mail-empty` | 领取后连续两次观察仍有领取按钮且无确认，关闭并观察主页 | `Completed` / `mail.returned-home` |
| `mail-unknown` | 未识别页面持续至时限，期间不点击 | `Failed` / `mail.timeout` |

在仓库根目录运行：

```powershell
dotnet run --project src/AALC.Cli -c Release -- replay scenarios/mail-rewards.json
dotnet run --project src/AALC.Cli -c Release -- replay scenarios/mail-empty.json
dotnet run --project src/AALC.Cli -c Release -- replay scenarios/mail-unknown.json
dotnet test tests/AALC.Core.Tests/AALC.Core.Tests.csproj -c Release
```

`ScenarioSession` 在每次观察时产生新帧编号；生产运行器的 500 ms 等待推进虚拟时间和场景步骤。当前步骤要求的点击必须先完成，才能进入下一步。`holdLastFrame: true` 允许最后一步继续产生新观察，用于未知页面超时契约；其余场景耗尽而运行器仍未结束时报告契约错误。

统一验收入口是 `session.Evaluate(result)`。只有实际 outcome、reason 与声明相同，所有步骤都被观察、所有预期点击均已执行且没有契约违规，`Passed` 才为 `true`。`Reason` 给出首个不匹配原因，另有两个覆盖布尔值供输出。`mail-unknown` 的运行结果虽然是 `Failed`，符合明确的超时契约时仍为验收通过；其他异常不会冒充超时。

## 增加邮件场景

1. 先定位进入邮箱的调用方、待改变的动作与退出后接手的调用方。`source` 填写可定位的函数、测试、源码 SHA 或证据文件及帧区间；区分源码、人类描述和实际画面证据。
2. 按已知观察顺序填写 `steps`，每步 `visible` 列出可见的 `HomeMail`、`ClaimAll`、`Confirm`、`Close`；有输入时填写唯一的 `expectedClick`，否则省略。动作后的页面必须有对应证据；未知后继保留未知。
3. 声明具体的 `expectedOutcome` 和 `expectedReason`。成功返回使用 `Completed` / `mail.returned-home`；有界等待契约使用 `Failed` / `mail.timeout`，并允许末帧保持。
4. 人工抽象的步骤继续标记 `evidence: "synthetic-contract"`，即使参考了真实截图。当前格式存储的是控制项观察，像素匹配另由视觉工具验证；它没有从图片自动构建场景的能力。
5. 在 `MailTests.SyntheticContractsMeetAllAcceptanceCriteria` 增加场景名，运行上面的 Release 测试与对应 `replay` 命令，并检查输入顺序和验收结果。

## 日常

`scenarios/daily/` 使用生产 `DailyRunner`、采光、编队与战斗流程。`DailyScenarioSession` 提供查询可见目标、人工 OCR 文字、虚拟时间以及点击、按键、拖动动作验收。

| 场景 | 契约 | 预期结果与原因 |
|---|---|---|
| `daily-exp-thread-three` | 经验 3 次、纺锤 3 次，按顺序选第一队，每类一个三连战批次，结束后返回主页 | `Completed` / `日常任务已完成` |
| `daily-entry-failure` | 经验入口有界尝试失败，停止后续纺锤任务 | `Failed` / `经验采光未完成` |

```powershell
dotnet run --project src/AALC.Cli -c Release -- daily-replay scenarios/daily/daily-exp-thread-three.json
dotnet run --project src/AALC.Cli -c Release -- daily-replay scenarios/daily/daily-entry-failure.json
```

两份场景都关闭模块、奖励和狂气兑换，以核验采光编排与失败停止。模块和奖励的状态变化由 `DailyRewardTests` 覆盖，真实 `GameSession` 的取消、旧帧、OCR 后超时以及中文服务器重试由 `GameSessionTests` 覆盖。当前 `daily-replay` 没有配置嵌套邮件运行器；需要邮件动作的契约使用独立 `replay`。

场景的 `options` 为 `DailyOptions`，`steps` 每步包含：

- `targets`：资源键、客户区中心点及可选分数和边界框。观察仅返回当前查询包含且达到阈值的目标。
- `text`：可选的人工识别文字、置信度和边界框。区域 OCR 查询按文字中心点过滤。
- `expectedActions`：按顺序填写 `rule`、`kind`（`Click`、`Key`、`Drag`）以及需要核验的坐标或按键。
- `advanceAfterObservation`：为 `true` 时，在本步已观察且动作完成后的下一次观察进入后继步骤；否则执行完本步预期动作后立即进入后继步骤。

每次观察产生新帧编号。动作必须使用当前帧，且点击或拖动坐标位于客户区；额外动作、顺序不符、坐标或按键不符均记录为契约违规。等待推进虚拟时间，不执行实际休眠。场景中未声明推进的末帧可继续被观察，供流程自身的有界等待与失败判定使用。

日常同样调用 `session.Evaluate(result)`：outcome 和 reason 一致、每步被观察、所有预期动作完成且没有违规时才通过。CLI 验收通过返回 0，契约不符返回 1，参数或载入异常返回 2。声明为失败的入口场景在符合失败契约时返回 0。

## 增加日常场景

1. 在 `source` 定位进入步骤、动作与退出后接手者的源码或证据，保持 `evidence: "synthetic-contract"`。
2. 填写 `options` 与按顺序出现的目标和文字，为动作后的页面声明后继步骤。使用 `advanceAfterObservation` 表达不需要输入的等待帧。
3. 填写具体的 `expectedOutcome`、`expectedReason`，并在 `DailyReplayTests.SyntheticDailyScenariosUseTheProductionRunner` 增加场景名。
4. 运行针对性测试及 `daily-replay`，检查完整观察覆盖、动作覆盖和验收结果。

合成契约核验任务对给定观察的行为。真实图像与录制的验证方法见 [截图回归](screenshot-regression.md)。
