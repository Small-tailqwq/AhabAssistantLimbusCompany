# AhabAssistantLimbusCompany — Agent 指引

`origin` → Small-tailqwq/AhabAssistantLimbusCompany，`upstream` → KIYI671/AhabAssistantLimbusCompany。

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

## 日志分析工具
uv run python .opencode/tools/log_analyzer.py <log>      # 日志压缩报告
uv run python .opencode/tools/mirror_analyzer.py <logs>  # 镜牢耗时分析（支持多文件）
```

> **Windows CI 编码陷阱**：`scripts/build.py` 中的 `print()` 如果包含非 ASCII 字符（中文、`→`、`✓` 等），在 GitHub Actions Windows runner（cp1252 终端）会触发 `UnicodeEncodeError` 导致构建失败。所有输出文本必须使用纯 ASCII（英文 + 基本符号）。`v1.5.0-canary.5` 因 `→` 字符构建失败，浪费一个版本号。

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

## 文件删除严格管控（最高优先级）

**绝不替用户删除任何本地文件。** 这是不可逾越的红线。

### 禁止的操作

- `git clean -fd` / `git clean`
- `rm` / `rmdir` / `rd` / `erase` / `del`
- `Remove-Item` / `ri`
- 任何通过 `cmd /c`、`pwsh -c`、`python -c` 包装的删除
- 写入文件时覆盖用户已存在的本地文件（如 write 工具覆盖）
- 代码中调用 `os.remove()`、`shutil.rmtree()` 等

以上操作已被全局 `opencode.json` 的 permission 规则通过 `deny` 阻断。

### 例外流程

当确实需要清理文件时（如清理已知的无用构建产物），必须：
1. 使用 **`question` 工具**向用户说明：需要删除什么、为什么、具体路径
2. 等待用户明确同意后再执行
3. 执行后报告结果

**这样用户同意后可以不中断会话直接回复，避免 permission ask 导致的会话中断。**

### 原则

- 需要删除 → 告知用户，让用户决定
- 写入文件发现目标已存在 → 先问用户是否覆盖
- 不慎执行了可能删除文件的操作 → 立即报告用户

## 🔒 安全红线：禁止在对话中泄漏凭证

**任何形式的 token、密码、API key 都不得在对话上下文中明文出现。** 包括：
- `$env:GITHUB_TOKEN` 等环境变量值的任何部分（即使截断）
- 配置文件中的 `apiKey`、`password`、`secret` 等字段值（包括配置文件的原始内容）
- `read-credential.ps1` 等脚本读取到的凭据输出值

读取凭证后必须直接用于 API 调用，不可在回复/日志中出现其值（包括部分截断）。

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

## 参考

- `README.md`
- `assets/doc/zh/develop_guide.md`
- `assets/doc/zh/build_guide.md`
- `assets/doc/zh/translateGuide.md`
- `assets/doc/zh/image_recognition.md`
- `assets/doc/zh/FAQ.md`
- `assets/doc/zh/How_to_use.md`
- `assets/doc/zh/Custom_setting.md`
