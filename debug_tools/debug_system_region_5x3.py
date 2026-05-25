from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


BASE = Path(__file__).resolve().parent
SCREENSHOT_PATH = BASE / "screenshot_20260524_215912.png"
OUT_IMAGE_PATH = BASE / "screenshot_20260524_215912_system_region_5x3.png"

SYSTEMS = ["burn", "bleed", "tremor", "rupture", "poise", "sinking", "charge", "slash", "pierce", "blunt"]


def nms_matches(response: np.ndarray, tpl_w: int, tpl_h: int, threshold: float, min_dist: int = 10):
    loc = np.where(response >= threshold)
    points = list(zip(*loc[::-1]))
    points.sort(key=lambda p: response[p[1], p[0]], reverse=True)

    kept: list[tuple[int, int]] = []
    for pt in points:
        if all(np.linalg.norm(np.array(pt) - np.array(k)) > min_dist for k in kept):
            kept.append(pt)

    return [(int(pt[0] + tpl_w / 2), int(pt[1] + tpl_h / 2), float(response[pt[1], pt[0]])) for pt in kept]


def collect_all_matches(scr_rgb: np.ndarray, threshold: float = 0.75):
    scale = 1080 / 1440
    scr_gray = cv2.cvtColor(scr_rgb, cv2.COLOR_RGB2GRAY)

    result = []
    for system in SYSTEMS:
        tpl_path = BASE / f"assets/images/default/share/mirror/shop/enhance_gifts/{system}.png"
        tpl_rgb = np.array(Image.open(tpl_path).convert("RGB"))
        tpl_rgb = cv2.resize(tpl_rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        tpl_gray = cv2.cvtColor(tpl_rgb, cv2.COLOR_RGB2GRAY)

        response = cv2.matchTemplate(scr_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
        tpl_h, tpl_w = tpl_gray.shape[:2]
        matches = nms_matches(response, tpl_w, tpl_h, threshold=threshold)
        for x, y, score in matches:
            result.append((system, x, y, score))

    return result


def propose_region(matches: list[tuple[str, int, int, float]], width: int, height: int):
    # High-confidence matches define the core area.
    core = [(x, y) for _, x, y, score in matches if score >= 0.85]
    if not core:
        raise ValueError("No high-confidence matches found.")

    xs = [p[0] for p in core]
    ys = [p[1] for p in core]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    # Add margin to tolerate different layouts/resolutions.
    margin_x = int(round(width * 0.04))
    margin_y = int(round(height * 0.06))

    left = max(0, x_min - margin_x)
    right = min(width - 1, x_max + margin_x)
    top = max(0, y_min - margin_y)
    bottom = min(height - 1, y_max + margin_y)

    # Snap to a practical 5x3 shop grid-like rectangle (wider than tall).
    # Keep at least 5 columns x 3 rows coverage feeling in relative terms.
    min_w = int(round(width * 0.32))
    min_h = int(round(height * 0.30))
    cur_w = right - left
    cur_h = bottom - top

    if cur_w < min_w:
        pad = (min_w - cur_w) // 2
        left = max(0, left - pad)
        right = min(width - 1, right + pad)
    if cur_h < min_h:
        pad = (min_h - cur_h) // 2
        top = max(0, top - pad)
        bottom = min(height - 1, bottom + pad)

    return int(left), int(top), int(right), int(bottom)


def draw_region_image(
    src_path: Path,
    out_path: Path,
    region: tuple[int, int, int, int],
    matches: list[tuple[str, int, int, float]],
) -> None:
    image = Image.open(src_path).convert("RGB")
    draw = ImageDraw.Draw(image)

    left, top, right, bottom = region
    draw.rectangle([left, top, right, bottom], outline=(255, 60, 60), width=4)

    # Draw high confidence points in green, others in yellow.
    for _, x, y, score in matches:
        color = (40, 220, 80) if score >= 0.85 else (250, 210, 60)
        r = 4
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color, outline=(0, 0, 0))

    image.save(out_path)


def main() -> None:
    screenshot = np.array(Image.open(SCREENSHOT_PATH).convert("RGB"))
    h, w = screenshot.shape[:2]

    # Threshold 0.75 captures plausible false positives like #8, useful for region design.
    matches = collect_all_matches(screenshot, threshold=0.75)
    region = propose_region(matches, w, h)

    draw_region_image(SCREENSHOT_PATH, OUT_IMAGE_PATH, region, matches)

    left, top, right, bottom = region
    rel = {
        "left": left / w,
        "top": top / h,
        "right": right / w,
        "bottom": bottom / h,
        "width": (right - left) / w,
        "height": (bottom - top) / h,
    }

    print("Proposed region (absolute):", region)
    print("Proposed region (relative):", {k: round(v, 4) for k, v in rel.items()})
    print("Output image:", OUT_IMAGE_PATH)


if __name__ == "__main__":
    main()
