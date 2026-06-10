from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

BASE = Path(__file__).resolve().parent
SYSTEMS = ["burn", "bleed", "tremor", "rupture", "poise", "sinking", "charge", "slash", "pierce", "blunt"]

# Proposed relative shop region from baseline calibration.
REGION_REL = {
    "left": 0.5151,
    "top": 0.3380,
    "right": 0.8844,
    "bottom": 0.7130,
}

INPUTS = [
    BASE / "screenshot_20260524_232156.png",
    BASE / "screenshot_20260524_232231.png",
]

THRESHOLDS = [0.85, 0.8, 0.75, 0.7]


def nms(response: np.ndarray, tpl_w: int, tpl_h: int, threshold: float, min_dist: int = 10):
    loc = np.where(response >= threshold)
    points = list(zip(*loc[::-1]))
    points.sort(key=lambda p: response[p[1], p[0]], reverse=True)

    kept: list[tuple[int, int]] = []
    for pt in points:
        if all(np.linalg.norm(np.array(pt) - np.array(other)) > min_dist for other in kept):
            kept.append(pt)

    return [(int(pt[0] + tpl_w / 2), int(pt[1] + tpl_h / 2), float(response[pt[1], pt[0]])) for pt in kept]


def abs_region(width: int, height: int):
    left = int(round(REGION_REL["left"] * width))
    top = int(round(REGION_REL["top"] * height))
    right = int(round(REGION_REL["right"] * width))
    bottom = int(round(REGION_REL["bottom"] * height))
    return left, top, right, bottom


def evaluate_one(image_path: Path):
    img_rgb = np.array(Image.open(image_path).convert("RGB"))
    img_gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    h, w = img_rgb.shape[:2]

    region = abs_region(w, h)
    scale = h / 1440.0

    per_threshold = {}

    for th in THRESHOLDS:
        total = 0
        inside = 0
        outside = []
        hits = []
        for system in SYSTEMS:
            tpl_path = BASE / f"assets/images/default/share/mirror/shop/enhance_gifts/{system}.png"
            tpl_rgb = np.array(Image.open(tpl_path).convert("RGB"))
            tpl_rgb = cv2.resize(tpl_rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            tpl_gray = cv2.cvtColor(tpl_rgb, cv2.COLOR_RGB2GRAY)

            response = cv2.matchTemplate(img_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
            tpl_h, tpl_w = tpl_gray.shape[:2]
            matches = nms(response, tpl_w, tpl_h, threshold=th)

            for x, y, score in matches:
                total += 1
                in_region = region[0] <= x <= region[2] and region[1] <= y <= region[3]
                if in_region:
                    inside += 1
                else:
                    outside.append((system, x, y, round(score, 3)))
                hits.append((system, x, y, score, in_region))

        per_threshold[th] = {
            "total": total,
            "inside": inside,
            "outside": outside,
            "hits": hits,
        }

    return {
        "image_path": image_path,
        "size": (w, h),
        "region": region,
        "scale": scale,
        "per_threshold": per_threshold,
        "img_rgb": img_rgb,
    }


def draw_overlay(result: dict, threshold: float = 0.75) -> Path:
    w, h = result["size"]
    region = result["region"]
    image = Image.fromarray(result["img_rgb"]).convert("RGB")
    draw = ImageDraw.Draw(image)

    draw.rectangle(region, outline=(255, 60, 60), width=4)

    hits = result["per_threshold"][threshold]["hits"]
    for _, x, y, score, in_region in hits:
        color = (40, 220, 80) if in_region else (255, 120, 0)
        r = 4 if score >= 0.8 else 3
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color, outline=(0, 0, 0))

    out_path = result["image_path"].with_name(result["image_path"].stem + "_region_eval_075.png")
    image.save(out_path)
    return out_path


def main() -> None:
    for image_path in INPUTS:
        result = evaluate_one(image_path)
        overlay = draw_overlay(result, threshold=0.75)
        w, h = result["size"]
        region = result["region"]
        print(f"\n=== {image_path.name} ({w}x{h}) ===")
        print(f"scale_to_1440={result['scale']:.4f}")
        print(f"region_abs={region}")
        print(
            "region_rel=({:.4f}, {:.4f})-({:.4f}, {:.4f})".format(
                region[0] / w,
                region[1] / h,
                region[2] / w,
                region[3] / h,
            )
        )
        for th in THRESHOLDS:
            info = result["per_threshold"][th]
            total = info["total"]
            inside = info["inside"]
            outside = info["outside"]
            print(f"th={th:.2f}: inside/total={inside}/{total}, outside={len(outside)}")
            if outside:
                print(f"  outside_samples={outside[:8]}")
        print(f"overlay={overlay}")


if __name__ == "__main__":
    main()
