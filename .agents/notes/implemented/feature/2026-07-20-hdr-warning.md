# Agent Note: 任务启动时提示游戏所在显示器已开启 HDR

Status: implemented

## 问题

AALC 用 GDI 截图做模板匹配。Windows HDR 开启时，截图像素颜色可能与 SDR 下的模板不同，匹配相似度下降，用户看到的是识别失败而不是环境原因。HDR 状态按显示器区分，主显示器的状态不能代表游戏所在显示器。

## 决策

[hdr.py](../../../../module/game_and_screen/hdr.py) 通过 ctypes 调用 DXGI：初始化 COM 套间，枚举适配器与输出，查询 `IDXGIOutput6::GetDesc1()`，所有 COM 对象在成功和失败路径都释放。仅当 `ColorSpace == 12`（`DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020`）时判定为 HDR；`BitsPerColor` 和亮度字段只作诊断，因为 8-bit+FRC 面板在 HDR 下可能报告 8bpc，SDR 面板也可能报告 10bpc。该模块不读取 `cfg`、不依赖 PySide6。[check_hdr.py](../../../../debug_tools/check_hdr.py) 调用同一模块输出全部显示器报告，避免调试工具与正式功能的枚举值或结构体布局分叉。

[script_task_scheme.py](../../../../tasks/base/script_task_scheme.py) 在顶层任务首次 `init_game()` 之后、任何截图、识别或点击之前调用 `_warn_if_game_monitor_hdr_enabled()`：

- 模拟器模式或 `experimental_hdr_warning` 关闭时不检测；该开关默认开启，位于设置页“实验性内容”。
- 用 `MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)` 取得游戏窗口所在显示器后查询。
- 句柄无效、DXGI 失败或找不到输出时记录日志并继续任务；检测失败不报告为 HDR 开启。
- 已开启 HDR 时，任务线程创建 `threading.Event` 并发出 `mediator.hdr_warning`，主窗口显示模态警告，在 `finally` 中设置事件。任务线程以短周期等待并调用 `auto.ensure_not_stopped()`；停止时发出 `hdr_warning_clear`，主窗口只关闭事件身份匹配的 HDR 弹窗。
- 重试、回主界面和恢复流程中再次调用 `init_game()` 不重复提示。

## 曾考虑的替代方案

**按主显示器或任一显示器的 HDR 状态判断。** 多显示器时游戏可能位于非主显示器，会误报或漏报；因此按游戏窗口所在的 `HMONITOR` 查询。

**把 `BitsPerColor` 或亮度作为判定条件。** 面板报告的位深与 HDR 开关不一一对应，只保留 `ColorSpace` 判定。

## 后果

用户在识别受 HDR 影响前得到一次说明，可在设置中关闭提示。提示需要用户确认后任务才继续；AALC 不自动开关 Windows HDR，也不检测模拟器所在显示器。

[test_check_hdr.py](../../../../tests/test_check_hdr.py)、[test_hdr_warning_gate.py](../../../../tests/test_hdr_warning_gate.py) 和 [test_hdr_warning_ui.py](../../../../tests/test_hdr_warning_ui.py) 覆盖判定、资源释放、预检门、停止与弹窗配对。
