# 仓库目录

根目录承载 .NET 解决方案、公共构建配置和项目入口文档。

| 位置 | 用途 |
|---|---|
| `src/AALC.Core` | 业务规则与不可变配置 |
| `src/AALC.Runtime` | 生产流程、外部效果接口、配置和录制 |
| `src/AALC.Vision` | OpenCV/ONNX Runtime 视觉实现 |
| `src/AALC.Platform.Windows` | Windows 窗口、输入、截图与分身 |
| `src/AALC.Desktop`、`src/AALC.Cli` | Avalonia 与命令行入口 |
| `src/AALC.Mcp` | stdio MCP 服务，通过当前用户管道连接桌面端 |
| `src/AALC.CloneHost` | 独立 net48 RDP ActiveX 宿主 |
| `tests/AALC.Core.Tests` | 确定性 xUnit 测试 |
| `tests/screenshots` | 截图测试集的 JSON 定义，图片位于外部数据目录 |
| `scenarios` | 合成场景与配置示例 |
| `assets` | 图片与模型资源 |
| `scripts` | 当前构建、logo 生成、Agent 指引与 notes 校验 |
| `tools/diagnostics` | 独立的日志、录制和模型诊断工具 |
| `.agents/skills`、`.agents/notes` | 技能正文与长期决策记录 |

Python 旧版保存在 `ahab` 分支；当前 GitHub Actions 入口位于 `.github/workflows/`。

`.agents/skills/<name>/SKILL.md` 是技能唯一维护位置；Claude 通过根 `CLAUDE.md` 读取 `AGENTS.md` 中的路由。

本机产物分为：`artifacts/` 构建输出，`logs/` 诊断日志与人工截图，`data/local-archive/` 整理存档，`issues/` issue 原始证据。这些位置均被忽略。真实游戏录制、profile 和截图以 `AALC_DATA_ROOT` / `EvidencePaths` 为准，详见 [应用说明](application.md)。
