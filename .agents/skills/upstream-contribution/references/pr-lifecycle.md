# Pull Request Lifecycle

Use this reference after a PR is created or when resuming work on an existing contribution.

## Establish current state

Read the PR metadata, current head SHA, base SHA, checks, reviews, inline threads, and maintainer commits. Do not rely only on timeline comments because resolved threads and requested-change state may be hidden there.

Record:

```text
PR URL:
Local validated SHA:
Remote head SHA:
Base branch and current base SHA:
Checks pending/failing/passing:
Unresolved actionable threads:
Maintainer edits:
```

If local and remote head differ, determine why before editing.

## Review iteration

For every actionable comment:

1. verify it against upstream code, the behavior contract, and the existing finding ledger;
2. classify it as an in-scope fix, scope decision, clarification, duplicate, or disagreement with evidence;
3. implement fixes in the contribution worktree;
4. run targeted tests and the upstream-profile `code-review` again;
5. push only the reviewed commit set;
6. reply with the concrete commit or evidence;
7. confirm the thread state after the response.

Do not mechanically satisfy a suggestion that adds redundancy or contradicts upstream patterns. Explain disagreements with source and test evidence.
Do not reopen a locally verified or rejected finding without new evidence. If a maintainer requests behavior outside the frozen contract, record the scope change explicitly before implementation rather than hiding it inside a review-fix commit.

## CI iteration

After every update:

- wait for checks associated with the new head SHA, not the previous run;
- inspect failing logs rather than guessing from job names;
- distinguish contribution failures from unrelated upstream infrastructure failures;
- fix contribution failures and rerun affected local checks;
- report external failures without claiming the PR is green.

## Base movement

If upstream base moves, inspect whether the new commits overlap the fix. Rebase only when needed for correctness or project policy. After rebasing, re-review the complete diff because conflict resolution can reintroduce downstream-shaped code.

## Terminal states

- **Merged:** identify the final merge/squash/rebase commit and proceed to downstream reconciliation.
- **Closed unmerged:** record the reason and check whether upstream applied an alternative fix.
- **Blocked:** report the exact pending party/action, current head SHA, latest checks, and unresolved threads. Do not call ordinary waiting a completed contribution.
