# 构建与打包

## 构建

使用 Windows x64 和 [global.json](../global.json) 指定的 .NET SDK，在仓库根目录运行：

```powershell
dotnet build AAALC.slnx -c Release
dotnet test tests/AALC.Core.Tests/AALC.Core.Tests.csproj -c Release
```

桌面主程序为 `src/AALC.Desktop/bin/Release/net10.0-windows/AAALC.exe`；RDP 宿主由 net48 项目单独构建并复制到 `clone-host/`。

## 打包

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
