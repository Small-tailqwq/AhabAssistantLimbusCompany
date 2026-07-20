# 实验性 HDR 警告设计

日期：2026-07-19

## 目标

将已验证的 Windows HDR 检测集成到 AALC，作为默认开启的实验性功能。
在 PC 模式下，每次任务启动时检测游戏窗口所在显示器；如果该显示器已开启 HDR，
则在任何截图、识别或点击开始前暂停任务并显示警告。用户确认后继续任务。

模拟器模式不执行检测。用户可在设置页“实验性内容”中关闭该功能，关闭后不再提示。

## 范围

包含：

- 抽取可供正式代码与调试 CLI 共用的 HDR 检测模块
- 按游戏窗口所在 `HMONITOR` 查询 HDR 状态
- 新增默认开启的实验性配置与设置卡
- 新增主线程警告弹窗和任务线程确认门
- 补充相关单元测试、配置类型和 i18n 文案

不包含：

- 自动关闭或恢复 Windows HDR
- 模拟器显示器检测
- 将显示器亮度或 `BitsPerColor` 作为 HDR 判定条件
- 在一次任务运行中的重试/恢复流程重复提示

## 架构

### 可复用 HDR 模块

新建 `module/game_and_screen/hdr.py`，从 `debug_tools/check_hdr.py` 抽取：

- COM/DXGI 结构体与 IID
- COM 初始化、枚举和引用释放
- `DXGI_COLOR_SPACE_TYPE` 名称映射
- 显示器 HDR 信息数据结构
- 按指定 `HMONITOR` 查询显示输出的接口

核心接口：

```python
def get_monitor_hdr_info(hmonitor: int) -> HdrDisplayInfo | None:
    """返回指定 HMONITOR 的 HDR 信息；查询失败或找不到输出时返回 None。"""
```

该模块不读取 `cfg`，不依赖 PySide6，不发出 UI 信号，也不决定是否警告。

`debug_tools/check_hdr.py` 保留 CLI 格式化和全显示器报告能力，但改为调用该模块，
避免实验工具与正式功能出现不同的枚举值或结构体布局。

现有 CLI 的 `os._exit()` 是早期 ctypes/结构体错误阶段的临时规避。当前修正后的代码已经通过
`raise SystemExit(main())` 正常退出验证，因此抽取时恢复常规 `sys.exit(main())`，正式 GUI 与
CLI 均不得依赖跳过 Python 清理流程的强制退出。

### HDR 判定

仅当当前输出的：

```text
ColorSpace == DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020 == 12
```

时判定 HDR 已开启。`BitsPerColor`、`MinLuminance`、`MaxLuminance` 和
`MaxFullFrameLuminance` 只作为诊断信息，不参与判定。

### 游戏显示器定位

任务完成 `init_game()` 后已有有效游戏窗口句柄。通过：

```python
win32api.MonitorFromWindow(
    screen.handle.hwnd,
    win32con.MONITOR_DEFAULTTONEAREST,
)
```

取得游戏窗口所在显示器，再调用 `get_monitor_hdr_info(hmonitor)`。
不以主显示器或所有显示器的 HDR 状态替代游戏窗口所在显示器。

## 运行流程

在 `tasks/base/script_task_scheme.py::script_task()` 中：

1. 调用 `init_game()`，确保游戏已启动并取得窗口句柄。
2. 若为模拟器模式，跳过 HDR 检测。
3. 若 `experimental_hdr_warning` 为 `False`，跳过 HDR 检测。
4. 查询游戏窗口所在显示器。
5. 查询失败或未开启 HDR，继续任务。
6. 若已开启 HDR，创建 `threading.Event` 并发出专用 `mediator.hdr_warning` 信号。
7. 任务线程以短周期等待事件，同时调用 `auto.ensure_not_stopped()`。
8. GUI 显示模态警告；用户关闭弹窗后在 `finally` 中设置事件。
9. 任务线程继续 OBS 校验、截图、识别和点击。

检查只放在顶层 `script_task()` 的首次 `init_game()` 之后。重试、回主界面或恢复流程中
再次调用 `init_game()` 时不重复提示。

## 线程与停止

新增 mediator 信号：

```python
hdr_warning = Signal(object)
hdr_warning_clear = Signal(object)
```

信号参数为任务线程创建的 `threading.Event`。主窗口槽函数负责显示文案：

```python
def show_hdr_warning(self, acknowledged_event):
    try:
        MessageBoxWarning(...).exec()
    finally:
        acknowledged_event.set()
```

任务线程等待逻辑不做无限阻塞调用，而是循环 `event.wait(short_interval)` 并调用
`auto.ensure_not_stopped()`。因此用户在弹窗显示期间关闭 AALC 或请求停止时，任务线程
仍能沿现有 `userStopError` 路径退出。

主窗口槽发生异常时也必须释放事件，避免任务线程永久等待。
HDR 弹窗复用主窗口现有 `_current_warning_box` 引用，同时记录
`_current_hdr_warning_event`。任务线程若在等待期间因停止请求退出，则在 `finally` 中发出
专用 `mediator.hdr_warning_clear(event)`。GUI 仅在 event 与当前 HDR 弹窗的 event 身份一致时
关闭弹窗，避免误关其他警告；弹窗槽的 `finally` 随后设置确认事件。

## 配置与设置页

新增配置：

```yaml
experimental_hdr_warning: True
```

同步修改：

- `assets/config/config.example.yaml`
- `module/config/config_typing.py`
- `app/setting_interface.py`

设置卡位于“实验性内容”分组：

- 标题：`HDR 检测警告`
- 说明：`任务启动时检测游戏所在显示器的 HDR 状态；开启 HDR 时提示可能发生图像识别问题`
- 默认值：`True`

配置加载会将用户配置与 `config.example.yaml` 默认值合并，因此旧用户配置没有该字段时
也会默认开启。用户关闭开关后，现有 `SwitchSettingCard -> cfg.set_value()` 路径将其持久化。
不直接修改用户 `config.yaml`。

## 警告文案

标题：

```text
检测到 HDR 已开启
```

正文：

```text
检测到游戏所在显示器已开启 HDR。开启 HDR 可能导致图像识别问题；如果运行中遇到识别异常，请先关闭 Windows HDR 后重试。

如果不想再看到本通知，请在“设置 > 实验性内容”中关闭“HDR 检测警告”。
```

使用现有 `MessageBoxWarning`，确认按钮继续显示“我已了解以上信息”。文案在 GUI 层通过
`self.tr()` 管理，纳入现有翻译文件更新流程。

## 失败处理

| 场景 | 行为 |
|---|---|
| 模拟器模式 | 不调用 HDR API，直接继续 |
| 实验性开关关闭 | 不调用 HDR API，直接继续 |
| 游戏窗口句柄无效 | 记录 warning，继续任务 |
| COM/DXGI 初始化或枚举失败 | 记录 warning/debug，继续任务 |
| 找不到匹配 `HMONITOR` | 记录 debug，继续任务 |
| HDR 未开启 | 不提示，继续任务 |
| HDR 已开启 | 弹窗并等待用户确认 |
| 弹窗槽异常 | 记录错误，并在 `finally` 中释放等待事件 |
| 等待期间停止任务 | `auto.ensure_not_stopped()` 抛出 `userStopError`；等待逻辑发出 `hdr_warning_clear(event)` 关闭对应弹窗，再沿现有收尾路径退出 |

检测属于提醒功能，不得因检测失败阻止任务运行，也不得将查询失败误报为 HDR 开启。

## 测试

### HDR 模块

- `ColorSpace=12` 判定为 HDR
- `ColorSpace=0` 判定为 SDR
- 只返回指定 `HMONITOR` 的输出
- 找不到输出时返回 `None`
- COM 工厂、adapter、output 和 output6 在成功与失败路径均释放
- CLI 继续输出全部显示器信息
- CLI 使用正常 `sys.exit(main())` 退出且不崩溃

### 任务预检门

- 模拟器模式跳过检测
- `experimental_hdr_warning=False` 时跳过检测
- 无有效窗口或查询失败时继续任务
- PC + HDR 时发出 `hdr_warning` 并等待确认
- 事件确认后继续任务
- 等待期间停止请求能够中断，不产生永久等待
- 等待期间停止后会主动关闭 HDR 弹窗
- 一次顶层任务启动只检查一次

### GUI 与配置

- HDR 弹窗关闭后事件被设置
- 弹窗执行异常时事件仍被设置
- 缺失配置字段时默认值为 `True`
- 设置卡读取并持久化 `experimental_hdr_warning`
- 新文案进入翻译文件

### 验证命令

```powershell
uv run python -m py_compile <changed Python files>
uv run ruff check <changed Python files>
uv run python -m unittest <relevant test modules> -v
uv run python scripts/check_i18n.py --update
uv run python debug_tools/check_hdr.py
```

最后在 Windows 实机上分别关闭、开启 HDR 各运行一次，并确认警告只依据游戏窗口所在显示器。
