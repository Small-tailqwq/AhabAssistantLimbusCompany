# 冻结归档

类别目录中的已封存文件是历史快照。禁止编辑、格式化、翻译、修复、删除或移动；当前事实写入活跃笔记。

归档只移动已实施笔记及其语言副本、sidecar，在每个语言文件的 `Status: implemented` 下一行插入 `Archived: YYYY-MM-DD`，并更新入链。正文与出链保持原样。双语笔记须在移动前、加入归档行后重新记录 sidecar。

按 [agent-notes skill](../../skills/agent-notes/SKILL.md) 执行 `uv run python scripts/agent_notes.py seal` 和 `uv run python scripts/agent_notes.py check`。封存清单只追加；通用文档检查跳过已封存笔记的格式、过时路径和出链。
