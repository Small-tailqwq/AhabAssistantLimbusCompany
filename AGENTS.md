# AAALC — Agent 指引

AAALC 是用 C#、.NET 10、Avalonia 与 SukiUI 重写的 AALC。原 Python 项目保存在 `ahab` 分支；本分支只含 .NET 产品与其开发工具。`origin` → Small-tailqwq/AhabAssistantLimbusCompany。

## 执行

- 在权限边界内，用户明确指令优先于 Skill 的一般建议；已授权的可逆仓库内工作直接做到约定结果。
- 只有会实质改变结果、范围或风险的歧义才询问；先完成不受影响的部分。
- 与用户沟通使用中文；提交信息使用中文。

## 快速命令

```ps1
dotnet build dotnet/AAALC.slnx -c Release
dotnet test dotnet/tests/AALC.Core.Tests/AALC.Core.Tests.csproj -c Release
dotnet run --project dotnet/src/AALC.Desktop/AALC.Desktop.csproj -c Release
dotnet run --project dotnet/src/AALC.Cli/AALC.Cli.csproj -c Release -- <命令>
python scripts/agent_notes.py check
python scripts/link_skills.py
```

[dotnet/README.md](dotnet/README.md) 是功能、CLI 与阅读入口的总览；各流程说明在 `dotnet/docs/`。

## 项目现实

- Windows-only 桌面自动化。项目依赖方向：Core ← Runtime ← Vision／Platform.Windows ← Desktop／CLI；Core 不依赖 UI、模型和设备。
- 运行时读取资源仓库中的 `assets/images` 与 OCR 模型目录（设置页或 CLI 参数指定），这些资源不在本分支。
- `debug_tools/` 与 `scripts/` 中的 Python 脚本只是开发工具，产品运行不依赖 Python。

## 核心不变量

- 流程依次观察、决策、输入、重新观察；动作后不把预期界面当作事实。
- 取消协作传播；关闭窗口最多等待 5 秒收尾。
- 首屏不初始化游戏连接、OpenCV、ONNX Runtime 或图片目录。
- 配置写入独立 profile 的 `settings.json`，不导入或覆盖 Python 的 `config.yaml`。
- 运行记录、截图与学习数据写入非 C 盘数据根（默认 `D:\AALCData`，`AALC_DATA_ROOT` 可改），不进仓库。

## 用户资产安全

未追踪文件、日志、截图、配置快照和 stash/merge 冲突默认是用户资产。删除、移动、整体覆盖或清理前核对已有授权；不自行裁决冲突。

## Agent Notes

代码、测试和现有文档未解释的长期决策理由，在同一变更中写入 `.agents/notes/`，遵循[笔记契约](.agents/notes/README.md)与 [agent-notes skill](.agents/skills/agent-notes/SKILL.md)。每条新笔记都检查取代关系；`.agents/notes/archived/` 是冻结历史，不作为当前依据。修改 notes 后运行 `python scripts/agent_notes.py check`。

`.agents/skills/` 是 skills 的唯一来源；Claude Code 通过 `scripts/link_skills.py` 生成 `.claude/skills/` 链接。
