# Agent Note: AAALC 桌面分身的进程与宿主边界

Status: implemented

## 问题

Child Session 需要独立的 RDP ActiveX 宿主，窗口外观需要与 AAALC 一致。任务进程、界面进程与配置写入者必须有明确边界，避免分身和主窗口分别保存同一配置。

## 决策

宿主放在 [`src/AALC.CloneHost`](../../../../src/AALC.CloneHost/AALC.CloneHost.csproj)，目标框架 net48，由 `AALC.Desktop` 引用构建产物并复制到 `clone-host/`。宿主通过 `tool-set` 命令同步工具栏的声音与输入状态。

分身内进程是 `AAALC.exe --clone-worker`，在初始化 Avalonia 前分流，无窗口，用受限令牌运行。主程序是配置的唯一写入者：任务配置经文件交付，队伍轮换由主程序写回。

AAALC 的管道名与 Python 版不同，避免两边的宿主连错；启用标记和 HKCU 自启动抑制沿用 Python 版的路径和格式，任一方崩溃遗留的抑制都能恢复。实测 HKCU 策略拦不住 explorer，AAALC 另外写 HKLM 策略，并临时禁用登录触发的计划任务，两者用独立标记记录，Python 版不读这些标记。

清单保持 `asInvoker`，普通任务不提权。分身启动前检查权限，失败时不启动宿主，因为普通权限连接留下的僵尸会话只有注销 Windows 才能清除。

## 曾考虑的替代方案

- 在 Avalonia 窗口里用 `NativeControlHost` 承载 ActiveX：工具栏可以直接复用 XAML，但 AxHost 依赖 WinForms 消息预处理，键盘、焦点和输入屏蔽链路都没有实测过，这正是不能破坏的部分。
- 宿主改用 net10.0-windows WinForms：写法与其他项目一致，但自包含发布要附带 WindowsDesktop 运行时，依赖框架发布要求用户另装，且裁剪模式不可用。net48 是系统自带的，宿主只有一个小文件。
- 与 Python 版共用同一份宿主源码，用参数切换外观：能避免重复，但要在 C# 5 约束下维护两套工具栏，每次改动都要回归 Python 版。独立宿主将两套界面的维护边界分开。
- 用 Python 控制器驱动新宿主，或在分身内运行完整桌面窗口：前者违背产品运行不依赖 Python 的目标；后者多占内存和启动时间，而任务进度已经能显示在主窗口，用户通过分身窗口看到的是游戏本身。
- 随包发布 CLI 作为分身内进程：CLI 不在发布包内，参数也与桌面配置不同，要再维护一套任务组装。
- 分身内进程沿用 Python 版的最高权限：Steam 和游戏会被提权拉起，与主桌面的运行条件不同；受限令牌足够完成任务。

## 后果

分身使用随 Windows 提供的 .NET Framework 4.8 宿主和包内的 .NET 任务进程。分身内外运行同一套任务代码，配置只有一个写入者。

Windows 行为变化需要核对宿主的连接、键盘和窗口焦点。主窗口崩溃时宿主会注销分身，分身内的游戏随之关闭，运行中的任务不能接续。

`dynamic` COM 调用依赖内置 COM 互操作，裁剪发布需要显式开启，`scripts/build_dotnet.py` 已配置但尚未实测。验证入口见[桌面分身](../../../../docs/desktop-clone.md#验证范围)。音频实际播放、WMI 开启远程桌面和主程序持久化分身队伍轮换仍缺实机记录。
