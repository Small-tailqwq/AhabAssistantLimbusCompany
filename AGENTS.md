# AhabAssistantLimbusCompany — Agent 指引

`origin` → Small-tailqwq/AhabAssistantLimbusCompany；`upstream` → KIYI671/AhabAssistantLimbusCompany。

## 执行与指令优先级

- 在系统、开发者与工具权限边界内，用户明确指令优先于 Skill 的一般建议。Skill 不撤销已有授权，也不扩大任务范围。
- 已获授权的、可逆的仓库内工作直接做到约定结果；不要停在确认能力、复述任务或只给计划，也不要为同一步重复确认。
- 只有无法从当前证据解决、且会实质改变结果、范围、访问或风险的歧义才询问；采用最窄合理解释并说明重要假设。先完成不受该问题影响的已授权工作。
- Skill 若导致询问、暂停、未完成或偏离任务，链接具体 SKILL.md（规则在 reference 中时一并链接），引用具体规则并解释适用性，区分原文要求与自己的推断。
- 下列命令、Skill 流程与报告模板按任务选择，不是每次全部执行的清单。报告保留结果、依据和重要缺口；简单任务不强制完整模板。
- 本地开发默认由主智能体完成；只有用户要求或当前任务适用的专门流程明确需要时才委派，不能因读到 CI 代理配置就启动独立审阅。
- 本文件是项目公共规则的唯一来源；目录级 AGENTS 只补充本目录规则。CLAUDE.md 只转发到本文件，不维护副本。

## 渐进式披露

本文件只保存高频项目不变量。不要预加载所有专项文档；任务命中时再加载：

- 修改或审阅自动化、图片匹配、任务生命周期、UI/config/debug 逻辑：加载 `aalc-automation-practices`。
- 创建、审计或优化 AGENTS/rules/skills：加载全局 `agent-guidance-health`；不可用时按本节原则执行。
- Issue/日志诊断：加载 `analyze`；不可用时读取 `.agents/skills/analyze/SKILL.md`。
- 用户截图的模板匹配重放：加载 `replay-matching`；不可用时读取 `.agents/skills/replay-matching/SKILL.md`。
- Canary 发版：加载 `canary-release`；不可用时读取 `.agents/skills/canary-release/SKILL.md`。
- 向上游贡献及 PR 后续闭环：加载 `upstream-contribution`；不可用时读取 `.agents/skills/upstream-contribution/SKILL.md`。
- 上游优秀提交或最终 PR 结果回流（fork ← upstream）：加载 `downstream-sync`；不可用时读取 `.agents/skills/downstream-sync/SKILL.md`。
- 代码审阅及复审：加载 `code-review`；不可用时读取 `.agents/skills/code-review/SKILL.md`。
- 长期决策记录或 `.agents/notes/` 维护：加载 [agent-notes](.agents/skills/agent-notes/SKILL.md)，普通局部修复无需自动写笔记。
- 新增/修改 `debug_*` 配置或受其控制的行为：再读取 `.opencode/tools/debug_model_constitution.md`。

Skills 内容使用中文编写；代码符号、命令、文件路径与协议术语（如 finding ID、Block/Warning、exact/adapt/rewrite）保留英文，以便与仓库工具链对齐。

Skill 正文只读任务所需 reference，不要因“可能有用”提前展开。

SKILL.md 正文保持热路径，减少加载后的上下文负担；失败处理、回滚、复审协议、报告模板等低频内容放 `references/`。`check_agent_guidance.py` 强制 SKILL.md 180 行、本文件 150 行的预算。

## 多 harness 共用 skills

`.agents/skills/` 是唯一真实来源。Codex、pi、OpenCode 等 harness 直接读取该目录；不为任何 harness 建立转发副本、桥接 skill 或同名入口。Claude Code 只读 `.claude/skills/`，克隆仓库后运行一次 `uv run python .\scripts\link_skills.py` 建立指向 `.agents/skills/` 的链接（Windows 无开发者模式时用目录联接，POSIX 用相对符号链接）。

`.claude/` 已被忽略，链接是本地产物，不提交也不手工编辑；新增或重命名 skill 后重跑该脚本。`check_agent_guidance.py` 在链接目录存在时校验漂移。

历史设计、.superpowers/sdd 任务记录与其他 harness 的旧说明仅作证据，不代表当前任务授权；专项文档与当前源码不符时先核对。OpenCode CI 代理的只读权限、固定输出和调度只适用于对应 CI 入口。

## Agent Notes

代码、测试和现有文档未解释的长期决策理由写入 `.agents/notes/`，遵循[笔记契约](.agents/notes/README.md)。新笔记检查取代关系，同一决策只保留一个活跃归属；部分取代保留各自仍有效的内容。

Agent Notes 单独允许记录真实考虑过的替代方案及理由；不编造取舍。其他仓库文字继续描述当前状态。`archived/` 是冻结历史，不作为当前行为依据。

新增决策记录使用 notes；剩余 `docs/superpowers/specs/` 仅在相关主题维护时按当前实现迁移。修改 notes 后运行 `uv run python scripts/agent_notes.py check`；模板问题按契约记录最小复现，在当前授权范围内反馈。

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
uv run python .\scripts\check_agent_guidance.py
uv run python .\scripts\agent_notes.py check
uv run python .\scripts\link_skills.py
```

调试工具位于 `.opencode/tools/`：`log_analyzer.py`、`mirror_analyzer.py`、`log_viewer.py`、`match_viewer.py`。模板匹配重放工具：`debug_tools/verify_matching.py`。可复用临时验证脚本放 `debug_tools/`，不纳入 CI。调试截图和中间图统一写入 `logs/<feature>_debug/` 等已忽略目录，不落到仓库根目录或未忽略的 `debug_*` 目录。

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
| Agent 指引 | `.agents/skills/`（共享 skill 唯一来源）、`.claude/skills/`（生成的链接）、`.opencode/agents/`（OpenCode 专用代理） |

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
- `my_script_task.run()` 收尾时清除停止状态、断开 OBS、发出 `mediator.script_finished`；子任务传播停止，不重复全局收尾。
- `FarmingInterfaceLeft.handle_script_finished()` 恢复 UI 并清理模拟器连接。
- 不使用 `QThread.terminate()` 进行正常停止。
- 修改游戏启动、窗口句柄或模拟器等待逻辑时，加入停止检查和有界重试。
- `app/my_app.py::closeEvent()` 最多等待 5 秒优雅退出，停止路径不得无限等待。

## 用户资产安全

- 未追踪文件、`issues/`、日志、截图、配置快照和 stash/merge 冲突默认是用户资产。
- 删除、移动、整体覆盖或清理这些内容前，核对已有授权是否覆盖具体路径和操作；未覆盖时再按全局规则确认。
- 不自行裁决 stash pop/merge 冲突。
- Issue 流程按请求推进：读取与分析；已授权修复时继续实现；有临时产物时列出清理候选，保留 issue 记录。

## 发布不变量

- 用户可见更新说明来自 GitHub Release body；发版同时维护 `CHANGELOG.md`。
- 可消费 Release 必须恰好包含一个 `AALC_<version>.7z` 和一个 `AALC.update_manifest.json`。
- 正式 Release 同时上传 `AALC_<version>.7z.sha256`。
- 常规 canary 使用平铺包和当前 `bootstrap_version`；不要使用仅供历史兼容的 `--bridge-updater`。
- `bootstrap_version` 只在协议不兼容时提升；发布构建生成的协议文件，不手工修改 sidecar manifest。
- 稳定通道过滤 prerelease；canary 通道读取完整 releases 列表。

## 验证范围

- 按风险选择最窄且足够的冷检查：改动 Python 文件的语法、针对性 ruff 或相关确定性 unittest；涉及 i18n、构建或更新协议时仅运行受影响的检查。
- 必要检查通过后，只有新改动、失败或具体未解决风险才重跑或扩大验证。纯指令/文档编辑只检查内容、引用与 diff，不运行项目测试；改动本文件、CLAUDE.md、共享 skills、`.opencode/` 指引或 OpenCode CI 协议时，运行 `uv run python .\scripts\check_agent_guidance.py`。
- 不因 Skill 建议自动新增测试；仅在用户要求或已接受的交付内容包含测试时添加。GUI、设备、真实环境、E2E 与独立审阅遵循用户授权和全局验证边界。
- 修改自动化调用前先查 API 签名和仓库同类用法，不显式重复默认参数。
- 不为了通过检查清理无关遗留警告。
