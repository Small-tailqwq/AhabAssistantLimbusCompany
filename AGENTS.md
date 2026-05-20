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

- Windows 桌面自动化（主）+ macOS 兼容，Python 3.12+，`uv` 管理
- 无自动化测试套件；`test/` 下是手动脚本，依赖真实游戏/OBS/模拟器
- `ruff` 已配置；遗留模块已有预存警告（通配符导入、裸 `except`），功能开发中不做无关清理

## macOS 构建与开发注意事项

### macOS 构建只在 CI 上验证，本地不可行

- 本项目 macOS 构建依赖 GitHub Actions `macos-latest` runner，本地 Mac 无法复现 CI 构建（PyInstaller 版本、macOS SDK 版本、Python 构建环境均不同）
- **本地测试通过不代表 CI 能通过**，反之亦然。每次修改必须等待 CI 构建产物验证

### PyInstaller BUNDLE 的 .app 内部布局（血的教训）

macOS 上 PyInstaller 用 `BUNDLE` 而非 `COLLECT` 模式，目录结构完全不同：

```
AALC.app/Contents/
├── MacOS/              ← 可执行文件 + config.yaml
├── Resources/          ← a.datas 的实际位置（rapidocr 的 yaml/onnx 等）
├── Frameworks/         ← base_library.zip + sys._MEIPASS 指向这里（__file__ 指向这里）
├── Info.plist
└── _CodeSignature/
```

**核心矛盾**：`rapidocr` 和 `certifi` 通过 `Path(__file__).resolve().parent.parent / "data.yaml"` 定位数据文件。但 frozen 模式下 `__file__` 合成路径指向 `Contents/Frameworks/<pkg>/`，而数据文件实际在 `Contents/Resources/<pkg>/`。`Frameworks/` 下只有 PyInstaller 创建的空目录壳。

### 运行时修复方案（已验证通过）

不依赖构建时 sync（已经被证明不可靠），而是改在 `main.py` 中、import rapidocr 前把数据从 Resources 复制到 Frameworks：

```python
if getattr(sys, "frozen", False) and _is_mac:
    _resources_dir = os.path.join(os.path.dirname(os.path.dirname(sys.executable)), "Resources")
    _frameworks_dir = os.path.join(os.path.dirname(os.path.dirname(sys.executable)), "Frameworks")
    for _pkg in ("rapidocr", "certifi"):
        _src = os.path.join(_resources_dir, _pkg)
        _dst = os.path.join(_frameworks_dir, _pkg)
        if os.path.isdir(_src) and os.path.isdir(_frameworks_dir):
            ...
```

### 构建时 sync 不可行（已趟的坑）

在 `build.py` 中做 post-build `shutil.copytree()` 有 3 个致命问题：

1. **路径算错**：`dist_app_root.parent.parent / "Frameworks"` = `AALC.app/Frameworks`（漏了 `Contents/`）。正确：`dist_app_root.parent / "Frameworks"`。
2. **BUNDLE hardlink 冲突**：PyInstaller BUNDLE 在某些 PyInstaller/macOS 版本上会将 `Resources/<pkg>/file.yaml` 和 `Frameworks/<pkg>/file.yaml` 创建为相同 inode 的硬链接。`shutil.copytree()` 检测到源和目标同一文件报错 `are the same file`。
3. **zip 打包丢失 hardlink**：硬链接在 zip 压缩后丢失，导致从 CI 下载的 zip 中 `Frameworks/` 下又变回空目录。但 `any(iterdir())` 在 CI 上检测到硬链接文件跳过了 sync，最终产物没有数据。

### CI 构建验证流程

```bash
# 1. 对比 SHA256 确认下载的是最新构建
shasum -a 256 AALC_dev-macos_macos.zip
# 2. 检查 zip 中 Frameworks 目录是否包含数据文件
unzip -l AALC_dev-macos_macos.zip | grep "Frameworks/rapidocr/"
# 3. 解压后检查目录结构
ls AALC.app/Contents/Frameworks/rapidocr/
# 4. 直接命令行启动 app 观察日志（不要双击）
./AALC.app/Contents/MacOS/AALC
```

### 模块级代码不能有运行时错误

`main.py` 中的 macOS 路径修复是**顶层代码**（不在函数内），在 import 链到达 rapidocr 之前执行。任何 `NameError`、`ImportError`、语法错误都会在模块加载时就崩溃，不经过任何 try/except。

之前因 `os.path.isdir(_frameworks)` 少写 `_dir` 后缀导致 `NameError`，CI 构建在本地纯 Python 模拟中无法发现，因为独立脚本没有这个变量名拼写问题。**必须实际运行 frozen app 才能发现这类错误**。

### macOS 特有模块导入问题

- `pyautogui` 在 macOS CI 上会触发 `SyntaxWarning`（非致命）
- `win32` 模块在 macOS 上不存在，frozen 环境中 `ctypes.windll` 会崩溃——`main.py` 中通过 `if not _is_mac:` 保护
- `darkdetect` 依赖 `AppKit.framework` 的 ctypes 导入，PyInstaller 只能按 basename 匹配
- `msvcrt` 在 macOS 上不存在，`ctypes` 导入时 warning（非致命）

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

## 文件删除严格管控（最高优先级）

**绝不替用户删除任何本地文件。** 这是不可逾越的红线。

### 禁止的操作

- `git clean -fd` / `git clean`
- `git rm`
- `rm` / `rmdir` / `rd` / `erase` / `del`
- `Remove-Item` / `ri`
- 任何通过 `cmd /c`、`pwsh -c`、`python -c` 包装的删除
- 写入文件时覆盖用户已存在的本地文件（如 write 工具覆盖）
- 代码中调用 `os.remove()`、`shutil.rmtree()` 等

以上操作已被全局 `opencode.json` 的 permission 规则通过 `deny` 阻断。

### git stash pop 冲突处理（最高风险场景）

`git stash pop` 产生冲突时，LLM 最容易误删用户文件。**必须遵循**：

1. **stash pop 冲突中的文件不是"需要清理的产物"，是用户的工作成果**。即使冲突标记为 "deleted by us"，也不代表应该删除（可能只是上游删了但你的本地修改要保留）。
2. **不允许自行 `git rm`、`git checkout --theirs/ours` 或任何方式解决冲突**。必须用 `question` 工具向用户展示冲突详情，让用户决定保留哪个版本。
3. 在用户回复前，正确的无害做法是 `git stash pop` 已失败但保留 stash，工作区状态已展示给用户，等待指示。

### 例外流程

当确实需要清理文件时（如清理已知的无用构建产物），必须：
1. 使用 **`question` 工具**向用户说明：需要删除什么、为什么、具体路径
2. 等待用户明确同意后再执行
3. 执行后报告结果

**这样用户同意后可以不中断会话直接回复，避免 permission ask 导致的会话中断。**

### 原则

- **stash pop 冲突 = 用户工作成果，决不容 LLM 自行裁决**
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
