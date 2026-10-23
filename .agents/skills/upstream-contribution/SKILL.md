---
name: upstream-contribution
description: 把下游 fork 中已验证的 AALC 行为或修复贡献给上游，包括隔离 worktree 搭建、移植策略选择、上游原生重写、污染与风格审阅、回归测试、pull request 审阅与 CI 迭代，以及合并后的下游核对。准备、打开、更新或跟进上游贡献时使用。
---

# AALC 上游贡献

把上游贡献当作行为移植。完成边界由用户请求决定：准备补丁、打开 PR、跟进反馈或完整闭环分别执行到约定阶段；后续阶段不自动扩大授权。

## 按已授权阶段交付

以下结果仅适用于当前请求包含的阶段；简单补丁用简短契约与溯源说明，多轮协调才维护完整台账。

1. 书面行为契约与溯源记录。
2. 基于当前上游目标、位于隔离 worktree 的命名分支。
3. 无意外 fork 耦合的上游原生实现。
4. 保留兼容的既有回归测试；新增测试遵循 AGENTS.md 的授权与验证范围。
5. 使用上游画像的干净 `code-review` 结果。
6. 本地检查与 PR 检查通过，或明确报告剩余失败。
7. 可执行 PR 反馈全部解决，且每次更新后复审。
8. 合并或关闭后对照最终上游状态与下游 fork 完成核对。
9. 一份审阅发现台账，说明每项请求改动为何被修复、拒绝、拆分或升级。

用户只要求打开或更新 PR 时，完成该阶段即可交付；用户要求全程跟进时才继续后续闭环。

## 安全与权限

- 保留原工作区及其未提交、未追踪文件。
- 实现、提交、rebase 与冲突处理只发生在贡献 worktree 内。
- 不用一刀切的 `ours` 或 `theirs` 解决冲突。
- 绝不读取或打印凭据。使用已认证的 Git/GitHub 工具。
- push、创建 PR、回复审阅与远端编辑都是外部写入。只执行用户授权的范围；否则停在下一个外部写入关口并提交完整报告。
- 除非用户看到精确分支与理由后明确授权，否则不 force-push。

## 渐进式 reference

只读当前阶段需要的那份：

| 阶段 | Reference |
|---|---|
| 创建分支或 worktree 前 | [references/git-isolation.md](references/git-isolation.md) |
| 应用代码前 | [references/porting-strategy.md](references/porting-strategy.md) |
| 暂存与最终审阅期间 | [references/upstream-style-review.md](references/upstream-style-review.md) |
| 应用审阅者要求的改动前，以及每次复审 | [references/review-convergence.md](references/review-convergence.md) |
| PR 存在后 | [references/pr-lifecycle.md](references/pr-lifecycle.md) |
| 合并、上游编辑或关闭后 | [references/downstream-reconciliation.md](references/downstream-reconciliation.md) |

## 阶段 1：不写入地确认事实

1. 检查 `git status --short`、remotes、当前分支与候选提交或 diff。
2. Fetch 目标 remote，确定精确的上游 base 分支与提交。
3. 读下游 issue、失败证据、相关测试，以及带调用方的完整变更函数。
4. 在上游树中检查同一 API 与相邻实现。
5. 写下行为契约：

```text
Trigger:
Observed failure:
Expected behavior:
Required state transition:
Regression oracle:
Non-goals:
User decisions and validation exceptions:
Downstream provenance:
Upstream base commit:
```

不要把下游 diff 当规格。观察到的行为无法解释时，暂停实现并报告证据缺口。

## 阶段 2：分类每个变更点

移植前先建显式范围表：

| 关注点或 hunk | 处置 | 理由 |
|---|---|---|
| 契约要求的行为 | port | 上游必需行为 |
| 回归测试 | port 或 rewrite | 匹配上游测试约定 |
| 仅下游的配置/调试/发布/工具 | exclude | fork 基础设施 |
| 行为不需要的重构 | exclude | 无关范围 |
| API 适配 | rewrite | 匹配上游接口与默认值 |

不要一刀切排除 `tests/`。保留上游可运行的已有测试；新增回归测试仅在用户要求或已接受的交付包含测试时进行。上游缺少相应依赖时，不复制下游专属 fixture 或手动 `test/` 脚本。

测试适配以目标上游提交的配置、CI 命令和相邻测试为准，核对收集规则、fixture 与运行依赖。仅在下游 runner 中可运行、依赖下游专属 offscreen 设置或完整 UI 构造的测试留在下游维护，并在 PR body 验证小节注明本地验证命令。

## 阶段 3：创建隔离分支

遵循 `references/git-isolation.md`。worktree 必须挂接到从已 fetch 上游目标创建的命名分支——游离 `HEAD`、意外 base 或既有改动都会阻断实现。

## 阶段 4：选择并执行移植策略

使用 `references/porting-strategy.md` 的决策规则：只有整个提交在行为与结构上都兼容时才 exact 搬运；大体兼容时免提交应用加适配；历史、API、风格或职责分化时按行为重写。交织型 fork 代码默认 rewrite。

应用代码后：

1. 与相邻上游代码对比实现，而不是下游邻居。
2. 移除对上游维护者无用的 fork 溯源。
3. 测试属于已授权交付时，添加或适配修复前失败、修复后通过的最小上游原生回归测试。
4. 只暂存已分类的范围。混合 worktree 中绝不用 `git add -A`。

## 阶段 5：提交前审阅

对暂存 diff 运行 `code-review`，并明确要求其上游贡献画像。它必须使用 `references/upstream-style-review.md`，检查完整变更函数与相关上游调用点。

提交前解决全部已确认的 High/Critical 发现与所有上游污染发现。低严重度观察要么简化代码，要么记录上游模式为何使其合理。

不要把审阅者原始输出直接转成实现任务。按 `references/review-convergence.md` 对照行为契约核实发现、识别范围扩张；简单反馈用简短记录，多轮协调才分配稳定的 finding ID。既有路径不构成贡献阻断项，除非当前 diff 新调用、修改它或依赖其被违反的性质。

首次提交前运行确定性范围检查，然后检查暂存 diff：

```powershell
& .agents/skills/upstream-contribution/scripts/validate_contribution.ps1 `
  -BaseRef upstream/main `
  -TargetRef HEAD `
  -IncludeIndex
git diff --cached --stat
git diff --cached
```

用上游原生信息提交。必要时在工作报告或 PR body 中保留下游溯源；不要把 `Backport of ...` 硬塞进读起来像 fork 中心历史的上游提交。

## 阶段 6：验证分支

审阅整个贡献，而不只是最后一个提交：

```powershell
git log --oneline upstream/main..HEAD
git diff upstream/main...HEAD --stat
git diff upstream/main...HEAD
```

运行最窄且足够的上游检查：变更 Python 文件的语法或导入检查；不清扫无关遗留警告的针对性 Ruff 检查；相关自动化回归测试；涉及构建、i18n、更新协议或资源时对应检查。

提交后核对最终分支与已验证暂存内容一致；只有内容、base 或范围变化才重跑受影响检查。修复后按 delta 与直接影响上下文复审，沿用已有契约与发现记录；内容未变不重复整轮审阅。

若连续两轮复审产生需要架构扩展的新阻断项，或某提议修复推翻先前审阅决定，停止追加补丁。保留 worktree，在继续前选择重写、显式范围扩张、拆分贡献或延后。

## 阶段 7：打开并迭代 PR

在已授权的外部写入关口，推送命名分支并对已验证的上游仓库与 base 打开 PR。PowerShell 中多行 Markdown 用字面 here-string 或 notes 文件。

用户已要求跟进时遵循 `references/pr-lifecycle.md`；等待上游行动时报告当前 head、CI、未解决反馈与待办方，不无限轮询。本地与远端沿用同一份发现记录；准确区分本轮已完成工作与 PR 仍未合并的状态。

## 阶段 8：核对最终上游结果

已授权最终核对时，在合并、维护者编辑、squash/rebase 合并或关闭后遵循 `references/downstream-reconciliation.md`。上游含下游未体现的改进时记录差异；已授权回流才用 `downstream-sync` 并做必要验证。记录原下游提交应保留、应替换还是需要后续清理。

## 最终报告

只填写当前请求阶段适用的字段；尚未进入 PR 或下游核对阶段时省略相应项。

```markdown
## 上游贡献结果

- 行为契约：
- Worktree / branch：
- Upstream base：
- Porting strategy：exact / adapt / rewrite
- 贡献提交与 PR：
- 上游风格审阅：
- 审阅收敛：contract revision、finding ledger 与仍开放项
- 本地验证：
- CI 与评审线程：
- 当前上游状态：未开 PR / open / merged / closed / blocked
- 下游对账：already equivalent / synced final upstream / follow-up required
- 剩余风险：
```

每个声称的成功都必须点名证明它的命令、检查、审阅状态或提交。
