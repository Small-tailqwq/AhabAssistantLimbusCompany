# AAALC

<img src="src/AALC.Desktop/Assets/Logo.png" alt="AAALC Logo" width="112" />

AAALC，即 AI 驱动的 AALC，是使用 .NET 开发的新版 AALC。

Windows 桌面入口使用 .NET 10、Avalonia 12.0.3、SukiUI 7.0.1 和 CommunityToolkit.Mvvm。提供日常任务、镜牢、运行监控、工具箱（含单独领取邮件与截图）、邮件场景回放与设置。启动时不初始化游戏连接、OpenCV 或 ONNX Runtime；模板与 OCR 模型在任务需要时加载。

## 运行

在仓库根目录执行：

```powershell
dotnet run --project dotnet/src/AALC.Desktop/AALC.Desktop.csproj -c Release
dotnet run --project dotnet/src/AALC.Cli/AALC.Cli.csproj -c Release -- daily-replay dotnet/scenarios/daily/daily-exp-thread-three.json
dotnet run --project dotnet/src/AALC.Cli/AALC.Cli.csproj -c Release -- replay dotnet/scenarios/mail-rewards.json
dotnet test dotnet/tests/AALC.Core.Tests/AALC.Core.Tests.csproj -c Release
```

桌面设置位于 `%LOCALAPPDATA%/AALC.Next/settings.json`。`--profile <目录>` 指定独立配置目录；日常选项、资源路径和 OCR 模型目录保存在此目录，不导入或覆盖 Python 的 `config.yaml`。首次启动自动查找包含 `assets/images` 的仓库，设置页可修改资源位置、游戏语言、图像主题和模型目录。

## 日常任务

默认页以完整宽度显示滚动配置；开始任务后自动切换到“运行监控”页查看游戏画面与进度。经验和纺锤次数、编队、连战批次、模块兑换与奖励领取优先显示；经验四组、纺锤七组按日编队以及其他选项可折叠。编队支持编号或顺序选择，连战按每批上限拆分。例如经验 3 次、纺锤 3 次、每批最多 3 次时，分别执行一个三连战批次。

生产编排依次完成返回主页、采光与可选模块兑换、邮件及通行证奖励、可选狂气换体，最后确认主页。通行证中的赛季任务有独立开关，默认关闭；开启后按分区领取提示扫描滚动列表，详见[通行证领取](docs/pass-rewards.md)。狂气换体默认关闭，开启后按当日价格决定还可购买的档位，配置为不兑换、第一档、第二档或第三档。消费确认后等待价格或按钮状态变化，未确认变化时停止继续消费。战斗流程包含回合操作、事件选项与结算识别。

页面 OCR 使用原生 PP-OCRv4 检测与识别模型，执行文字检测、透视裁剪和识别。模型目录包含 `ch_PP-OCRv4_det_infer.onnx`、`ch_PP-OCRv4_rec_infer.onnx`；识别模型没有内嵌字符表时，还需 `ppocr_keys_v1.txt`。桌面仅检查 `assets/models/ocr` 和 `.venv/Lib/site-packages/rapidocr/models` 是否存在以填入默认路径，也可指定独立目录。

运行中禁用配置与重复启动。停止按钮和窗口内 Esc 取消任务，关闭窗口最多等待 5 秒收尾。CLI 支持 Ctrl+C。真实任务保存截图、`events.jsonl` 和 `result.json`；桌面和 CLI 默认写入 `D:\AALCData\recordings/{mirror,daily,mail}/时间戳`。可用 `AALC_DATA_ROOT` 指定其他本地非 C 盘目录，C 盘及指向 C 盘的目录链接会被拒绝。

## 镜牢配置

镜牢提供队伍轮换、罪人顺序、主题封面权重、商店与初始增益配置。星光沿用游戏的两行五列和三段选择；观测按体系、等级和八列目录位置选取，最多三件。独立编辑窗口应用到队伍草稿，主页面保存后写入 profile，详见[镜牢主题、奖励与事件](docs/mirror-rewards.md)。

## 工具箱

提供零协汉化版本检查与安装、Windows 新手提示关闭与恢复、游戏窗口截图。汉化工具独立保存游戏程序路径，查询 GitHub 实际发布附件，安装前保留原语言目录。新手提示工具读取本机存档密钥，修改前保留原始加密存档；两项写入操作均要求先退出游戏。截图保存到数据根的 `screenshots/`，可直接打开目录。操作复用停止按钮、Esc 和任务互斥，详见[工具说明](docs/tools.md)。

## CLI

```text
windows
daily <进程ID> <日常配置.json> [仓库] [OCR模型目录]
daily-battle <进程ID> <当前批次数> [仓库] [OCR模型目录]
capture <进程ID> <输出.png>
read-text <截图> <模型目录> [x y width height scale]
daily-replay <场景.json>
mirror --options <镜牢配置.json> [--pid <进程ID>] [--root <仓库>] [--models <OCR模型目录>]
mirror-replay --run <录制目录> [--vision <资源仓库>] [--models <OCR模型目录>]
screenshot-test [--suite <用例.json>] [--data <非C盘测试集目录>] [--root <仓库>] [--models <OCR模型目录>] [--filter <用例ID片段>]
replay <场景.json>
mail <进程ID> [仓库]
```

命令通过 `dotnet run --project dotnet/src/AALC.Cli -c Release -- <命令及参数>` 调用。`daily` 读取 `DailyOptions` JSON，字段不区分大小写；`daily-battle` 只继续已经进入的当前批次，不选关、不选择编队、不开启新批次。恢复前需从已有记录确认当前批次数，参数范围为 1–10。`capture` 只读取截图，不发送输入，同样遵守窗口所有权。`read-text` 的可选区域使用原图像素坐标。

## 阅读入口

| 问题 | 实现 |
| --- | --- |
| 日常编排、停止与超时 | [日常流程](docs/daily-flow.md)、`src/AALC.Runtime/Daily/DailyRunner.cs`、`GameSession.cs` |
| 镜牢编排、配置和队伍轮转 | [镜牢流程](docs/mirror-flow.md)、`src/AALC.Runtime/Mirror/MirrorRunner.cs` |
| 镜牢图谱和真实录制回放 | [地图与回放](docs/mirror-route.md)、`src/AALC.Runtime/Replay/MirrorScenario.cs` |
| 邮件观察与决策 | [邮件流程](docs/mail-flow.md)、`src/AALC.Core/Features/Mail/MailFlow.cs` |
| 离线动作契约 | [场景契约](docs/scenarios.md) |
| 原图识别回归与真实视觉回放 | [截图回归](docs/screenshot-regression.md)、`tests/screenshots/mirror.json` |
| 模板与 OCR | [视觉接口](docs/vision.md)、`src/AALC.Vision/PageTextReader.cs` |
| 截图、输入和新旧实例互斥 | [Windows 运行接口](docs/windows-runtime.md) |
| 页面、配置和实时画面 | `src/AALC.Desktop/MainWindow.axaml`、`MainViewModel.Daily.cs` |
| 汉化、新手提示和截图 | [工具箱](docs/tools.md)、`src/AALC.Desktop/MainViewModel.Tools.cs` |
| 重写范围及长期决策理由 | [Agent Note](../.agents/notes/proposed/architecture/2026-10-25-dotnet-rewrite.md) |

Core 不依赖 UI、模型和设备。Runtime 定义观察、输入和时钟接口并实现任务流程。Vision 与 Platform.Windows 实现外部效果，Desktop 和 CLI 组合这些实现。离线场景将人工观察交给生产运行器，以虚拟时间逐项核验动作。

## 桌面样式

侧栏和控件使用 SukiUI，页面共用主题与语义样式。窗口使用系统原生标题栏与最小化、最大化、关闭按钮。应用内 logo 为矢量资源，由 `scripts/build_dotnet_logos.py` 从 `Assets/*.svg` 生成。颜色、间距、字号与折叠动效集中在 `Styles/`，规则见[界面设计规范](docs/ui-design.md)。游戏窗口选择只在侧栏底部出现一次，画面监视只在“运行监控”页出现。日常和镜牢配置采用统一标签列、行高和间距，运行按钮固定在页面底部。镜牢提供 2×6 可视化选人与完整主题海报墙，图片按需解码并共享缓存，详见[镜牢编辑器](docs/mirror-rewards.md)。

## 启动测量

```powershell
uv run python debug_tools/dotnet_startup_baseline.py --entry python-main --repeat 5 --output logs/dotnet_milestone_debug/python-startup.json
uv run python debug_tools/dotnet_startup_baseline.py --entry desktop --executable dotnet/src/AALC.Desktop/bin/Release/net10.0-windows/AAALC.exe --repeat 3 --output logs/dotnet_milestone_debug/desktop-startup.json
```

每个样本启动新进程，系统文件缓存未清空。Avalonia 在窗口 `Opened` 后经过两次动画帧回调及 UI 空闲回调记录时间，报告包含测量边界与已加载程序集。Python 使用配置副本，在主窗口绘制后的 UI 回调记录时间；两个框架的回调边界不同。

参考机器为 Ryzen 7 7800X3D、系统报告 31.2 GiB 内存、Windows 11 build 26300、.NET SDK 10.0.402。2026-10-25 M2 在游戏运行环境中的三个首屏样本为 1.709、1.659、1.711 秒，首屏未加载 Vision/ONNX Runtime。这三个样本均超过 1.5 秒初始预算，未测量重启系统后的首次运行。

此前 Python 主界面三个样本为 9.98、4.05、4.08 秒，监听器首次哈希扫描为 14.43 秒。此前较小桌面任务页的 20 次启动为 1.343～1.478 秒，中位数 1.374 秒；测量记录位于本地 `logs/dotnet_milestone_debug/avalonia-task-startup-20.json`。这些记录对应各自的页面与运行环境。

## 当前验证范围

自动化回归覆盖邮件规则、日常批次与编队、战斗和事件、模块与奖励消费边界、取消与超时、中文服务器错误重试，以及邮件、日常和镜牢场景验收。镜牢还覆盖同帧寻路、主题/奖励、商店和完成领取后的队伍轮转。日常合成场景包含经验 3 次加纺锤 3 次的生产编排，以及经验入口失败后不继续纺锤的路径。

实机邮件的完整空邮箱路径、领取与确认、停止按钮和 Esc 已验证，记录见 [邮件流程](docs/mail-flow.md#实机记录)。M2 在 1280×720 中文游戏窗口上分段完成最右侧经验三连战、最高等级纺锤三连战、任务与通行证奖励、三档狂气换体及模块转换，详见 [日常实机记录](docs/daily-flow.md#实机记录)。截图调用方等待上限为 15 秒。普通镜牢已通过修复后续跑完成五层首领与领奖，当前截图回归包含442帧实机视觉及动作回放。完整日常和镜牢从头到尾无人干预的运行、英文游戏、模拟器和 OBS 后端、发布更新仍属于后续验证或实现范围。
