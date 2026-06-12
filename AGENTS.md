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
uv run python -m unittest discover -s tests -p "test_*.py" -v  # 运行 tests/ 自动化回归
uv run python .\scripts\build.py --version dev           # 构建
uv run python .\scripts\translation_files_build.py       # 刷新 ts 源
uv run python .\scripts\translation_files_compile.py     # 编译 ts → qm
uv run python .\scripts\check_i18n.py --update           # i18n 完整性检查（与 CI 一致）
uv run python .\scripts\export-requirements-from-uv-lock.py  # 从 uv.lock 刷新 requirements.txt

## 调试工具
uv run python .opencode/tools/log_analyzer.py <log>      # 日志压缩报告
uv run python .opencode/tools/mirror_analyzer.py <logs>  # 镜牢耗时分析（支持多文件）
uv run python .opencode/tools/log_viewer.py              # 日志可视化 Web 面板（自动打开 http://localhost:9812）
uv run python .opencode/tools/log_viewer.py -l issues/25/original.log  # 直接加载特定日志
uv run python .opencode/tools/match_viewer.py              # 图片匹配诊断工具（自动打开 http://localhost:9813）

## 调试脚本存档
`debug_tools/` 收录可复用的调试/验证脚本（镜像匹配、区域提取、多分辨率评估等），非 CI 集成。
```

> **Windows CI 编码陷阱**：`scripts/build.py` 中的 `print()` 如果包含非 ASCII 字符（中文、`→`、`✓` 等），在 GitHub Actions Windows runner（cp1252 终端）会触发 `UnicodeEncodeError` 导致构建失败。所有输出文本必须使用纯 ASCII（英文 + 基本符号）。`v1.5.0-canary.5` 因 `→` 字符构建失败，浪费一个版本号。

## 项目现实

- Windows-only 桌面自动化，Python 3.12+，`uv` 管理
- `tests/` 下有 `unittest` 自动化用例；统一入口见上方 `unittest discover` 命令
- `test/` 下仍是手动脚本，依赖真实游戏/OBS/模拟器
- `ruff` 已配置；遗留模块已有预存警告（通配符导入、裸 `except`），功能开发中不做无关清理

## 更新发布约束

- 自动更新的用户可见“更新信息”来自 GitHub Release body；不再维护额外的本地更新说明文件。发版时需要同步维护 `CHANGELOG.md` 和 Release body。
- 每个可被自动更新消费的 Release 必须包含且只包含一份匹配的主包：`AALC_<version>.7z`。若出现 0 份或多份匹配 `.7z` 资产，当前更新逻辑会跳过该 Release。
- 每个 Release 必须同时上传构建产物 `AALC.update_manifest.json`。这是 sidecar 更新协议文件，GUI 侧会先读取它来判断 `bootstrap_version` 和兼容性；缺失、损坏或重复时，该 Release 会被跳过。
- 每个 Release 应同时上传 `AALC_<version>.7z.sha256`。客户端会在下载完成后校验 SHA256；缺失时会降级为“跳过校验”而不是失败，因此正式发版不要漏传。
- 常规 `canary.10+` 发版使用默认平铺包：`uv run python .\scripts\build.py --version <version> --bootstrap-version 2`。不要在正常发版时使用 `--bridge-updater`；该参数只用于生成 legacy `root_dir` 包做历史兼容/排障。
- `bootstrap_version` 只在 updater 协议发生不兼容变化时提升。只要提升它，旧客户端就会跳过该 Release，因此发版前必须同时准备兼容迁移方案。
- `scripts/build.py` 生成的 `update_manifest.json`、`managed_files.txt`、`bootstrap_version.txt` 是一组协议文件；发布时应直接上传构建产物，不要手工修改 sidecar manifest 内容。
- 当前稳定通道会过滤 GitHub `prerelease=true` 的 Release；canary 通道读取完整 releases 列表。金丝雀发布仍建议保持 Release 元数据完整可读，不要依赖额外渠道补发更新说明。

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
| 调试脚本 | `debug_tools/` | 非 CI 集成的调试/验证脚本 |

## 文件删除与覆盖管控

删除与覆盖规则由全局 `AGENTS.md` 第 5 节统一约束。本项目额外强调：

- 曾发生 LLM 误删未追踪文件的事故，删除类操作必须视为高风险操作
- 未追踪文件、issue、日志、截图、配置快照默认视为用户资产
- 删除/整体覆盖前必须用 `question` 工具获得确认
- stash pop 冲突文件是用户工作成果，禁止自行裁决

## 🔒 凭证安全

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
- **工具窗口主题**：`tasks/tools/` 下每个独立 QWidget 窗口必须在 `__init__` 中连接 `qconfig.themeChanged.connect(self._apply_theme_style)`，确保主题切换时实时刷新。`_apply_theme_style` 需调用 `apply_tool_window_theme()` 和 `setStyleSheet(get_status_label_style())`。
- **调试开关描述统一**：`app/setting_interface.py` 中每个子调试开关的描述遵循以下格式——
  - 同时记录日志和保存截图：`记录[内容]，并保存[文件类型]到 logs/xxx 目录`
  - 仅保存截图：`在[场景]时保存[文件类型]到 logs/xxx 目录`
  - 仅输出日志：`在[场景]时输出[内容]`
  `module/config/config_typing.py` 的注释和 `config.yaml` 的注释应同步保持一致。
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

## AI 生成代码质量约束

本项目的代码被大量 AI 工具参与生成，历史 Review 发现了若干反复出现的模式性问题。以下约束用于减少此类问题，不限定于特定 API 或文件名。

### 参数默认值

AI 常倾向于"显式写出所有参数"，但本项目多数函数有精心调优的默认值。显式写出默认值的行为要不得，因为它：
- 制造噪音，掩盖真正有意义的参数
- 让人无法区分"这个是特意选的"和"这个是 AI 顺手写出来的"
- 在框架默认值变更时产生误导

**规则**：在 `auto.*`、`ImageUtils.*`、`auto.find_element`、`auto.click_element`、`ocr.*` 等模块的调用中，除非你**确认**该参数的意义并且其值**非默认**，否则不要显式写出。不确定默认值是什么时，先查源码。

反面示例：
```python
# threshold=0.8 是 auto.click_element 的默认值，写出来是噪音
auto.click_element("some/asset.png", threshold=0.8)
```

正确做法：不确定就查 `module/automation/automation.py` 中 `click_element` 和 `find_element` 的签名。

### 理解机制而非堆参数

当某个 API 调用"默认不工作"时，AI 倾向于堆砌参数（换 model、加 threshold、改 find_type）直到"试出来"——这是危险的。每个参数组合有语义含义，随机试出来的组合可能在特定条件下失效。

**规则**：对于图片搜索、模板匹配、UI 定位等核心操作，写代码前先理解两步：
1. **搜索区域**：搜索被限制在哪块屏幕区域？（全屏？上次位置 ±30px？±100px？）
2. **模板裁剪**：带 `_assets.png` 后缀和不带有什么区别？（不带 = 无 bbox 限制 = 全屏搜索）

这两条知识能解释 80% 的图片搜索失败场景，并且通常比加 `model="aggressive"` 有更轻量的修复方案。

例如：需要全屏搜索一个特定按钮图片时，优先考虑**让 `bbox=None`**（移除 `_assets.png` 后缀/改文件名），而非加 `model="aggressive"` 去绕过 bbox 限制。

### 最小抽象原则

AI 有强烈的"提取函数、加抽象层、写防御性代码"倾向。但自动化代码的特点是：**90% 的函数只被一个调用者使用，且在可见未来不会变。**

适用以下判断：

- **这个函数有超过一个调用者吗？** 如果现在没有，不要提取，不要"方便以后"。以后真有时再提取也来得及。
- **这个参数会以不同值传入吗？** 如果所有调用者都传同一个值，把这个值硬编码进去，删掉参数。
- **这个分支真的会发生吗？** 防御性代码（"如果 X 失败则清理 Y"）必须建立在**Y 确实需要被清理**的前提下。如果 Y 的状态不影响后续操作（因为 UI 已切换、或 Y 不遮挡任何内容），那这个分支可以删掉。
- **这段逻辑的复杂度与它所解决问题的复杂度匹配吗？** 一个"点击按钮 N 次"的操作不需要 4 层函数调用栈。每次新增抽象层之前反问自己：我是否在用代码量解决一个"只需两行注释就能说清"的问题？

### 自动化代码的特殊性

与其他软件工程领域不同，桌面自动化代码有以下特殊约束，AI 通常不了解：

1. **"刚好能用"比"优雅"重要**：UI 截图匹配天然有噪声，定位偏移、渲染差异、主题切换都可能导致失败。经实机验证的硬编码通常比可配置的抽象更可靠。
2. **防御性代码通常是负收益**：桌面自动化的每一步操作都在改变 UI 状态。"做完 A 后顺手做 B 来清理"→如果 A 成功时 B 不影响后续，那 A 失败时 UI 状态已经不对了，B 也于事无补。防御性代码需要**每条失败路径都有针对性的恢复策略**才有意义，否则只是"撞大运"。
3. **UI 层级变换就是最好的清理**：点击一个按钮进入新页面 → 旧页面的弹窗/面板自动消失。不需要手动去关它。理解屏幕层级变化比写清理函数更重要。
4. **相同的"模式"不一定需要提取**：三个函数有类似的三次重试循环并不表示应该抽一个 `retry_click` 函数——如果提取会导致参数膨胀（传入成功条件、截图策略、重试间隔等），那内联重复是更好的选择。

### AI 辅助开发的流程建议

1. **写之前先看**：修改现有函数前，先用 `auto.find_element("目标图")` 之类的模式搜一下同类代码，理解惯用写法。
2. **不堆参数**：解决问题时先确认"是哪个参数真正导致了差异"，而不是把所有可能参数都塞进去。
3. **对冗余敏感**：如果一段代码让你觉得"不太可能真的需要"，那它很可能确实不需要。验证的方法是：删掉它，然后问自己——没有它会怎样？如果答案是"也能工作"或"只是少个日志"，那就删掉。
4. **review 时关注 diff 方向**：Review 不是只看功能是否正确，还要看**改动量是不是和问题难度匹配**。一个 200 行 diff 解决的问题通常有一个 20 行的等价方案。

## 本地 Issue 追踪

`issues/` 目录存放 bug 记录，不纳入版本控制。模板：`issues/TEMPLATE.md`。

典型文件：
- `<id>.md` — 描述、复现步骤、日志片段
- `<id>.log` — 完整日志
- `config_<id>.yaml` — 当时配置
- `screenshot_<id>.png` — 可选截图

流程：读取 issue → 分析根因 → 修复 → 列出可清理的临时文件，保留 issue 记录；删除前必须获得用户确认。

## 参考

- `README.md`
- `assets/doc/zh/develop_guide.md`
- `assets/doc/zh/build_guide.md`
- `assets/doc/zh/translateGuide.md`
- `assets/doc/zh/image_recognition.md`
- `assets/doc/zh/FAQ.md`
- `assets/doc/zh/How_to_use.md`
- `assets/doc/zh/Custom_setting.md`

