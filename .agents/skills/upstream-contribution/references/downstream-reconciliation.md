# Downstream Reconciliation

Use the final upstream repository state as the source of truth. The originally submitted branch is not authoritative after maintainer edits, squash merges, alternative fixes, or conflict resolutions.

## Identify the final upstream behavior

Fetch upstream and obtain the final PR state. For a merged PR, record the merge, squash, or rebased commit SHA and inspect its complete patch. For a closed PR, search upstream for an alternative commit that satisfies the behavior contract.

Compare:

1. original downstream behavior and test;
2. submitted contribution branch;
3. final upstream implementation;
4. current downstream branch.

## Reconciliation outcomes

| Outcome | Action |
|---|---|
| Downstream is behaviorally equivalent to final upstream | record equivalence; no duplicate commit |
| Upstream refined or corrected the submitted fix | use `downstream-sync` to port the final upstream delta |
| Upstream implemented an alternative fix | evaluate and port that behavior rather than preserving local authorship |
| PR closed and no upstream fix exists | retain downstream fix if valid; record rejection reason and remaining divergence |
| Downstream contains obsolete scaffolding after upstream-native rewrite | create a focused downstream cleanup with regression coverage |

Use patch identity and behavior comparison, not commit title or author, to decide whether a fix already exists.

## Verification

Run the original regression oracle against current downstream after reconciliation. Also run checks required by any upstream refinement. Confirm that config, debug, release, or compatibility code intentionally retained downstream is still necessary.

The final report must state which upstream SHA was compared, which downstream SHA was verified, and whether any fork-only difference remains by design.
