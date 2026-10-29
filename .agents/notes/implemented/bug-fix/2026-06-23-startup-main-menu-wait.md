# Agent Note: 启动后等待主界面与任务中途返回主界面分开计时

Status: implemented

## 问题

[back_init_menu()](../../../../tasks/base/back_init_menu.py) 处理任务中途从未知界面回到主界面，需要尽快收敛，避免卡死时长期空转。刚启动游戏时，画面会在标题页、清缓存页、连接页和加载页之间长时间切换。两者共用 `LOOP_COUNT = 30` 时，启动阶段的每个 `continue` 都消耗兜底预算，主界面出现前就会触发 `kill_game()`。issue #752 的日志显示首次失败发生在 `init_game()` 之后的第一次 `back_init_menu()`。

## 决策

刚启动过游戏的路径由 `wait_until_main_menu_after_launch()` 等待主界面，按秒计时；`back_init_menu()` 保留 30 次预算，继续承担任务前回主界面、中途异常兜底和退出战斗、剧情或镜牢菜单。

- [script_task_scheme.py](../../../../tasks/base/script_task_scheme.py) 在 PC 发起启动（游戏原本未运行）或模拟器拉起游戏时调用 `mark_startup_main_menu_wait_pending()`，`init_game()` 结束前消费该标记并进入启动等待；超时抛出 `cannotOperateGameError`。
- [retry.py](../../../../tasks/base/retry.py) 的 `restart_game()` 在 `init_game()` 后进入启动等待；模拟器自动拉起游戏后同样由启动等待接管。
- 等待上限来自 `startup_wait_timeout_pc`（默认 120 秒）和 `startup_wait_timeout_simulator`（默认 180 秒），定义在 [config_typing.py](../../../../module/config/config_typing.py) 与 [config.example.yaml](../../../../assets/config/config.example.yaml)，设置页可调。
- 启动等待自行处理清缓存确认、连接、等待和唯一选项弹窗，先处理这些可长时间静止的已知画面，再做截屏冻结判断；识别到运行中界面返回 `RUNTIME_UI`，识别到主页窗口与邮件入口返回 `MAIN_MENU`。等待到一半时记录日志，每轮检查 `auto.ensure_not_stopped()`。
- 启动等待不调用 `retry()`。运行中的网络与异常重试保持 `check_times(timeout=90)` 的卡死检测语义。

## 曾考虑的替代方案

**启动等待复用 `retry()`。** `retry()` 固定 90 秒触发 `kill_game()` 与 `restart_game()`；启动等待默认 120／180 秒且可调大，复用会让 90 秒先触发重启，覆盖启动超时设置。两者只共享标题页安全点击等小范围识别与点击辅助。

**用循环次数表达启动预算。** 启动阶段单轮耗时随截图、识别和画面变化而不稳定，次数没有稳定的时间含义；用户诉求（issue #747、#752）是可调的启动等待时长，因此用秒数。

## 后果

冷启动、重启游戏和模拟器自动拉起使用独立的秒数预算，不消耗中途兜底的 30 次预算，`back_init_menu()` 的快速收敛语义不变。PC 与模拟器的等待时长可分别按机器性能调节。

默认上限较长，启动真正卡死时恢复会比中途兜底慢，但仍是有界等待。启动等待与 `retry()` 各自处理启动画面，新增启动态时需要同时核对两处。[test_startup_main_menu_wait.py](../../../../tests/test_startup_main_menu_wait.py) 与 [test_simulator_recovery.py](../../../../tests/test_simulator_recovery.py) 覆盖调用链与超时路径。
