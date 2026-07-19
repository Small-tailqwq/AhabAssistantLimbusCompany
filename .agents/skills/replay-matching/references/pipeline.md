# Template Matching Replay Pipeline

## Required production-equivalent path

Reproduce `find_element()` → `find_image_element()` → `ImageUtils.match_template()` rather than calling raw OpenCV matching.

```python
# 1. Derive scale from the actual screenshot.
scale = screenshot_np.shape[0] / 1440.0

# 2. Load the repository asset through the same language/theme resolution used by production.
# 3. Resize the template consistently with the production loader.
# 4. Convert channels as ImageUtils expects.
# 5. Crop transparent/text assets with their production bbox rule.
# 6. Call ImageUtils.match_template(screen_np, template, bbox, model=model).
```

Read the current implementations before reproducing details:

- `utils/image_utils.py`: `load_image`, `get_bbox`, `crop`, `match_template`, and normalization helpers;
- `module/automation/automation.py`: `find_element`, `find_image_element`, and template loading;
- `debug_tools/verify_matching.py`: supported CLI replay path.

The code is authoritative if it differs from old issue notes.

## Scale

Use screenshot height, not configured window size:

```python
scale = screenshot_np.shape[0] / 1440.0
```

`cfg.set_win_size` can differ from the captured PNG or runtime frame. Record nonstandard aspect ratios or additional borders because height-only scaling may not explain them.

## `_assets.png` bbox behavior

Templates with transparent or empty surroundings must follow the production bbox/crop path. Skipping it can make background dominate similarity and can also change the reported center.

Do not blindly apply a filename rule copied from this reference. Confirm the current loader's condition and returned bbox in the incident's source version.

## Matching models

Model names control the search area in `ImageUtils.match_template()`:

- `clam`: narrow search around expected bbox;
- `normal`: broader bounded search;
- `aggressive`: unrestricted or broadest search.

Verify exact expansion values in current source rather than hardcoding remembered pixel counts in a diagnosis.

## Channel and capture differences

Check RGB/BGR/gray conversion, alpha removal, resizing interpolation, screenshot backend, compression, DPI scaling, emulator borders, and overlays. A manually saved screenshot can differ from a runtime `PrintWindow`, OBS, or emulator frame even at the same nominal resolution.

## Reproduction record

Capture:

```text
Incident version/source:
Screenshot path and dimensions:
Asset key and resolved asset path:
Scale and bbox:
Model and threshold:
Similarity and center:
Runtime log value and center:
Difference and supported explanation:
```
