# Automation Implementation and Review

## Contents

1. API defaults
2. Image search behavior
3. Minimal abstraction
4. Desktop-automation tradeoffs
5. Self-review

## 1. API defaults

- Read source signatures before calling `auto.*`, `ImageUtils.*`, `find_element`, `click_element`, or `ocr.*`.
- Pass an argument explicitly only when it intentionally changes behavior from the default or makes a non-obvious contract safer.
- Judge defaults from the mechanism and failure evidence, not one accidental success.
- Do not change model, threshold, search type, and retry count together. Isolate the behavioral difference.
- Remove explicit arguments that equal current defaults unless repository context proves the explicitness communicates a durable invariant.

## 2. Image search behavior

Answer these before changing matching code:

1. Is the search full-screen, near a template bbox, or inside a caller-provided crop?
2. Does the current loader crop the template because of its asset type or suffix?

Templates with asset bboxes commonly constrain the search; a missing bbox commonly permits a broad search. `model` controls bbox expansion or whether the bbox is ignored. Read current source instead of recalling numeric values.

When broad search appears necessary, first verify that template naming, bbox, scale, and crop express the intended location. Do not replace `ImageUtils.match_template()` with raw `cv2.matchTemplate()` unless the task explicitly requires a pipeline comparison and the difference is explained.

For user screenshots, derive scale from the actual image, not the configured window size. Load `replay-matching` for the complete production-equivalent pipeline.

## 3. Minimal abstraction

- Inline a short single-caller helper unless its name captures an important reason or lifecycle boundary.
- Remove a parameter when all callers pass the same value and no near-term variant is real.
- Do not extract a self-explanatory one-use value into a constant, especially an underscore-prefixed disposable name.
- Keep a simple coordinate offset at the call site; extract repeated or genuinely multi-step calculations.
- Do not create a parameter-heavy retry framework merely because several loops look similar.
- Defensive cleanup must correspond to a reachable recoverable state; do not add clicks or resets after a transition already removes the old UI.

## 4. Desktop-automation tradeoffs

- A simple behavior verified on the real UI can be safer than an unverified configurable abstraction.
- Every automated action changes UI state. Recovery must target an identified state rather than adding a hopeful extra click.
- Understand hierarchy, template regions, and rendering timing before adding branches and tuning parameters.
- Duplication alone does not justify abstraction; compare abstraction cost with realistic reuse.
- A simple action should not become a single-call `_prepare` → `_open` → `_click` chain.

## 5. Self-review

- Does each new argument differ from the default for an evidence-backed reason?
- Does each new function have multiple callers or real semantic/documentation value?
- Is each failure branch reachable and its recovery state-specific?
- Did the change add unrelated cleanup, logging, config, or debug state?
- Can a large diff be reduced to a small behavior-equivalent change?

Code-index results about single callers, clones, or complexity are review leads, not mechanical refactoring orders.
