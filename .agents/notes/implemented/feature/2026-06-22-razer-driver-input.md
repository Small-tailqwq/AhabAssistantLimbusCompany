# Agent Note: 雷蛇驱动输入与罗技后端并列且互斥

Status: implemented

## 问题

罗技后端通过厂商内核驱动发送键鼠输入，绕开 Windows 标准输入栈；没有罗技设备与 G HUB 的用户无法使用这条通道。雷蛇设备配合 Synapse 3 的 `RZCONTROL` 驱动可以提供同类输入，但设备枚举、结构体和键码都与罗技不同。

## 决策

[RazerInput](../../../../module/automation/input_handlers/razer.py) 与 [LogitechInput](../../../../module/automation/input_handlers/logitech.py) 是并列的实验性后端，`KEY_BACKEND = "razer"`。两者通过同一组 DLL 导出交互：设备打开与关闭、移动、按键状态移动、三键按下、抬起、滚轮、键盘按下与释放、全部释放。雷蛇 DLL 由独立的 `Razer_driver-main` 工程编译，不在本仓库；缺少导出时报错提示用户更换为新编译产物。

雷蛇 DLL 的对接事实：在 `\GLOBAL??` 中枚举 `RZCONTROL*` 符号链接，以 `CreateFileW(GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE)` 打开，所有输入使用 IOCTL `0x88883020` 和 32 字节 `RzControl` 结构，`type` 区分鼠标（2）与键盘（1）。鼠标按键用位掩码，滚轮设置 `WHEEL` 标志并把 ±120 写入 `movement`；键名经 VK 与 HID Usage 转为 Razer MakeCode，方向键、Insert、Delete、Home、End、PgUp、PgDn、Win 附加 `KEY_E0`。码表来源为 razerctl v0.5.1。

- 配置字段为 `lab_mouse_razer`（默认关闭）、`razer_dll_path`、`razer_bionic_trajectory`（默认开启），见 [config_typing.py](../../../../module/config/config_typing.py)。
- [automation.py](../../../../module/automation/automation.py) 在罗技分支之后选择雷蛇后端，并延迟导入；DLL 在首次实际输入时加载。两者同时开启时罗技优先。
- 仿生轨迹与点击偏移对两个硬件后端共用同一判断，分别由各自开关控制。
- [设置页](../../../../app/setting_interface.py) 的实验性内容中，打开一个硬件后端会关闭另一个。

## 曾考虑的替代方案

**把罗技与雷蛇的共用逻辑抽取成公共基类。** 仿生轨迹、状态观测和焦点检测在两个类中各自持有，代码重复但互不影响；当时以最小改动接入第二个后端，没有为两个实现做抽象。

## 后果

用户可在罗技与雷蛇之间择一，后端缺 DLL 或驱动时只在实际输入时失败。两个类的共用逻辑需要同步修改。

IOCTL 码、MakeCode 码表和“按住按键时移动”的语义依赖 Synapse 版本，随驱动更新可能变化；滚轮 delta 的编码依据 Windows raw input 惯例推断。必须安装 Synapse 3 且存在 `RZCONTROL` 符号链接；真实设备行为只能手动验证。
