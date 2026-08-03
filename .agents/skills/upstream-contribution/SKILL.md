---
name: upstream-contribution
description: 把下游 fork 中已验证的 AALC 行为或修复贡献给上游，包括隔离 worktree 搭建、移植策略选择、上游原生重写、污染与风格审阅、回归测试、pull request 审阅与 CI 迭代，以及合并后的下游核对。准备、打开、更新或跟进上游贡献时使用。
---

# AALC 上游贡献

把上游贡献当作行为移植，而不是下游提交搬运。只有上游原生改动通过审阅、最终上游结果已知且下游核对完成，任务才算结束。

## 必需结果

1. 书面行为契约与溯源记录。
2. 基于当前上游目标、位于隔离 worktree 的命名分支。
3. 无意外 fork 耦合的上游原生实现。
4. 可行时覆盖相关行为的上游原生回归测试。
5. 使用上游画像的干净 `code-review` 结果。
6. 本地检查与 PR 检查通过，或明确报告剩余失败。
7. 可执行 PR 反馈全部解决，且每次更新后复审。
8. 合并或关闭后对照最终上游状态与下游 fork 完成核对。
9. 一份审阅发现台账，说明每项请求改动为何被修复、拒绝、拆分或升级。

打开或更新 PR 只是中间状态，不是成功完成。

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

不要一刀切排除 `tests/`。上游有自动化测试且行为可测时，添加或适配一个聚焦的回归测试。上游缺少相应依赖时，不复制下游专属 fixture 或手动 `test/` 脚本。

与上游测试框架或运行约定不符的测试不随 PR 带入上游：例如上游用 `unittest.TestCase` 而下游是 pytest 风格普通函数、依赖 offscreen 平台或完整 UI 构造、或在上游规范 runner 下不会被收集的测试。此类测试留在下游本地维护，并在 PR body 验证小节注明本地验证命令。

## 阶段 3：创建隔离分支

遵循 `references/git-isolation.md`。worktree 必须挂接到从已 fetch 上游目标创建的命名分支——游离 `HEAD`、意外 base 或既有改动都会阻断实现。

## 阶段 4：选择并执行移植策略

使用 `references/porting-strategy.md` 的决策规则：只有整个提交在行为与结构上都兼容时才 exact 搬运；大体兼容时免提交应用加适配；历史、API、风格或职责分化时按行为重写。交织型 fork 代码默认 rewrite。

应用代码后：

1. 与相邻上游代码对比实现，而不是下游邻居。
2. 移除对上游维护者无用的 fork 溯源。
3. 可行时添加修复前失败、修复后通过的最小上游原生回归测试。
4. 只暂存已分类的范围。混合 worktree 中绝不用 `git add -A`。

## 阶段 5：提交前审阅

对暂存 diff 运行 `code-review`，并明确要求其上游贡献画像。它必须使用 `references/upstream-style-review.md`，检查完整变更函数与相关上游调用点。

提交前解决全部已确认的 High/Critical 发现与所有上游污染发现。低严重度观察要么简化代码，要么记录上游模式为何使其合理。

不要把审阅者原始输出直接转成实现任务。先用 `references/review-convergence.md` 分配稳定的 finding ID、对照行为契约核实资格、识别范围扩张。既有路径不构成贡献阻断项，除非当前 diff 新调用、修改它或依赖其被违反的性质。

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

对已提交分支重跑不带 `-IncludeIndex` 的 `validate_contribution.ps1`。修复后对最终分支 diff 重跑 `code-review`，传入契约修订版、完整发现台账、先前已审阅 SHA 与 delta。测试套件通过不能替代上游风格审阅。

若连续两轮复审产生需要架构扩展的新阻断项，或某提议修复推翻先前审阅决定，停止追加补丁。保留 worktree，在继续前选择重写、显式范围扩张、拆分贡献或延后。

## 阶段 7：打开并迭代 PR

在已授权的外部写入关口，推送命名分支并对已验证的上游仓库与 base 打开 PR。PowerShell 中多行 Markdown 用字面 here-string 或 notes 文件。

然后遵循 `references/pr-lifecycle.md`，直到 PR 合并、带记录理由地关闭，或确实阻塞在上游行动且当前 CI 与审阅状态已报告。本地与远端审阅共用同一份发现台账。仅因反馈已答复或新提交已推送就报告完成，不算完成。

## 阶段 8：核对最终上游结果

合并、维护者编辑、squash/rebase 合并或关闭后遵循 `references/downstream-reconciliation.md`。上游含下游未体现的修复或改进时用 `downstream-sync`，然后运行下游回归验证基准，并记录原下游提交应保留、应替换还是需要后续清理。

## 最终报告

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
- 最终上游状态：merged / closed / blocked
- 下游对账：already equivalent / synced final upstream / follow-up required
- 剩余风险：
```

每个声称的成功都必须点名证明它的命令、检查、审阅状态或提交。
