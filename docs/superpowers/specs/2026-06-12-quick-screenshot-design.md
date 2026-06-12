# 快捷截图小工具 — 设计文档

## 问题

现有截图小工具在 PC 模式下调用 `init_game()`，内部 `screen.set_win()` 会强制调整游戏窗口到配置分辨率（如 1080p），导致用户想快速截取当前窗口状态时，窗口被意外改变。

## 设计目标

- 不经 `init_game()`，不调整游戏窗口
- PC 模式：直接截取游戏窗口当前位置/分辨率
- 模拟器模式：复用已有连接，无连接时报错
- 游戏/模拟器未启动时直接报错，不自动启动
- 不污染运行中任务的截图缓存
- 最小代码改动，复用现有截图管线

## 架构

### QuickScreenshotGet（新 QThread 子类）

```
QuickScreenshotGet.run()
│
├─ cfg.simulator == True ──────────────────────────
│   ├─ Mumu: MumuControl.connection_device
│   │   ├─ 已存在 → ScreenShot.mumu_screenshot()
│   │   └─ None   → on_error("未连接到 Mumu 模拟器")
│   ├─ ADB: SimulatorControl.connection_device
│   │   ├─ 已存在 → ScreenShot.adb_screenshot()
│   │   └─ None   → on_error("未连接到 ADB 设备")
│   └─ OBS 启用时 → ScreenShot.take_screenshot() 自动走 OBS 路径
│
└─ cfg.simulator == False ─────────────────────────
    ├─ screen.handle.init_handle()         ← 轻量 FindWindow
    ├─ hwnd == 0 → on_error("未检测到游戏窗口")
    ├─ hwnd != 0, isMinimized → on_error("游戏窗口已最小化")
    └─ ScreenShot.take_screenshot(gray=False)  ← 直接调，不经过 auto 实例
```

与现有 `ScreenshotGet` 的差异：

| | `ScreenshotGet`（原） | `QuickScreenshotGet`（新） |
|--|--|--|
| 初始化 | `init_game()` → `set_win()` 调窗口 | `screen.handle.init_handle()` 轻量找窗 |
| 截图调用 | `auto.take_screenshot()`（有缓存副作用） | `ScreenShot.take_screenshot()`（无副作用） |
| 窗口操作 | `set_win()` / `reset_win()` / 自动启动游戏 | **不做任何窗口/进程操作** |
| 模拟器连接 | `init_game()` 建立连接 | 有则用，无则报错，不建立 |
| 未启动时 | 自动启动游戏/模拟器 | **报错** |

关键约束：
- 绝对不调用 `init_game()` → 不 `set_win()` / `reset_win()`
- 绝对不调 `game_process.start_game()` / `Screen.init_handle()` — 无自动启动
- PC 模式下只用 `screen.handle.init_handle()`（`Handle` 实例的轻量 `FindWindow`），不用 `screen.init_handle()`（`Screen` 实例的含自动启动版本）
- 截图用 `ScreenShot.take_screenshot()`，不走 `auto.take_screenshot()` 避免污染 `auto.screenshot` / `auto.screenshot_rgb`

### 信号

| 信号 | 类型 | 触发条件 |
|--|--|--|
| `on_saved_timestr` | `Signal(str)` | 截图成功，附带时间戳 |
| `on_error` | `Signal(str)` | 任何失败，附带错误信息 |

### 文件

- 存为 `quick_screenshot_{timestr}.png`，保存在工作目录
- `timestr` 使用 `%Y%m%d_%H%M%S_%f` 精度（含毫秒），避免同秒覆盖

## UI

### tools_interface.py

在现有「截图小工具」card 上方新增一张 card：

| 属性 | 值 |
|--|--|
| button 文字 | "运行" |
| 图标 | `FIF.CAMERA` |
| 标题 | "快速截图" |
| 描述 | "不调整窗口，直接截取游戏当前画面" |
| tool_name | `"quick_screenshot"` |

信号连接（复用现有 `_tool_start` 模式）：

```python
if tool_name == "quick_screenshot":
    tool.w.on_saved_timestr.connect(self._onScreenshotToolButtonPressed)
    tool.w.on_error.connect(lambda msg: BaseInfoBar.error(
        title="截图失败", content=msg, ...
    ))
```

### tools/__init__.py

扩展 `ToolManager` / `start()` 的 `Literal` 类型和 `run_tools()` 分支，新增 `"quick_screenshot"` 映射到 `QuickScreenshotGet`。

`ToolManager.run_tools()` 中现有 `elif self.tool == "screenshot":` 后追加：

```python
elif self.tool == "quick_screenshot":
    self.w = QuickScreenshotGet()
```

## 变更清单

| 文件 | 改动 |
|--|--|
| `tasks/tools/screenshot_module.py` | 新增 `QuickScreenshotGet` 类 |
| `tasks/tools/__init__.py` | 注册 quick_screenshot 工具类型 |
| `app/tools_interface.py` | 新增 card + 信号连接 |
| `tests/test_screenshot_tool.py` | 追加 `TestQuickScreenshotTool` |

## 错误处理

| 场景 | 行为 |
|--|--|
| PC 模式，找不到窗口 | `on_error("未检测到游戏窗口")` |
| PC 模式，窗口最小化 | `on_error("游戏窗口已最小化，无法截图")` |
| 模拟器，Mumu 未连接 | `on_error("未连接到 MuMu 模拟器")` |
| 模拟器，ADB 未连接 | `on_error("未连接到 ADB 设备")` |
| 截图 API 异常 | `on_error(str(e))` |
