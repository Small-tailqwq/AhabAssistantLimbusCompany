# AAALC — Agent 指引

AAALC 是 Windows 桌面自动化项目，主线使用 .NET 10、Avalonia、SukiUI 与 CommunityToolkit.Mvvm。
`origin` → Small-tailqwq/AhabAssistantLimbusCompany；`upstream` → KIYI671/AhabAssistantLimbusCompany。

## 执行边界

- 在系统、开发者和工具权限内执行用户请求；Skill 不撤销已有授权，也不扩大任务范围。
- 已授权的可逆仓库工作直接完成。只有无法从现有证据解决、且实质影响结果或权限的歧义才询问；先完成独立部分。
- Skill 导致暂停、询问或未完成时，链接具体规则并引用原文，区分规则与自己的推断。
- 默认由主智能体完成；用户或适用的专门流程明确要求时才委派。
- 本文件是项目公共规则的唯一来源；目录级 AGENTS 只补充局部规则，CLAUDE.md 只转发到本文件。
- 保留未提交改动。日志、截图、配置、issue、未追踪文件及冲突是用户资产；移动、删除或覆盖前核对授权，不自行裁决 stash/merge 冲突。
- 提交信息使用中文。只修改任务需要的内容，不顺手清理其他警告。

## 目录与职责

| 目录 | 职责 |
|---|---|
| `AAALC.slnx`、`global.json`、`Directory.Build.props` | 解决方案、SDK 与公共构建设置 |
| `src/AALC.Core/` | 无 UI、模型或设备依赖的业务规则 |
| `src/AALC.Runtime/` | 任务编排、配置、观察与输入接口、录制和回放 |
| `src/AALC.Vision/` | 模板匹配、OCR、地图识别 |
| `src/AALC.Platform.Windows/` | Windows 窗口、截图、输入、桌面分身 |
| `src/AALC.Desktop/`、`src/AALC.Cli/` | 桌面和命令行组合入口 |
| `src/AALC.CloneHost/` | 独立的 .NET Framework 4.8 RDP 宿主 |
| `tests/`、`scenarios/` | xUnit、截图用例定义、离线流程场景 |
| `assets/` | 共享图片、模型和配置参考 |
| `scripts/`、`tools/diagnostics/` | 构建与文档维护脚本、诊断工具 |
| `docs/` | 当前版本文档；入口为 `docs/README.md` |
| `.agents/skills/`、`.agents/notes/` | 共享技能唯一来源、长期决策记录 |

构建产物放 `artifacts/`；本地整理存档放已忽略的 `data/local-archive/`。不要把截图、日志或临时脚本放在根目录。真实运行证据按 `EvidencePaths` 的数据根规则保存。

## 按需读取

技能统一位于 `.agents/skills/<name>/SKILL.md`，正文使用中文；代码符号、路径与命令保留原文。通过本文件发现技能的宿主直接读取对应文件。

- 自动化、视觉、任务生命周期、UI 或配置：[aalc-automation-practices](.agents/skills/aalc-automation-practices/SKILL.md)。
- 桌面界面动效：[desktop-ui-motion](.agents/skills/desktop-ui-motion/SKILL.md)。
- 桌面布局、按钮、文本与焦点：[desktop-ui-craft](.agents/skills/desktop-ui-craft/SKILL.md)。
- 界面极端数据检查：[ui-resilience](.agents/skills/ui-resilience/SKILL.md)。
- Issue、日志与卡死诊断：[analyze](.agents/skills/analyze/SKILL.md)。
- 截图或模板匹配重放：[replay-matching](.agents/skills/replay-matching/SKILL.md)。
- 发布：[canary-release](.agents/skills/canary-release/SKILL.md)。
- 代码审阅：[code-review](.agents/skills/code-review/SKILL.md)。
- 上游贡献或回流：[upstream-contribution](.agents/skills/upstream-contribution/SKILL.md)、[downstream-sync](.agents/skills/downstream-sync/SKILL.md)，按目标树语言和架构适配。
- 长期决策记录：[agent-notes](.agents/skills/agent-notes/SKILL.md)，遵循 [notes 契约](.agents/notes/README.md)。普通局部修复不自动写笔记。
- 指令与技能维护：加载宿主提供的 `agent-guidance-health`；只读取当前任务需要的 reference。

技能正文上限 180 行，本文件上限 150 行。文档维护遵循 [docs/AGENTS.md](docs/AGENTS.md)；实质提案和长期决策统一存放于 `.agents/notes/`，冻结 notes 只作历史证据。

## 核心约束

- Core 保持纯规则；外部效果通过 Runtime 的接口接入，Desktop/CLI 负责组合。
- 截图、识别、输入和等待传播 `CancellationToken`；长循环有界重试。取消后仍须释放按键、鼠标和窗口租约。
- 输入必须使用生产 `GameSession` / `GameWindow` 契约，保留帧编号、窗口所有权、时效与坐标检查。
- 同一窗口不重叠运行任务。停止按钮、Esc、CLI Ctrl+C 走协作取消；关闭桌面窗口最多等待 5 秒收尾。
- 运行时使用启动时的配置快照；持久化通过 `SettingsStore`，不覆盖用户配置。默认配置为数据根下 `profile/settings.json`。
- 图片保持 `assets/images/` 的语言、主题和资源键约定；OCR 默认目录为 `assets/models/ocr/`，允许现有配置或 CLI 参数指定外部模型。
- 模板验证走 `AALC.Vision` 的生产管线；截图回放与合成场景分别说明，不把合成场景当作实机验证。
- UI 更新走 Avalonia Dispatcher；颜色、间距与控件样式遵循 [界面设计](docs/ui-design.md)，不在页面复制主题值。
- Desktop 启动不主动连接游戏或初始化 OpenCV/ONNX Runtime，模型按任务需要加载。
- `AALC_DATA_ROOT`、截图与录制目录遵循 `RecordingStorage.cs`，不绕过非 C 盘及目录链接检查。

## 常用命令

在仓库根目录运行，SDK 版本以 `global.json` 为准：

```powershell
dotnet build AAALC.slnx -c Release
dotnet test tests/AALC.Core.Tests/AALC.Core.Tests.csproj -c Release
dotnet run --project src/AALC.Desktop -c Release
dotnet run --project src/AALC.Cli -c Release -- replay scenarios/mail-rewards.json
dotnet run --project src/AALC.Cli -c Release -- daily-replay scenarios/daily/daily-exp-thread-three.json
python scripts/build_dotnet.py full
python scripts/build_dotnet_logos.py
python scripts/check_agent_guidance.py
python scripts/agent_notes.py check
```

辅助脚本使用 Python 3.12+；.NET 构建和运行不需要 Python 虚拟环境。打包要求 OCR 模型、7-Zip 与 Windows VC++ 运行库，见 [构建说明](docs/build.md)。

## 验证与发布

- 按改动选择最窄且足够的构建、相关 xUnit 或离线场景。必要检查通过后，只有新改动、失败或具体未解决风险才扩大验证。
- 纯文档编辑只检查内容、引用与 diff；修改 AGENTS.md、CLAUDE.md 或 skills 时运行 `python scripts/check_agent_guidance.py`。修改 notes 时再运行 `python scripts/agent_notes.py check`。
- 不因 Skill 建议自动新增测试或检查基础设施。GUI、设备、实机和 E2E 检查按用户授权执行。
- 当前 CI 构建并测试 .NET 解决方案；本地发布入口为 `scripts/build_dotnet.py`。发布说明与 `CHANGELOG.md` 同步，外部写入按用户授权执行。
