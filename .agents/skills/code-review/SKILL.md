---
name: code-review
description: 审阅 AALC 未提交改动、暂存 diff、提交、分支、pull request、上游贡献或下游同步分支，确认缺陷、回归、自动化安全、i18n 漂移、上游风格不匹配、多余默认参数、一次性下划线变量与可维护性风险。用户要求审阅，或已授权贡献流程需要审阅时使用；复审限于实际改动与新证据。
---

# AALC 代码审阅

先确定目标，读足够源码来判断改动，逐条对照源码核实发现，最后给出基于证据的单一裁决。裸 diff 或通过测试都不构成充分的审阅上下文。

## 按目标缩放协议

| 目标 | 协议 |
|---|---|
| 未提交或暂存 diff | 就地审阅。跳过 finding ID、台账与完整报告模板。 |
| 简单提交、分支或局部复审 | 就地审阅，记录目标 SHA、发现和重要验证缺口。 |
| 多轮 PR 协调或需要跨审阅者追踪的贡献 | 加载 [references/pr-protocol.md](references/pr-protocol.md)，按实际轮次维护发现台账。 |

本地默认就地审阅；用户已要求委派且有独立领域可并行时使用 subagent。

## 确定目标

| 意图 | 需收集的证据 |
|---|---|
| 未提交工作 | `git status --short`、未暂存与暂存的 stat/diff |
| 暂存工作 | `git diff --cached --stat` 与完整暂存 diff |
| 提交 | `git show --stat <sha>` 与完整补丁 |
| 分支 | base/head SHA、提交列表、三点 stat 与完整 diff |
| Pull request | PR 元数据、base/head SHA、完整 PR diff、检查、历史审阅与未解决线程 |

未指定目标时，同时审阅暂存与未暂存改动。保留无关的用户工作，除非用户另行要求修复，否则不做任何编辑。

## 构建审阅上下文

1. 识别声明的意图与预期行为。
2. 读完整变更定义，而不只是补丁片段。
3. 读决定正确性的直接调用方、API 签名、配置 schema、测试或生成器。
4. 区分行为变更与既有代码。
5. 记录已执行的验证与仍开放的缺口。

超大 diff 按连贯子系统或行为分批。diff 大小决定分批深度，不决定哪些领域适用。

## 专项路由

当前主线是根 `src/` 中的 .NET 项目。按实际目标树选择检查，跨语言移植先核对两侧契约。

只有 diff 触及该领域时才选择它：

| 领域 | 选择条件 |
|---|---|
| 自动化 | `src/AALC.Runtime/`、`src/AALC.Platform.Windows/`、`src/AALC.Vision/` 的输入、帧校验、重试、取消和任务生命周期；读取 `aalc-automation-practices` |
| UI/配置 | `src/AALC.Desktop/` 的绑定、Dispatcher、配置快照、SettingsStore 与语义样式 |
| Python/i18n | 审阅 Python 目标树时核对其单例、QWidget、翻译、配置同步和停止规则 |

上游贡献还要读 `.agents/skills/upstream-contribution/references/upstream-style-review.md`，并与上游目标树对比。

## 逐条核实发现

1. 定位被改行或直接受影响的行为。
2. 从源码、测试或规格复现触发路径。
3. 拒绝臆测、既有问题或纯偏好类评论。
4. 按用户影响与可达性校准严重度。
5. 合并重复项，保留最清晰的触发条件与修复方向。

具体缺陷不因跨领域而掩盖。归到最相关领域并保留一条发现。

## AALC 检查

项目不变量在 `AGENTS.md`（核心不变量、生命周期与停止、发布不变量）。对照它们核实 diff，而不是复述。

审阅专属增补项：

- 与 callee 默认值相等且无具体理由的显式关键字参数；
- 只使用一次的下划线前缀变量、常量、参数或辅助函数，以及只有单个调用点的包装辅助函数；
- downstream 专属脚手架，或移植代码与相邻目标树在命名、日志、错误处理、测试风格上的不匹配；
- 生成与非代码文件按承载行为的产物审阅：diff 含 lockfile、编译翻译、图片、发布元数据、CI/构建脚本或更新 manifest 时读 [references/non-code-files.md](references/non-code-files.md)。

改动涉及包管理、测试/构建流程、必需环境、目录结构、CI/CD、跨模块契约或持久不变量时，评估 `AGENTS.md`、skills 或机械检查是否需要同步更新。

## 收敛

审阅有界。满足以下任一条件即停止并报告，而不是再开一轮：

- 当前请求的范围已覆盖，已确认缺陷已报告或已授权修复并核验；不要为凑轮次再审；
- 已核实发现需要超出当前授权的架构扩展，或尚未解决的证据冲突会推翻先前审阅决定；
- 同一文件已修三轮，发现数量仍未下降。

需要范围决策时只暂停受影响的修复，继续不依赖该决定的已授权工作；报告剩余项及其证据。审阅者严重度本身不授权扩大修复范围，"再多过一遍更稳妥"不构成继续的理由。

修复只触及上一轮已清文件的，绝不重新派发整套审阅者。每轮审阅本轮 delta 及其影响上下文；台账延续前几轮对完整 diff 已建立的覆盖。

## 裁决

已确认 Critical 或 High 缺陷 → **Block**。已确认 Medium 生产风险或成片 Medium → **Warning**。只有 Low/Suggestion → **Approve with comments**。无待办项且验证与该风险相称 → **Approve**。

验证明显不完整时绝不用裸 **Approve**。人工可推翻合并决定，但要记录未解决的技术风险。

## 输出

```markdown
- [Critical/High/Medium/Low/Suggestion] `文件:行` [领域] — 触发条件、影响、证据和修复方向。

**裁决：Block / Warning / Approve with comments / Approve**
```

无发现时明确说明，并只列影响结论的验证缺口。复杂 PR 协调使用 `references/pr-protocol.md` 的适用字段；简单复审只报告变化、结论与重要缺口。
