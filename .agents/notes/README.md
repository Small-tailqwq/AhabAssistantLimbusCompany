# Agent Notes

Agent Note 保存代码、测试和现有文档未能解释、但会影响后续工作的决策理由。项目采用中文单语；参数在 [agent-notes.config.json](agent-notes.config.json)，格式与封存由 `python scripts/agent_notes.py check` 检查。真实性、记录价值和入链由作者审阅。

模板来源为 [agent-notes-kit](https://github.com/Small-tailqwq/agent-notes-kit)，本地化选择见[采纳笔记](implemented/process/2026-10-23-adopt-agent-notes.md)，模板与门禁许可见 [LICENSE](LICENSE)。

<a id="layout-and-naming"></a>
## 目录与命名

路径为 `{lifecycle}/{class}/yyyy-mm-dd-topic-title.md`。日期取主题首次提出的日期；迁移时核对 Git 历史，不因状态变化而改日期。

- `proposed/`：实质性提案，尚未完成实现。
- `implemented/`：已实施的决策；路径、名称、默认值等事实随代码更新，决策改变用新笔记取代。详见 [implemented/AGENTS.md](implemented/AGENTS.md)。
- `rejected/`：已否决且仍能帮助避免重复错误的提案。
- `archived/{class}/`：已实施决策的冻结历史；详见 [archived/AGENTS.md](archived/AGENTS.md)。

目录即清单，不建立中央 `INDEX.md`。笔记之间及对源码的引用使用相对 Markdown 链接；移动时修复入链。

<a id="classification"></a>
## 分类

每条笔记只属于一个类别。增加类别时，同时修改 config、本表、对应的 `archived/<class>/`，并用 process 笔记说明决定。

| 类别 | 内容 |
|---|---|
| `feature` | 面向用户或模型的新能力 |
| `bug-fix` | 缺陷修复及事故暴露的缺口 |
| `simplification` | 减少代码、行为或使用入口 |
| `architecture` | 交付源码的模块关系、运行时概念与所有权 |
| `process` | 工具、CI、包管理、规范及代理工作流程 |
| `testing` | 测试设施和验证策略 |

<a id="when-to-write-one"></a>
## 何时记录

只有代码、测试、注释及当前文档未能承载、且后续贡献者可能重新推导或误改的长期理由才写笔记。机械编辑、局部 UI 调整、原因与修复直接可见的小缺陷、没有策略选择的依赖升级无需笔记。

同一决策只有一个活跃归属。已有笔记承载该决定时更新事实；改变决定时创建新笔记并双向链接。每条新笔记都在同次变更中搜索并判断同主题记录的取代关系，使用 [agent-notes skill](../skills/agent-notes/SKILL.md)。

完全被取代的 implemented 笔记可合并进当前归属后删除，但目标必须保留所有独有理由、真实替代方案、后果、必要验证和已知覆盖缺口，并修复全部入链。部分取代时两者继续活跃并保持剩余事实准确。

功能新增笔记合并到移除笔记前，须确认功能已从生产代码、配置、schema、持久化或传输格式、迁移和兼容处理中完整移除，当前文档和测试也不再将它作为受支持行为。目标保留原动机、移除理由、真实替代方案、失去的能力、重新引入条件与核验依据。移除一种实现、默认值或入口属于部分取代。

## 退役与归档

按未来决策价值判断，不以年龄、字数或配额清理：

- 仅描述小 UI 调整或机械变更的 implemented 笔记可删除；小改动中的命名、兼容、所有权或行为规则仍需保留。
- 仍约束未来改动的理由、兼容语义、安全规则或重新引入条件留在活跃区。
- 已完成、不再指导后续工作而仍有历史价值的 implemented 笔记可归档。
- proposed 不归档；不再推进的提案转为 rejected，写明真实原因。
- rejected 只在仍能防止有可能重现的错误时保留。

删除或移动须修复入链，并遵守根 AGENTS 的用户资产边界。已封存文件永久冻结，不能因文档清扫而删除。

归档时在 `Status: implemented` 下一行插入 `Archived: YYYY-MM-DD`；双语组在笔记仍处于活跃目录时重新记录一次 sidecar（`pair --write` 只接受活跃路径），然后移动整组，正文不变。`seal` 将原始字节的 SHA-256 追加到 [archived/manifest.json](archived/manifest.json)，`check` 拒绝变更、丢失、未封存文件或相对基线删除的封存记录。其他文档检查跳过封存文件及其出链；活跃文件可为引用历史而链接归档。

<a id="the-file-format"></a>
## 文件格式

开头固定为：

```markdown
# Agent Note: 标题

Status: implemented

## 问题
```

`# Agent Note: `、`Status:`、`Archived:` 和目录名保持英文。状态与目录一致；只有 rejected 带一行理由：`Status: rejected — 原因`。状态不含日期或括号，代码块外只出现一次。

正文以 `## 问题` 开始，章节名与 config 一致。允许插入必要的技术章节，代码块内标题不参与结构检查。

| 生命周期 | 必需章节（按顺序） |
|---|---|
| proposed | 问题、提案、曾考虑的替代方案、验收标准、风险 |
| implemented | 问题、决策、曾考虑的替代方案、后果 |
| rejected | 问题、提案、曾考虑的替代方案；其余保留提案时内容 |

implemented 用现在时描述当前实现；不保留“提案”“计划”“迁移计划”“验收标准”及其冒号变体。必要的测试、覆盖缺口等写为当前事实。

`## 曾考虑的替代方案` 只记录真正比较过的选项和理由，每项一段或一个三级标题；不补写想象。Agent Notes 可单独保存这些真实取舍，日常文档、注释与测试仍按根规则描述当前状态。

早于 `formatAdopted`、且替代方案无从考证的迁移笔记，可用以下注释替代该章节；新笔记不得使用：

```markdown
<!-- agent-note-format: alternatives-not-recorded (pre-format Agent Note) -->
```

proposed 转 implemented 时改写提案为当前决策，将验收标准和风险归入后果或现有验证事实；转 rejected 时只修改状态行并冻结正文。决策反转创建新笔记。

## 语言与副本

`primaryLanguage: zh`、`counterpartLanguages: []` 表示每条笔记一个中文文件。需要双语时明确修改项目约定、config 和契约；主文件 `foo.md`、副本 `foo.<lang>.md` 和 `foo.i18n.json` 构成一组。双方状态行相同、标题结构一一对应，语义等价。

修改双语笔记后，对照 diff 最小更新副本，确认语义一致，再运行 `python scripts/agent_notes.py pair --write <路径>`；路径相对 `.agents/notes/`。sidecar 按章节记录哈希，只检测修改是否登记，语义由审阅确认。`--all` 只用于明确的全量核对。切换语言模式不改写冻结归档。

## 检查与模板反馈

本地运行 `python scripts/agent_notes.py check`；接入 CI 时把 `AGENT_NOTES_BASE_REF` 设为 PR base SHA 或 push 前的提交。归档前运行 `seal`，然后运行 `check`。`python scripts/agent_notes.py lint` 列出改动笔记（相对 `AGENT_NOTES_BASE_REF`，默认 `HEAD`，含未追踪文件）的文风候选，并标出指向基线中不存在笔记的取代链接；`NOTE...` 或 `--all` 扩大范围，命中只是候选，退出码恒为 0。config 中 `proseLint` 为 `false`，`check` 不附带这些候选。

更新模板时比较采纳笔记固定的提交，合并规则与配置本地化，Python 门禁按来源文件更新。遇到模板缺陷时，记录来源提交、最小复现、预期与实际结果以及项目适配方式；向模板仓库反馈前查重。反馈不携带本地路径、配置、日志或未发布业务内容；发布反馈仍以当前任务授权为准。
