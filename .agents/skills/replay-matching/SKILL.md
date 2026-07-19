---
name: replay-matching
description: Replay AALC template matching from user screenshots against repository assets, verify logged similarity values, compare resolutions or matching models, diagnose bbox and crop failures, and reproduce the production ImageUtils pipeline. Use only when evidence includes a screenshot or a template-matching question.
---

# AALC Template Matching Replay

Use `debug_tools/verify_matching.py` to reproduce project behavior. Preserve source screenshots and assets; write any derived images under an ignored `logs/<feature>_debug/` directory.

## Read the required pipeline reference

Before interpreting replay values, read [references/pipeline.md](references/pipeline.md). It defines scale, `_assets.png` bbox cropping, channel handling, and model-specific search behavior.

## Commands

```powershell
uv run python debug_tools/verify_matching.py <screenshot>
uv run python debug_tools/verify_matching.py <screenshot> --minimal
uv run python debug_tools/verify_matching.py <screenshot> --assets KEY1 KEY2
uv run python debug_tools/verify_matching.py <screenshot> --models clam aggressive
uv run python debug_tools/verify_matching.py <problem.png> --compare <normal.png> --minimal
uv run python debug_tools/verify_matching.py <screenshot> --pixel X Y W H
```

## Workflow

1. Record screenshot dimensions, language, theme, capture source, and issue version when known.
2. Select exact asset keys from the relevant log or code path.
3. Run `clam` and `aggressive` together when diagnosing search-region drift.
4. Compare replay values, centers, and bounding boxes with the log, not only threshold pass/fail.
5. If values differ, test capture quality, scale, template version, overlay, crop, and runtime/source-version mismatch.
6. Tie conclusions to the production call chain and the incident's source version.

## Interpretation

| Pattern | Investigation direction |
|---|---|
| `clam < threshold`, `aggressive >= threshold` | bbox search region or scaled-position drift |
| both below threshold | template, UI version, language, theme, overlay, or capture quality mismatch |
| models return different centers | constrained search found a different local maximum |
| replay differs from log | runtime screenshot source, compression, scaling, or version mismatch |

These are starting hypotheses. Inspect the actual image and pipeline before claiming root cause.

## Output

Report the screenshot, asset key, scale, models, thresholds, returned values/centers, production path, and any unresolved difference from runtime evidence. Never substitute raw OpenCV matching results for project results.
