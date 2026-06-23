# 启动后主界面等待与返回主界面兜底拆分设计

## 背景

当前 `back_init_menu()` 同时承担两类职责：

1. 任务中途从未知界面回到主界面
2. 刚启动游戏后等待进入主界面

这两类场景的超时语义完全不同：

- 任务中途兜底需要尽快收敛，避免卡死时长期空转
- 冷启动需要容忍标题页、清缓存页、连接页、加载页之间的长时间切换

现状中两者共用 `back_init_menu()` 的 `loop_count = 30`。在 `22ca6dfb` 将 `loop_count -= 1` 移到循环顶部后，`clear_all_caches_assets`、`connecting_assets`、`waiting_assets` 等启动阶段的 `continue` 也会消耗这 30 次预算，导致启动还没完成就触发 `kill_game()`。

issue #752 的日志已确认：首次失败发生在 `init_game()` 之后第一次 `back_init_menu()`，并非任务中途兜底，也不是 `retry.check_times(timeout=90)` 先触发。

## 目标

1. 拆分“启动后等待主界面”和“任务中途返回主界面兜底”两条路径
2. 保留 `back_init_menu()` 的快速兜底语义，不再让其承担冷启动等待职责
3. 为模拟器和 PC 分别提供可配置的启动后主界面等待秒数
4. 覆盖首次启动、重启游戏、运行中自动拉起游戏三类“刚启动过游戏”的场景
5. 保持停止检查、有界等待和现有单例/线程约束不变

## 非目标

1. 不重做 `retry()` 的 90 秒卡死检测语义
2. 不全面改造所有任务模块的超时策略
3. 不改动用户现有 `config.yaml`，仅新增默认字段与 UI
4. 不顺手清理与本问题无关的识图、日志或历史 warning

## 根因总结

### 直接根因

`back_init_menu()` 的 30 次循环预算被用于冷启动场景。启动阶段的多个 `continue` 分支会持续消耗预算，最终在主界面真正出现前触发 `kill_game()`。

### 放大因素

1. `restart_game()` 在重新 `init_game()` 后仍直接调用 `back_init_menu()`
2. `ensure_simulator_game_started()` 自动拉起游戏后，调用者仍继续走同一条通用兜底路径
3. MuMu 截屏冻结检测会进一步消耗循环时间，但它不是原始回归点，只会放大误杀概率

## 设计方案

采用“职责拆分 + 启动等待显式建模”的方案。

### 新增启动等待函数

新增一个专门的启动等待入口，例如 `wait_until_main_menu_after_launch()`，职责仅限：

1. 游戏已被启动或刚被拉起
2. 允许经历标题页、更新确认、清缓存页、连接页、等待页
3. 用“秒数预算”控制超时，而不是复用 `back_init_menu()` 的 30 次预算

它不会承担任务中途复杂状态收敛的职责，也不会替代 `back_init_menu()`。

### 与 `retry()` 的关系

启动等待函数**不直接调用现有 `retry()`**。

原因：

1. `retry()` 内部固定使用 `check_times(timeout=90)`
2. 启动等待默认目标是 120/180 秒，可配置值也可能大于 90 秒
3. 如果直接复用 `retry()`，则会在 90 秒先触发 `kill_game() + restart_game()`，覆盖新的启动等待超时语义

因此启动等待函数将自己处理冷启动相关状态，不继承 `retry()` 的 90 秒超时语义。

保留 `retry()` 的原则：

1. 运行中网络重试、异常重试仍保持现有 90 秒语义
2. 冷启动等待使用独立的秒数预算
3. 两者只共享小范围的识别/点击辅助逻辑，不共享超时控制器

### `back_init_menu()` 继续保留

`back_init_menu()` 继续用于：

1. 各任务执行前确保回到主界面
2. 任务中途异常状态兜底
3. 战斗、剧情、镜牢菜单等运行中状态退出

它的核心语义保持“快速收敛”，默认仍保留当前较小预算，不做冷启动级别的超长等待。

### 启动等待的调用点

启动等待函数应覆盖以下调用点：

1. `script_task_scheme.py::script_task()` 中 `init_game()` 之后
2. `tasks/base/retry.py::restart_game()` 中 `init_game()` 之后
3. `tasks/base/retry.py::ensure_simulator_game_started()` 触发自动拉起游戏之后，由调用者接管进入启动等待路径

这样可以覆盖：

1. 首次运行 AALC 时自动启动游戏
2. 运行中 `kill_game() + restart_game()` 后再次等待主界面
3. 模拟器里游戏被系统杀掉或退到后台后被自动重新拉起

## 超时配置

新增两个配置字段：

1. `startup_wait_timeout_pc: int = 120`
2. `startup_wait_timeout_simulator: int = 180`

语义：

- 从“确认发起游戏启动”到“允许进入主界面等待流程超时”的总秒数上限
- PC 与模拟器默认值分开，模拟器默认更长

选择秒数而不是循环次数的原因：

1. 用户更容易理解和调节
2. 启动阶段的单轮耗时不稳定，循环次数没有稳定时间语义
3. issue #747 / #752 的用户诉求本质就是“启动等待时长可调”

## 启动等待函数的行为

### 成功条件

当识别到主界面条件满足时返回成功：

- `home/window_assets.png`
- `home/mail_assets.png`

### 允许处理的启动态

启动等待函数允许并持续等待以下状态：

1. `clear_all_caches_assets`
2. `update_confirm_assets`
3. `only_option_assets`
4. `connecting_assets`
5. `waiting_assets`
6. `waiting_2_assets`

并保留标题页处理能力：

7. `clear_all_caches_assets` 命中时，沿用 `click_title_screen_safely()` 的点击穿透逻辑
8. `click_title_screen_safely()` 的 5 秒 CD 与轮换点击点语义保持不变

这样可以覆盖：

1. 标题页需要安全点击进入
2. 更新确认后再次回到标题页
3. 标题页、连接页、等待页之间往返切换

这些状态不应消耗 `back_init_menu()` 的 30 次兜底预算，而应只消耗秒数预算。

### 超时后的处理

启动等待超时后，沿用现有恢复策略：

1. 记录明确日志，区分“启动后等待主界面超时”和“返回主界面失败”
2. 若允许恢复，则走 `kill_game() + restart_game()`
3. 若调用点明确禁用恢复，则返回失败

这样可以保留现有自动恢复能力，但避免在冷启动期间过早误杀。

### 与 `retry.check_times(90)` 的边界

启动等待函数内部不调用 `check_times(timeout=90)`。

它只使用自己的 deadline：

1. PC 使用 `startup_wait_timeout_pc`
2. 模拟器使用 `startup_wait_timeout_simulator`

因此：

1. 冷启动阶段不会被 `retry()` 的 90 秒先截断
2. 运行中 `retry()` 仍保持原有 90 秒恢复语义
3. 两种超时来源在调用链上严格分离

## 代码结构调整

### `tasks/base/back_init_menu.py`

新增：

1. 启动等待超时读取帮助函数
2. 启动等待主函数
3. 共享的“主界面判定/冷启动页处理”小范围内聚逻辑

保留：

1. `back_init_menu()` 对运行中场景的退出分支
2. 现有 `allow_restart` 语义
3. 冻结检测逻辑，仅仍用于运行中兜底路径

此外明确修改：

1. `back_init_menu()` 中若 `ensure_simulator_game_started()` 返回 `True`，不再直接 `continue` 消耗 30 次预算
2. 此时立即切换到启动等待路径；若启动等待成功，则视为已满足“回到主界面”的目标并返回成功
3. 若启动等待失败，则按调用场景返回失败或交给现有恢复路径处理

### `tasks/base/script_task_scheme.py`

在 `init_game()` 后新增一次显式启动等待调用，确保第一次任务开始前游戏已真正到主界面。

### `tasks/base/retry.py`

1. `restart_game()` 改为在 `init_game()` 后调用启动等待函数，而不是直接 `back_init_menu()`
2. `retry()` 中若 `ensure_simulator_game_started()` 返回 `True`，不再仅重置 `start_time` 后 `continue`
3. 改为由 `retry()` 调用启动等待函数；成功后结束当前 `retry()`，失败则返回失败

为了保持最小改动：

1. `ensure_simulator_game_started()` 继续返回 `bool`，不改公共返回类型
2. 模式切换放在调用者（`back_init_menu()` / `retry()`）中完成
3. 避免在 `ensure_simulator_game_started()` 内部直接依赖启动等待函数，减少职责耦合

## UI 与配置

### 配置模型

同步更新：

1. `module/config/config_typing.py`
2. `assets/config/config.example.yaml`

### 设置界面

在现有“启动游戏”/“模拟器设置”区域新增两个可调卡片：

1. PC 启动后等待主界面超时时间（秒）
2. 模拟器启动后等待主界面超时时间（秒）

建议：

- 模拟器项放在模拟器设置组
- PC 项放在启动游戏设置组

这样用户能直观看出两者对应不同运行模式。

## 测试策略

### 单元测试

新增测试覆盖：

1. `script_task()` 在 `init_game()` 后会调用启动等待函数
2. `restart_game()` 不再直接调用 `back_init_menu()`，而是走启动等待函数
3. `back_init_menu()` 在 `ensure_simulator_game_started()` 返回 `True` 时会切换到启动等待路径，而不是继续消耗 30 次预算
4. `retry()` 在 `ensure_simulator_game_started()` 返回 `True` 时会切换到启动等待路径，而不是继续走 `check_times(90)` 链路
5. 启动等待函数会根据 `cfg.simulator` 读取不同的超时配置
6. 启动等待函数超时后走秒数预算耗尽路径，而不是依赖 `back_init_menu()` 的 30 次预算

### 回归测试重点

1. 原 issue #752 场景：模拟器慢启动，不应在加载期间被 30 次预算误杀
2. 原 `22ca6dfb` 修复的场景：运行中卡在无法返回主界面时，仍能触发普通兜底重启
3. `restart_game()` 链路：首次重启后仍能正确等待到主界面
4. 标题页需要多次安全点击时，仍遵守 `click_title_screen_safely()` 的节流与轮换点击语义

## 风险与约束

### 风险

1. 若启动等待函数过度复用 `back_init_menu()` 的内部细节，容易再次耦合回旧问题
2. 若在 `ensure_simulator_game_started()` 中直接做过重逻辑，可能影响普通轮询节奏
3. 若默认超时设置过长，真正卡死时恢复速度会变慢
4. 若冷启动状态处理与 `retry()` 各自演化而没有共享最小辅助逻辑，后续可能出现分叉维护成本

### 约束

1. 所有等待都必须保留 `auto.ensure_not_stopped()` 检查
2. 不重新实例化 `cfg`、`auto`、`screen`、`game_process`
3. 不覆盖用户现有 `config.yaml`
4. 不把修复扩展成无关的大重构
5. `retry()` 的运行中 90 秒超时语义保持不变，仅冷启动等待链路绕开它

## 推荐默认值

建议默认值：

1. PC：120 秒
2. 模拟器：180 秒

理由：

1. 足以覆盖慢机、慢盘、网络波动和模拟器额外启动开销
2. 明显大于当前误杀窗口（约 15-20 秒）
3. 仍然是有界等待，不会无限卡住

## 实施顺序

1. 先补测试，锁定启动等待调用链
2. 在 `back_init_menu.py` 中引入启动等待函数
3. 替换 `script_task()` 与 `restart_game()` 的调用点
4. 增加配置模型与 `config.example.yaml`
5. 增加设置界面
6. 运行相关 unittest 与 `py_compile`

## 预期结果

修复后：

1. 冷启动、自动重启、自动拉起游戏不再依赖 `back_init_menu()` 的 30 次预算
2. 任务中途返回主界面的快速兜底语义保持不变
3. 用户可按机器性能分别调整 PC/模拟器启动等待时长
4. 本仓库与 upstream 可共享同一修复思路，便于后续 clean cherry-pick 或直接上游提交
