# 日常采光、选队与战斗

本流程迁移自 Python 的 [日常编排](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/blob/ahab/tasks/base/script_task_scheme.py)、[采光入口](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/blob/ahab/tasks/daily/luxcavation.py)、[队伍选择](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/blob/ahab/tasks/teams/team_formation.py)、[战斗](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/blob/ahab/tasks/battle/battle.py)及[事件页判断](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/blob/ahab/tasks/event_page.py)。下面描述当前 .NET 实现、合成契约与已记录的实机事件片段。

## 责任与配置

| 层 | 实现 | 责任 |
|---|---|---|
| 纯规则 | [DailyPlan.cs](../src/AALC.Core/Features/Daily/DailyPlan.cs) | 总次数分批、首尔换日后的队伍、参数验证 |
| 一个采光批次 | [LuxcavationFlow.cs](../src/AALC.Runtime/Daily/LuxcavationFlow.cs) | 进入关卡、设置本批次数、选择队伍、等待胜利结算 |
| 预设队伍 | [TeamSelection.cs](../src/AALC.Runtime/Automation/TeamSelection.cs) | 按列表顺序或 OCR 名称选择 |
| 普通日常战斗 | [BattleFlow.cs](../src/AALC.Runtime/Automation/BattleFlow.cs) | 开战、回合输入、全灭重试、胜利结算 |
| 战斗事件 | [BattleEvents.cs](../src/AALC.Runtime/Automation/BattleEvents.cs) | 选项、成功率选择、判定与结果推进 |

`DailyPlan.Batches(total, continuous, maximum)` 是分批的唯一位置：例如总次数 10、每批最多 3，输出 `3,3,3,1`。关闭连续作战时每批为 1；零次数没有批次。`LuxcavationFlow.RunAsync` 接收已经分好的 `combatCount`，不重新读取总次数。

`DailyPlan.TeamFor` 默认使用 `TeamNumber`；开启按日选队后，经验本按周一二、周三四、周五六、周日四组，纺锤按一周七天取值。星期先换算为首尔时间并减去六小时，周一 05:59 仍取周日队伍，06:00 开始取周一队伍。

参数验证包括次数非负、队伍编号 1 到 20、每批连战 1 到 10、四组经验队伍与七组纺锤队伍，以及补充档位 0 到 3。日常这里只选择已有预设队伍，不执行 12 名罪人的重排、编队码导入或镜牢专用配队。

## 观察、动作与出口

```mermaid
flowchart LR
    E[进入采光页面] --> C[设置本批连战次数]
    C --> L[选择可进入关卡]
    L --> T[选择预设队伍]
    T --> B[点击开始战斗]
    B --> F[识别回合并输入]
    F --> V[OCR 战斗胜利与确认]
    V --> R[点击确认并交回编排层]
```

### 采光入口

共同入口为 `home/drive_assets.png`、`home/luxcavation_assets.png`；识别 `teams/identify_assets.png` 才算进入编队页。提示遮挡用 `home/first_prompt_assets.png` 和 `home/back_assets.png` 联合判断。入口搜索逐步由 `Clam` 扩大至 `Normal`、`Aggressive`，一轮最多 31 次，耗尽后仅返回主页恢复一次，再搜索一轮；恢复失败直接结束批次。

- 经验本对 `luxcavation/exp_enter.png` 以 0.8 阈值取得多个匹配，至少有一项达到 0.85 才判断已进入经验采光页；随后按所有 0.8 以上候选的横坐标从右向左尝试。连战次数大于 1 时，从所选入口按 1440p 基准偏移 `(+300,-450)` 定位次数框。
- 纺锤先切换 `luxcavation/thread_assets.png`，识别 `luxcavation/thread_enter_assets.png` 使用 0.78 阈值，在进入列表前设置次数。列表使用 `luxcavation/thread_consume.png` 多匹配；只保留右侧 `x >= 700 * scale` 的入口，按行距去重、纵坐标由下至上尝试。滚动条存在时使用滚动条，否则在入口区域拖动；没有可用行时最多反向拖动 11 次。
- 次数框使用 `luxcavation/thread_continuous_combat_show_box.png` 与 `luxcavation/continuous_combat_up_box.png`，阈值均为 0.85；增加按钮最多识别两次，点 `combatCount - 1` 次。设置是从默认 1 开始的按钮操作，没有 OCR 校验游戏显示次数。
- 每个关卡最多点击三次，每次等待并最多观察三次编队页。进本失败不继续选队和开战。

采光入口和队伍的锚点偏移按实际帧高度与 1440 的比例计算。改变页面后重新观察；拖动终点限制在客户区内。

每轮采光场景搜索使用 `ObserveAsync`，按 [日常观察策略](daily-flow.md#观察与输入) 检查服务器弹窗；次数面板、关卡入场与列表拖动后的局部反馈使用 `ObserveControlsAsync`，只做控件及模板网络状态观察，仍受截图、取消、超时和新帧校验约束。当前帧已提供静态入口锚点时直接操作；私有步骤交回最新反馈帧，后续判断复用该帧，打开面板或切换页面后的反馈观察继续保留。

### 选择预设队伍

队伍列表位置来自 `teams/identify_assets.png` 的偏移。按序模式每次先复位列表，按五队一页拖动至目标页，再按行号点击；按名称模式先检查黄色高亮行和当前 OCR 结果，随后最多搜索十页。OCR 从文本中的最后一组数字提取队号，输入采用返回的全图文本坐标。

高亮行使用原始 BGRA 像素的黄色 HSV 范围与连通区域外框筛选。按序点击和名称点击返回后等待一秒；这里没有另一次 OCR 确认所选队号。无法识别编队锚点或找不到指定队伍时返回失败。

### 战斗

开战识别 `battle/normal_to_battle_assets.png` 或 `battle/chaim_to_battle_assets.png`。按钮点击后等待两秒；仍在编队页时可 OCR 识别 `当前人数/上限`，结合 `teams/selected.png` 与顺位 OCR 取消超额罪人。开战最多尝试 16 次，开始按钮消失后进入战斗循环。

`BattleFlow.ContinueAsync` 直接进入相同的战斗循环，供已确认处于当前批次的恢复入口使用；它不选关、不改变连战次数，也不点击开战按钮。完成后仍交回调用者处理主页与剩余任务。

战斗循环先使用 `ObserveControlsAsync`。没有调用方控件时重新进行完整观察，以处理未知页面与文字网络提示。回合识别优先看 `battle/more_information_assets.png`、`battle/win_rate_assets.png`，多次未识别后使用 `battle/turn_assets.png` 和 OCR 的 `turn`；明确的回合控件且没有事件模板时不读取全屏文字。

默认通过后台消息输入 `P`，等待 500 ms，再用控件观察确认当前仍有回合或开始控件后输入 `Enter`。控件已消失时返回主循环重新判断。回合输入后的反馈同样不附带周期性 OCR，以 0.75 阈值检查 `battle/pause_assets.png`，没有看到该模板时，可用 `battle/win_rate_card.png` 和 `battle/gear_right.png` 的鼠标路径。主循环仍以 0.8 阈值识别 `pause` 交战动画，`battle/continue_assets.png` 用于恢复暂停。

战斗主循环每次观察后先处理 `base/leave_up_confirm_assets.png` 或 `base/leave_up_assets.png` 的升级提示，确认优先，动作后重新观察；该处理不依赖被遮挡的胜利文字，也先于背景交战动画判断。

全灭识别 `battle/dead_all.png` 与确认按钮，最多重试四次，第五次停止。每次挑战的等待时限为 `900 + 300 * combatCount` 秒；连续 17 次未知观察也会失败。单个批次的局部时限之外，所有操作仍受共享 session 的总任务时限与取消检查约束。

普通日常结算要求同一帧 OCR 中同时出现 `战斗胜利` 或 `Battle Victory`，以及带坐标的 `确认` 或 `Confirm`。胜利文字已出现但确认尚未出现时，点击画面中心推进结算动画，沿用最多 16 次的识别重试预算。点击确认后该批返回成功，由编排层决定下一批或返回主页；没有使用镜牢战斗统计模板代替普通胜利。单次批次不主动返回主页、换模块或领取通行证。

## 战斗事件

启用 `HandleChoiceEvents` 时，叙述式事件按“叙述待推进 → 选择参与者 → 判定 → 结果待推进 → 继续战斗”处理：

1. 左侧叙述、右下 `SKIP`、右上文字及米色卡片像素共同识别叙述待推进页。该页允许点击任意位置推进，程序选择已识别卡片内的文字中心，动作规则为 `battle.event.reveal-interaction`，表示点开交互。
2. 参与者按底部 `very_high/high/normal/low/very_low` 模板或中英文成功率 OCR 选择，优先极高、高、一般、低、极低。点击成功率文字下方头像，偏移随帧缩放。下一帧出现位于操作区域且文字完全匹配的判定按钮后才开始判定；选人说明不作为按钮。按钮暂未出现时等待；至少 1.25 秒后仍明确显示未选人的提示时重新点击头像。连续八次观察未推进后失败。
3. OCR 识别“判定成功/判定失败”后，优先点击已出现的“继续”或事件推进模板。左侧叙述加右下 `SKIP`、没有可识别推进按钮时，按空格并在 150 ms 后重新观察；叙述文字十秒不变时失败。结果文字出现但页面布局信息不足时等待。
4. “继续”出现后，通过 `continue/proceed/commence/skip` 模板或结果上下文中的 OCR“继续”推进，交回战斗循环；事件判定成功不等于本批采光已经结算。

带“选项”标题或 `choices` 模板的选项页继续使用首项处理：只有彩色按钮区域明确呈低饱和且存在下一项时，才点击下一项；信息不足时等待，不因首项点击未推进就改点次项。连续八次未推进后失败。

该标题页的原始首项偏移 105、行距 124、横向范围与容差使用 900p 布局基准，按 `choiceScale = frame.Scale * 1.6`（即帧高除以 900）缩放。既有 Python 720p OCR 回归中，首项距标题约 84 像素、两项相距约 99 像素，.NET 同时保留该坐标与等比放大的 1440p 回归。灰色按钮区域优先按实际两项行距缩放，仅识别首项时使用同一基准下的默认行距。

本采光入口没有加入镜牢专用阵亡弃战、避免三技能、首回合防御、无限战斗或主线剧情出口。

## 验证证据

完整日常语义回放位于 [daily-exp-thread-three.json](../scenarios/daily/daily-exp-thread-three.json)，包含主页进入、经验三连战、纺锤三连战及最终主页；模块转换、领奖和狂气补充均关闭。[daily-entry-failure.json](../scenarios/daily/daily-entry-failure.json) 则验证经验入口搜索及恢复失败后中止，不执行纺锤。

两个场景均标记 `synthetic-contract`。JSON 的每个步骤声明 `targets`、可选 OCR `text` 与有序 `expectedActions`；动作至少校验 `rule` 和 `kind`，可选校验点击坐标、按键或拖动起终点。步骤在预期动作全部完成后推进；纯等待帧用 `advanceAfterObservation` 明确声明下一次观察进入后继，末帧持续保持。回放产生空白像素缓冲区，模板与 OCR 由声明提供，不验证视觉算法。

统一运行与验收入口：

```csharp
var scenario = DailyScenario.Load(path);
var session = new DailyScenarioSession(scenario, onEvent);
var result = await new DailyRunner(session,
    _ => throw new InvalidOperationException("场景未配置邮件回放"))
    .RunAsync(scenario.Options, cancellationToken);
var acceptance = session.Evaluate(result);
```

`onEvent` 接收 `RunEvent`，`Report` 发布带中文描述的 `Progress`，动作发布带机器规则的 `Sent`。验收必须同时满足具体 outcome/reason、全部步骤被观察、全部有序动作被执行，且没有契约违规。

[DailyCombatTests.cs](../tests/AALC.Core.Tests/DailyCombatTests.cs) 使用虚拟时间和 fake session 覆盖分批、首尔换日、输入参数、经验和纺锤三连战动作契约、选队失败、名称坐标、回合输入及胜利结算条件；升级提示遮住胜利文字、回合反馈 0.75 阈值与胜利动画推进均有对应回归。事件回归覆盖叙述与卡片的联合布局、无模板点开交互、中文选人后进行判定、避免重复选人、成功与失败结果的叙述推进及八次上限、不完整页面等待，以及 720p/1440p 槽位、列范围、容差和单灰首项的默认间距。

[DailyReplayTests.cs](../tests/AALC.Core.Tests/DailyReplayTests.cs) 通过生产 `DailyRunner` 验证这两个 JSON，并覆盖坐标/按键不符、取消输入、末帧漏动作以及失败原因不匹配。

Python 来源测试包括 [采光连战](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/blob/ahab/tests/test_luxcavation_continuous_combat.py)、[日常失败传播](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/blob/ahab/tests/test_daily_team_selection.py)、[普通胜利结算](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/blob/ahab/tests/test_battle_settlement.py)与[事件恢复](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/blob/ahab/tests/test_daily_event_recovery.py)。这些来源描述源码的行为约束，本轮没有执行 Python 回归。

```powershell
dotnet test dotnet/tests/AALC.Core.Tests/AALC.Core.Tests.csproj -c Release
```

fake session 中每次动作的后继由测试预先声明；实际游戏的入口位置、模板有效性、OCR 效果和点击后的页面变化，需要帧图与实际动作日志分别核验。

实机事件证据来自 `logs/dotnet_daily_debug/20261025-151708-112/frame-000086.png`、`20261025-152800-718/` 与 `20261025-153222-886/` 的帧图及 `events.jsonl`：叙述页点开交互后完成选人和判定；结果页点击叙述区后出现继续按钮，点击继续约 4.5 秒后回到战斗。最后一份记录第 130 帧为纺锤三连战胜利结算。经验与纺锤的分段记录及资源预算见 [日常实机记录](daily-flow.md#实机记录)。
