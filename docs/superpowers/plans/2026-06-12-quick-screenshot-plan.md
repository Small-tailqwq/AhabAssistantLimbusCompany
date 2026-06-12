# 快捷截图小工具 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个不调整游戏窗口的快捷截图按钮

**Architecture:** 新建 `QuickScreenshotGet` QThread 子类，PC 模式下 `screen.handle.init_handle()` 轻量找窗，模拟器模式检查现有连接；截图直接调 `ScreenShot.take_screenshot()` 避免缓存污染

**Tech Stack:** Python, PySide6, win32gui

---

### Task 1: QuickScreenshotGet 类 + 单元测试

**Files:**
- Modify: `tasks/tools/screenshot_module.py` — 新增 QuickScreenshotGet 类
- Modify: `tests/test_screenshot_tool.py` — 追加测试类

- [ ] **Step 1: 在 test_screenshot_tool.py 追加测试类 TestQuickScreenshotTool**

```python
class _DummyImage:
    def __init__(self):
        self.saved_path = None

    def save(self, path: str):
        self.saved_path = path


class TestQuickScreenshotTool(unittest.TestCase):
    def test_pc_mode_success(self):
        """PC 模式：找到窗口→截图成功→保存并发射信号"""
        QApplication.instance() or QApplication([])
        image = _DummyImage()
        tool = QuickScreenshotGet()

        with (
            mock.patch.object(cfg, "simulator", False),
            mock.patch.object(screen.handle, "init_handle") as init_handle,
            mock.patch.object(screen.handle, "hwnd", 12345, create=True),
            mock.patch.object(screen.handle, "isMinimized", False, create=True),
            mock.patch("tasks.tools.screenshot_module.ScreenShot.take_screenshot", return_value=image) as take_screenshot,
            mock.patch("tasks.tools.screenshot_module.time.strftime", return_value="20260517_151500_123456"),
        ):
            with mock.patch.object(tool, "on_saved_timestr") as mock_signal:
                tool.run()

        init_handle.assert_called_once_with()
        take_screenshot.assert_called_once_with(gray=False)
        self.assertEqual(image.saved_path, "quick_screenshot_20260517_151500_123456.png")
        mock_signal.emit.assert_called_once_with("20260517_151500_123456")

    def test_pc_mode_no_window(self):
        """PC 模式：找不窗口→on_error"""
        QApplication.instance() or QApplication([])
        tool = QuickScreenshotGet()

        with (
            mock.patch.object(cfg, "simulator", False),
            mock.patch.object(screen.handle, "init_handle"),
            mock.patch.object(screen.handle, "hwnd", 0, create=True),
            mock.patch.object(tool, "on_error") as mock_error,
        ):
            tool.run()

        mock_error.emit.assert_called_once()

    def test_pc_mode_minimized(self):
        """PC 模式：窗口最小化→on_error"""
        QApplication.instance() or QApplication([])
        tool = QuickScreenshotGet()

        with (
            mock.patch.object(cfg, "simulator", False),
            mock.patch.object(screen.handle, "init_handle"),
            mock.patch.object(screen.handle, "hwnd", 12345, create=True),
            mock.patch.object(screen.handle, "isMinimized", True, create=True),
            mock.patch.object(tool, "on_error") as mock_error,
        ):
            tool.run()

        mock_error.emit.assert_called_once()

    def test_mumu_mode_success(self):
        """MuMu 模拟器：已有连接→截图成功"""
        QApplication.instance() or QApplication([])
        image = _DummyImage()
        tool = QuickScreenshotGet()

        with (
            mock.patch.object(cfg, "simulator", True),
            mock.patch.object(cfg, "simulator_type", 0),
            mock.patch("tasks.tools.screenshot_module.MumuControl") as MockMumu,
            mock.patch("tasks.tools.screenshot_module.ScreenShot.mumu_screenshot", return_value=image) as mumu_screenshot,
            mock.patch("tasks.tools.screenshot_module.time.strftime", return_value="20260517_151500_123456"),
        ):
            MockMumu.connection_device = mock.MagicMock()
            with mock.patch.object(tool, "on_saved_timestr") as mock_signal:
                tool.run()

        mumu_screenshot.assert_called_once_with(gray=False)
        self.assertEqual(image.saved_path, "quick_screenshot_20260517_151500_123456.png")
        mock_signal.emit.assert_called_once_with("20260517_151500_123456")

    def test_mumu_mode_not_connected(self):
        """MuMu 模拟器：无连接→on_error"""
        QApplication.instance() or QApplication([])
        tool = QuickScreenshotGet()

        with (
            mock.patch.object(cfg, "simulator", True),
            mock.patch.object(cfg, "simulator_type", 0),
            mock.patch("tasks.tools.screenshot_module.MumuControl") as MockMumu,
            mock.patch.object(tool, "on_error") as mock_error,
        ):
            MockMumu.connection_device = None
            tool.run()

        mock_error.emit.assert_called_once()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run python -m unittest tests.test_screenshot_tool.TestQuickScreenshotTool -v`
Expected: FAIL — `QuickScreenshotGet` not defined

- [ ] **Step 3: 在 screenshot_module.py 新增 QuickScreenshotGet 类**

追加到文件末尾 `screenshot_module.py`：

```python
class QuickScreenshotGet(QThread):
    on_saved_timestr = Signal(str)
    on_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.finished.connect(self.deleteLater)

    def run(self):
        try:
            if cfg.simulator:
                self._ensure_emulator_connected()
            else:
                screen.handle.init_handle()
                if screen.handle.hwnd == 0:
                    raise RuntimeError("未检测到游戏窗口")
                if screen.handle.isMinimized:
                    raise RuntimeError("游戏窗口已最小化，无法截图")

            img = ScreenShot.take_screenshot(gray=False)
            if img:
                timestr = time.strftime("%Y%m%d_%H%M%S_%f", time.localtime())
                img.save(f"quick_screenshot_{timestr}.png")
                log.info(f"快捷截图保存为 quick_screenshot_{timestr}.png")
                self.on_saved_timestr.emit(timestr)
            else:
                raise RuntimeError("截图返回为空")
        except Exception as e:
            log.error(f"快捷截图失败: {str(e)}")
            self.on_error.emit(str(e))

    def _ensure_emulator_connected(self):
        if cfg.simulator_type == 0:
            from module.automation.input_handlers.simulator.mumu_control import MumuControl
            if MumuControl.connection_device is None:
                raise ConnectionError("未连接到 MuMu 模拟器")
        elif cfg.simulator_type == 10:
            from module.automation.input_handlers.simulator.simulator_control import SimulatorControl
            if SimulatorControl.connection_device is None:
                raise ConnectionError("未连接到 ADB 设备")
        else:
            raise RuntimeError(f"未知的模拟器类型: {cfg.simulator_type}")
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run python -m unittest tests.test_screenshot_tool.TestQuickScreenshotTool -v`
Expected: 4 tests PASS

- [ ] **Step 5: 运行全部截图工具测试，确保原 ScreenshotGet 不受影响**

Run: `uv run python -m unittest tests.test_screenshot_tool -v`
Expected: 6 tests PASS (2 original + 4 new)

- [ ] **Step 6: 提交**

```bash
git add tests/test_screenshot_tool.py tasks/tools/screenshot_module.py
git commit -m "feat: 新增快捷截图 QuickScreenshotGet 类"
```

### Task 2: 注册 quick_screenshot 工具类型

**Files:**
- Modify: `tasks/tools/__init__.py`

- [ ] **Step 1: 注册工具类型**

在 `tasks/tools/__init__.py` 中：

```python
from tasks.tools.screenshot_module import ScreenshotGet, QuickScreenshotGet
```

更新 `ToolManager.__init__` 的 `Literal` 类型：

```python
tool: Literal["battle", "production", "screenshot", "quick_screenshot", "issue_replay", "asset_manager", "tutorial_skip"]
```

在 `run_tools()` 的 `elif self.tool == "screenshot":` 后追加：

```python
elif self.tool == "quick_screenshot":
    self.w = QuickScreenshotGet()
```

更新 `start()` 函数的 `Literal` 类型：

```python
tool: Literal["battle", "production", "screenshot", "quick_screenshot", "issue_replay", "asset_manager", "tutorial_skip"]
```

- [ ] **Step 2: 提交**

```bash
git add tasks/tools/__init__.py
git commit -m "feat: 注册 quick_screenshot 工具类型到 ToolManager"
```

### Task 3: 添加 UI 卡片

**Files:**
- Modify: `app/tools_interface.py`

- [ ] **Step 1: 在 tools_interface.py 添加卡片和信号连接**

在 `__init_card` 中，在 `get_screenshot_card` 定义之前新增：

```python
self.quick_screenshot_card = BasePushSettingCard(
    QT_TRANSLATE_NOOP("BasePushSettingCard", "运行"),
    FIF.CAMERA,
    QT_TRANSLATE_NOOP("BasePushSettingCard", "快速截图"),
    QT_TRANSLATE_NOOP(
        "BasePushSettingCard",
        "不调整窗口，直接截取游戏当前画面",
    ),
    parent=self.tools_group,
)
```

在 `__initLayout` 中，在 `self.tools_group.addSettingCard(self.get_screenshot_card)` 之前插入：

```python
self.tools_group.addSettingCard(self.quick_screenshot_card)
```

在 `__connect_signal` 中，在现有截图卡片信号之前添加：

```python
self.quick_screenshot_card.clicked.connect(lambda: self._tool_start("quick_screenshot", self.quick_screenshot_card))
```

在 `_tool_start` 中，在 `if tool_name == "screenshot":` 块后追加：

```python
if tool_name == "quick_screenshot":
    tool.w.on_saved_timestr.connect(self._onScreenshotToolButtonPressed)
    tool.w.on_error.connect(self._onQuickScreenshotError)
```

在 `retranslateUi` 中追加：

```python
self.quick_screenshot_card.retranslateUi()
```

在 `ToolsInterface` 中新增错误处理回调：

```python
def _onQuickScreenshotError(self, msg: str):
    title = QT_TRANSLATE_NOOP("BaseInfoBar", "截图失败")
    BaseInfoBar.error(
        title=title,
        content=msg,
        orient=Qt.Horizontal,
        isClosable=True,
        position=InfoBarPosition.BOTTOM_RIGHT,
        duration=-1,
        parent=self,
    )
```

- [ ] **Step 2: 提交**

```bash
git add app/tools_interface.py
git commit -m "feat: 添加快捷截图 UI 卡片和信号连接"
```

### Task 4: 完整验证

- [ ] **Step 1: 运行全量测试**

Run: `uv run python -m unittest tests.test_screenshot_tool -v`
Expected: 6 tests PASS

- [ ] **Step 2: 运行 lint 检查**

Run: `uv run ruff check tasks/tools/screenshot_module.py tasks/tools/__init__.py app/tools_interface.py tests/test_screenshot_tool.py`
Expected: no errors (may have pre-existing warnings in unrelated lines)

- [ ] **Step 3: 最终提交**

```bash
git add -A
git commit -m "feat: 完整实现快捷截图小工具"
```
