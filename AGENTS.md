# AhabAssistantLimbusCompany — Agent 指引

`origin` → Small-tailqwq/AhabAssistantLimbusCompany；`upstream` → KIYI671/AhabAssistantLimbusCompany。

## 渐进式披露

本文件只保存高频项目不变量。不要预加载所有专项文档；任务命中时再加载：

- 修改或审阅自动化、图片匹配、任务生命周期、UI/config/debug 逻辑：加载 `aalc-automation-practices`。
- 创建、审计或优化 AGENTS/rules/skills：加载全局 `agent-guidance-health`；不可用时按本节原则执行。
- Issue/日志诊断：加载 `analyze`；不可用时读取 `.opencode/skills/analyze/SKILL.md`。
- 用户截图的模板匹配重放：加载 `replay-matching` skill；不可用时读取 `.opencode/skills/replay-matching/SKILL.md`。
- Canary 发版：加载 `canary-release`；不可用时读取 `.opencode/skills/canary-release/SKILL.md`。
- 向上游贡献：加载 `upstream-contribution`；不可用时读取 `.opencode/skills/upstream-contribution/SKILL.md`。
- 代码审阅：加载 `code-review`；不可用时读取 `.opencode/skills/code-review/SKILL.md`。
- 新增/修改 `debug_*`：再读取 `.opencode/tools/debug_model_constitution.md`。

Skill 正文只读任务所需 reference，不要因“可能有用”提前展开。

## 快速命令

```ps1
uv sync --frozen
uv run python .\main.py
uv run python .\main_dev.py
uv run python .\main_dev.py --no-reload
uv run ruff check .
uv run python -m py_compile path\to\file.py
uv run python -m unittest discover -s tests -p "test_*.py" -v
uv run python .\scripts\build.py --version dev
uv run python .\scripts\translation_files_build.py
uv run python .\scripts\translation_files_compile.py
uv run python .\scripts\check_i18n.py --update
uv run python .\scripts\export-requirements-from-uv-lock.py
```

调试工具位于 `.opencode/tools/`：`log_analyzer.py`、`mirror_analyzer.py`、`log_viewer.py`、`match_viewer.py`。模板匹配重放工具：`debug_tools/verify_matching.py`。可复用临时验证脚本放 `debug_tools/`，不纳入 CI。

## 项目现实

- Windows-only 桌面自动化，Python 3.12+，使用 `uv`。
- `tests/` 是 `unittest` 自动化回归；`test/` 是依赖真实游戏/OBS/模拟器的手动脚本。
- 遗留模块存在预存 ruff 警告；功能开发不做无关清理。
- `scripts/build.py` 的输出必须为纯 ASCII，避免 Windows CI cp1252 `UnicodeEncodeError`。

关键入口：

| 范围 | 路径 |
|---|---|
| 启动 | `main.py`、`main_dev.py`、`updater.py` |
| UI/信号 | `app/my_app.py`、`app/mediator.py`、`app/farming_interface.py` |
| 任务线程 | `tasks/base/script_task_scheme.py` |
| 自动化/单例 | `module/` |
| 图片 | `assets/images/default/{en,zh_cn,share}/`、`assets/images/dark/` |
| OpenCode | `.opencode/agents/`、`.opencode/skills/`、`.opencode/reference/` |

## 核心不变量

- 持久化配置使用 `cfg.set_value()`；临时 UI 更新使用 `cfg.unsaved_set_value()`。
- 绝不重新实例化 `cfg`、`auto`、`ocr`、`screen`、`game_process`。
- 图片通过 `ImageUtils.load_image(相对 key)` 加载，路径由 `utils.pic_path` 处理语言和主题。
- 跨组件/线程通信走 `mediator` 信号，不直接持有其他页面实例。
- UI 组件向 `LanguageManager()` 注册并实现 `retranslateUi`；动态销毁时注销。
- 关闭父级 `debug_mode` 时，所有子调试开关重置为 `False`。
- `tasks/tools/` 独立 QWidget 必须响应 `qconfig.themeChanged` 并重新应用工具窗口主题。
- 配置字段/注释同步到 `module/config/config_typing.py` 与 `assets/config/config.example.yaml`，不要覆盖用户 `config.yaml`。
- 提交信息使用中文。

## 生命周期与停止

- 正常停止必须协作式传播：`my_script_task.stop()` → `auto.request_stop()` → `userStopError`。
- 长任务和阻塞等待必须检查 `auto.ensure_not_stopped()` 或输入处理器的停止检查。
- `run()` 收尾时清除停止状态、断开 OBS、发出 `mediator.script_finished`。
- `FarmingInterfaceLeft.handle_script_finished()` 恢复 UI 并清理模拟器连接。
- 不使用 `QThread.terminate()` 进行正常停止。
- 修改游戏启动、窗口句柄或模拟器等待逻辑时，加入停止检查和有界重试。
- `app/my_app.py::closeEvent()` 最多等待 5 秒优雅退出，停止路径不得无限等待。

## 用户资产安全

- 未追踪文件、`issues/`、日志、截图、配置快照和 stash/merge 冲突默认是用户资产。
- 删除、移动、整体覆盖或清理这些内容前，必须按全局规则获得路径级确认。
- 不自行裁决 stash pop/merge 冲突。
- Issue 流程：读取 → 分析 → 修复 → 列出可清理临时文件；保留 issue 记录。

## 发布不变量

- 用户可见更新说明来自 GitHub Release body；发版同时维护 `CHANGELOG.md`。
- 可消费 Release 必须恰好包含一个 `AALC_<version>.7z` 和一个 `AALC.update_manifest.json`。
- 正式 Release 同时上传 `AALC_<version>.7z.sha256`。
- 常规 canary 使用平铺包和当前 `bootstrap_version`；不要使用仅供历史兼容的 `--bridge-updater`。
- `bootstrap_version` 只在协议不兼容时提升；发布构建生成的协议文件，不手工修改 sidecar manifest。
- 稳定通道过滤 prerelease；canary 通道读取完整 releases 列表。

## 验证范围

- 根据改动运行最窄且足够的 `py_compile`、ruff、相关 unittest；涉及 i18n、构建或更新协议时运行对应脚本。
- 修改自动化调用前先查 API 签名和仓库同类用法，不显式重复默认参数。
- 不为了通过检查清理无关遗留警告。
