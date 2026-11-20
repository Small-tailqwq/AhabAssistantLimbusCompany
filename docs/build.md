# 构建与打包

## 构建

使用 Windows x64 和 [global.json](../global.json) 指定的 .NET SDK，在仓库根目录运行：

```powershell
dotnet build AAALC.slnx -c Release
dotnet test tests/AALC.Core.Tests/AALC.Core.Tests.csproj -c Release
```

桌面主程序为 `src/AALC.Desktop/bin/Release/net10.0-windows/AAALC.exe`；RDP 宿主由 net48 项目单独构建并复制到 `clone-host/`。

## macOS 构建与发布目录

在 macOS 上使用同版 SDK，以下构建不引用 Win32 后端或 net48 RDP 宿主：

```sh
dotnet build AAALC.macOS.slnf -c Release
dotnet test tests/AALC.Core.Tests -c Release --no-build
python3 scripts/build_macos.py               # 构建本机架构
python3 scripts/build_macos.py --arch x86_64 # 从 Mac 交叉打 Intel 包
```

解压 `artifacts/publish/AAALC-osx-arm64.zip` 或 `AAALC-osx-x64.zip`，运行其中的 AAALC.app。两个包均自带 .NET，每个包仅含一个 CPU 架构；签名为本机 ad-hoc 签名，非 Developer ID 签名、公证或 App Store 发行。ADB 和模拟器由用户安装。**Intel 额外依赖**：OpenCV 的 x64 原生库链接 Intel Homebrew 的 `/usr/local/opt/libavif/lib/libavif.16.dylib`；截图、模板和 OCR 操作前需安装提供该 ABI 的 libavif。arm64 不需要它。

| 随轻量桌面包 | 按需使用独立 CLI，不随桌面包 | Windows 专属，不打入桌面包 |
|---|---|---|
| 主线 SukiUI 窗口、设置、运行监控与预览 | 邮件、日常和镜牢离线回放 | Win32、Steam、桌面分身和 RDP 宿主 |
| ADB 设备选择、截图、单击、取消 | 多模板匹配、截图回归、OCR 和模型 | Win32 输入、游戏安装和本地文件工具 |
| 中英文及明暗邮件模板、邮件录制和合成回放 | 完整资源可指向源码仓库或外部目录 | Windows 专属页面、MCP、战斗用素材 |

需要完整 CLI 时执行 `dotnet run --project src/AALC.Cli -c Release -- <命令>`；它依赖 ONNX Runtime，但桌面包只引用模板视觉程序集。打包脚本对可达的业务代码和 .NET 运行时执行 IL 裁剪，去掉通用原生库的另一 CPU 切片后重新签名；配置和回放使用源生成 JSON 保留所需字段。脚本分别输出启动器、完整 .app、ZIP 的字节数。操作步骤见 [macOS 安卓模拟器](application.md#macos-安卓模拟器)。

## Windows 打包

`scripts/build_dotnet.py` 使用 Python 标准库，不需要旧版 Python 依赖。准备 Python 3.12+、7-Zip 和 Windows VC++ x64 运行库。[OCR 模型](../assets/models/ocr/README.md)随仓库提供。

```powershell
python scripts/build_dotnet.py full
python scripts/build_dotnet.py fdd
```

| 模式 | 要求 |
|---|---|
| `full` | 包含 .NET 运行时 |
| `fdd` | 目标机器安装 .NET 10 运行时 |
| `trimmed` | 包含运行时并裁剪程序集，需要单独验证桌面与分身功能 |

不传模式时依次构建所有模式。每个模式输出 `artifacts/publish/<mode>/AAALC/` 与 `AAALC-<mode>.7z`，再次构建会替换该模式的旧产物。

压缩包内包含 `AAALC.exe`、`app/`、`assets/` 和 `scenarios/`。必须完整解压，不能只复制 exe。`app/` 存放运行时和程序集，`app/clone-host/` 存放 RDP 宿主。模型来自 `assets/models/ocr/`。

当前 CI 构建与测试解决方案；发布目录和压缩包由本地打包脚本生成。

发布包另含 `mcp/AAALC.Mcp.exe`，用于 [Agent 连接](agent-control.md)。`full` 与 `trimmed` 包中的 MCP 自带运行时；`fdd` 包中的 MCP 使用机器上的 .NET 10。
