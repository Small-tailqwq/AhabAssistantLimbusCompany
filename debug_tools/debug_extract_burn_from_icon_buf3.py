from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

BASE = Path(__file__).resolve().parent
ATLAS_PATH = BASE / "archive/2026-04-30_card_pack_extraction/extracted/other/local_assets/Icon_buf_3.png"
SCREENSHOT_PATH = BASE / "screenshot_20260524_215912.png"
CURRENT_BURN_PATH = BASE / "assets/images/default/share/mirror/shop/enhance_gifts/burn.png"
OUT_DIR = BASE / "archive/2026-04-30_card_pack_extraction/extracted/other/local_assets/_debug_burn_extract"

TRUE_POINTS = [(1066, 570), (1203, 570)]
FALSE_POINT = (1825, 580)


def score_point(res: np.ndarray, center: tuple[int, int], tpl_size: tuple[int, int]) -> float | None:
    w, h = tpl_size
    x = int(center[0] - w // 2)
    y = int(center[1] - h // 2)
    if 0 <= x < res.shape[1] and 0 <= y < res.shape[0]:
        return float(res[y, x])
    return None


def eval_template(scr_rgb: np.ndarray, tpl_rgb: np.ndarray) -> dict:
    scr_gray = cv2.cvtColor(scr_rgb, cv2.COLOR_RGB2GRAY)
    tpl_gray = cv2.cvtColor(tpl_rgb, cv2.COLOR_RGB2GRAY)

    scale = 1080 / 1440
    tpl_rgb_scaled = cv2.resize(tpl_rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    tpl_gray_scaled = cv2.cvtColor(tpl_rgb_scaled, cv2.COLOR_RGB2GRAY)

    res_gray = cv2.matchTemplate(scr_gray, tpl_gray_scaled, cv2.TM_CCOEFF_NORMED)
    res_rgb = cv2.matchTemplate(scr_rgb, tpl_rgb_scaled, cv2.TM_CCOEFF_NORMED)
    h, w = tpl_gray_scaled.shape[:2]

    true_gray = [score_point(res_gray, p, (w, h)) for p in TRUE_POINTS]
    true_rgb = [score_point(res_rgb, p, (w, h)) for p in TRUE_POINTS]
    true_gray = [v for v in true_gray if v is not None]
    true_rgb = [v for v in true_rgb if v is not None]

    false_gray = score_point(res_gray, FALSE_POINT, (w, h))
    false_rgb = score_point(res_rgb, FALSE_POINT, (w, h))

    return {
        "size": (tpl_rgb.shape[1], tpl_rgb.shape[0]),
        "scaled_size": (w, h),
        "max_gray": float(res_gray.max()),
        "max_rgb": float(res_rgb.max()),
        "true_mean_gray": float(np.mean(true_gray)) if true_gray else None,
        "true_mean_rgb": float(np.mean(true_rgb)) if true_rgb else None,
        "false_gray": false_gray,
        "false_rgb": false_rgb,
        "delta_gray": (float(np.mean(true_gray)) - false_gray) if true_gray and false_gray is not None else None,
        "delta_rgb": (float(np.mean(true_rgb)) - false_rgb) if true_rgb and false_rgb is not None else None,
    }


def find_best_window(atlas_rgb: np.ndarray, ref_rgb: np.ndarray) -> tuple[tuple[int, int], tuple[int, int], float, float]:
    atlas_gray = cv2.cvtColor(atlas_rgb, cv2.COLOR_RGB2GRAY)
    ref_gray = cv2.cvtColor(ref_rgb, cv2.COLOR_RGB2GRAY)

    best = (-1.0, 1.0, (0, 0), (ref_rgb.shape[1], ref_rgb.shape[0]))
    for s in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]:
        tpl = cv2.resize(ref_gray, None, fx=s, fy=s, interpolation=cv2.INTER_LINEAR if s > 1 else cv2.INTER_AREA)
        if tpl.shape[0] >= atlas_gray.shape[0] or tpl.shape[1] >= atlas_gray.shape[1]:
            continue
        res = cv2.matchTemplate(atlas_gray, tpl, cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(res)
        if mx > best[0]:
            best = (float(mx), float(s), (int(loc[0]), int(loc[1])), (int(tpl.shape[1]), int(tpl.shape[0])))

    maxv, scale, loc, size = best
    return loc, size, scale, maxv


def trim_by_alpha(rgba: np.ndarray) -> np.ndarray:
    alpha = rgba[:, :, 3]
    ys, xs = np.where(alpha > 5)
    if len(xs) == 0 or len(ys) == 0:
        return rgba
    x1, x2 = int(xs.min()), int(xs.max()) + 1
    y1, y2 = int(ys.min()), int(ys.max()) + 1
    return rgba[y1:y2, x1:x2]


def to_rgb(rgba: np.ndarray) -> np.ndarray:
    return rgba[:, :, :3]


def main() -> None:
    atlas_rgba = np.array(Image.open(ATLAS_PATH))
    atlas_rgb = atlas_rgba[:, :, :3]
    screenshot_rgb = np.array(Image.open(SCREENSHOT_PATH).convert("RGB"))
    ref_rgba = np.array(Image.open(CURRENT_BURN_PATH))
    ref_rgb = ref_rgba[:, :, :3]

    loc, size, scale, maxv = find_best_window(atlas_rgb, ref_rgb)
    x, y = loc
    w, h = size
    win_rgba = atlas_rgba[y : y + h, x : x + w]
    win_trim = trim_by_alpha(win_rgba)

    # Prepare replacement candidates in current burn template size (41x42)
    ref_w, ref_h = ref_rgb.shape[1], ref_rgb.shape[0]
    cand_a = cv2.resize(to_rgb(win_rgba), (ref_w, ref_h), interpolation=cv2.INTER_AREA)
    cand_b = cv2.resize(to_rgb(win_trim), (ref_w, ref_h), interpolation=cv2.INTER_AREA)

    baseline = eval_template(screenshot_rgb, ref_rgb)
    eval_a = eval_template(screenshot_rgb, cand_a)
    eval_b = eval_template(screenshot_rgb, cand_b)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    Image.fromarray(win_rgba).save(OUT_DIR / "window_raw_rgba.png")
    Image.fromarray(win_trim).save(OUT_DIR / "window_trimmed_rgba.png")
    Image.fromarray(cand_a).save(OUT_DIR / "candidate_a_resize_raw_to_41x42.png")
    Image.fromarray(cand_b).save(OUT_DIR / "candidate_b_resize_trim_to_41x42.png")

    print("Best atlas match window from current burn template:")
    print({"loc": loc, "size": size, "scale": scale, "max_score": maxv})
    print("\nBaseline current burn template:")
    print(baseline)
    print("\nCandidate A (raw window -> 41x42):")
    print(eval_a)
    print("\nCandidate B (trimmed window -> 41x42):")
    print(eval_b)
    print(f"\nSaved debug outputs to: {OUT_DIR}")


if __name__ == "__main__":
    main()
