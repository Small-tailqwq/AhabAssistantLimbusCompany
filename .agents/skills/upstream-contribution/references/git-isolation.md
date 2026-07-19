# Git Isolation and Branch Topology

Use this reference before creating or changing a contribution worktree.

## Preflight

Inspect without changing the original workspace:

```powershell
git status --short
git remote -v
git branch --show-current
git worktree list --porcelain
git fetch upstream
git rev-parse upstream/main
```

Confirm the intended topology rather than assuming remote names:

- the downstream fork is normally pushed through `origin`;
- the contribution target is normally `upstream/main`;
- the PR head branch must exist on a remote from which upstream accepts PRs.

If remotes do not match that topology, report the actual URLs and ask before adding or rewriting remotes.

## Worktree creation

Choose a unique slug. Create both a branch and a worktree in one command:

```powershell
$branch = "upstream-contrib/<slug>"
$worktree = ".worktrees/upstream-contribution/<slug>"
git worktree add -b $branch $worktree upstream/main
```

Never use this form for contribution work:

```powershell
git worktree add <path> upstream/main
```

It checks out the remote-tracking commit with detached `HEAD`, leaving no named branch to push.

Verify the result from inside the worktree:

```powershell
git -C $worktree branch --show-current
git -C $worktree rev-parse HEAD
git -C $worktree merge-base --is-ancestor upstream/main HEAD
git -C $worktree status --short
```

## Base updates

Before the PR exists, prefer recreating an untouched contribution branch from the latest upstream base. After commits exist, fetch and inspect divergence before rebasing. Rebase or force-push changes remote history; obtain the authority required by the current task and never hide the rewrite.

Do not merge downstream `main` into a contribution branch. A contribution branch must contain only upstream base history plus upstream-compatible contribution commits.

## Conflict handling

On cherry-pick, rebase, or merge conflicts:

1. stop and list the conflicting paths;
2. read base, upstream, and intended behavior;
3. resolve each conflict by the behavior contract and upstream code shape;
4. run the same review and checks as a hand-written change;
5. never select all `ours` or all `theirs` as a shortcut.

Abort only the in-progress operation when necessary; do not reset or clean the user's original workspace.

## Cleanup

Worktree cleanup is optional and occurs only after the branch is no longer needed. Show the exact worktree path and confirm it contains no unique unpushed work before removal. Do not delete ignored worktrees merely because the PR merged.
