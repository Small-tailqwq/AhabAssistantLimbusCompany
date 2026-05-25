from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image


BASE = Path(__file__).resolve().parent
ATLAS_PATH = BASE / "archive/2026-04-30_card_pack_extraction/extracted/other/local_assets/Icon_buf_3.png"
SCREENSHOT_PATH = BASE / "screenshot_20260524_215912.png"
REF_TEMPLATE_PATH = BASE / "assets/images/default/share/mirror/shop/enhance_gifts/burn.png"
OUT_DIR = BASE / "archive/2026-04-30_card_pack_extraction/extracted/other/local_assets/_debug_buf3_candidates"

# These are the two clear burn icon locations on screenshot_20260524_215912.png
TRUE_POINTS = [(1066, 570), (1203, 570)]
FALSE_POINT = (1825, 580)


def score_at_center(response: np.ndarray, center_x: int, center_y: int, tpl_w: int, tpl_h: int) -> float | None:
    x = int(center_x - tpl_w // 2)
    y = int(center_y - tpl_h // 2)
    if 0 <= x < response.shape[1] and 0 <= y < response.shape[0]:
        return float(response[y, x])
    return None


def nms_count(response: np.ndarray, tpl_w: int, tpl_h: int, threshold: float = 0.8) -> tuple[int, bool]:
    loc = np.where(response >= threshold)
    points = list(zip(*loc[::-1]))
    points.sort(key=lambda p: response[p[1], p[0]], reverse=True)

    kept: list[tuple[int, int]] = []
    for pt in points:
        if all(np.linalg.norm(np.array(pt) - np.array(other)) > 10 for other in kept):
            kept.append(pt)

    centers = [(int(pt[0] + tpl_w / 2), int(pt[1] + tpl_h / 2)) for pt in kept]
    has_false = any(abs(px - FALSE_POINT[0]) < 30 and abs(py - FALSE_POINT[1]) < 30 for px, py in centers)
    return len(centers), has_false


def analyze_template(
    screenshot_rgb: np.ndarray,
    screenshot_gray: np.ndarray,
    template_rgb: np.ndarray,
    scale: float,
) -> dict:
    scaled = cv2.resize(template_rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    scaled_gray = cv2.cvtColor(scaled, cv2.COLOR_RGB2GRAY)

    response_gray = cv2.matchTemplate(screenshot_gray, scaled_gray, cv2.TM_CCOEFF_NORMED)
    response_rgb = cv2.matchTemplate(screenshot_rgb, scaled, cv2.TM_CCOEFF_NORMED)

    tpl_h, tpl_w = scaled_gray.shape[:2]

    true_gray = [score_at_center(response_gray, x, y, tpl_w, tpl_h) for x, y in TRUE_POINTS]
    true_gray = [v for v in true_gray if v is not None]
    true_rgb = [score_at_center(response_rgb, x, y, tpl_w, tpl_h) for x, y in TRUE_POINTS]
    true_rgb = [v for v in true_rgb if v is not None]

    false_gray = score_at_center(response_gray, FALSE_POINT[0], FALSE_POINT[1], tpl_w, tpl_h)
    false_rgb = score_at_center(response_rgb, FALSE_POINT[0], FALSE_POINT[1], tpl_w, tpl_h)

    count_gray, has_false_gray = nms_count(response_gray, tpl_w, tpl_h, threshold=0.8)
    count_rgb, has_false_rgb = nms_count(response_rgb, tpl_w, tpl_h, threshold=0.8)

    return {
        "scaled_size": (tpl_w, tpl_h),
        "max_gray": float(response_gray.max()),
        "max_rgb": float(response_rgb.max()),
        "true_mean_gray": float(np.mean(true_gray)) if true_gray else None,
        "true_mean_rgb": float(np.mean(true_rgb)) if true_rgb else None,
        "false_gray": false_gray,
        "false_rgb": false_rgb,
        "delta_gray": (float(np.mean(true_gray)) - false_gray) if true_gray and false_gray is not None else None,
        "delta_rgb": (float(np.mean(true_rgb)) - false_rgb) if true_rgb and false_rgb is not None else None,
        "count_08_gray": count_gray,
        "count_08_rgb": count_rgb,
        "has_false_08_gray": has_false_gray,
        "has_false_08_rgb": has_false_rgb,
    }


def make_ref_sized(rgb: np.ndarray, out_w: int, out_h: int) -> np.ndarray:
    return cv2.resize(rgb, (out_w, out_h), interpolation=cv2.INTER_AREA)


def main() -> None:
    atlas = np.array(Image.open(ATLAS_PATH))
    screenshot_rgb = np.array(Image.open(SCREENSHOT_PATH).convert("RGB"))
    screenshot_gray = cv2.cvtColor(screenshot_rgb, cv2.COLOR_RGB2GRAY)

    ref_rgba = np.array(Image.open(REF_TEMPLATE_PATH))
    ref_rgb = ref_rgba[:, :, :3]
    ref_gray = cv2.cvtColor(ref_rgb, cv2.COLOR_RGB2GRAY)
    ref_h, ref_w = ref_gray.shape

    scale = 1080 / 1440

    # Baseline current template
    baseline = analyze_template(screenshot_rgb, screenshot_gray, ref_rgb, scale)

    alpha_mask = (atlas[:, :, 3] > 5).astype(np.uint8)
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(alpha_mask, connectivity=8)

    results: list[dict] = []
    for label in range(1, num_labels):
        x, y, w, h, area = map(int, stats[label])
        crop_rgba = atlas[y : y + h, x : x + w]
        crop_rgb = crop_rgba[:, :, :3]

        cand_rgb = make_ref_sized(crop_rgb, ref_w, ref_h)
        cand_gray = cv2.cvtColor(cand_rgb, cv2.COLOR_RGB2GRAY)
        sim_to_ref = float(cv2.matchTemplate(cand_gray, ref_gray, cv2.TM_CCOEFF_NORMED)[0, 0])

        eval_data = analyze_template(screenshot_rgb, screenshot_gray, cand_rgb, scale)
        results.append(
            {
                "label": label,
                "bbox": (x, y, w, h),
                "area": area,
                "sim_to_ref_gray": sim_to_ref,
                **eval_data,
                "template_rgb": cand_rgb,
            }
        )

    by_ref = sorted(results, key=lambda row: row["sim_to_ref_gray"], reverse=True)
    by_delta_gray = sorted(
        [row for row in results if row["delta_gray"] is not None],
        key=lambda row: row["delta_gray"],
        reverse=True,
    )
    by_delta_rgb = sorted(
        [row for row in results if row["delta_rgb"] is not None],
        key=lambda row: row["delta_rgb"],
        reverse=True,
    )

    print("=== Baseline current burn template ===")
    print(baseline)

    def print_rows(title: str, rows: list[dict], limit: int = 10) -> None:
        print(f"\n=== {title} (top {min(limit, len(rows))}) ===")
        for row in rows[:limit]:
            print(
                "label={label:02d} bbox={bbox} area={area} sim={sim:.3f} "
                "true_g={tg:.3f} false_g={fg:.3f} d_g={dg:.3f} cnt_g={cg} false_g@0.8={hfg} "
                "true_r={tr:.3f} false_r={fr:.3f} d_r={dr:.3f} cnt_r={cr} false_r@0.8={hfr}".format(
                    label=row["label"],
                    bbox=row["bbox"],
                    area=row["area"],
                    sim=row["sim_to_ref_gray"],
                    tg=row["true_mean_gray"] if row["true_mean_gray"] is not None else float("nan"),
                    fg=row["false_gray"] if row["false_gray"] is not None else float("nan"),
                    dg=row["delta_gray"] if row["delta_gray"] is not None else float("nan"),
                    cg=row["count_08_gray"],
                    hfg=row["has_false_08_gray"],
                    tr=row["true_mean_rgb"] if row["true_mean_rgb"] is not None else float("nan"),
                    fr=row["false_rgb"] if row["false_rgb"] is not None else float("nan"),
                    dr=row["delta_rgb"] if row["delta_rgb"] is not None else float("nan"),
                    cr=row["count_08_rgb"],
                    hfr=row["has_false_08_rgb"],
                )
            )

    print_rows("Closest to existing burn template", by_ref, limit=10)
    print_rows("Best delta on grayscale", by_delta_gray, limit=10)
    print_rows("Best delta on RGB", by_delta_rgb, limit=10)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    exported: set[int] = set()
    for row in by_ref[:6] + by_delta_gray[:6] + by_delta_rgb[:6]:
        label = row["label"]
        if label in exported:
            continue
        exported.add(label)
        out_name = (
            f"label_{label:02d}_sim_{row['sim_to_ref_gray']:.3f}_"
            f"dg_{row['delta_gray'] if row['delta_gray'] is not None else -9:.3f}_"
            f"dr_{row['delta_rgb'] if row['delta_rgb'] is not None else -9:.3f}.png"
        )
        out_path = OUT_DIR / out_name
        Image.fromarray(row["template_rgb"]).save(out_path)

    print(f"\nExported {len(exported)} candidate crops to: {OUT_DIR}")


if __name__ == "__main__":
    main()
