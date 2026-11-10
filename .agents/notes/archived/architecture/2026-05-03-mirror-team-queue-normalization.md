# Agent Note: 镜牢编队以活动队列维护启用与执行顺序

Status: implemented
Archived: 2026-11-03

## 问题

编队是否启用、执行顺序和启用数量曾分别由 `teams_be_select`、`teams_order`、`teams_be_select_num` 维护。编队增删与镜牢轮转分别更新这些字段时，配置槽位、激活数字和 widget 编号容易失去一致性。

编队删除还会压缩槽位编号。只删掉队列中的目标编号，或者只重译界面文本，都不能同步其余编队的新编号。

## 决策

`teams_active_queue` 是启用状态与镜牢执行顺序的唯一事实来源。元素是当前配置槽位的正整数编号，元素顺序是执行顺序；不在队列中的编队未启用。`teams` 继续保存各槽位的队伍设置。

槽位编号、激活数字与 `TeamSetting.team_number` 分属不同概念：

- 槽位编号对应 `teams` 的字符串键，例如 `"2"`；队列保存相应整数 `2`。
- 激活数字是队列中的 1-based 位置，不能当作槽位主键。
- `TeamSetting.team_number` 是用户选择的游戏内队伍序号；配置加载、归一化和槽位重排不得重写它。

例如有 5 个连续槽位，队列 `[2, 5, 1]` 对应激活数字 `teams_order = [3, 1, 0, 0, 2]`。

### 配置归一化与兼容投影

[Config](../../../../module/config/config.py) 集中完成队列迁移、归一化与旧字段派生。业务层通过 `set_team_enabled()`、`remove_team_from_queue()`、`reindex_team_queue()`、`rotate_team_queue()` 改变启用状态或顺序，不自行维护旧投影。

归一化后的不变量：

- 队列只含当前存在的槽位整数，过滤布尔值、非法编号和重复项，保留首次出现的相对顺序。
- `teams_be_select_num == len(teams_active_queue)`。
- 两个兼容数组长度均为最大槽位编号；槽位连续时等于 `len(teams)`，稀疏槽位的空位保持 `False` 或 `0`。
- 对队列中的第 `order` 个 `team_num`，`teams_be_select[team_num - 1]` 为 `True`，`teams_order[team_num - 1]` 为 `order`。
- `teams_order` 的非零值恰为 `1..N`，其中 `N` 为活动队列长度；未启用槽位为 `0`。

加载不含队列字段或队列值为 `None` 的旧配置时，先按有效的正数 `teams_order` 还原顺序；重复顺序值只采用按槽位升序遇到的第一项。再按槽位升序追加已勾选但尚未入队的编队。已有队列直接归一化；显式空队列 `[]` 必须保持为空，不能从旧投影复活已取消的选择。

`normalize_and_sync_team_state()` 默认保存；`persist=False` 只同步内存。`just_load_config()` 同样在内存中迁移与归一化，不写回配置。

### UI 与删除重编号

[PageMirror](../../../../app/page_card.py) 的 `get_setting()` 在重建 `MirrorTeamCombination` 前执行内存归一化，避免复选框构造时读取过期投影。新增空白编队后归一化；[BaseCheckBox.on_toggle()](../../../../app/base_tools.py) 调用 `set_team_enabled()`，随后通过 `mediator.refresh_teams_order` 刷新激活数字。

删除编队按以下顺序维护同一份关系：

1. 从队列和 `teams` 移除目标槽位，删除其主题包权重配置。
2. 将剩余槽位按旧编号升序压缩，构造 `old_to_new` 映射。
3. 按映射迁移主题包权重配置，并重写队列；保留各 `TeamSetting` 对象及其游戏内队伍序号。
4. 归一化、保存，再通过 `get_setting()` 重建 widget。

例如 `{1,2,3,4,5,6}` 删除槽位 `3` 后，映射为 `{1:1,2:2,4:3,5:4,6:5}`，队列 `[2,6,4]` 变为 `[2,5,3]`，激活数字为 `[0,1,3,0,2]`。

`retranslateUi()` 只更新文本，不能替代 widget 重建；`refresh()` 只刷新激活数字，不负责修复对象名或槽位身份。星光卡片对可能已删除的槽位继续使用 `.get()` 读取，当前入口位于 [app/starlight_bonus.py](../../../../app/starlight_bonus.py)。

### 镜牢取队与轮转

[Mirror_task()](../../../../tasks/base/script_task_scheme.py) 在检查队伍用途前归一化，使用 `teams_active_queue[0]` 取队，不从 `teams_order.index(1)` 推算。

- 队首的固定用途不匹配当前难度时，调用 `rotate_team_queue()` 跳过；跳过不消耗镜牢执行次数。
- 一轮镜牢确认成功后调用同一入口轮转，再减少剩余次数。
- 队列为空或没有匹配当前难度的启用队伍时退出；不能靠持续轮转等待可用队伍。
- 单轮未确认成功时停止后续镜牢，不轮转到下一队或消耗本轮次数。

`rotate_team_queue()` 先归一化，将队首移到队尾，再同步投影并保存；空队列和单队列不改变顺序。

## 曾考虑的替代方案

- 继续由各业务入口分别同步启用标记、激活数字和计数：这是被队列方案替代的多源状态做法，增删与轮转需要重复维护相同关系。
- 为编队引入稳定 `team_id`，并把主题包权重文件一起迁移到稳定 ID：该方案同时改变队伍身份与文件命名。队列方案保留槽位编号、配置习惯和现有 UI，稳定 ID 需要独立设计。
- 删除后只调用 `retranslateUi()`：保留旧 widget 身份的做法不能同步压缩后的槽位，因此删除流程采用完整重建。

## 后果

旧字段继续存在以兼容现有消费者，但其内容由队列决定。槽位仍然可重编号，任何新增的删除或压缩入口都必须同时处理队列、主题包权重和 UI 身份，不能只修改 `teams`。

此决策不改变 UI 文案，不把主题包文件改为稳定 ID 命名，也不要求结构性重写队伍设置页。归一化不改变用户选中的游戏内队伍序号。

当前有两处需要准确区分实现边界：`create_team_from_file()` 仍临时直接补长兼容数组，随后由 `get_setting()` 统一归一化；[启动检查](../../../../app/farming_interface.py) 仅在启用数量与投影不符时归一化，任务入口仍会无条件归一化。前者是集中写入约束的现存偏差，不作为新增入口的示例。

## 关键验证

变更此决策涉及的代码时，优先选择 [test_team_queue_normalization.py](../../../../tests/test_team_queue_normalization.py) 中直接相关的现有检查；结果结算涉及 [test_mirror_reward_completion.py](../../../../tests/test_mirror_reward_completion.py)。需要覆盖的行为包括：

- 旧配置迁移、重复顺序值、部分有效顺序与剩余勾选项；显式空队列不恢复旧选择。
- 幽灵编号、重复编号、布尔值过滤；内存归一化不持久化，也不覆盖 `TeamSetting.team_number`。
- 删除中间或最前槽位后的映射、主题包权重与 widget 重建；保存后重新加载仍保持执行顺序。
- 新增编队后勾选、删除已勾选编队后激活数字连续；删除后打开星光卡片。
- 队首选取、固定用途跳过、成功轮转，以及未确认成功时停止。

真实界面与游戏运行验证按任务授权选择；文档维护只核对源码、现有检查定义和引用，不因本记录运行游戏或业务测试。
