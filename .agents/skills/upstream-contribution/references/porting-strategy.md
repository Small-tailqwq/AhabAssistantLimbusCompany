# Porting Strategy

Choose a strategy from evidence, not convenience.

## Decision table

| Condition | Strategy | Method |
|---|---|---|
| Whole commit is single-purpose; paths, APIs, dependencies, defaults, tests, and style match upstream | exact transfer | `git cherry-pick -n <commit>`, then inspect every hunk |
| Core logic matches but a small number of names, signatures, paths, or tests differ | adapt | apply without committing, then rewrite the mismatches |
| Commit is mixed, fork-only concerns are interwoven, or upstream responsibilities differ | behavior rewrite | implement from the behavior contract in upstream code |
| Failure or expected behavior is not established | stop | collect evidence before choosing code |

Exact transfer is the exception. Similar filenames or a clean cherry-pick do not prove semantic compatibility.

## Compatibility questions

Before exact transfer, answer yes to all of these:

- Does upstream expose the same API with the same semantics and default values?
- Do imported symbols exist upstream at the same responsibility boundary?
- Are configuration keys and lifecycle rules shared?
- Does upstream use the same error, logging, translation, and resource-loading patterns?
- Are tests written with the same framework and fixtures?
- Is every hunk required by the behavior contract?

Any uncertain answer changes the strategy to adapt or rewrite.

## Mixed commits

Do not cherry-pick a mixed commit and then trust a visual cleanup. First classify hunks. Apply only the behavior-bearing portions, or rewrite them manually. Preserve a provenance map in the report:

```text
downstream <commit>:path:lines -> upstream path:function -> ported/adapted/excluded
```

## Tests

Tests are part of the behavior port when upstream supports them.

- Prefer a focused regression test that demonstrates the original failure.
- Rewrite fixtures and imports to use upstream conventions.
- Do not import fork-only debug helpers just to reuse a downstream test.
- If reliable automation is impossible, document the manual oracle and why an automated test was not added.

## Dependency and configuration changes

Do not add a dependency, config key, feature flag, debug switch, or generalized abstraction unless the behavior contract truly requires it and upstream has no simpler local pattern. These changes expand maintenance scope and require explicit justification in the PR.
