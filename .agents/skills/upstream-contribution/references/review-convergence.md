# Review Convergence

Use this protocol before turning reviewer output into another code change. The objective is not to minimize review; it is to make every iteration traceable to the behavior contract and prevent sequential reviewers from widening the patch by accident.

## Freeze the decision boundary

Before the first implementation review, record:

```text
Contract revision:
Required behavior:
Allowed files and responsibility boundary:
Explicit non-goals:
User decisions and validation exceptions:
Current base/head:
```

A reviewer may reveal that the contract is unsafe or incomplete, but cannot silently expand it. A change to timeout ownership, retry semantics, lifecycle ownership, public signatures, dependencies, configuration, or the set of required behaviors is a contract change and requires a scope decision before more code is written.

Record a user-approved verification exception once. For example, if the user explicitly chooses not to add an upstream test, keep `no automated regression coverage` as a validation gap; do not let each reviewer rediscover it as a new defect or describe it as covered.

## Maintain one finding ledger

Give every finding a stable ID and retain it across reviewers and head SHAs:

| Field | Required content |
|---|---|
| ID | Stable identifier such as `RV-01` |
| First seen | Reviewed head SHA and reviewer |
| Claim | Concrete trigger and impact |
| Evidence | Changed line, directly affected call path, API contract, or reproduction |
| Contract relation | Required behavior, necessary dependency, non-goal, or unrelated |
| Classification | In-scope defect, scope-expanding dependency, pre-existing/unrelated, duplicate, suggestion, or invalid |
| Decision | Fix, clarify, reject with evidence, split to follow-up, or ask user |
| State | Open, fixed-awaiting-review, verified, superseded, or reopened |

Do not erase rejected, superseded, or verified findings. A later reviewer sees their evidence and disposition instead of restating them from scratch. Reopen an item only when the current diff or new source/runtime evidence invalidates the prior decision; record that evidence in the same ledger entry.

## Triage before implementation

For each proposed finding, inspect the full changed definition, direct callers, current upstream signature, and relevant adjacent pattern. Then apply these eligibility rules:

1. **In-scope defect:** a changed line or directly changed behavior has a reachable failure that violates the frozen contract or upstream contract. Fix it.
2. **Scope-expanding dependency:** the required behavior cannot be correct without changing an excluded responsibility. Stop and choose whether to expand, split, or narrow the behavior contract before editing.
3. **Pre-existing or unrelated:** the path existed before the contribution and the current diff neither invokes it in a new way nor relies on a property it violates. It cannot block this contribution; record it as a possible follow-up.
4. **Suggestion:** a non-required alternative or preference. Accept only when it simplifies the current patch without widening scope.
5. **Invalid or duplicate:** evidence does not support the claim, or the ledger already covers it. Reject or link it; do not create another implementation task.

Reviewer severity does not bypass this classification. A claimed High issue can still be pre-existing, speculative, or scope-expanding rather than an immediate patch instruction.

## Impact note before every review fix

Before dispatching an implementation task, write:

```text
Finding IDs addressed:
Smallest correction:
Files and signatures affected:
Timeout/retry/lifecycle boundary changed: yes/no
New states or failure paths introduced:
Contract or non-goals changed: yes/no
Validation to rerun:
```

If `Contract or non-goals changed` is yes, do not dispatch the fix. Obtain the scope decision first. This specifically prevents a local bounded wait from gradually becoming a hard deadline for an entire launch transaction without deliberate approval.

## Re-review package

Every re-review receives all of the following:

- frozen contract revision and user exceptions;
- original base, previously reviewed SHA, and current head SHA;
- complete current branch diff;
- delta since the previously reviewed SHA;
- finding ledger with prior decisions and evidence;
- checks executed for the current head.

Ask reviewers to verify fixed findings, interaction effects, and genuinely new defects. A new finding must name the changed or directly affected behavior that makes it eligible. Reviewers must not reopen a rejected or verified finding without new evidence.

## Convergence stop condition

Stop dispatching additional code fixes and return to the contract decision when either condition occurs:

- two consecutive re-reviews each introduce a new blocker that requires widening an architectural boundary; or
- a proposed fix reverses a design decision made by an earlier review round.

At that point, preserve the worktree and evidence. Do not automatically reset, revert, or add another fix commit. Present the smallest choices:

1. rewrite from the frozen behavior contract;
2. explicitly expand the contract and validation scope;
3. split the dependency into a separate contribution;
4. defer or close the contribution with the unresolved reason.

After a choice, supersede affected ledger entries, create a new contract revision, and perform one complete branch review. The contribution is review-converged only when no eligible blocking item remains, the full current diff has been reviewed, and verification gaps are stated accurately.
