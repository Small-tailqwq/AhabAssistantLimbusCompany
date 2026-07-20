# HDR 检测工具设计文档

日期：2026-07-15
主题：Windows HDR 状态检测脚本（debug_tools/check_hdr.py）

## 背景

AALC 使用 GDI 截图进行模板匹配。HDR 开启时，Windows 会以广色域/高动态范围渲染画面，
GDI 截图取到的像素颜色可能与非 HDR 环境不同，导致模板匹配相似度下降。
当前 `module/automation/screenshot.py` 的注释已提到"避免 HDR/系统渲染差异"，
但项目尚无手段检测用户是否开启了 HDR。

本设计创建一个独立的验证工具，用于测试 DXGI `IDXGIOutput6::GetDesc1()` 能否在
Windows 10/11 上准确检测 HDR 开启状态。验证通过后，后续可在此基础上集成到主程序
（启动时检测 + 警告 / 运行时临时关闭 HDR），但本次范围仅限独立脚本。

## 范围

- **包含**：`debug_tools/check_hdr.py` 独立检测脚本
- **不包含**：主程序集成、HDR 自动开关、UI 警告

## 技术方案

### 检测方法：DXGI via ctypes

使用 `ctypes` 调用 `dxgi.dll` 的 COM 接口，查询每个显示器的 HDR 状态。
不引入新依赖，仅使用 `ctypes`（标准库）和 `pywin32`（项目已有依赖）。

### 调用链

```
CoInitializeEx(NULL, COINIT_APARTMENTTHREADED)          ← COM 套间初始化
CreateDXGIFactory1(IID_IDXGIFactory1) -> IDXGIFactory1
  factory.EnumAdapters1(index) -> IDXGIAdapter1
    adapter.EnumOutputs(index) -> IDXGIOutput
      output.QueryInterface(IID_IDXGIOutput6) -> IDXGIOutput6
        output6.GetDesc1() -> DXGI_OUTPUT_DESC1
      output6.Release()
    output.Release()
  adapter.Release()
factory.Release()
CoUninitialize()                                        ← COM 套间清理
```

所有 COM/DXGI 调用前必须通过 `ole32.dll!CoInitializeEx` 初始化套间，
否则 `CreateDXGIFactory1` 返回 `CO_E_NOTINITIALIZED (0x800401F0)`。
脚本结束时调用 `CoUninitialize` 清理。使用 `try...finally` 确保清理始终执行。

### HDR 判定

`DXGI_OUTPUT_DESC1.ColorSpace` 字段值为 `DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020`
（枚举值 16）时，HDR 已开启；其他值（通常为 `RGB_FULL_G22_NONE_P709` = 0）表示 SDR。

仅依赖 `ColorSpace` 单一判定。`BitsPerColor` 和 `MaxLuminance` 仅作为信息性输出展示，
不参与 HDR 判定（8-bit+FRC 面板在 HDR 模式下可能仍报告 8bpc，SDR 面板也可能报告 10bpc）。

### Win32 信息补充

通过 `win32api.GetMonitorInfo(hMonitor)` 获取：
- GDI 设备名（`Device` 字段，如 `\\.\DISPLAY1\Monitor0`）
- 是否为主显示器（`Flags` 包含 `MONITORINFOF_PRIMARY = 1`）

通过 `win32api.EnumDisplayDevices(adapter_name, 0, 0)` 获取显示器友好名称：
- 从 `GetMonitorInfo` 的 `Device` 字段提取适配器名（去掉 `\Monitor0` 后缀，得到 `\\.\DISPLAY1`）
- `EnumDisplayDevices` 返回元组的第二元素 `DeviceString` 为友好名称（如 "Dell U2720Q"）
- 若 `EnumDisplayDevices` 失败，回退使用 GDI 设备名作为标识

## 架构

### 文件结构

单文件：`debug_tools/check_hdr.py`

### 代码分层

1. **COM 互操作层**
   - `GUID` 结构体（ctypes）
   - `RECT` 结构体（ctypes）
   - `DXGI_OUTPUT_DESC1` 结构体（ctypes，含自动对齐）
   - vtable 调用辅助函数：按索引从 COM 对象 vtable 获取函数指针并调用
   - `CoInitializeEx` / `CoUninitialize`：通过 `ole32.dll` 调用，管理 COM 套间生命周期
   - `com_release(ptr)`：封装 `IUnknown::Release`（vtable 索引 2），空指针安全

2. **DXGI 枚举层**
   - `_create_dxgi_factory()` -> IDXGIFactory1 指针
   - `_enumerate_outputs(factory)` -> 生成 (IDXGIOutput6 指针, DXGI_OUTPUT_DESC1) 列表
   - 引用计数管理：枚举完成后在调用方 `try...finally` 中按逆序 Release 所有 COM 对象

3. **信息收集层**
   - 对每个 output6 调用 `GetDesc1()` 获取 `DXGI_OUTPUT_DESC1`
   - 用 `desc1.Monitor`（HMONITOR）调用 `win32api.GetMonitorInfo()` 获取 GDI 设备名和主显示器标识
   - 用 `win32api.EnumDisplayDevices()` 获取显示器友好名称

4. **输出层**
   - 格式化打印每个显示器的完整信息
   - 汇总：检测到几台显示器，其中几台开启了 HDR

### COM 对象生命周期

所有 COM 对象遵循"谁获取谁释放"原则，按获取逆序释放：

| 对象 | 获取方式 | 释放时机 |
|---|---|---|
| factory | `CreateDXGIFactory1` | 所有枚举完成后，在 `finally` 中 Release |
| adapter | `factory.EnumAdapters1` | 该 adapter 的所有 output 处理完毕后 Release |
| output | `adapter.EnumOutputs` | QueryInterface + GetDesc1 完成后 Release |
| output6 | `output.QueryInterface` | GetDesc1 完成后立即 Release |

**失败路径**：任何中间步骤失败时，已获取的 COM 对象在 `finally` 块中释放。
使用 `try...finally` 嵌套确保每一层都不泄漏。

```python
# 伪代码结构
CoInitializeEx(...)
try:
    factory = CreateDXGIFactory1(...)
    try:
        for adapter in enumerate_adapters(factory):
            try:
                for output in enumerate_outputs(adapter):
                    try:
                        output6 = query_interface(output, IID_IDXGIOutput6)
                        try:
                            desc1 = get_desc1(output6)
                            # 收集信息
                        finally:
                            com_release(output6)
                    finally:
                        com_release(output)
            finally:
                com_release(adapter)
    finally:
        com_release(factory)
finally:
    CoUninitialize()
```

### COM vtable 索引

| 接口 | 方法 | vtable 索引 |
|---|---|---|
| IUnknown | QueryInterface | 0 |
| IUnknown | AddRef | 1 |
| IUnknown | Release | 2 |
| IDXGIFactory1 | EnumAdapters1 | 12 |
| IDXGIAdapter1 | EnumOutputs | 7 |
| IDXGIOutput6 | GetDesc1 | 27 |

### IID 常量

- `IID_IDXGIFactory1`: `{770aae78-f26f-4dba-a829-253c83d1b387}`
- `IID_IDXGIOutput6`: `{068346e8-aaec-4b84-add7-137f513f77a1}`

### DXGI_OUTPUT_DESC1 结构体布局

```python
class DXGI_OUTPUT_DESC1(ctypes.Structure):
    _fields_ = [
        ("DeviceName", ctypes.c_wchar * 32),      # 设备名
        ("DesktopCoordinates", RECT),              # 桌面坐标
        ("AttachedToDesktop", ctypes.c_int),       # BOOL
        ("Rotation", ctypes.c_uint),               # DXGI_MODE_ROTATION
        ("Monitor", ctypes.c_void_p),              # HMONITOR
        ("BitsPerColor", ctypes.c_uint),           # 每通道位数
        ("ColorSpace", ctypes.c_int),              # DXGI_COLOR_SPACE_TYPE
        ("MaxLuminance", ctypes.c_float),          # 最大亮度 (nits)
        ("MinLuminance", ctypes.c_float),          # 最小亮度 (nits)
        ("MaxFullFrameLuminance", ctypes.c_float), # 最大全帧亮度 (nits)
    ]
```

ctypes 自动处理 x64 对齐（HMONITOR 为指针，8 字节对齐）。

## 输出格式

```
HDR 检测报告
========================================
显示器 1:
  设备名: \\.\DISPLAY1
  友好名: Dell U2720Q
  主显示器: 是
  桌面区域: (0, 0) - (3840, 2160)
  连接到桌面: 是
  HDR 已开启: 是
  每通道位数: 10
  色彩空间: RGB_FULL_G2084_NONE_P2020 (16)
  最大亮度: 350.0 nits
  最小亮度: 0.1 nits
  最大全帧亮度: 350.0 nits
----------------------------------------
显示器 2: ...
========================================
汇总: 检测到 2 台显示器，其中 1 台开启了 HDR
```

## 错误处理

| 场景 | 处理 |
|---|---|
| `CoInitializeEx` 失败（返回 RPC_E_CHANGED_MODE） | 打印错误，退出码 1 |
| `CreateDXGIFactory1` 失败 | 打印错误信息，退出码 1，`finally` 中 `CoUninitialize` |
| `EnumAdapters1`/`EnumOutputs` 返回 `DXGI_ERROR_NOT_FOUND` | 正常停止枚举（不是错误） |
| `QueryInterface(IDXGIOutput6)` 失败 | 跳过 HDR 信息，提示"不支持 HDR 检测（需 Win10 1703+）" |
| `GetMonitorInfo` 失败 | 跳过主显示器标识，其余信息正常输出 |
| `EnumDisplayDevices` 失败 | 回退使用 GDI 设备名作为标识 |
| 无显示器连接到桌面 | 打印"未检测到活动显示器" |
| 任何异常退出路径 | `try...finally` 确保：已获取的 COM 对象按逆序 Release，`CoUninitialize` 被调用 |

## 验证方式

1. 用户手动开启 HDR -> 运行脚本 -> 确认 `HDR 已开启: 是`
2. 用户手动关闭 HDR -> 运行脚本 -> 确认 `HDR 已开启: 否`
3. `ColorSpace` 值变化：`RGB_FULL_G22_NONE_P709 (0)` <-> `RGB_FULL_G2084_NONE_P2020 (16)`
4. 运行命令：`uv run python debug_tools/check_hdr.py`

## 依赖

- `ctypes`（Python 标准库）
- `pywin32`（项目已有依赖，用于 `win32api.GetMonitorInfo` 和 `win32api.EnumDisplayDevices`）
- 无新增依赖

## 未来扩展（不在本次范围）

- 集成到主程序：启动时检测 HDR，在 UI 中警告用户
- 运行时临时关闭 HDR：通过 Windows API 或注册表临时关闭，任务结束后恢复
- 自动检测并提示用户关闭 HDR 的 UI 对话框
