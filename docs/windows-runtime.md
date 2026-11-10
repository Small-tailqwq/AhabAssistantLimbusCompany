# Windows 运行接口

`AALC.Platform.Windows.GameWindow` 为选定的 `LimbusCompany` 窗口提供客户区截图、鼠标点击、按键与拖动。它通过 `IScreenCapture`、`IGameInput` 和 `IGameInput` 接入邮件及日常运行器。

## 输入

输入使用窗口消息和真实光标定位，不使用 `SendInput`。窗口消息通过带 1500 ms 时限的 `SendMessageTimeout` 发送，期间阻止本线程处理其他窗口消息，避免关闭重入；发送超时直接报告，不自动重发。

鼠标点击保存屏幕光标位置，通过 `ClientToScreen` 换算并设置真实光标，再发送 `WM_ACTIVATE`、`WM_LBUTTONDOWN`、`WM_LBUTTONUP`，按钮消息使用客户区坐标。按住 40 ms，抬起后停留 10 ms。原光标在游戏客户区外时恢复原位；在客户区内时停到 `(1,1)`，避免再次触发卡片悬停遮罩。抬键及停留位于 `finally`，外层 `finally` 完成光标处理。

按键支持 Esc、Enter、P 和 Space。激活窗口后发送带扫描码的 `WM_KEYDOWN`，等待 15 ms，再在 `finally` 发送 `WM_KEYUP`。拖动在客户区起点按下，按约 10 ms 步长移动真实光标，到达终点后停留至少 500 ms，再在 `finally` 抬起并按点击的同一规则处理光标。拖动时长限定为大于零且不超过 5 秒。取消令牌会中断按住与移动等待，释放输入仍会执行。

系统拒绝 `SetCursorPos` 时报告 `GameInputBlockedException`，输入视为未发送；恢复光标失败不覆盖原异常。镜牢运行器每 15 秒从当前页面重新接手，最多 20 次；游戏不重启。

三种输入共用同一执行槽，拒绝重叠输入。输入前检查窗口进程、句柄、客户区尺寸、最新成功截图编号及五秒有效期；点击与拖动还检查目标范围。最小化窗口需要先由用户恢复。消息发送或光标设置失败会向运行器报告异常。

自动操作期间，用户移动鼠标或点击界面可能干扰输入；AAALC 窗口获得键盘焦点时可按 Esc 停止。

## 截图与停止

截图沿用 `module/automation/screenshot.py::ScreenShot.background_screenshot` 的 `PrintWindow(..., 3)`，输出客户区尺寸的 BGRA 像素。C# 使用负高度 DIB 获取从上至下的行顺序，并在原生调用结束后释放 GDI 对象。当前 C# 没有 OBS 截图后端。

原生截图在工作线程执行，调用方最多等待 15 秒。取消令牌可以立即结束调用方的等待，底层 `PrintWindow` 继续运行至返回。同一个实例拒绝重叠截图。`Dispose` 先禁止新操作，待截图与输入的抬键、光标恢复结束后再释放所有权，窗口关闭无需等待原生调用。若原生调用一直不返回，所有权持续保留至进程退出。

`GameSession` 在观察、OCR、等待及输入边界检查取消和任务总时限，拒绝旧观察帧。输入事件同步发布后、调用输入设备前再次核对时限和帧引用。网络等待有界；中文服务器错误弹窗中的可用重试按钮最多每 5 秒点击一次，持续不可用 15 秒则结束。消费流程在确认后等待价格或按钮变化，不通过重新执行整段任务恢复。邮件运行器保留独立的状态机与 30 秒时限。

桌面运行中禁用配置和重复启动，停止按钮与 Esc 请求协作式取消；关闭窗口最多等待 5 秒收尾。CLI 使用 Ctrl+C 取消。输入保护分析依据 `.agents/skills/limbus-input-safety/references/input-safety-analysis.md` 标注的 2026-07-30 版本，该版本的分析不作为当前游戏的安全保证。

## 与旧版互斥

真实运行时同时占有两种资源：

- `Local\AALC.Next.Game.<pid>` 命名信号量阻止新端重复接管同一游戏窗口。
- 独占监听 `127.0.0.1:62333`，兼容 `main.py` 的根实例单实例检测。端口被占用时拒绝开始真实运行；持有期间接受旧入口的探测连接，消费而不执行参数，随后启动的 Python 根实例因探测成功退出。回放不占用这些资源。

两个资源都保留到截图及输入清理结束。端口互斥按整个旧应用生效，即使旧版当前没有任务，也需要先退出旧版才能启动 C# 的真实任务。`capture` 不发送输入，但使用同一 `GameWindow`，遵守上述互斥与释放规则。

旧版 `main.py` 在导入与 UI 初始化之后才监听端口，存在已启动但尚未监听的窗口；直接导入运行、child session 等绕过根实例端口的入口也不能由这个固定端口完整约束。运行真实任务前应完成旧实例退出；互斥覆盖参与上述资源协议的实例。

## 桌面分身

任务可以在 Windows Child Session 中运行，`GameWindow` 的 `SetCursorPos` 只作用于分身桌面，不影响主桌面鼠标。截图、输入和上述互斥都由分身内进程执行，流程代码与主桌面相同。连接要求、进程划分和停止语义见[桌面分身](desktop-clone.md)。

## 命令与验证范围

```powershell
dotnet build src/AALC.Platform.Windows/AALC.Platform.Windows.csproj -c Release
dotnet run --project src/AALC.Cli -c Release -- windows
```

CLI 提供 `capture <进程ID> <输出.png>` 只读截图，以及 `daily <进程ID> <配置.json> [仓库] [OCR模型目录]`。`daily-battle <进程ID> <当前批次数> [仓库] [OCR模型目录]` 直接进入当前战斗的继续流程，只用于已有明确批次记录的恢复，不选择关卡或开始新批次。
