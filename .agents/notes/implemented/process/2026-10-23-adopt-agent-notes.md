# Agent Note: AALC 决策记录采用 Agent Notes

Status: implemented

## 问题

AALC 由多个代理维护，项目规则、专项流程与历史设计承担不同职责。历史设计中的实现计划和当前代码会出现差异；长期决定需要可识别的状态、明确的归属及随实现更新的事实，才能避免重复分析或按旧提案修改代码。

## 决策

采用 [agent-notes-kit 的 1a5fab7c8db59789744cf97cbad6ab1bd9565553](https://github.com/Small-tailqwq/agent-notes-kit/tree/1a5fab7c8db59789744cf97cbad6ab1bd9565553)。[Python 门禁](../../../../scripts/agent_notes.py)保留该版本实现，只需 Python 3.9 及以上的标准库；本地入口为 `python scripts/agent_notes.py check`。

[配置](../../agent-notes.config.json)使用中文主语言 `zh`，无副本语言；格式启用日是 `2026-10-23`。保留 feature、bug-fix、simplification、architecture、process、testing 六类，生命周期由路径和状态行共同表达。

[根 AGENTS](../../../../AGENTS.md)负责触发入口，[agent-notes skill](../../../skills/agent-notes/SKILL.md)负责写作与生命周期操作。Claude 的本地入口继续引用根规则，skills 通过现有 `scripts/link_skills.py` 的目录联接或符号链接共享。Agent Notes 允许记录真实的落选方案，其他仓库文字仍描述当前状态。

本分支尚未接入 CI，笔记检查在本地运行；接入时完整获取 Git 历史，以 PR base 或 push 前提交检查封存记录。notes 内的 `.gitattributes` 固定 LF。

新增决策写入 notes。Python 版的历史设计已在 `ahab` 分支迁移为笔记，见[历史设计目录迁移](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/blob/ahab/.agents/notes/implemented/process/2026-10-29-retire-design-spec-directory.md)；本分支 `forbiddenRoots` 为空。历史材料不赋予任务执行权限。

## 曾考虑的替代方案

**继续只用历史设计目录。** 其中的计划语气和具体实现步骤需要读完整正文才能辨别状态；按生命周期组织笔记能直接区分当前决定与提案，同时保留有价值的理由。

**Node 门禁。** 采纳时项目运行与检查使用 Python，Python 版可复用现有环境，免去单独维护 Node 运行时。

**中英双语笔记。** 项目 skills 和维护规则使用中文，单语足以支持当前协作；双语会增加每次修改副本和 sidecar 的成本。

**批量迁移全部历史资料。** 资料中包含未追踪的分析、实验和不同阶段的设计。按主题核实当前实现后迁移，能保留证据且避免把旧计划直接认定为当前契约。

## 后果

需要维护笔记的事实、取代关系和引用，并在修改 notes 时执行格式检查。笔记只用于现有载体未解释的长期理由，普通局部修复无需额外记录。

封存使历史内容保持稳定；活跃笔记负责当前依据。语言、分类和模板版本的变化同时更新配置与契约，改变采纳决定时使用新笔记取代。模板缺陷按契约的反馈约定提供可复现证据。
