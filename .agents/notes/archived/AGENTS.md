# 冻结归档

类别目录中的已封存文件是历史快照。禁止编辑、格式化、翻译、修复、删除或移动；当前事实写入活跃笔记。

归档只在每个语言文件的 `Status: implemented` 下一行插入 `Archived: YYYY-MM-DD`，笔记仍在活跃目录时用 `pair --write` 重新记录一次 sidecar，再移动笔记及其语言副本、sidecar，并更新入链。正文与出链保持原样。

按 [agent-notes skill](../../skills/agent-notes/SKILL.md) 执行 `uv run python scripts/agent_notes.py seal` 和 `uv run python scripts/agent_notes.py check`。封存清单只追加；通用文档检查跳过已封存笔记的格式、过时路径和出链。
