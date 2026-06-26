---
name: upstream-contribution
description: Use when backporting verified AALC bug fixes from the canary fork to upstream while excluding fork-only code, local artifacts, tests, release notes, and unrelated changes.
license: AGPL-3.0
compatibility: opencode
metadata:
  audience: maintainers
  workflow: github
---

# AALC Upstream Contribution

## Non-negotiables

1. Use an isolated git worktree. Do not switch the original workspace.
2. Scan for canary-only code before cherry-picking.
3. Do not contribute `tests/`, `test/`, `.opencode/`, `issues/`, logs, local tools,
   release notes, version bumps, or canary branding.
4. Final diff must contain only the upstream-compatible bug fix.
5. Stop before pushing. Push only after the user reviews the report and confirms.

## Phase 1: Pre-pick analysis

This phase is read-only.

1. Fetch upstream:

```powershell
git fetch upstream
```

2. For each candidate commit:

```powershell
git show --stat <commit>
git show <commit>
```

3. Build an allow/exclude file list:

```text
保留:
- path/to/core_bugfix.py

排除:
- tests/...                 # tests are not contributed in this workflow
- .opencode/...             # local agent tooling
- issues/...                # user evidence archive
- CHANGELOG.md              # upstream maintains release notes separately
- assets/config/version.txt # release metadata
```

4. Run the canary-only scan below before any cherry-pick.

## Canary-only scan

Use OpenCode `explore` subagents in parallel when available. If the current environment
does not expose subagent delegation, run the same scans sequentially and state that
fallback in the report.

### Scan A: Added imports

Goal: every added import must exist upstream or be standard library.

```powershell
git show <commit> | Select-String "^\+.*(^import |^from )"
git grep "<symbol>" upstream/main
```

Mark standard-library imports as safe. Mark missing project symbols as blocking.

### Scan B: Config keys

Goal: no fork-only config keys enter upstream.

Search added `cfg.get_value`, `cfg.set_value`, and `cfg.unsaved_set_value` calls, then
verify each key under `upstream/main`:

```powershell
git grep "\"<key>\"" upstream/main -- "module/config/" "*.yaml"
```

Known fork-only or high-risk patterns include `debug_*`, `lab_*`, `canary`,
`mirrorchyan_cdk`, and removed update-source fields.

### Scan C: Fork-only functions and paths

Search added symbols and strings for:

- debug helper names such as `_debug_*`, `_is_*_debug*`, `_shop_debug*`;
- `.opencode/`, `issues/`, `logs/`, `assets/images/dark/`;
- canary branding or release-channel strings;
- special capture/debug helpers unless upstream already contains the same API.

Verify suspicious symbols with `git grep "<symbol>" upstream/main`.

### Scan D: File categories

Confirm the candidate commit does not require excluded categories:

- tests or manual scripts;
- issue archives, screenshots, logs, generated reports;
- release metadata, changelog, version files;
- project-local agent/tooling files.

### Scan report

Use this shape:

```text
Canary scan report
Blocking:
- <file:line> reason

Needs review:
- <file:line> reason

Safe:
- <file:line> reason
```

Blocking items must be removed, rewritten for upstream, or brought back to the user.

## Phase 2: Create worktree and apply changes

After Phase 1 is clean or the user accepts the rewrite plan, create an isolated worktree:

```powershell
git worktree add .worktrees/upstream-fix/<short-name> upstream/main
Set-Location .worktrees/upstream-fix/<short-name>
uv sync --frozen
```

If `.worktrees/` is not ignored, add it to `.gitignore` in the original workspace only
with user-safe review.

Apply the fix conservatively:

- Pure commit: `git cherry-pick -n <commit>`, then stage only allowed files.
- Mixed commit: manually port only the upstream-compatible hunks.
- Interwoven fork-only code: stop and explain the required rewrite.

Before committing, verify staged content:

```powershell
git diff --cached --stat
git diff --cached
```

The commit message may reuse the original message if the port is semantically identical;
otherwise mention `Backport of <commit>`.

## Phase 3: Diff audit and verification

Review the complete branch diff:

```powershell
git log --oneline upstream/main..HEAD
git diff upstream/main...HEAD --stat
git diff upstream/main...HEAD
```

Checklist:

- No canary-only imports, config keys, debug switches, or release-channel changes.
- No `.opencode/`, `issues/`, logs, screenshots, `test/`, or `tests/`.
- No `CHANGELOG.md`, version file, user config, or generated local artifacts.
- Modified APIs exist on upstream.
- File list matches the Phase 1 allow list.

Run the narrowest checks for changed Python files:

```powershell
uv run python -m py_compile path\to\changed.py
uv run ruff check path\to\changed.py
```

Do not clean unrelated legacy ruff warnings.

## Phase 4: Report and stop before push

Report to the user:

```markdown
## 上游贡献审查报告

### 基本信息
- Worktree:
- Base:
- Commits:

### 变更摘要
<git diff --stat>

### Canary-only 扫描
<blocking / needs review / safe>

### 验证
<commands and results>

### 剩余风险
<anything not verified>
```

Then stop. Ask for explicit confirmation before pushing any branch or opening a PR.

Only after confirmation:

```powershell
git push origin <branch>
```

## Failure handling

- Merge/cherry-pick conflict: do not choose ours/theirs automatically. Explain the
  conflicting files and ask for direction.
- Dirty original workspace: do not switch branches; preserve user changes.
- Missing upstream API: rewrite for upstream or stop.
- Verification failure: fix in the worktree and rerun the failed check before reporting
  success.
