---
name: replay-matching
description: Use when the user provides screenshots and asks to replay template matching against AALC asset images — verifying log similarity values, diagnosing match failures, or comparing match results across resolutions/models.
license: AGPL-3.0
compatibility: opencode
metadata:
  audience: maintainers
  workflow: issue-diagnosis
---

# AALC Template Matching Replay

## Tool

`debug_tools/verify_matching.py` — CLI template matching verification tool.

```powershell
uv run python debug_tools/verify_matching.py <screenshot>                          # default asset set
uv run python debug_tools/verify_matching.py <screenshot> --minimal                  # minimal asset set
uv run python debug_tools/verify_matching.py <screenshot> --assets KEY1 KEY2 ...     # specific assets
uv run python debug_tools/verify_matching.py <screenshot> --models clam aggressive   # specific models
uv run python debug_tools/verify_matching.py <screenshot> --compare <screenshot2>    # A/B compare
uv run python debug_tools/verify_matching.py <screenshot> --pixel X Y W H             # pixel analysis
```

## Workflow

1. **Determine screenshot resolution** — tool auto-prints `分辨率: WxH scale=N`
2. **Select assets** — use asset keys from the log with `--assets`
3. **Run replay** — recommended `--models clam aggressive` together, compare bbox-restricted vs full-screen results
4. **Analyze results** — look for `***` (≥0.80) / `! ` (≥0.70) tags

## Required reference

Full simulation of `find_element()` → `find_image_element()` → `ImageUtils.match_template()` pipeline is required.
Details in `.opencode/reference/replay_matching.md`:

- `_assets.png` suffix templates MUST undergo bbox cropping, otherwise match values are severely depressed
- Compute scale from screenshot actual height: `scale = screenshot_np.shape[0] / 1440` (NOT `cfg.set_win_size`)
- MUST use `ImageUtils.match_template()`, never raw `cv2.matchTemplate()`

## Common diagnostic patterns

| Symptom | Investigation direction |
|---|---|
| clam < 0.80 but aggressive ≥ 0.80 | bbox search region misses target, possibly scale-induced position drift |
| aggressive < 0.80 | template itself doesn't match, check game version/theme/language |
| clam and aggressive positions differ | clam found a suboptimal false match within bbox region |
| log match values differ from replay | runtime screenshot quality (PrintWindow vs manually saved PNG) |

## Related code

- `utils/image_utils.py` → `ImageUtils.match_template()`, `get_bbox()`, `crop()`
- `module/automation/automation.py` → `find_element()`, `find_image_element()`, `_load_template_for_path()`
- `debug_tools/verify_matching.py` → wraps the above pipeline for CLI replay
