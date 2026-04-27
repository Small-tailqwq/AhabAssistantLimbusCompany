# AhabAssistantLimbusCompany — Agent 指引

## 快速命令

```ps1
uv sync --frozen                                         # 安装依赖
uv run python .\main.py                                  # 生产运行
uv run python .\main_dev.py                              # 开发运行（热重载）
uv run python .\main_dev.py --no-reload                  # 开发运行（无热重载）
uv run ruff check .                                      # Lint
uv run python -m py_compile path\to\file.py              # 语法检查
uv run python .\scripts\build.py --version dev           # 构建
uv run python .\scripts\translation_files_build.py       # 刷新 ts 源
uv run python .\scripts\translation_files_compile.py     # 编译 ts → qm
```

## 项目现实

- Windows-only 桌面自动化，Python 3.12+，`uv` 管理
- 无自动化测试套件；`test/` 下是手动脚本，依赖真实游戏/OBS/模拟器
- `ruff` 已配置；遗留模块已有预存警告（通配符导入、裸 `except`），功能开发中不做无关清理

## 架构要点

| 层 | 目录 | 关键文件 |
|---|---|---|
| 入口 | 根目录 | `main.py`（生产）, `main_dev.py`（开发）, `updater.py` |
| UI | `app/` | `my_app.py`（主窗口）, `mediator.py`（信号总线）, `farming_interface.py` |
| 任务编排 | `tasks/base/` | `script_task_scheme.py`（`my_script_task` 线程类） |
| 镜牢 | `tasks/mirror/` | `mirror.py`, `search_road.py`, `in_shop.py` |
| 共享服务 | `module/` | 单例：`cfg` / `auto` / `ocr` / `screen` / `game_process` |
| OBS 截图 | `module/automation/` | `obs_capture.py` |
| 图片资源 | `assets/images/` | `default/{en,zh_cn,share}/`, `dark/` |

## 核心约定

- **配置**：持久化用 `cfg.set_value()`，临时 UI 更新用 `cfg.unsaved_set_value()`。绝不重新实例化 `cfg`。
- **单例**：绝不重新实例化 `cfg`、`auto`、`ocr`、`screen`、`game_process`。
- **图片**：`ImageUtils.load_image(相对key)`，如 `mirror/road_in_mir/enter_assets.png`。路径经 `utils.pic_path` 语言感知处理。
- **通信**：跨组件/线程走 `mediator` 信号，不直接持有其他页面实例。
- **语言切换**：UI 组件向 `LanguageManager()` 注册并实现 `retranslateUi`；动态销毁需注销。
- **调试开关**：关闭父级 `debug_mode` 时，所有子调试开关必须重置为 `False`。
- **提交信息**：使用中文。

## 生命周期

- 主脚本线程：`tasks/base/script_task_scheme.py` 中的 `my_script_task`
- 启动/停止 UI：`app/farming_interface.py`
- **停止是协作式的，不是强制的**：
  - `my_script_task.stop()` → `auto.request_stop()`
  - 长任务必须检查 `auto.ensure_not_stopped()` 或调用输入处理器的 `check_stop_requested()`
  - 停止传播为 `userStopError`
  - `run()` 结束时清除停止状态、断开 OBS、发出 `mediator.script_finished`
  - `FarmingInterfaceLeft.handle_script_finished()` 恢复 UI、清理模拟器连接
- 绝不用 `QThread.terminate()` 做正常停止

## 启动与停止安全

- 启动可能阻塞：游戏启动、窗口句柄发现、模拟器启动
- 修改 `init_game()`、`screen.init_handle()`、`MumuControl`、`SimulatorControl` 时，要在阻塞等待中加入停止检查
- `app/my_app.py::closeEvent()` 最多等 5 秒优雅退出；停止路径中避免无限等待
- 停止后清理的重试有界，防止冻结 UI 线程

## OBS 截图

- 通过 `cfg.lab_screenshot_obs` 启用
- `script_task()` 启动前用 `get_obs_capture().validate_capture_ready()` 预检
- 预检会清除连接冷却，方便用户修好 OBS 后立即重试
- 关闭时始终调用 `disconnect_obs_capture()`

## 镜牢

- `MirrorMap` 缓存每层路线数据。优先复用缓存或定向重试，避免盲目加 `take_screenshot=True` 轮询
- 键盘导航可复用缓存方向；鼠标导航需要根据巴士当前位置重新计算点击目标
- 输入模式分叉：前台、后台、Logitech、OBS、模拟器——各模式行为不统一

## 验证

修改停止流程后至少手动验证：
- 从 UI 按钮启停
- `Ctrl+Q` 在任务执行中停止
- 在启动或模拟器等待中停止
- OBS 启用的启动预检
- 线程结束后 UI 恢复

## 本地 Issue 追踪

`issues/` 目录存放 bug 记录，不纳入版本控制。模板：`issues/TEMPLATE.md`。

典型文件：
- `<id>.md` — 描述、复现步骤、日志片段
- `<id>.log` — 完整日志
- `config_<id>.yaml` — 当时配置
- `screenshot_<id>.png` — 可选截图

流程：读取 issue → 分析根因 → 修复 → 清理临时文件，保留 issue 记录。

## 灾难恢复

当对话中提及文件损失报告（`issues/loss-report-*.md`）时，执行以下流程：

1. **读取损失报告**，提取被删除的文件/目录清单及删除操作描述
2. **交叉对比对话上下文**：遍历损失清单，在当前对话历史中搜索是否出现过该文件（被 read/write/edit 操作过、在 diff/讨论中描述过内容或修改）
3. **分级恢复**：
   | 匹配类型 | 恢复策略 |
   |---------|---------|
   | 对话中写了**完整内容**（write 操作） | 从上下文直接重建文件 |
   | 对话中描述了**特定修改**（edit 操作、diff 片段） | 先 `git show HEAD:<路径>` 获取基准，再叠加修改 |
   | git 跟踪但对话中**仅提及路径**无内容 | 从 `git show HEAD:<路径>` 恢复基准版本 |
   | 对话中**从未出现** | 标记为不可恢复，不虚构内容 |
4. **逐文件验证**：恢复后确认内容与对话描述一致
5. **输出恢复报告**：`✅ 已恢复（来源）` / `❌ 不可恢复（原因）` / `⚠️ 部分恢复（说明）`

**原则：宁可标记不可恢复，也绝不凭空生成。git 跟踪文件优先从 git 恢复基准再叠加对话变更。**

## 参考

- `README.md`
- `assets/doc/zh/develop_guide.md`
- `assets/doc/zh/build_guide.md`
- `assets/doc/zh/translateGuide.md`
- `assets/doc/zh/image_recognition.md`
- `assets/doc/zh/FAQ.md`
- `assets/doc/zh/How_to_use.md`
- `assets/doc/zh/Custom_setting.md`
