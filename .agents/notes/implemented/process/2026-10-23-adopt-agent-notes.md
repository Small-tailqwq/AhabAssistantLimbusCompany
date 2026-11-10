# Agent Note: AAALC 决策记录采用 Agent Notes

Status: implemented

## 问题

AAALC 由多个代理维护，项目规则、专项流程与历史设计承担不同职责。历史设计中的实现计划和当前代码会出现差异；长期决定需要可识别的状态、明确的归属及随实现更新的事实，才能避免重复分析或按旧提案修改代码。

## 决策

采用 [agent-notes-kit 的 3541d1b85f9ac7dca25346858eecbee049d97ffe](https://github.com/Small-tailqwq/agent-notes-kit/tree/3541d1b85f9ac7dca25346858eecbee049d97ffe)。[Python 门禁](../../../../scripts/agent_notes.py)保留该版本实现，使用项目现有 Python 运行时和标准库；本地入口为 `python scripts/agent_notes.py check`。

[配置](../../agent-notes.config.json)使用中文主语言 `zh`，无副本语言；格式启用日是 `2026-10-23`。保留 feature、bug-fix、simplification、architecture、process、testing 六类，生命周期由路径和状态行共同表达。

[根 AGENTS](../../../../AGENTS.md)负责触发入口，[agent-notes skill](../../../skills/agent-notes/SKILL.md)负责写作与生命周期操作。根 `CLAUDE.md` 引用根规则，skills 由 `.agents/skills/` 统一维护并按任务直接读取。Agent Notes 允许记录真实的落选方案，其他仓库文字仍描述当前状态。

[Agent Guidance CI](../../../../.github/workflows/agent-guidance.yml)执行笔记检查，完整获取 Git 历史，以 PR base 或 push 前提交检查封存记录。notes 内的 `.gitattributes` 固定 LF；通用指引检查跳过封存笔记，归档完整性由专门门禁检查。

`docs/` 的内容范围由 [文档规则](../../../../docs/AGENTS.md) 规定，提案和长期理由集中在 `.agents/notes/`。`forbiddenRoots` 包含 `docs/superpowers`。Python 更新协议与镜牢队列笔记保存在 `archived/architecture/`。

`proseLint` 使用模板默认值 `false`。笔记作者运行 `python scripts/agent_notes.py lint <笔记路径>`，逐条判定候选；格式与封存检查使用 `check`，文风候选不改变退出码。

## 曾考虑的替代方案

**继续只用历史设计目录。** 其中的计划语气和具体实现步骤需要读完整正文才能辨别状态；按生命周期组织笔记能直接区分当前决定与提案，同时保留有价值的理由。

**Node 门禁。** 构建和维护脚本已经使用 Python，标准库版本复用该环境。应用运行依赖 .NET。

**中英双语笔记。** 项目 skills 和维护规则使用中文，单语足以支持当前协作；双语会增加每次修改副本和 sidecar 的成本。

**批量迁移全部历史资料。** 旧实现的设计稿与运行报告不具备相同的长期记录价值。按主题核实实现和取舍后，只将仍有决策价值的内容纳入 notes。

## 后果

需要维护笔记的事实、取代关系和引用，并在修改 notes 时执行格式检查。笔记只用于现有载体未解释的长期理由，普通局部修复无需额外记录。

封存使历史内容保持稳定；活跃笔记负责当前依据。语言、分类和模板版本的变化同时更新配置与契约，改变采纳决定时使用新笔记取代。模板缺陷按契约的反馈约定提供可复现证据。
