# Upstream-Native Style Review

Use this checklist on the staged diff and again on the full branch diff. The comparison baseline is the target upstream tree, not the downstream fork.

## Read context first

For each changed function or class:

1. read the full definition;
2. read direct callers and the API signature being invoked;
3. read two or more adjacent upstream examples that solve a similar problem;
4. inspect upstream tests for naming and fixture patterns;
5. compare the proposed code with upstream `main`, not with a stale local copy.

## Redundancy and code flavor

Actively remove these porting artifacts unless the upstream code around them establishes the same pattern:

- explicit keyword arguments whose values equal the callee's defaults;
- one-use locals introduced only to rename a literal, default, or direct expression;
- underscore-prefixed one-use variables, constants, parameters, or helpers with no real reuse or abstraction value;
- wrapper helpers that forward unchanged arguments to a single call site;
- defensive branches for states the upstream API makes impossible;
- comments that narrate obvious code or explain downstream history instead of upstream intent;
- copied type annotations, logging, exception handling, or naming conventions that differ from adjacent upstream code;
- expanded configuration or feature flags where upstream uses an existing default behavior.

An underscore prefix does not make a disposable name harmless. Ask whether deleting the name and using the existing default or expression makes the upstream code clearer.

## API and lifecycle fit

Verify:

- called arguments match the current upstream signature and semantics;
- omitted arguments intentionally use upstream defaults;
- error and retry behavior matches upstream call sites;
- singleton, configuration, UI signal, translation, resource-loading, and cooperative-stop patterns match upstream reality;
- no downstream-only import, config key, debug switch, release channel, asset path, issue archive, agent tool, or local script enters the diff;
- no downstream refactor is carried merely because the fix was originally implemented inside it.

## Scope and test fit

Verify:

- every changed line traces to the behavior contract, regression test, or necessary upstream adaptation;
- automated tests are retained or rewritten when upstream supports them;
- test names describe behavior rather than the downstream incident;
- generated files are changed only through their upstream generator;
- changelog and release metadata follow upstream policy rather than downstream policy.

## Review output

Record each item as one of:

- `blocking`: fork contamination, incorrect upstream behavior, or confirmed regression;
- `simplify`: redundant or non-native construction that should be removed before PR;
- `accepted`: difference justified by upstream context;
- `unverified`: context or runtime evidence still missing.

Do not approve while any `blocking` or unexplained `unverified` item remains.

For re-review, preserve each item's stable finding ID and prior disposition. A newly reported blocker must identify the changed or directly affected path that makes it part of this contribution. Record pre-existing or unrelated concerns as follow-up observations rather than widening the patch.
