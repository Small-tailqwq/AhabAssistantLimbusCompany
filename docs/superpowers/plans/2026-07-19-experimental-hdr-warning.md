# Experimental HDR Warning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 PC 模式每次任务启动时检测游戏窗口所在显示器的 HDR 状态；HDR 开启时暂停自动化并显示可由实验性设置关闭的警告。

**Architecture:** 将 `debug_tools/check_hdr.py` 中已验证的 COM/DXGI 实现原样抽取到 `module/game_and_screen/hdr.py`，CLI 与任务代码共用同一检测接口。任务线程在 `init_game()` 后通过专用 mediator 信号请求 GUI 显示模态警告，并用可停止的 `threading.Event` 门等待用户确认。

**Tech Stack:** Python 3.12+、ctypes/DXGI 1.6、pywin32、PySide6、unittest、现有 AALC mediator/config/i18n

## Global Constraints

- Windows-only，Python 3.12+
- `DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020` 的官方枚举值为 `12`
- HDR 只由当前输出 `ColorSpace == 12` 判定；亮度和 `BitsPerColor` 不参与判定
- 只检测游戏窗口所在 `HMONITOR`，不使用主显示器或其他显示器替代
- 模拟器模式完全跳过检测
- `experimental_hdr_warning` 默认 `True`，但不得直接修改用户 `config.yaml`
- 每次顶层任务启动最多提示一次，重试流程不重复提示
- 警告确认前自动化不得继续；等待必须响应 `auto.ensure_not_stopped()`
- 查询失败不得阻断任务，也不得误报 HDR 开启
- 配置字段同步到 `module/config/config_typing.py` 与 `assets/config/config.example.yaml`
- 用户可见文案纳入 `i18n/myapp_en.ts`
- 不重新实例化 `cfg`、`auto`、`screen`、`game_process` 或 `mediator`
- 不使用 `QThread.terminate()`
- 不使用 `os._exit()`；CLI 使用正常 `sys.exit(main())`
- 提交信息使用中文

---

### Task 1: 抽取可复用 HDR 检测模块

**Files:**
- Create: `module/game_and_screen/hdr.py`
- Modify: `debug_tools/check_hdr.py`
- Modify: `tests/test_check_hdr.py`

**Interfaces:**
- Produces: `HdrDisplayInfo`、`color_space_name(value: int) -> str`、`enumerate_hdr_displays() -> list[HdrDisplayInfo]`、`get_monitor_hdr_info(hmonitor: int) -> HdrDisplayInfo | None`
- Preserves: CLI `uv run python debug_tools/check_hdr.py`

- [ ] **Step 1: Write failing tests for the reusable module**

Update `tests/test_check_hdr.py` to import the production module and add target-monitor selection coverage:

```python
from unittest import mock

from module.game_and_screen import hdr


class TestHdrDetectionModule(unittest.TestCase):
    def test_pq_bt2020_color_space_is_hdr(self):
        info = hdr.HdrDisplayInfo(
            monitor_handle=1,
            device_name=r"\\.\DISPLAY1",
            color_space=12,
        )

        self.assertTrue(info.hdr_enabled)
        self.assertEqual(
            hdr.color_space_name(info.color_space),
            "RGB_FULL_G2084_NONE_P2020",
        )

    def test_get_monitor_hdr_info_returns_only_matching_monitor(self):
        first = hdr.HdrDisplayInfo(monitor_handle=1, device_name=r"\\.\DISPLAY1")
        second = hdr.HdrDisplayInfo(monitor_handle=2, device_name=r"\\.\DISPLAY2")

        with mock.patch.object(
            hdr,
            "enumerate_hdr_displays",
            return_value=[first, second],
        ):
            result = hdr.get_monitor_hdr_info(2)

        self.assertIs(result, second)

    def test_get_monitor_hdr_info_returns_none_when_output_is_missing(self):
        with mock.patch.object(hdr, "enumerate_hdr_displays", return_value=[]):
            result = hdr.get_monitor_hdr_info(999)

        self.assertIsNone(result)

    def test_com_initialization_failure_returns_empty_without_uninitialize(self):
        with (
            mock.patch.object(
                hdr._ole32,
                "CoInitializeEx",
                return_value=-2147417850,
            ),
            mock.patch.object(hdr._ole32, "CoUninitialize") as uninitialize,
        ):
            result = hdr.enumerate_hdr_displays()

        self.assertEqual(result, [])
        uninitialize.assert_not_called()
```

Keep formatter tests against the CLI formatter, but construct `hdr.HdrDisplayInfo` rather than a CLI-owned dataclass.

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
uv run python -m unittest tests.test_check_hdr -v
```

Expected: import fails because `module.game_and_screen.hdr` and `HdrDisplayInfo` do not exist.

- [ ] **Step 3: Move the verified DXGI implementation into the production module**

Create `module/game_and_screen/hdr.py` by moving, without changing values or vtable indices, these definitions from `debug_tools/check_hdr.py`:

- `HDR_COLOR_SPACE = 12`
- `_COLOR_SPACE_NAMES`
- `GUID`, `RECT`, `DXGI_OUTPUT_DESC1`
- `IID_IDXGIFactory1`, `IID_IDXGIOutput6`
- `_QueryInterface`, `_Release`, `_EnumAdapters1`, `_EnumOutputs`, `_GetDesc1`
- `_vtable_func`, `com_release`, `_com_query_interface`, `_create_dxgi_factory`
- existing adapter/output enumeration and Win32 friendly-name enrichment

Define the public data object and APIs:

```python
from dataclasses import dataclass


@dataclass
class HdrDisplayInfo:
    monitor_handle: int
    device_name: str
    friendly_name: str = ""
    is_primary: bool = False
    desktop_rect: tuple[int, int, int, int] = (0, 0, 0, 0)
    attached_to_desktop: bool = False
    bits_per_color: int = 0
    color_space: int = 0
    max_luminance: float = 0.0
    min_luminance: float = 0.0
    max_full_frame_luminance: float = 0.0

    @property
    def hdr_enabled(self) -> bool:
        return self.color_space == HDR_COLOR_SPACE

    @property
    def color_space_name(self) -> str:
        return color_space_name(self.color_space)


def enumerate_hdr_displays() -> list[HdrDisplayInfo]:
    """用新建的 DXGI factory 返回当前所有输出；失败时记录日志并返回空列表。"""
    hr = _ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    if hr not in (S_OK, S_FALSE):
        log.warning(f"COM 初始化失败，跳过 HDR 检测: 0x{hr & 0xFFFFFFFF:08X}")
        return []

    try:
        factory_ptr = _create_dxgi_factory()
        if factory_ptr is None:
            log.warning("CreateDXGIFactory1 失败，跳过 HDR 检测")
            return []
        try:
            descs = _enumerate_output_descs(factory_ptr)
        finally:
            com_release(factory_ptr)
    except Exception as exc:
        log.warning(f"查询显示器 HDR 状态失败: {exc}")
        return []
    finally:
        _ole32.CoUninitialize()

    return [_build_display_info(desc) for desc in descs]


def get_monitor_hdr_info(hmonitor: int) -> HdrDisplayInfo | None:
    """返回指定 HMONITOR 的当前 HDR 信息。"""
    return next(
        (info for info in enumerate_hdr_displays() if info.monitor_handle == int(hmonitor)),
        None,
    )
```

`_enumerate_output_descs()` 必须保留现有 factory → adapter → output → output6 的嵌套 `try/finally` Release 顺序。`_build_display_info()` 使用当前已经实机验证的：

```python
display_device = win32api.EnumDisplayDevices(desc.DeviceName, 0, 0)
friendly_name = display_device.DeviceString
```

- [ ] **Step 4: Convert the CLI into a thin presentation layer**

`debug_tools/check_hdr.py` 只保留报告格式化和入口：

```python
# ruff: noqa: T201

import sys

from module.game_and_screen.hdr import HdrDisplayInfo, enumerate_hdr_displays


def format_monitor_info(info: HdrDisplayInfo, index: int) -> str:
    lines = [f"显示器 {index}:"]
    lines.append(f"  设备名: {info.device_name}")
    lines.append(f"  友好名: {info.friendly_name or '(未知)'}")
    lines.append(f"  主显示器: {'是' if info.is_primary else '否'}")
    left, top, right, bottom = info.desktop_rect
    lines.append(f"  桌面区域: ({left}, {top}) - ({right}, {bottom})")
    lines.append(f"  连接到桌面: {'是' if info.attached_to_desktop else '否'}")
    lines.append(f"  HDR 已开启: {'是' if info.hdr_enabled else '否'}")
    lines.append(f"  每通道位数: {info.bits_per_color}")
    lines.append(f"  色彩空间: {info.color_space_name} ({info.color_space})")
    lines.append(f"  最大亮度: {info.max_luminance:.1f} nits")
    lines.append(f"  最小亮度: {info.min_luminance:.1f} nits")
    lines.append(f"  最大全帧亮度: {info.max_full_frame_luminance:.1f} nits")
    return "\n".join(lines)


def main() -> int:
    monitors = enumerate_hdr_displays()
    if not monitors:
        print("未检测到活动显示器")
        return 0

    print("HDR 检测报告")
    print("=" * 40)
    for index, info in enumerate(monitors, 1):
        print(format_monitor_info(info, index))
        print("-" * 40)
    print("=" * 40)

    hdr_count = sum(1 for monitor in monitors if monitor.hdr_enabled)
    print(f"汇总: 检测到 {len(monitors)} 台显示器，其中 {hdr_count} 台开启了 HDR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

CLI 不保留 COM、ctypes、`os._exit()` 或第二份颜色空间映射。

- [ ] **Step 5: Run focused tests and CLI verification**

Run:

```powershell
uv run python -m unittest tests.test_check_hdr -v
uv run python -m py_compile module/game_and_screen/hdr.py debug_tools/check_hdr.py tests/test_check_hdr.py
uv run ruff check module/game_and_screen/hdr.py debug_tools/check_hdr.py tests/test_check_hdr.py
uv run python debug_tools/check_hdr.py
uv run python -c "import debug_tools.check_hdr as c; raise SystemExit(c.main())"
```

Expected: tests pass; CLI reports the same monitor/HDR state; normal interpreter shutdown exits with code 0 and no access violation.

- [ ] **Step 6: Commit**

```powershell
git add module/game_and_screen/hdr.py debug_tools/check_hdr.py tests/test_check_hdr.py
git commit -m "重构: 抽取可复用 HDR 检测模块"
```

---

### Task 2: 增加任务启动 HDR 确认门

**Files:**
- Modify: `app/mediator.py`
- Modify: `tasks/base/script_task_scheme.py`
- Create: `tests/test_hdr_warning_gate.py`

**Interfaces:**
- Consumes: `get_monitor_hdr_info(hmonitor: int) -> HdrDisplayInfo | None`
- Produces: `_warn_if_game_monitor_hdr_enabled() -> None`、`mediator.hdr_warning: Signal(object)`

- [ ] **Step 1: Write failing gate tests**

Create `tests/test_hdr_warning_gate.py`:

```python
import unittest
from types import SimpleNamespace
from unittest import mock

import tasks.base.script_task_scheme as scheme
from module.game_and_screen.hdr import HdrDisplayInfo
from module.my_error.my_error import userStopError


class ImmediateSignal:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)
        event.set()


class TestHdrWarningGate(unittest.TestCase):
    def test_simulator_mode_skips_hdr_query(self):
        cfg_stub = SimpleNamespace(simulator=True)
        with (
            mock.patch.object(scheme, "cfg", cfg_stub),
            mock.patch.object(scheme, "get_monitor_hdr_info") as query,
        ):
            scheme._warn_if_game_monitor_hdr_enabled()

        query.assert_not_called()

    def test_disabled_setting_skips_hdr_query(self):
        cfg_stub = SimpleNamespace(
            simulator=False,
            get_value=lambda key, default=None: False,
        )
        with (
            mock.patch.object(scheme, "cfg", cfg_stub),
            mock.patch.object(scheme, "get_monitor_hdr_info") as query,
        ):
            scheme._warn_if_game_monitor_hdr_enabled()

        query.assert_not_called()

    def test_hdr_display_emits_warning_and_waits_for_acknowledgement(self):
        signal = ImmediateSignal()
        cfg_stub = SimpleNamespace(
            simulator=False,
            get_value=lambda key, default=None: True,
        )
        mediator_stub = SimpleNamespace(
            hdr_warning=signal,
            warning_clear=SimpleNamespace(emit=mock.Mock()),
        )
        screen_stub = SimpleNamespace(handle=SimpleNamespace(hwnd=123))
        info = HdrDisplayInfo(
            monitor_handle=456,
            device_name=r"\\.\DISPLAY1",
            color_space=12,
        )
        with (
            mock.patch.object(scheme, "cfg", cfg_stub),
            mock.patch.object(scheme, "mediator", mediator_stub),
            mock.patch.object(scheme, "screen", screen_stub),
            mock.patch.object(scheme.win32api, "MonitorFromWindow", return_value=456),
            mock.patch.object(scheme, "get_monitor_hdr_info", return_value=info),
            mock.patch.object(scheme.auto, "ensure_not_stopped") as stop_check,
        ):
            scheme._warn_if_game_monitor_hdr_enabled()

        self.assertEqual(len(signal.events), 1)
        stop_check.assert_not_called()

    def test_stop_during_warning_closes_dialog_and_propagates(self):
        event = mock.Mock()
        event.wait.return_value = False
        event.is_set.return_value = False
        cfg_stub = SimpleNamespace(
            simulator=False,
            get_value=lambda key, default=None: True,
        )
        clear = mock.Mock()
        mediator_stub = SimpleNamespace(
            hdr_warning=SimpleNamespace(emit=mock.Mock()),
            warning_clear=SimpleNamespace(emit=clear),
        )
        screen_stub = SimpleNamespace(handle=SimpleNamespace(hwnd=123))
        info = HdrDisplayInfo(456, r"\\.\DISPLAY1", color_space=12)
        with (
            mock.patch.object(scheme, "cfg", cfg_stub),
            mock.patch.object(scheme, "mediator", mediator_stub),
            mock.patch.object(scheme, "screen", screen_stub),
            mock.patch.object(scheme.win32api, "MonitorFromWindow", return_value=456),
            mock.patch.object(scheme, "get_monitor_hdr_info", return_value=info),
            mock.patch.object(scheme, "Event", return_value=event),
            mock.patch.object(scheme.auto, "ensure_not_stopped", side_effect=userStopError("stop")),
        ):
            with self.assertRaises(userStopError):
                scheme._warn_if_game_monitor_hdr_enabled()

        clear.assert_called_once_with()
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
uv run python -m unittest tests.test_hdr_warning_gate -v
```

Expected: import/attribute failures because the signal and gate do not exist.

- [ ] **Step 3: Add the dedicated mediator signal**

In `app/mediator.py::Mediator` add:

```python
hdr_warning = Signal(object)
```

- [ ] **Step 4: Implement the stoppable warning gate**

In `tasks/base/script_task_scheme.py`, import `Event`, `win32api`, `win32con`, and `get_monitor_hdr_info`, then add:

```python
def _warn_if_game_monitor_hdr_enabled() -> None:
    if cfg.simulator or not bool(cfg.get_value("experimental_hdr_warning", True)):
        return

    hwnd = screen.handle.hwnd
    if not hwnd:
        log.warning("游戏窗口句柄无效，跳过 HDR 检测")
        return

    try:
        hmonitor = win32api.MonitorFromWindow(
            hwnd,
            win32con.MONITOR_DEFAULTTONEAREST,
        )
        info = get_monitor_hdr_info(int(hmonitor))
    except Exception as exc:
        log.warning(f"检测游戏显示器 HDR 状态失败: {exc}")
        return

    if info is None or not info.hdr_enabled:
        return

    acknowledged = Event()
    mediator.hdr_warning.emit(acknowledged)
    try:
        while not acknowledged.wait(0.1):
            auto.ensure_not_stopped()
    finally:
        if not acknowledged.is_set():
            mediator.warning_clear.emit()
```

Immediately after `init_game()` in `script_task()` add:

```python
_warn_if_game_monitor_hdr_enabled()
```

This call must remain before OBS validation, path initialization, screenshots, matching and clicks.

- [ ] **Step 5: Run gate and lifecycle verification**

Run:

```powershell
uv run python -m unittest tests.test_hdr_warning_gate -v
uv run python -m unittest tests.test_emulator_failure_lifecycle tests.test_team_queue_normalization -v
uv run python -m py_compile app/mediator.py tasks/base/script_task_scheme.py tests/test_hdr_warning_gate.py
uv run ruff check app/mediator.py tasks/base/script_task_scheme.py tests/test_hdr_warning_gate.py
```

Expected: all focused tests pass; existing script lifecycle tests remain green.

- [ ] **Step 6: Commit**

```powershell
git add app/mediator.py tasks/base/script_task_scheme.py tests/test_hdr_warning_gate.py
git commit -m "功能: 任务启动时等待 HDR 警告确认"
```

---

### Task 3: 增加实验性设置、GUI 弹窗和翻译

**Files:**
- Modify: `app/my_app.py`
- Modify: `app/setting_interface.py`
- Modify: `module/config/config_typing.py`
- Modify: `assets/config/config.example.yaml`
- Modify: `i18n/myapp_en.ts`
- Create: `tests/test_hdr_warning_ui.py`

**Interfaces:**
- Consumes: `mediator.hdr_warning: Signal(object)`、`mediator.hdr_warning_clear: Signal(object)`
- Produces: `MainWindow.show_hdr_warning(acknowledged_event) -> None`、持久化配置 `experimental_hdr_warning: bool`

- [ ] **Step 1: Write failing GUI/config tests**

Create `tests/test_hdr_warning_ui.py`:

```python
import unittest
from pathlib import Path
from typing import get_type_hints
from unittest import mock

from PySide6.QtWidgets import QApplication

import app.my_app as my_app_module
import module.config.config_typing as config_typing_module
from app.setting_interface import SettingInterface


class EventStub:
    def __init__(self):
        self.was_set = False

    def set(self):
        self.was_set = True


class TestHdrWarningUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_hdr_warning_sets_event_after_dialog_closes(self):
        event = EventStub()
        dialog = mock.Mock()
        window = my_app_module.MainWindow.__new__(my_app_module.MainWindow)
        window.tr = lambda text: text

        with mock.patch.object(my_app_module, "MessageBoxWarning", return_value=dialog):
            my_app_module.MainWindow.show_hdr_warning(window, event)

        dialog.exec.assert_called_once_with()
        self.assertTrue(event.was_set)
        self.assertIsNone(window._current_warning_box)

    def test_hdr_warning_sets_event_when_dialog_raises(self):
        event = EventStub()
        dialog = mock.Mock()
        dialog.exec.side_effect = RuntimeError("dialog failed")
        window = my_app_module.MainWindow.__new__(my_app_module.MainWindow)
        window.tr = lambda text: text

        with mock.patch.object(my_app_module, "MessageBoxWarning", return_value=dialog):
            my_app_module.MainWindow.show_hdr_warning(window, event)

        self.assertTrue(event.was_set)
        self.assertIsNone(window._current_warning_box)

    def test_hdr_warning_clear_only_closes_matching_event(self):
        current_event = EventStub()
        other_event = EventStub()
        dialog = mock.Mock()
        window = my_app_module.MainWindow.__new__(my_app_module.MainWindow)
        window._current_hdr_warning_event = current_event
        window._current_warning_box = dialog

        my_app_module.MainWindow.clear_hdr_warning(window, other_event)
        dialog.accept.assert_not_called()

        my_app_module.MainWindow.clear_hdr_warning(window, current_event)
        dialog.accept.assert_called_once_with()

    def test_config_declares_default_enabled_hdr_warning(self):
        hints = get_type_hints(config_typing_module.ConfigModel)
        self.assertIs(hints["experimental_hdr_warning"], bool)

        content = (
            Path(__file__).resolve().parents[1]
            / "assets/config/config.example.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("experimental_hdr_warning: True", content)

    def test_setting_interface_adds_hdr_warning_to_experimental_group(self):
        interface = SettingInterface()
        try:
            widgets = interface.experimental_group.cardLayout._ExpandLayout__widgets
            self.assertIn(interface.hdr_warning_card, widgets)
            self.assertTrue(interface.hdr_warning_card.switchButton.checked)
        finally:
            interface.close()
            self.app.processEvents()
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
uv run python -m unittest tests.test_hdr_warning_ui -v
```

Expected: missing method, config field and setting card failures.

- [ ] **Step 3: Add the default-enabled experimental setting**

Add to `module/config/config_typing.py::ConfigModel`:

```python
experimental_hdr_warning: bool
"""任务启动时检测游戏显示器 HDR 状态并提示潜在识别问题"""
```

Add to the experimental section of `assets/config/config.example.yaml`:

```yaml
experimental_hdr_warning: True # 任务启动时检测游戏显示器 HDR 状态并提示潜在识别问题
```

Do not modify `config.yaml`.

- [ ] **Step 4: Add the experimental setting card**

In `app/setting_interface.py`, create next to `keep_screen_awake_card`:

```python
self.hdr_warning_card = SwitchSettingCard(
    FIF.BRIGHTNESS,
    QT_TRANSLATE_NOOP("SwitchSettingCard", "HDR 检测警告"),
    QT_TRANSLATE_NOOP(
        "SwitchSettingCard",
        "任务启动时检测游戏所在显示器的 HDR 状态；开启 HDR 时提示可能发生图像识别问题",
    ),
    config_name="experimental_hdr_warning",
    parent=self.experimental_group,
)
```

If `FIF.BRIGHTNESS` is unavailable in the installed qfluentwidgets version, use existing `FIF.VIEW` without adding a custom icon. Add the card to `experimental_group` immediately before `keep_screen_awake_card`.

- [ ] **Step 5: Add the modal GUI slot and connection**

In `app/my_app.py`, add:

```python
def show_hdr_warning(self, acknowledged_event):
    self._current_hdr_warning_event = acknowledged_event
    try:
        self._current_warning_box = MessageBoxWarning(
            self.tr("检测到 HDR 已开启"),
            self.tr(
                "检测到游戏所在显示器已开启 HDR。开启 HDR 可能导致图像识别问题；"
                "如果运行中遇到识别异常，请先关闭 Windows HDR 后重试。\n\n"
                "如果不想再看到本通知，请在“设置 > 实验性内容”中关闭“HDR 检测警告”。"
            ),
            self,
        )
        self._current_warning_box.exec()
    except Exception as exc:
        log.error(f"显示 HDR 警告失败: {exc}")
    finally:
        if self._current_hdr_warning_event is acknowledged_event:
            self._current_warning_box = None
            self._current_hdr_warning_event = None
        acknowledged_event.set()


def clear_hdr_warning(self, acknowledged_event):
    if getattr(self, "_current_hdr_warning_event", None) is not acknowledged_event:
        return
    if getattr(self, "_current_warning_box", None):
        self._current_warning_box.accept()
```

In `connect_mediator()` add:

```python
mediator.hdr_warning.connect(self.show_hdr_warning)
mediator.hdr_warning_clear.connect(self.clear_hdr_warning)
```

The slots must compare Event identity before closing `_current_warning_box`, so a stale HDR cleanup request cannot close another warning.

- [ ] **Step 6: Update and fill English translations**

Run:

```powershell
uv run python scripts/check_i18n.py --update
```

In `i18n/myapp_en.ts`, provide these translations:

```text
HDR 检测警告
HDR detection warning

任务启动时检测游戏所在显示器的 HDR 状态；开启 HDR 时提示可能发生图像识别问题
Checks HDR on the display containing the game window at task startup and warns about possible image recognition issues

检测到 HDR 已开启
HDR Is Enabled

检测到游戏所在显示器已开启 HDR。开启 HDR 可能导致图像识别问题；如果运行中遇到识别异常，请先关闭 Windows HDR 后重试。

如果不想再看到本通知，请在“设置 > 实验性内容”中关闭“HDR 检测警告”。
HDR is enabled on the display containing the game window. HDR may cause image recognition issues. If recognition fails, disable Windows HDR and try again.

To stop seeing this notice, disable "HDR detection warning" under Settings > Experimental.
```

Then compile translations:

```powershell
uv run python scripts/translation_files_compile.py
```

- [ ] **Step 7: Run GUI/config/i18n verification**

Run:

```powershell
uv run python -m unittest tests.test_hdr_warning_ui -v
uv run python -m unittest tests.test_hdr_warning_gate tests.test_check_hdr -v
uv run python -m py_compile app/my_app.py app/setting_interface.py module/config/config_typing.py tests/test_hdr_warning_ui.py
uv run ruff check app/my_app.py app/setting_interface.py module/config/config_typing.py tests/test_hdr_warning_ui.py
uv run python scripts/check_i18n.py
```

Expected: tests pass; i18n check has no missing new strings.

- [ ] **Step 8: Manual Windows verification**

Verify these exact scenarios:

1. PC mode, HDR off: task starts without warning.
2. PC mode, HDR on: warning appears after game starts and before automation; clicking acknowledgement continues.
3. PC mode, HDR on, feature off: no warning.
4. Simulator mode, HDR on: no warning.
5. HDR warning open, stop/close requested: worker exits cooperatively and dialog closes.
6. Game on SDR display while another display has HDR: no warning.
7. Game on HDR display while another display is SDR: warning appears.

- [ ] **Step 9: Commit**

```powershell
git add app/my_app.py app/setting_interface.py module/config/config_typing.py assets/config/config.example.yaml i18n/myapp_en.ts tests/test_hdr_warning_ui.py
git commit -m "功能: 添加实验性 HDR 检测警告"
```

---

### Task 4: Final focused regression and review

**Files:**
- Verify only; modify files only to address confirmed review findings

**Interfaces:**
- Consumes: all interfaces from Tasks 1-3
- Produces: verified end-to-end feature

- [ ] **Step 1: Run the complete focused suite**

```powershell
uv run python -m unittest tests.test_check_hdr tests.test_hdr_warning_gate tests.test_hdr_warning_ui tests.test_emulator_failure_lifecycle tests.test_startup_main_menu_wait -v
uv run ruff check module/game_and_screen/hdr.py debug_tools/check_hdr.py app/mediator.py tasks/base/script_task_scheme.py app/my_app.py app/setting_interface.py module/config/config_typing.py tests/test_check_hdr.py tests/test_hdr_warning_gate.py tests/test_hdr_warning_ui.py
uv run python scripts/check_i18n.py
```

Expected: all focused tests and checks pass with no new warnings.

- [ ] **Step 2: Review the final diff**

Review specifically:

- no duplicated DXGI implementation remains in the CLI
- `DXGI_OUTPUT_DESC1` field layout and IID/vtable values remain unchanged
- every COM object still releases on every path
- task warning happens only after top-level `init_game()` and before automation
- event wait has stop checks and stop closes the dialog
- config default is `True` without touching user config
- all new user-visible strings are translated

- [ ] **Step 3: Address confirmed Critical/Important findings and rerun covering tests**

Do not make speculative cleanup. For each confirmed finding, add or update the smallest regression test, apply the minimal fix, and rerun the commands from Step 1 that cover it.
