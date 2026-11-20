<div align="center">

<img src="src/AALC.Desktop/Assets/Logo.png" alt="AAALC" width="112" />

# AAALC

AI 驱动的 AALC · Limbus Company 桌面自动化

AI-powered ~~Ahab~~ Angela Assistant for Limbus Company

Windows x64 / macOS（安卓模拟器） · .NET 10 · Avalonia · SukiUI

[功能与运行说明](docs/application.md) · [文档索引](docs/README.md) · [反馈问题](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/issues)

</div>

AAALC 是基于 [AALC](https://github.com/KIYI671/AhabAssistantLimbusCompany) 开发的实验性非官方 fork，由人提出需求与验证结果，AI 参与实现。当前桌面提供日常、镜牢、运行监控、桌面分身、工具箱和设置；CLI 提供离线场景、截图与录制回放。

自动化可能因游戏版本、画面或环境变化失败。首次运行请使用少量任务并观察日志；停止按钮或窗口内 Esc 请求停止，CLI 使用 Ctrl+C。

## 从源码运行

安装对应平台的 .NET 10 SDK（版本见 [global.json](global.json)），在仓库根目录执行：

```powershell
# Windows 使用 AAALC.slnx；macOS 使用 AAALC.macOS.slnf
dotnet run --project src/AALC.Desktop -c Release
```

macOS 使用[安卓模拟器入口](docs/application.md#macos-安卓模拟器)：可连接本机 ADB、保存截图、领取邮件；不启动 Steam 或运行日常、镜牢战斗。Windows 继续使用原生窗口。

游戏图片位于 `assets/images/`。OCR 模型放在 `assets/models/ocr/`，所需文件见 [模型说明](assets/models/ocr/README.md)，也可在 Windows 设置页指定已有模型目录。配置默认写入数据根下的 `profile/settings.json`；录制与截图的数据位置见 [运行说明](docs/application.md)。

```powershell
dotnet test tests/AALC.Core.Tests/AALC.Core.Tests.csproj -c Release
dotnet run --project src/AALC.Cli -c Release -- replay scenarios/mail-rewards.json
dotnet run --project src/AALC.Cli -c Release -- daily-replay scenarios/daily/daily-exp-thread-three.json
```

离线场景不连接游戏。截图回归需要本地测试集，见 [截图回归](docs/screenshot-regression.md)。

## 仓库结构

```text
AAALC.slnx                 解决方案
global.json                SDK 版本
Directory.Build.props      公共构建设置
src/                       Core、Runtime、Vision、Windows、Desktop、CLI、CloneHost
tests/                     xUnit 与截图用例定义
scenarios/                 离线场景和配置示例
assets/                    图片、模型和共享资源
scripts/                   构建、资源生成和文档维护
tools/diagnostics/         日志、录制与模型诊断
docs/                      当前版本文档
.agents/                   skills 与决策 notes
artifacts/                 本地构建产物（忽略）
```

详细职责见 [目录说明](docs/repository-layout.md)。Agent 规则以 [AGENTS.md](AGENTS.md) 为准，`CLAUDE.md` 转发到同一入口，技能统一存放在 `.agents/skills/`。

## 打包与版本

Windows 使用 `python scripts/build_dotnet.py full`，macOS 使用 `python3 scripts/build_macos.py`；命令、Intel 视觉库依赖及产物见 [构建说明](docs/build.md)。

Python 旧版保存在 `ahab` 分支。

完整日常与镜牢无人干预运行、英文游戏、模拟器和 OBS 后端、自动更新的当前范围见 [功能与验证情况](docs/application.md#当前验证范围)。版本记录见 [CHANGELOG.md](CHANGELOG.md)。

## 来源与许可

源自 [AhabAssistantLimbusCompany](https://github.com/KIYI671/AhabAssistantLimbusCompany)。代码许可见 [LICENSE](LICENSE)，第三方依赖、字体和游戏素材保留各自权利，见 [来源与致谢](docs/credits.md)。本项目与游戏官方无关联。
