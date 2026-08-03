---
name: downstream-sync
description: 把精选的上游 AALC 修复或改进回流到下游 fork，包括补丁身份筛选、隔离 worktree 集成、exact/adapt/rewrite 选择、提交前验证与审阅、单逻辑修复提交，以及上游贡献完成后对最终上游结果的核对。在不合并无关上游历史的前提下做 fork 同步时使用。
---

# AALC 下游回流

把上游行为移植进 fork，且不抹掉有意的下游差异。提交身份、作者与标题只是线索；补丁身份与当前行为才决定工作是否缺失。

## 必需结果

- 候选提交派生自已 fetch 的上游图谱。
- 已等价的修复通过补丁与行为检查排除。
- 集成发生在隔离 worktree 的命名分支上。
- 每个提交只含一个逻辑上游修复或一个不可拆分的依赖组。
- 每个提交前通过相关检查与 `code-review`。
- 做出明确集成选择前，原下游工作区保持不动。

## 预检与隔离

1. 检查 `git status --short`、remotes、当前分支与已有 worktree。
2. 不切换原工作区地 fetch upstream。
3. 明确确定下游 base 提交。
4. 创建命名分支与 worktree：

```powershell
$branch = "downstream-sync/<short-name>"
$path = ".worktrees/downstream-sync/<short-name>"
git worktree add -b $branch $path HEAD
```

验证分支名、base SHA 与干净状态。原工作区脏时，未先商定这些改动如何保留，不得稍后合并或切换它。

## 阶段 1：构建候选清单

```powershell
git merge-base HEAD upstream/main
git log --no-merges --oneline <merge-base>..upstream/main
git cherry -v HEAD upstream/main
```

为每个疑似修复记录：

```text
Upstream SHA and title:
Changed behavior:
Files and APIs:
Dependencies on earlier upstream commits:
Patch-equivalent downstream commit:
Current downstream behavior already equivalent:
Candidate status:
```

不能只因作者或标题像先前贡献就跳过某提交。squash 合并、维护者重写与替代修复都会改变身份。需要时用 `git patch-id --stable`，然后检查行为与测试。

## 阶段 2：选择集成策略

- **exact**：上游提交单一目的，且与下游结构干净匹配；
- **adapt**：核心补丁兼容，但下游配置、API 或布局需要本地调整；
- **rewrite**：历史或职责分化，或只应保留上游行为。

选择不明显时读 `.agents/skills/upstream-contribution/references/porting-strategy.md`。无冲突的 cherry-pick 不能证明语义契合。

上游回归测试兼容时保留，需要时适配到下游 fixture。不要把 `tests/` 一刀切排除。

## 阶段 3：应用单个逻辑修复

一次只处理一个候选或不可拆分依赖组：

```powershell
git cherry-pick -n <upstream-commit>
```

adapt 或 rewrite 时编辑 worktree，使最终 diff 通过下游原生 API 表达上游行为。移除不属于 fork 的无关上游重构、发布元数据与路径。

同时检查暂存与未暂存状态。只暂存明确路径，绝不用一刀切的 `git add -A` 混入 worktree 状态。

## 阶段 4：提交前验证

1. 读完整变更函数与受影响调用方。
2. 运行回归测试或回归验证基准。
3. 运行针对性语法与 Ruff 检查。
4. 按变更路径选择自动化或 i18n 领域运行 `code-review`。
5. 检查 `git diff --cached --stat` 与 `git diff --cached`。
6. 确认没有无关的上游发布、配置、品牌或 CI 改动被暂存。

以上检查通过才提交。提交信息用中文，正文保留上游溯源：

```text
上游回流: <简短标题>

Upstream: KIYI671/AhabAssistantLimbusCompany@<full-or-abbrev-sha>
Strategy: exact | adapt | rewrite

<行为和适配说明>
```

## 阶段 5：审阅完整回流分支

```powershell
git log --oneline <downstream-base>..HEAD
git diff <downstream-base>...HEAD --stat
git diff <downstream-base>...HEAD
```

对完整分支运行 `code-review`，并重跑受提交间交互影响的测试。确认每个提交仍可独立理解，且后续提交没有静默撤销先前修复。

## 阶段 6：审慎集成

改动原下游分支前先报告回流分支与验证结果。用户授权本地集成且原工作区干净时，按仓库选定的 merge、fast-forward 或 cherry-pick 策略集成。工作区脏时停下，保留 worktree 分支并请求保留方案。

未经用户授权，绝不 push 或开 PR（外部写入）。

## 条件模式

- 上游 PR 到达终态后：读 [references/reconciliation.md](references/reconciliation.md)。
- 出现冲突、依赖缺失、验证失败、部分历史移植或原工作区脏时：读 [references/failure-handling.md](references/failure-handling.md)。

## 最终报告

```markdown
## 上游回流结果

- Downstream base / worktree / branch：
- Upstream range：
- 已回流（SHA、strategy、commit、验证）：
- 已等价（patch/behavior evidence）：
- 阻塞或跳过（原因）：
- 完整分支复审：
- 原工作区集成状态：
- 剩余风险：
```
