# 镜牢编队队列归一化设计

## 1. 概述

当前镜牢编队系统把同一份业务事实分散保存在 4 份状态里：

- `teams`
- `teams_be_select`
- `teams_order`
- `teams_be_select_num`

删除编队、新增编队、勾选编队、镜牢轮转分别在不同位置直接修改这些字段，导致它们容易失去一致性。近期连续出现的 `NameError`、`IndexError`、`KeyError`、新增后日志报错、激活编号不是从 1 开始等问题，本质上都来自这套多源状态模型。

本设计的目标是：

- 保持现有 UI 文案和用户认知不变
- 保持现有配置文件尽量兼容
- 用最小破坏性改动引入单一事实源，根除顺序漂移和长度失配问题

## 2. 术语澄清

- `编队 N`：配置槽位编号，也是当前代码中的 `teams` 字典键
- `激活数字 N`：镜牢执行队列中的位置，不是主键

例如：

- `teams_active_queue = [2, 5, 1]`
- 表示下次先跑编队 2，然后编队 5，然后编队 1
- 派生出来的 `teams_order` 应为 `[3, 1, 0, 0, 2]`

这与开发者说明一致：每次执行激活 1 的队伍，执行完成后把它轮转到最后。

## 3. 根因

### 3.1 多源状态

同一事实被拆成 4 份：

- 哪些编队存在：`teams`
- 哪些编队启用：`teams_be_select`
- 启用了多少个：`teams_be_select_num`
- 启用编队的执行顺序：`teams_order`

这些状态之间没有单一权威来源，也没有统一归一化入口。

### 3.2 删除后的重编号污染

`refresh_team_setting_card()` 会把 `teams` 的 key 压缩重排。例如删除 `team_3` 后：

- 删除前：`teams = {1,2,3,4,5,6}`
- 删除后：`teams = {1,2,3,4,5}`，原 `4->3`、`5->4`、`6->5`

如果执行队列仍保留旧编号，就会与压缩后的 `teams` 漂移。

例如：

- 删除前 `queue = [2, 6, 4]`
- 删除后必须变成 `queue = [2, 5, 3]`

这是显式的 reindex 逻辑，不能依赖派生规则自动解决。

### 3.3 UI widget 与配置槽位脱节

删除编队后如果只调用 `retranslateUi()`，widget 仍可能保留旧的 `team_4`、`team_5`、`team_6` 标识，而配置已经压缩为 `teams {1,2,3,4,5}`。此时 `refresh()` 按 widget 当前编号读取 `teams_order[number - 1]`，会出现展示错位。

因此删除编队后必须重建 widget，而不是只重译文本。

## 4. 设计原则

### 4.1 单一事实源

新增 `teams_active_queue: list[int]`，作为镜牢启用状态与执行顺序的唯一事实源。

其含义：

- 元素值是当前存在的编队编号（1-based）
- 元素顺序是镜牢执行顺序
- 不在 queue 中的编队视为未启用

### 4.2 旧字段保留为兼容投影

以下旧字段继续保留在配置模型中，用于兼容现有 UI 和历史代码：

- `teams_be_select`
- `teams_order`
- `teams_be_select_num`

但它们不再允许被业务代码直接写入，只能由统一归一化函数从 `teams_active_queue` 派生回写。

### 4.3 统一归一化入口

所有新增、删除、勾选、轮转、启动校验都必须收口到一个统一入口：

- `normalize_and_sync_team_state()`

该函数负责：

- 迁移旧配置
- 清理非法 queue
- 处理去重
- 派生旧字段
- 保证长度和顺序一致

## 5. 数据模型

在 `ConfigModel` 中新增：

```python
teams_active_queue: List[int] = []
```

### 5.1 不变量

每次归一化后都必须满足：

- `len(teams_be_select) == len(teams)`
- `len(teams_order) == len(teams)`
- `teams_be_select_num == len(teams_active_queue)`
- `teams_active_queue` 中每个值都属于当前 `teams` 的 key 集合
- `teams_active_queue` 中无重复
- `teams_order` 的非零值必须是 `1..N` 全排列，其中 `N = len(teams_active_queue)`

### 5.2 派生规则

```python
team_count = len(teams)
teams_be_select = [False] * team_count
teams_order = [0] * team_count

for order, team_num in enumerate(teams_active_queue, start=1):
    teams_be_select[team_num - 1] = True
    teams_order[team_num - 1] = order

teams_be_select_num = len(teams_active_queue)
```

## 6. 迁移与自愈

### 6.1 旧配置迁移

当配置中不存在 `teams_active_queue` 时，由旧字段迁移生成：

1. 若 `teams_order` 可解释：
   - 收集所有 `>0` 的项
   - 按值升序还原执行顺序
   - 生成 queue
2. 否则回退到 `teams_be_select`：
   - 按编号从小到大收集启用编队
   - 生成 queue

### 6.2 已有 queue 的校验

如果 `teams_active_queue` 已存在，则：

- 过滤不存在于 `teams` 的编号
- 去重
- 保留原顺序

### 6.3 normalize 的执行时机

`normalize_and_sync_team_state()` 必须在 UI 构建之前执行，避免 `BaseCheckBox.__init__` 读取到脏的 `teams_be_select`。

执行时机：

- 配置加载完成后
- `PageMirror.get_setting()` 开始构建 widget 之前
- 启动镜牢前的检查阶段
- 每次编队增删/勾选/轮转后

## 7. 删除与重编号

### 7.1 删除流程

删除编队 `team_N` 的正确流程：

1. 从 queue 中移除 `N`
2. 删除 `teams[N]`
3. 构造 `old_to_new` 映射，把剩余 `teams` key 压缩为连续编号
4. 用映射重写 `teams_active_queue`
5. 同步主题包权重配置的重命名/删除
6. 执行 `normalize_and_sync_team_state()`
7. 调用 `get_setting()` 重建 UI widget

### 7.2 queue reindex 规则

示例：

- 删除前：`teams={1,2,3,4,5,6}`，`queue=[2,6,4]`
- 删除 `3`
- `old_to_new={1:1,2:2,4:3,5:4,6:5}`
- reindex 后：`queue=[2,5,3]`

重写规则：

```python
new_queue = [old_to_new[team_num] for team_num in old_queue if team_num in old_to_new]
```

### 7.3 UI 重建要求

删除编队后不能只调用 `retranslateUi()`。

原因：

- `retranslateUi()` 仅更新文本
- 不会刷新 `MirrorTeamCombination` 的对象名和 `team_number`
- 会导致 widget 编号与压缩后的配置编号不一致

因此设计要求：

- `delete_team()` 末尾必须调用 `get_setting()` 重建 widget
- `refresh()` 仅用于刷新展示，不承担重建职责

## 8. 镜牢轮转

### 8.1 当前问题

当前镜牢轮转直接写 `teams_order`，这与“旧字段仅为派生投影”的设计冲突。

### 8.2 新规则

镜牢执行逻辑改为直接操作 `teams_active_queue`：

- 当前队伍：`queue[0]`
- 执行后轮转：`queue.append(queue.pop(0))`

固定用途不适用于当前难度时，也使用同样的轮转规则跳过当前队伍。

### 8.3 轮转后同步

每次轮转后必须调用：

- `normalize_and_sync_team_state()`

不再允许业务代码直接 `set_value("teams_order", ...)`。

## 9. 函数级改动清单

### 9.1 `module/config/config_typing.py`

- 在 `ConfigModel` 新增 `teams_active_queue`

### 9.2 `module/config/config.py`

新增集中方法：

- `get_team_numbers()`：返回当前存在的编队编号，按升序
- `migrate_legacy_team_queue()`：从旧字段构建 queue
- `normalize_and_sync_team_state()`：归一化并派生旧字段
- `reindex_team_queue(old_to_new)`：删除压缩后重写 queue
- `rotate_team_queue()`：轮转当前队列
- `remove_team_from_queue(team_num)`：删除特定编队
- `set_team_enabled(team_num, enabled)`：勾选/取消勾选统一入口

要求：

- 这些方法是唯一允许写 `teams_active_queue` 和旧派生字段的位置
- 业务层不再自行修改 `teams_order`、`teams_be_select`、`teams_be_select_num`

### 9.3 `app/base_tools.py`

`BaseCheckBox.on_toggle()` 中 `the_team_*` 分支：

- 删除直接操作 `teams_be_select` / `teams_order` / `teams_be_select_num` 的逻辑
- 改为调用 `cfg.set_team_enabled(team_num, checked)`
- 之后发 `mediator.refresh_teams_order.emit()`

### 9.4 `app/page_card.py`

`PageMirror.get_setting()`：

- 开始构建 widget 前先调用 `cfg.normalize_and_sync_team_state()`
- 删除手工补长 `teams_be_select` / `teams_order` 的 grow 逻辑

`PageMirror.new_team()`：

- 新增 `teams[number]` 后调用 `cfg.normalize_and_sync_team_state()`
- 不再手工 append `teams_be_select` / `teams_order`

`PageMirror.delete_team()`：

- 删除目标队伍
- 重排 `teams` key
- 用 `old_to_new` 重写 queue
- 执行 `cfg.normalize_and_sync_team_state()`
- 最后调用 `get_setting()` 重建 widget
- 不再依赖 `retranslateUi()` 修复结构

`PageMirror.refresh_team_setting_card()`：

- 保留为“重排 teams key + 主题包配置”职责
- 增加 queue reindex 逻辑
- 执行 normalize
- 调用 `get_setting()`

### 9.5 `tasks/base/script_task_scheme.py`

`Mirror_task()`：

- 把 `teams_order.index(1)` 改为读取 `cfg.teams_active_queue[0]`
- 跳过固定用途不匹配的队伍时，调用 `cfg.rotate_team_queue()`
- 镜牢完成后，调用 `cfg.rotate_team_queue()`
- 删除直接写 `teams_order` 的逻辑

当前只有这一处 `teams_order.index(1)`，无需额外清理其它调用点。

### 9.6 `app/farming_interface.py`

启动检查时：

- 删除分散的旧字段自愈逻辑
- 改为调用 `cfg.normalize_and_sync_team_state()`
- 之后基于规范化结果继续检查是否存在可用队伍

### 9.7 `app/team_setting_card.py`

- 保留 `StarlightCard` 中 `.get()` 的防御性读取
- 该处不参与 queue 逻辑，不引入新行为变化

## 10. 场景推演

### 10.1 场景 A：删除中间编队

初始：

- `teams={1,2,3,4,5,6}`
- `queue=[2,6,4]`

删除 `team_3` 后：

- `old_to_new={1:1,2:2,4:3,5:4,6:5}`
- 新 queue 为 `[2,5,3]`
- `normalize()` 后：
  - `teams_be_select=[False, True, True, False, True]`
  - `teams_order=[0, 1, 3, 0, 2]`
  - 长度均为 5

结果：

- 无越界
- 无缺号
- 执行顺序保持原语义

### 10.2 场景 B：删除后打开星光卡片

`StarlightCard` 继续使用 `.get()` 防御读取。

结果：

- 删除后的短暂缺失状态不会触发 `KeyError`
- queue 重构不会引入此处新问题

### 10.3 场景 C：旧配置中 queue 含幽灵编号

例如：

- `teams={1,2,3,4}`
- `queue=[2,6,1]`

执行 `normalize()` 后：

- 过滤非法编号 `6`
- 新 queue 变成 `[2,1]`
- 旧字段重新派生

结果：

- UI 构建前状态已干净
- 不会触发越界或错位展示

## 11. 验证

至少验证以下路径：

1. 删除中间编队后立即查看主界面
2. 删除最前编队后重启程序
3. 新增超过旧配置初始个数的编队并勾选
4. 勾选多个编队后删除其中一个，再检查激活数字是否重新变成连续 `1..N`
5. 运行镜牢一轮，确认执行完后队列正确轮转
6. 固定用途队伍在当前难度不匹配时，确认队列跳过逻辑正确
7. 用不含 `teams_active_queue` 的旧配置启动，确认自动迁移成功

## 12. 范围控制

本次不做：

- 稳定 `team_id` 全量重构
- 主题包权重文件命名从槽位编号迁移到稳定 ID
- UI 文案调整
- 队伍设置页的结构性重写

这是下一阶段才考虑的更大改动。本次仅引入 queue 作为单一事实源，在保持现有用户界面和配置习惯的前提下修复技术债。
