# Agent Notes 文风检查

读者只看当前仓库时，应能定位引用并核实事实。先保留必要事实，再删除会话叙述。

## 逐段判断

- 会话编号、审计阶段、草稿版本和“如上讨论”换成可访问的源码、文档或 issue 引用。
- “本次改动”“后来会”“维护者要求”写成项目当前机制。真实替代方案保留在专门章节。
- 工具运行记录、作者机器版本、检查清单和取代检索结果放在交付报告。
- 同次改动中新建的两份记录只描述最终职责，不把草稿迭代写成决策取代。
- implemented 使用现在时；未来工作放在有明确验收标准的 proposed 笔记。
- 每个事实只维护一处。行为、默认值、边界或测量值应能定位到源码、配置、命令或证据；删除重复转述。
- 检查含糊指代和范围：“相关文件”“必要时”等须写清对象与条件。通读长句，消除歧义和病句。
- 范围限定只在读者可能误解前句时保留；反例只在确实可能误用时比较。去掉没有新增事实的总结、口号和反复强调。
- Issue、已合并 PR、真实替代方案和“缺少 X 会导致 Y”的回归解释可以保留。

## 检索与交付

运行 `python scripts/agent_notes.py lint <笔记路径>`，路径相对 `.agents/notes/`；省略路径时检查相对 `AGENT_NOTES_BASE_REF`（默认 `HEAD`）改动及未追踪的活跃笔记。`--all` 检查全部活跃笔记。检索结果只是候选，逐条按上述标准保留或改写，并在交付中给出判定；不能以清零命中为目标删除事实。

其他文档可用以下同源表达式检索，将 `FILES` 替换为已修改的文件。机器标记与冻结归档保持原样。

```sh
# Scope disclaimers and unprompted negatives
rg -ni "(does not|doesn't|cannot|can't|won't) (prove|guarantee|mean|imply|ensure|verify|judge)|不能(证明|保证|判断|代表|说明)|不(意味着|代表|等于|保证)|并不|只(能)?说明|不配置|不提供|不涉及" FILES
# Straw-man contrasts and escalation pairs
rg -ni "not [^.]{1,40}, but|rather than|instead of|不是.*而是|而非|并非|不仅|既.*，也" FILES
# Announcements and closing summaries
rg -ni "worth noting|importantly|essentially|in short|值得注意|关键在于|本质上|总之|这样一来" FILES
# Session vantage, process reports, and author-machine facts
rg -ni "(^|[^A-Za-z])this (PR|change|note|session)([^A-Za-z]|$)|本次|这次|此次|本笔记|维护者(的)?(明确)?要求|用户要求|locally|本机|(Python|Node|node|python) ?v?[0-9]+\.[0-9]+\.[0-9]+" FILES
# Draft history
rg -ni "originally|previously|formerly|no longer|used to|the old |legacy|[0-9]+ original|最初|原先|原本|原来|此前|曾经|不再|改为|原 ?[0-9]|旧 ?\`" FILES
# Vague references
rg -ni "(^|[^A-Za-z])(etc\.|and so on|as needed|as appropriate|various|relevant (files|docs|code|parts|settings|rationale|changes))|相关(文件|文档|代码|配置|逻辑|内容|部分|理由)|相应的?(文件|文档|代码|配置|修改|处理)|某些|若干|一些|适当|必要时|等等|之类" FILES
```
