---
name: upstream-contribution
description: Contribute a verified AALC behavior or fix from the downstream fork to upstream, including isolated worktree setup, porting-strategy selection, upstream-native rewriting, contamination and style review, regression tests, pull-request review and CI iteration, and post-merge downstream reconciliation. Use whenever preparing, opening, updating, or following through on an upstream contribution.
---

# AALC Upstream Contribution

Treat an upstream contribution as a behavior port, not as a downstream commit transfer. The job is complete only when the upstream-native change has passed review, the final upstream result is known, and downstream reconciliation has been checked.

## Required outcome

Produce all of the following:

1. A written behavior contract and provenance record.
2. A named branch in an isolated worktree based on the current upstream target.
3. An upstream-native implementation with no accidental fork coupling.
4. Relevant upstream-native regression coverage when practical.
5. A clean `code-review` result using the upstream profile.
6. Passing local checks and PR checks, or an explicit report of remaining failures.
7. Resolution of actionable PR feedback and re-review after every update.
8. Post-merge or post-close reconciliation against the final upstream state and the downstream fork.
9. A review finding ledger showing why every requested change was fixed, rejected, split, or escalated.

Opening or updating a PR is an intermediate state, not successful completion.

## Safety and authority

- Preserve the original workspace and its uncommitted or untracked files.
- Perform implementation, commits, rebases, and conflict work only inside the contribution worktree.
- Do not resolve conflicts with blanket `ours` or `theirs` choices.
- Never read or print credentials. Use existing authenticated Git/GitHub tooling.
- Treat push, PR creation, review replies, and remote edits as external writes. Execute only the scope the user authorized; otherwise stop at the next external-write gate with a complete report.
- Do not force-push unless the user explicitly authorizes it after the exact branch and reason are shown.

## Progressive references

Read only the reference needed for the current phase:

- Before creating a branch or worktree, read [references/git-isolation.md](references/git-isolation.md).
- Before applying code, read [references/porting-strategy.md](references/porting-strategy.md).
- During staged and final review, read [references/upstream-style-review.md](references/upstream-style-review.md).
- Before applying reviewer-requested changes, and on every re-review, read [references/review-convergence.md](references/review-convergence.md).
- After a PR exists, read [references/pr-lifecycle.md](references/pr-lifecycle.md).
- After merge, upstream edits, or closure, read [references/downstream-reconciliation.md](references/downstream-reconciliation.md).

## Phase 1: Establish facts without writing

1. Inspect `git status --short`, remotes, current branch, and candidate commits or diff.
2. Fetch the target remote and identify the exact upstream base branch and commit.
3. Read the downstream issue, failure evidence, relevant tests, and the full changed functions with their callers.
4. Inspect the same APIs and adjacent implementation in the upstream tree.
5. Write a behavior contract:

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

Do not use the downstream diff as the specification. If the observed behavior cannot be explained, pause implementation and report the evidence gap.

## Phase 2: Classify every changed concern

Build an explicit scope table before porting:

| Concern or hunk | Disposition | Reason |
|---|---|---|
| Behavior required by the contract | port | Required upstream behavior |
| Regression test | port or rewrite | Match upstream test conventions |
| Downstream-only config/debug/release/tooling | exclude | Fork infrastructure |
| Refactor not required for the behavior | exclude | Unrelated scope |
| API adaptation | rewrite | Match upstream interfaces and defaults |

Do not categorically exclude `tests/`. If upstream has automated tests and the behavior is testable, add or adapt a focused regression test. Do not copy downstream-only fixtures or manual `test/` scripts when upstream lacks their dependencies.

## Phase 3: Create the isolated branch

Follow `references/git-isolation.md`. The worktree must be attached to a named branch created from the fetched upstream target, for example:

```powershell
$branch = "upstream-contrib/<short-name>"
$path = ".worktrees/upstream-contribution/<short-name>"
git worktree add -b $branch $path upstream/main
```

Immediately verify:

```powershell
git -C $path branch --show-current
git -C $path merge-base --is-ancestor upstream/main HEAD
git -C $path status --short
```

A detached `HEAD`, unexpected base, or pre-existing changes blocks implementation.

## Phase 4: Select and execute the porting strategy

Use the decision rules in `references/porting-strategy.md`:

- Exact transfer only when the whole commit is behaviorally and structurally compatible.
- Apply-without-commit plus adaptation when the change is mostly compatible.
- Behavior-based rewrite when histories, APIs, style, or responsibilities diverge. This is the default for interwoven fork code.

After applying code:

1. Compare the implementation with adjacent upstream code, not downstream neighbors.
2. Remove fork provenance that does not help upstream maintainers.
3. Add the smallest upstream-native regression test that fails before and passes after the fix, when practical.
4. Stage only the classified scope. Never use `git add -A` in a mixed worktree.

## Phase 5: Review before commit

Run the `code-review` skill against the staged diff and explicitly request its upstream-contribution profile. It must use `references/upstream-style-review.md` and inspect complete changed functions and relevant upstream call sites.

Resolve all confirmed High/Critical findings and all upstream-contamination findings before committing. For lower-severity observations, either simplify the code or record why the upstream pattern justifies it.

Do not convert raw reviewer output directly into an implementation task. Use `references/review-convergence.md` to assign stable finding IDs, verify eligibility against the behavior contract, and identify scope expansion first. A pre-existing path is not a contribution blocker unless the current diff newly invokes it, changes it, or relies on the violated property.

Run the deterministic scope check:

```powershell
& .agents/skills/upstream-contribution/scripts/validate_contribution.ps1 `
  -BaseRef upstream/main `
  -TargetRef HEAD `
  -IncludeIndex
```

Before the first commit, also inspect:

```powershell
git diff --cached --stat
git diff --cached
```

Commit with an upstream-native message. Preserve downstream provenance in the work report or PR body when useful; do not force `Backport of ...` into an upstream commit when it reads as fork-centric history.

## Phase 6: Verify the branch

Review the entire contribution, not only the last commit:

```powershell
git log --oneline upstream/main..HEAD
git diff upstream/main...HEAD --stat
git diff upstream/main...HEAD
```

Run the narrowest sufficient upstream checks:

- syntax or import checks for changed Python files;
- targeted Ruff checks without cleaning unrelated legacy warnings;
- relevant automated regression tests;
- build, i18n, update-protocol, or asset checks when those areas changed.

Re-run `validate_contribution.ps1` without `-IncludeIndex` against the committed branch.
Re-run `code-review` on the final branch diff after fixes, passing the contract revision, complete finding ledger, previous reviewed SHA, and delta. A passing test suite does not replace upstream-style review.

If two consecutive re-reviews produce new blockers that require architectural expansion, or a proposed fix reverses an earlier review decision, stop adding patches. Preserve the worktree and choose rewrite, explicit scope expansion, a split contribution, or deferral before continuing.

## Phase 7: Open and iterate the PR

At the authorized external-write gate, push the named branch and open the PR against the verified upstream repository and base. Use a literal here-string or notes file for multiline Markdown in PowerShell.

Then follow `references/pr-lifecycle.md` until one of these terminal remote states is reached:

- merged;
- closed without merge with a documented reason;
- genuinely blocked on upstream action, with current CI and review state reported.

For every pushed update:

1. Fetch the current upstream base and determine whether the branch is stale.
2. Re-run affected checks and the upstream-profile review.
3. Inspect new CI results and unresolved review threads.
4. Reply only after the code and evidence support the response.
5. Confirm that the remote PR head matches the locally validated commit.

Keep the same finding ledger through local and remote review. Do not reopen a verified or rejected item without recording new evidence, and do not repeatedly convert an explicit user-approved validation exception into a new blocker.

Do not report completion merely because feedback was answered or a new commit was pushed.

## Phase 8: Reconcile the final upstream result

Follow `references/downstream-reconciliation.md` after merge, maintainer edits, squash/rebase merge, or closure.

At minimum:

1. Fetch upstream and identify the final upstream commit or the final rejected state.
2. Compare final upstream behavior with the original behavior contract.
3. Compare that final behavior with downstream current code.
4. Use `downstream-sync` when upstream contains a fix or refinement not represented downstream.
5. Run the downstream regression oracle and relevant checks.
6. Record whether the original downstream commit can remain, should be replaced, or needs a follow-up cleanup.

## Final report

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

Every claimed success must name the command, check, review state, or commit that proves it.
