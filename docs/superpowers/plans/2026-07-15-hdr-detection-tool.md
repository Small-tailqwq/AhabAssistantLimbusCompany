# HDR 检测工具实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 `debug_tools/check_hdr.py` 独立脚本，通过 DXGI `IDXGIOutput6::GetDesc1()` 检测 Windows 10/11 每个显示器的 HDR 开启状态并输出完整信息。

**Architecture:** 单文件脚本，分四层：纯函数（可测试）、COM 互操作、DXGI 枚举 + Win32 补充、主函数。COM 对象通过 `try...finally` 嵌套管理引用计数，`CoInitializeEx`/`CoUninitialize` 管理 COM 套间生命周期。

**Tech Stack:** Python 3.12+，ctypes（标准库），pywin32（项目已有依赖），unittest

## Global Constraints

- Windows-only 桌面自动化项目，Python 3.12+
- 提交信息使用中文
- 遗留模块存在预存 ruff 警告；功能开发不做无关清理
- `debug_tools/` 中的可复用临时验证脚本不纳入 CI
- 验证命令：`uv run ruff check .`、`uv run python -m unittest discover -s tests -p "test_*.py" -v`
- 设计文档：`docs/superpowers/specs/2026-07-15-hdr-detection-tool-design.md`

---

### Task 1: 纯函数 — 色彩空间映射、MonitorInfo、格式化输出

**Files:**
- Create: `debug_tools/check_hdr.py`
- Create: `tests/test_check_hdr.py`

**Interfaces:**
- Produces: `color_space_name(value: int) -> str`、`MonitorInfo` dataclass、`format_monitor_info(info: MonitorInfo, index: int) -> str`、`HDR_COLOR_SPACE: int` 常量

- [ ] **Step 1: Write the failing test**

Create `tests/test_check_hdr.py`:

```python
import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_hdr",
    Path(__file__).parent.parent / "debug_tools" / "check_hdr.py",
)
check_hdr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_hdr)


class TestColorSpaceName(unittest.TestCase):
    def test_sdr_color_space(self):
        self.assertEqual(check_hdr.color_space_name(0), "RGB_FULL_G22_NONE_P709")

    def test_hdr_color_space(self):
        self.assertEqual(check_hdr.color_space_name(16), "RGB_FULL_G2084_NONE_P2020")

    def test_unknown_color_space(self):
        result = check_hdr.color_space_name(999)
        self.assertIn("UNKNOWN", result)
        self.assertIn("999", result)


class TestFormatMonitorInfo(unittest.TestCase):
    def test_format_hdr_monitor(self):
        info = check_hdr.MonitorInfo(
            device_name=r"\\.\DISPLAY1",
            friendly_name="Dell U2720Q",
            is_primary=True,
            desktop_rect=(0, 0, 3840, 2160),
            attached_to_desktop=True,
            hdr_enabled=True,
            hdr_supported=True,
            bits_per_color=10,
            color_space=16,
            color_space_name="RGB_FULL_G2084_NONE_P2020",
            max_luminance=350.0,
            min_luminance=0.1,
            max_full_frame_luminance=350.0,
        )
        result = check_hdr.format_monitor_info(info, 1)
        self.assertIn("HDR 已开启: 是", result)
        self.assertIn("Dell U2720Q", result)
        self.assertIn("主显示器: 是", result)
        self.assertIn("10", result)

    def test_format_sdr_monitor(self):
        info = check_hdr.MonitorInfo(
            device_name=r"\\.\DISPLAY1",
            hdr_enabled=False,
            hdr_supported=True,
            color_space=0,
            color_space_name="RGB_FULL_G22_NONE_P709",
        )
        result = check_hdr.format_monitor_info(info, 1)
        self.assertIn("HDR 已开启: 否", result)

    def test_format_unsupported_monitor(self):
        info = check_hdr.MonitorInfo(
            device_name=r"\\.\DISPLAY1",
            hdr_supported=False,
        )
        result = check_hdr.format_monitor_info(info, 1)
        self.assertIn("不支持 HDR 检测", result)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_check_hdr -v`
Expected: FAIL / ERROR — module not found or attributes missing

- [ ] **Step 3: Write minimal implementation**

Create `debug_tools/check_hdr.py`:

```python
"""HDR 检测工具 - 检测 Windows 10/11 是否开启了 HDR。

使用 DXGI IDXGIOutput6::GetDesc1() 查询每个显示器的 HDR 状态。
验证工具，用于测试检测方法在 Win10/11 上的准确性。

Usage:
    uv run python debug_tools/check_hdr.py
"""

from dataclasses import dataclass

# DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020
HDR_COLOR_SPACE = 16

_COLOR_SPACE_NAMES: dict[int, str] = {
    0: "RGB_FULL_G22_NONE_P709",
    1: "RGB_FULL_G10_NONE_P709",
    2: "RGB_STUDIO_G22_NONE_P709",
    3: "RGB_STUDIO_G22_NONE_P2020",
    4: "RESERVED",
    5: "YCBCR_FULL_G22_NONE_P709_X601",
    6: "YCBCR_STUDIO_G22_LEFT_P601",
    7: "YCBCR_FULL_G22_LEFT_P601",
    8: "YCBCR_STUDIO_G22_LEFT_P709",
    9: "YCBCR_FULL_G22_LEFT_P709",
    10: "YCBCR_STUDIO_G22_LEFT_P2020",
    11: "YCBCR_FULL_G22_LEFT_P2020",
    16: "RGB_FULL_G2084_NONE_P2020",
    17: "YCBCR_STUDIO_G2084_LEFT_P2020",
    18: "RGB_STUDIO_G2084_NONE_P2020",
    19: "YCBCR_STUDIO_G22_TOP_P709",
    20: "YCBCR_STUDIO_G22_TOP_P2020",
    21: "RGB_FULL_G22_NONE_P2020",
    22: "YCBCR_STUDIO_GHLG_TOP_P2020",
    23: "YCBCR_FULL_GHLG_TOP_P2020",
    24: "RGB_STUDIO_G24_NONE_P709",
    25: "RGB_STUDIO_G24_NONE_P2020",
    26: "YCBCR_STUDIO_G24_LEFT_P709",
    27: "YCBCR_STUDIO_G24_LEFT_P2020",
    28: "YCBCR_STUDIO_G24_TOP_P709",
    29: "YCBCR_STUDIO_G24_TOP_P2020",
}


def color_space_name(value: int) -> str:
    """返回 DXGI_COLOR_SPACE_TYPE 枚举值的人类可读名称。"""
    return _COLOR_SPACE_NAMES.get(value, f"UNKNOWN ({value})")


@dataclass
class MonitorInfo:
    """显示器信息容器。"""

    device_name: str = ""
    friendly_name: str = ""
    is_primary: bool = False
    desktop_rect: tuple[int, int, int, int] = (0, 0, 0, 0)
    attached_to_desktop: bool = False
    hdr_enabled: bool = False
    hdr_supported: bool = True
    bits_per_color: int = 0
    color_space: int = 0
    color_space_name: str = ""
    max_luminance: float = 0.0
    min_luminance: float = 0.0
    max_full_frame_luminance: float = 0.0


def format_monitor_info(info: MonitorInfo, index: int) -> str:
    """将 MonitorInfo 格式化为显示字符串。"""
    lines = [f"显示器 {index}:"]
    lines.append(f"  设备名: {info.device_name}")
    lines.append(f"  友好名: {info.friendly_name or '(未知)'}")
    lines.append(f"  主显示器: {'是' if info.is_primary else '否'}")
    left, top, right, bottom = info.desktop_rect
    lines.append(f"  桌面区域: ({left}, {top}) - ({right}, {bottom})")
    lines.append(f"  连接到桌面: {'是' if info.attached_to_desktop else '否'}")
    if info.hdr_supported:
        lines.append(f"  HDR 已开启: {'是' if info.hdr_enabled else '否'}")
        lines.append(f"  每通道位数: {info.bits_per_color}")
        lines.append(f"  色彩空间: {info.color_space_name} ({info.color_space})")
        lines.append(f"  最大亮度: {info.max_luminance:.1f} nits")
        lines.append(f"  最小亮度: {info.min_luminance:.1f} nits")
        lines.append(f"  最大全帧亮度: {info.max_full_frame_luminance:.1f} nits")
    else:
        lines.append("  HDR 已开启: 不支持 HDR 检测（需 Win10 1703+）")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_check_hdr -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run ruff check**

Run: `uv run ruff check debug_tools/check_hdr.py tests/test_check_hdr.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add debug_tools/check_hdr.py tests/test_check_hdr.py
git commit -m "feat: 添加 HDR 检测工具的纯函数和单元测试"
```

---

### Task 2: COM 互操作基础设施

**Files:**
- Modify: `debug_tools/check_hdr.py` (在纯函数之后追加 COM 互操作层)

**Interfaces:**
- Consumes: 无（底层基础设施）
- Produces: `GUID`、`RECT`、`DXGI_OUTPUT_DESC1` 结构体；`_vtable_func()`、`com_release()`、`_com_query_interface()` 辅助函数；`_ole32`、`_dxgi` DLL 引用；`IID_IDXGIFactory1`、`IID_IDXGIOutput6` 常量

- [ ] **Step 1: 添加 COM 互操作层代码**

在 `debug_tools/check_hdr.py` 的 `format_monitor_info` 函数之后追加以下代码，并在文件顶部添加 `import ctypes` 和 `import sys`：

首先，修改文件顶部的 import 区域，将：
```python
from dataclasses import dataclass
```
替换为：
```python
import ctypes
from dataclasses import dataclass
```

然后，在 `format_monitor_info` 函数之后追加：

```python
# === COM 互操作层 ===

# 常量
COINIT_APARTMENTTHREADED = 0x2
S_OK = 0
S_FALSE = 1
RPC_E_CHANGED_MODE = 0x80010106
MONITORINFOF_PRIMARY = 0x00000001


class GUID(ctypes.Structure):
    """Windows GUID/IID 结构体。"""

    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class RECT(ctypes.Structure):
    """Windows RECT 结构体。"""

    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class DXGI_OUTPUT_DESC1(ctypes.Structure):
    """IDXGIOutput6::GetDesc1 返回的显示器描述结构体。"""

    _fields_ = [
        ("DeviceName", ctypes.c_wchar * 32),
        ("DesktopCoordinates", RECT),
        ("AttachedToDesktop", ctypes.c_int),
        ("Rotation", ctypes.c_uint),
        ("Monitor", ctypes.c_void_p),
        ("BitsPerColor", ctypes.c_uint),
        ("ColorSpace", ctypes.c_int),
        ("MaxLuminance", ctypes.c_float),
        ("MinLuminance", ctypes.c_float),
        ("MaxFullFrameLuminance", ctypes.c_float),
    ]


# IID 常量
IID_IDXGIFactory1 = GUID(
    0x770AAE78,
    0xF26F,
    0x4DBA,
    (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87),
)

IID_IDXGIOutput6 = GUID(
    0x068346E8,
    0xAAEC,
    0x4B84,
    (ctypes.c_ubyte * 8)(0xAD, 0xD7, 0x13, 0x7F, 0x51, 0x3F, 0x77, 0xA1),
)

# COM 方法函数原型
_QueryInterface = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_void_p,
    ctypes.POINTER(GUID),
    ctypes.POINTER(ctypes.c_void_p),
)

_Release = ctypes.WINFUNCTYPE(
    ctypes.c_ulong,
    ctypes.c_void_p,
)

_EnumAdapters1 = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_void_p,
    ctypes.c_uint,
    ctypes.POINTER(ctypes.c_void_p),
)

_EnumOutputs = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_void_p,
    ctypes.c_uint,
    ctypes.POINTER(ctypes.c_void_p),
)

_GetDesc1 = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_void_p,
    ctypes.POINTER(DXGI_OUTPUT_DESC1),
)

# DLL 引用
_ole32 = ctypes.windll.ole32
_ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
_ole32.CoInitializeEx.restype = ctypes.c_long
_ole32.CoUninitialize.argtypes = []
_ole32.CoUninitialize.restype = None

_dxgi = ctypes.windll.dxgi
_dxgi.CreateDXGIFactory1.argtypes = [
    ctypes.POINTER(GUID),
    ctypes.POINTER(ctypes.c_void_p),
]
_dxgi.CreateDXGIFactory1.restype = ctypes.c_long


def _vtable_func(com_ptr: int, index: int, prototype):
    """按 vtable 索引获取 COM 方法可调用对象。

    com_ptr: COM 对象地址（整数）
    index: vtable 索引
    prototype: ctypes.WINFUNCTYPE 函数原型
    """
    vtable_ptr = ctypes.POINTER(ctypes.c_void_p).from_address(com_ptr)[0]
    func_ptr = ctypes.POINTER(ctypes.c_void_p).from_address(vtable_ptr)[index]
    return prototype(func_ptr)


def com_release(ptr) -> None:
    """调用 IUnknown::Release。空指针安全。"""
    if not ptr:
        return
    release = _vtable_func(ptr, 2, _Release)
    release(ptr)


def _com_query_interface(com_ptr: int, iid: GUID) -> int | None:
    """QueryInterface 包装。返回新接口指针或 None。"""
    out = ctypes.c_void_p()
    qi = _vtable_func(com_ptr, 0, _QueryInterface)
    hr = qi(com_ptr, ctypes.byref(iid), ctypes.byref(out))
    if hr == S_OK:
        return out.value
    return None
```

- [ ] **Step 2: Verify py_compile passes**

Run: `uv run python -m py_compile debug_tools/check_hdr.py`
Expected: No output (success)

- [ ] **Step 3: Run ruff check**

Run: `uv run ruff check debug_tools/check_hdr.py`
Expected: No errors

- [ ] **Step 4: Run existing tests to ensure no regression**

Run: `uv run python -m unittest tests.test_check_hdr -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add debug_tools/check_hdr.py
git commit -m "feat: 添加 COM 互操作基础设施（GUID/vtable/CoInitialize）"
```

---

### Task 3: DXGI 枚举 + Win32 补充 + 主函数 + 端到端验证

**Files:**
- Modify: `debug_tools/check_hdr.py` (在 COM 互操作层之后追加枚举、补充、主函数)

**Interfaces:**
- Consumes: Task 1 的 `color_space_name`、`MonitorInfo`、`format_monitor_info`、`HDR_COLOR_SPACE`；Task 2 的所有 COM 辅助函数和结构体
- Produces: `_create_dxgi_factory()`、`_enumerate_monitors()`、`_enrich_monitor_info()`、`main()`

- [ ] **Step 1: 添加 `import sys` 并添加 DXGI 枚举函数**

首先，在文件顶部的 import 区域，将：
```python
import ctypes
from dataclasses import dataclass
```
替换为：
```python
import ctypes
import sys
from dataclasses import dataclass
```

然后，在 `debug_tools/check_hdr.py` 的 `_com_query_interface` 函数之后追加：

```python
# === DXGI 枚举层 ===


def _create_dxgi_factory() -> int | None:
    """创建 IDXGIFactory1 实例。返回指针或 None。"""
    factory = ctypes.c_void_p()
    hr = _dxgi.CreateDXGIFactory1(
        ctypes.byref(IID_IDXGIFactory1),
        ctypes.byref(factory),
    )
    if hr == S_OK:
        return factory.value
    return None


def _enumerate_monitors(factory_ptr: int) -> list[DXGI_OUTPUT_DESC1]:
    """枚举所有显示器的 DXGI_OUTPUT_DESC1。

    遍历 factory -> adapters -> outputs -> IDXGIOutput6 -> GetDesc1。
    QI 失败的 output 被跳过（IDXGIOutput6 不可用 = Win10 < 1703）。
    """
    results: list[DXGI_OUTPUT_DESC1] = []
    enum_adapters1 = _vtable_func(factory_ptr, 12, _EnumAdapters1)

    adapter_index = 0
    while True:
        adapter = ctypes.c_void_p()
        hr = enum_adapters1(factory_ptr, adapter_index, ctypes.byref(adapter))
        if hr != S_OK:
            break

        try:
            enum_outputs = _vtable_func(adapter.value, 7, _EnumOutputs)
            output_index = 0
            while True:
                output = ctypes.c_void_p()
                hr = enum_outputs(
                    adapter.value, output_index, ctypes.byref(output)
                )
                if hr != S_OK:
                    break

                try:
                    output6_ptr = _com_query_interface(
                        output.value, IID_IDXGIOutput6
                    )
                    if output6_ptr is not None:
                        try:
                            desc = DXGI_OUTPUT_DESC1()
                            get_desc1 = _vtable_func(output6_ptr, 27, _GetDesc1)
                            hr = get_desc1(output6_ptr, ctypes.byref(desc))
                            if hr == S_OK:
                                results.append(desc)
                        finally:
                            com_release(output6_ptr)
                finally:
                    com_release(output.value)
                output_index += 1
        finally:
            com_release(adapter.value)
        adapter_index += 1

    return results
```

- [ ] **Step 2: 添加 Win32 信息补充函数**

在 `_enumerate_monitors` 之后追加：

```python
# === Win32 信息补充 ===


def _enrich_monitor_info(desc: DXGI_OUTPUT_DESC1) -> MonitorInfo:
    """从 DXGI_OUTPUT_DESC1 构建 MonitorInfo，用 Win32 API 补充友好名称等。"""
    import win32api

    info = MonitorInfo(
        device_name=desc.DeviceName,
        desktop_rect=(
            desc.DesktopCoordinates.left,
            desc.DesktopCoordinates.top,
            desc.DesktopCoordinates.right,
            desc.DesktopCoordinates.bottom,
        ),
        attached_to_desktop=bool(desc.AttachedToDesktop),
        bits_per_color=desc.BitsPerColor,
        color_space=desc.ColorSpace,
        color_space_name=color_space_name(desc.ColorSpace),
        max_luminance=desc.MaxLuminance,
        min_luminance=desc.MinLuminance,
        max_full_frame_luminance=desc.MaxFullFrameLuminance,
        hdr_enabled=(desc.ColorSpace == HDR_COLOR_SPACE),
        hdr_supported=True,
    )

    if not desc.Monitor:
        return info

    try:
        mon_info = win32api.GetMonitorInfo(desc.Monitor)
        info.is_primary = bool(mon_info.get("Flags", 0) & MONITORINFOF_PRIMARY)
        device = mon_info.get("Device", "")
        if "\\Monitor" in device:
            adapter_name = device.split("\\Monitor")[0]
            for i in range(5):
                try:
                    result = win32api.EnumDisplayDevices(adapter_name, i, 0)
                    if result[0] == device:
                        info.friendly_name = result[1]
                        break
                except Exception:
                    break
    except Exception:
        pass

    return info
```

- [ ] **Step 3: 添加主函数**

在 `_enrich_monitor_info` 之后追加：

```python
# === 主函数 ===


def main() -> int:
    """主入口。返回退出码。"""
    hr = _ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    if hr == RPC_E_CHANGED_MODE:
        print("错误: COM 套间类型冲突（线程已初始化为 MTA）", file=sys.stderr)
        return 1

    try:
        factory_ptr = _create_dxgi_factory()
        if factory_ptr is None:
            print("错误: CreateDXGIFactory1 失败", file=sys.stderr)
            return 1

        try:
            descs = _enumerate_monitors(factory_ptr)
        finally:
            com_release(factory_ptr)

        if not descs:
            print("未检测到活动显示器")
            return 0

        monitors = [_enrich_monitor_info(desc) for desc in descs]

        print("HDR 检测报告")
        print("=" * 40)
        for i, info in enumerate(monitors, 1):
            print(format_monitor_info(info, i))
            print("-" * 40)
        print("=" * 40)

        hdr_count = sum(1 for m in monitors if m.hdr_enabled)
        print(f"汇总: 检测到 {len(monitors)} 台显示器，其中 {hdr_count} 台开启了 HDR")

        return 0
    finally:
        _ole32.CoUninitialize()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Verify py_compile passes**

Run: `uv run python -m py_compile debug_tools/check_hdr.py`
Expected: No output (success)

- [ ] **Step 5: Run ruff check**

Run: `uv run ruff check debug_tools/check_hdr.py`
Expected: No errors

- [ ] **Step 6: Run existing tests to ensure no regression**

Run: `uv run python -m unittest tests.test_check_hdr -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Run the script end-to-end**

Run: `uv run python debug_tools/check_hdr.py`
Expected: Prints HDR detection report with per-monitor info and summary line.
Verify: `ColorSpace` value is `0` when HDR is off, `16` when HDR is on.

- [ ] **Step 8: Commit**

```bash
git add debug_tools/check_hdr.py
git commit -m "feat: 完成 HDR 检测工具（DXGI 枚举 + Win32 补充 + 主函数）"
```
