---
name: downstream-sync
description: Bring selected upstream AALC fixes or refinements back into the downstream fork, including patch-identity screening, isolated worktree integration, exact/adapt/rewrite selection, pre-commit validation and review, one-logical-fix commits, and reconciliation of the final upstream result after an upstream contribution. Use for fork-from-upstream synchronization without merging unrelated upstream history.
---

# AALC Downstream Sync

Port upstream behavior into the fork without erasing intentional downstream differences. Commit identity, author, and title are hints only; patch identity and current behavior determine whether work is missing.

## Required outcome

- Candidate commits are derived from the fetched upstream graph.
- Already-equivalent fixes are excluded by patch and behavior checks.
- Integration occurs on a named branch in an isolated worktree.
- Each commit contains one logical upstream fix or one inseparable dependency group.
- Relevant checks and `code-review` pass before each commit.
- The original downstream workspace remains untouched until an explicit integration choice is made.

## Preflight and isolation

1. Inspect `git status --short`, remotes, current branch, and existing worktrees.
2. Fetch upstream without switching the original workspace.
3. Determine the downstream base commit explicitly.
4. Create a named branch and worktree:

```powershell
$branch = "downstream-sync/<short-name>"
$path = ".worktrees/downstream-sync/<short-name>"
git worktree add -b $branch $path HEAD
```

Verify the branch name, base SHA, and clean status. If the original workspace is dirty, do not merge or switch it later without agreeing on how those changes will be preserved.

## Phase 1: Build candidate inventory

```powershell
git merge-base HEAD upstream/main
git log --no-merges --oneline <merge-base>..upstream/main
git cherry -v HEAD upstream/main
```

For each likely fix, record:

```text
Upstream SHA and title:
Changed behavior:
Files and APIs:
Dependencies on earlier upstream commits:
Patch-equivalent downstream commit:
Current downstream behavior already equivalent:
Candidate status:
```

Do not skip a commit only because its author or title resembles a prior contribution. Squash merges, maintainer rewrites, and alternative fixes change identity. Use `git patch-id --stable` where useful, then inspect behavior and tests.

## Phase 2: Select the integration strategy

Use the same evidence-based strategy as `upstream-contribution`:

- **exact:** upstream commit is single-purpose and cleanly matches downstream structure;
- **adapt:** core patch is compatible but downstream config, APIs, or layout require local changes;
- **rewrite:** histories or responsibilities diverge, or only the upstream behavior should be retained.

Read `.agents/skills/upstream-contribution/references/porting-strategy.md` when the choice is not obvious. A conflict-free cherry-pick does not prove semantic fit.

Keep upstream regression tests when compatible. Adapt them to downstream fixtures when needed. Do not exclude `tests/` categorically.

## Phase 3: Apply one logical fix

Work on one candidate or inseparable dependency group at a time:

```powershell
git cherry-pick -n <upstream-commit>
```

For adapt or rewrite, edit the worktree so the final diff expresses upstream behavior through downstream-native APIs. Remove unrelated upstream refactors, release metadata, and paths that do not belong in the fork.

Inspect both staged and unstaged state. Stage explicit paths, never a blanket mixed-worktree `git add -A`.

## Phase 4: Validate before commit

Before committing each logical fix:

1. read complete changed functions and affected callers;
2. run the regression test or behavioral oracle;
3. run targeted syntax and Ruff checks;
4. run `code-review` with automation or i18n specialists selected by changed domain;
5. inspect `git diff --cached --stat` and `git diff --cached`;
6. confirm no unrelated upstream release, config, branding, or CI change is staged.

Commit only after these checks. Use a Chinese downstream commit message and retain upstream provenance in the body:

```text
上游回流: <简短标题>

Upstream: KIYI671/AhabAssistantLimbusCompany@<full-or-abbrev-sha>
Strategy: exact | adapt | rewrite

<行为和适配说明>
```

## Phase 5: Review the complete sync branch

After all candidate commits:

```powershell
git log --oneline <downstream-base>..HEAD
git diff <downstream-base>...HEAD --stat
git diff <downstream-base>...HEAD
```

Run `code-review` on the complete branch and rerun tests affected by interactions between commits. Confirm that each commit remains independently understandable and that later commits do not silently undo earlier fixes.

## Phase 6: Integrate deliberately

Report the sync branch and validation before altering the original downstream branch. If the user authorized local integration and the original workspace is clean, integrate using the repository's chosen merge, fast-forward, or cherry-pick policy. If it is dirty, stop with the worktree branch intact and request a preservation choice.

Never push or open a PR unless the user authorized that external write.

## Upstream-contribution reconciliation mode

When invoked after an upstream PR:

1. identify the final upstream merge/squash/rebase SHA, not merely the submitted head;
2. compare final upstream code with current downstream behavior;
3. port maintainer refinements or alternative fixes that downstream lacks;
4. avoid duplicating behavior already present in the original downstream commit;
5. run the original regression oracle in downstream;
6. record intentional remaining fork differences.

## Failure handling

- Conflict: stop, inspect base/upstream/downstream behavior, and resolve per file; never blanket-select one side.
- Missing dependency: either include the minimal dependency in the same group or rewrite without it.
- Validation failure: do not commit; fix or abort only the in-progress application.
- Partial prior port: separate already-present behavior from missing behavior and commit only the missing delta.
- Dirty original workspace: leave it untouched and keep the validated worktree branch for later integration.

## Final report

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
