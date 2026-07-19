---
name: code-review
description: Review AALC uncommitted changes, staged diffs, commits, branches, pull requests, upstream contributions, or downstream sync branches for confirmed defects, regressions, automation safety, i18n drift, upstream-style mismatch, unnecessary defaults, one-use underscore variables, and maintainability risks. Use for initial review and every re-review after changes or feedback.
---

# AALC Code Review

Act as the review coordinator. Establish the target, collect enough source context, route domains to named specialist reviewers, verify findings, deduplicate them, and issue one evidence-based verdict. Do not treat a raw diff or a passing test as sufficient review context.

## Resolve the target

| Intent | Evidence to collect |
|---|---|
| Uncommitted work | `git status --short`, unstaged and staged stats/diffs |
| Staged work | `git diff --cached --stat` and full staged diff |
| Commit | `git show --stat <sha>` and full patch |
| Branch | base/head SHAs, commit list, three-dot stat and full diff |
| Pull request | PR metadata, base/head SHAs, full PR diff, checks, prior reviews and unresolved threads |
| Re-review | prior reviewed SHA, current SHA, delta since prior review, full current diff, stable finding ledger and prior decisions |

If no target is specified, review both staged and unstaged changes. Preserve unrelated user work and perform no edits unless the user separately asks for fixes.

## Build review context

Before dispatching reviewers:

1. identify the stated intent and expected behavior;
2. read the full changed definitions, not only patch fragments;
3. read direct callers, API signatures, config schemas, tests, or generators that determine correctness;
4. distinguish changed behavior from pre-existing code;
5. note verification already performed and gaps still open.

For very large diffs, batch by coherent subsystem or behavior. Diff size controls batching depth, not which domain reviewers apply.

## Domain-based reviewer routing

Always run the general correctness review. Add specialists when their domain is touched:

| Reviewer | Select when |
|---|---|
| `code-reviewer` | Always |
| `automation-reviewer` | `module/automation/**`, `module/game_and_screen/**`, `tasks/**`, `app/my_app.py`, config mutation, input, retry/wait, task lifecycle, singleton, or stop behavior |
| `i18n-reviewer` | user-visible UI strings, QWidget lifecycle, translations, localized images, `assets/config/config.example.yaml`, or translation scripts |

For upstream contributions, also provide `.agents/skills/upstream-contribution/references/upstream-style-review.md` to the general reviewer and require comparison with the upstream target tree.

In OpenCode, invoke the custom agents by their exact names. Do not dispatch a `general` agent and ask it to impersonate a named reviewer. In another environment, use equivalent dedicated reviewers when available; otherwise perform the domain checklist synchronously and state that fallback.

Pass each reviewer:

- target and base/head SHAs;
- intent or behavior contract;
- changed-path list and complete diff;
- locations of the full source context already identified;
- relevant prior findings for a re-review;
- only the domain-specific reference it needs.

## Review generated and non-code files proportionally

Do not ignore a file merely because it is generated or binary:

- lockfiles: verify they correspond to intentional dependency-manifest changes and flag unexplained churn;
- compiled translations: verify the source translation and generator relationship rather than line-reviewing binary output;
- images: verify key, language/theme placement, dimensions, and code references when the change depends on them;
- changelog/release metadata: check accuracy when part of release scope;
- minified or bundled output: verify source/generator provenance and unexpected inclusion;
- CI, build scripts, example config, migrations, and update manifests: review as behavior-bearing artifacts.

## Coordinator verification

For every proposed finding:

1. locate the changed line or directly impacted behavior;
2. reproduce the trigger path from source, test, or specification;
3. reject speculative, pre-existing, or preference-only comments;
4. calibrate severity by user impact and reachability;
5. merge duplicates while preserving the clearest trigger and fix direction.

For a re-review, also verify that a new finding is caused by a changed line, newly affected behavior, or a newly evidenced interaction. A pre-existing path that the diff does not newly invoke, change, or rely on is not an eligible blocker.

Do not suppress a concrete defect because it crosses reviewer domains. Assign it to the most relevant domain and keep one finding.

## AALC-specific checks

Confirm changed code respects project invariants, including:

- singleton reuse and `cfg.set_value()` versus `cfg.unsaved_set_value()` semantics;
- mediator-based cross-component communication;
- cooperative stop propagation and bounded waiting;
- PySide6 UI, translation, and theme lifecycle;
- image loading and template-matching pipeline;
- config typing/example synchronization;
- ASCII-only output in `scripts/build.py`;
- no explicit repetition of API defaults without a concrete reason.

For ported code, additionally check one-use underscore-prefixed variables, constants, parameters, and helpers; wrapper-only abstractions; downstream-only scaffolding; and mismatch with adjacent target-tree naming, logging, error handling, or test style.

## Guidance freshness

When a change alters package management, test/build workflow, required environment, directory structure, CI/CD, cross-module contracts, or durable project invariants, assess whether `AGENTS.md`, skills, agents, or mechanical checks need an update. Use `agent-guidance-health` for substantive guidance changes; do not inflate `AGENTS.md` with one-off details.

## Re-review protocol

On every PR or branch update:

1. retain stable finding IDs and verify which prior items are fixed, still present, superseded, disputed, or rejected with evidence;
2. review the delta for regressions introduced by the fix;
3. review the complete current diff for interaction effects;
4. require every genuinely new finding to identify its changed or directly affected trigger path;
5. bind the result to the current head SHA;
6. do not repeat unchanged prose as a new finding or reopen a settled item without new evidence—update its existing state instead.

If a proposed correction widens timeout/retry semantics, lifecycle ownership, public APIs, dependencies, configuration, or explicit non-goals, classify it as a scope decision before asking an implementer to change code. Reviewer severity alone does not authorize scope expansion.

A re-review is required after conflict resolution, maintainer edits, rebase, or any pushed fix that changes reviewed code.

## Verdict matrix

| Highest remaining result | Verdict |
|---|---|
| Confirmed Critical or High defect | **Block** |
| Confirmed Medium production risk, or a repeated pattern of Medium defects | **Warning** |
| Only Low/Suggestion items or non-blocking verification gaps | **Approve with comments** |
| No actionable findings and verification is adequate for the risk | **Approve** |

If verification is materially incomplete, do not use plain **Approve**. Human override instructions may change the merge decision, but record the unresolved technical risk.

## Output

```markdown
## 审阅概览
- 目标与 base/head：
- 意图与风险面：
- 实际调度：
- 已读上下文：
- 已执行验证：

## 发现
- [RV-01] [Critical/High/Medium/Low/Suggestion] `文件:行` [领域] — 触发条件、影响、证据和修复方向。

## 复审状态
- [RV-01] 已修复 / 仍存在 / 新增 / 不再适用：

## 指引保鲜
- 无需更新，或应更新的常驻规则 / skill / 检查：

## 验证缺口与假设
- 只列影响结论的内容。

**裁决：Block / Warning / Approve with comments / Approve**
```

When there are no findings, say so explicitly and still report meaningful verification gaps and the reviewed head SHA.
