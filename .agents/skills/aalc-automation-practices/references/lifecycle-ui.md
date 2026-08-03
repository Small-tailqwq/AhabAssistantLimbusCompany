# 生命周期、UI 与配置

## 目录

1. 协作式停止
2. 阻塞操作
3. UI 通信与重译
4. 主题与调试开关
5. 配置同步

## 1. 协作式停止

全局任务线程所有者是 `tasks/base/script_task_scheme.py::my_script_task`。

- `stop()` 请求停止而非终止线程。
- 长任务调用 `auto.ensure_not_stopped()`；输入处理器使用其既有的停止检查。
- `userStopError` 传播到集中清理。
- `my_script_task.run()` 收尾时清除停止状态、断开 OBS、发出 `mediator.script_finished`。
- `FarmingInterfaceLeft.handle_script_finished()` 恢复 UI 并清理模拟器连接。

不要要求每个名为 `run()` 的子方法重复全局收尾。正常停止不使用 `QThread.terminate()`。

## 2. 阻塞操作

改动以下等待时逐个检查：

- 游戏启动；
- `screen.init_handle()` 窗口发现；
- `MumuControl` 或 `SimulatorControl` 启动与重连；
- 停止清理与重试路径。

等待需要协作检查与有界重试。`closeEvent()` 最多 5 秒优雅退出，UI 线程绝不能进入无界停止路径。

## 3. UI 通信与重译

- 跨页面、跨线程通过 `mediator` 信号通信，不直接持有其他页面实例。
- 响应语言变化的组件向 `LanguageManager()` 注册并实现 `retranslateUi`。
- 动态注册组件销毁时遵循现有注销模式。
- 持久化配置用 `cfg.set_value()`；当前临时 UI 状态用 `cfg.unsaved_set_value()`。

## 4. 主题与调试开关

- `tasks/tools/` 下独立 QWidget 工具连接 `qconfig.themeChanged`。
- `_apply_theme_style()` 在既定组件模式下同时应用窗口主题与状态标签样式。
- 子级 `debug_*` 行为同时受 `debug_mode` 与自身开关门控。
- 关闭 `debug_mode` 会重置子开关及其 UI 状态。
- 新增调试开关前读 `.opencode/tools/debug_model_constitution.md`；不要在此重复其模板。

## 5. 配置同步

新增配置字段时至少检查：

- `module/config/config_typing.py`；
- `assets/config/config.example.yaml`；
- 对应 UI 卡片与读写位置。

绝不通过修改或替换用户 `config.yaml` 来更新默认值。保持调试描述在日志加截图、仅截图、仅日志三种行为下的语义准确。
