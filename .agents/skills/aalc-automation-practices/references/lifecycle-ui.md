# 生命周期、UI 与配置

## 目录

1. 协作式停止
2. 阻塞操作
3. UI 通信与重翻译
4. 主题和调试开关
5. 配置同步

## 1. 协作式停止

主线程入口是 `tasks/base/script_task_scheme.py::my_script_task`。

- `stop()` 只请求停止，不强制终止线程。
- 长任务调用 `auto.ensure_not_stopped()`；输入处理器使用自己的停止检查。
- 停止通过 `userStopError` 传播到统一收尾。
- `run()` 收尾清除停止状态、断开 OBS 并发出 `mediator.script_finished`。
- `FarmingInterfaceLeft.handle_script_finished()` 恢复 UI、清理模拟器连接。

不要用 `QThread.terminate()` 实现正常停止。

## 2. 阻塞操作

修改以下路径时逐个检查等待循环：

- 游戏启动；
- `screen.init_handle()` 窗口发现；
- `MumuControl` / `SimulatorControl` 启动和重连；
- 停止后的清理与重试。

等待中加入停止检查，重试必须有界。`closeEvent()` 的优雅退出预算最多 5 秒，不能把 UI 线程卡在无限等待。

## 3. UI 通信与重翻译

- 跨页面和线程通过 `mediator` 信号通信，不直接持有其他页面实例。
- 需要响应语言切换的组件注册到 `LanguageManager()` 并实现 `retranslateUi`。
- 动态销毁组件时注销语言管理器。
- 持久配置使用 `cfg.set_value()`；只更新当前 UI 状态使用 `cfg.unsaved_set_value()`。

## 4. 主题和调试开关

- `tasks/tools/` 的独立 QWidget 在初始化时连接 `qconfig.themeChanged`。
- `_apply_theme_style()` 同时应用工具窗口主题和状态标签样式。
- 子 `debug_*` 同时受 `debug_mode` 与自身开关门控。
- 关闭 `debug_mode` 时，显式重置所有子开关和对应 UI。
- 新增 debug 开关前读取 `.opencode/tools/debug_model_constitution.md`，不要在这里复制完整模板。

## 5. 配置同步

新增配置至少检查：

- `module/config/config_typing.py`
- `assets/config/config.example.yaml`
- 对应 UI 卡片及读取/写入点

不要修改或覆盖用户根目录 `config.yaml` 来同步默认值。调试描述保持三类语义一致：日志+截图、仅截图、仅日志。
