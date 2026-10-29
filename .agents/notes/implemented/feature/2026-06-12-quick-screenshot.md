# Agent Note: 快速截图不初始化游戏也不改动窗口

Status: implemented

## 问题

截图小工具的 `ScreenshotGet` 经 `init_game()` 取得画面，其中 `screen.set_win()` 会把游戏窗口调整到配置分辨率，游戏未运行时还会自动启动。用户只想记录当前窗口状态时，这些操作会改变要记录的画面；经 `auto.take_screenshot()` 截图还会覆盖运行中任务使用的 `auto.screenshot`。

## 决策

[QuickScreenshotGet](../../../../tasks/tools/screenshot_module.py) 是工具页截图卡片上的独立入口，与原截图工具并存：

- PC 模式只用 `screen.handle.init_handle()` 查找窗口；找不到窗口或窗口最小化时报错。不调用 `init_game()`、`set_win()`、`reset_win()` 或任何启动游戏的入口。
- 模拟器模式按 `simulator_type` 调用 `ScreenShot.mumu_screenshot()` 或 `ScreenShot.adb_screenshot()`，复用已有连接，没有连接时报错，不建立新连接。
- 截图直接调用 `ScreenShot`，不写入 `auto` 的截图缓存。
- 文件保存为 `screenshots/quick_screenshot_<%Y%m%d_%H%M%S_%f>.png`，时间精确到微秒，避免同一秒内互相覆盖。成功和失败分别通过 `on_saved_timestr`、`on_error` 信号交给 [工具页](../../../../app/tools_interface.py) 提示。

## 曾考虑的替代方案

**沿用 `ScreenshotGet` 的初始化路径。** 它能自动启动游戏、统一窗口分辨率，适合需要标准尺寸截图的场景，因此保留；但会调整窗口并写入 `auto` 缓存，不能用于记录当前状态，所以快速截图另设入口。

## 后果

快速截图得到的是窗口当前尺寸的画面，尺寸可能与模板基准不同；需要标准分辨率时使用原截图工具。游戏或模拟器未就绪时，快速截图只报错，用户需要自行启动。

[test_screenshot_tool.py](../../../../tests/test_screenshot_tool.py) 覆盖 PC 成功、无窗口、最小化与 MuMu 连接情况。
