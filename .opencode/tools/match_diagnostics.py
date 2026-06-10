"""Template match diagnostic: reproduce the app's matching pipeline step by step."""

import os
from copy import deepcopy

import cv2
import numpy as np
from PIL import Image

# Ensure we run from project root
os.chdir(os.path.dirname(os.path.abspath(__file__)) + "/../..")

SCREENSHOT = "screenshot_20260508_223519.png"
WIN_SIZE = 1440

# ---- helpers that mirror the app ----
def load_asset(rel_path):
    """Mirrors ImageUtils.load_image + _prepare_loaded_image + get_bbox + crop."""
    full = os.path.join(os.getcwd(), rel_path)
    if not os.path.exists(full):
        return None, None
    img = np.array(Image.open(full))
    # _prepare_loaded_image: channel
    if len(img.shape) > 2 and img.shape[2] > 3:
        img = img[:, :, :3].copy()
    # _prepare_loaded_image: resize
    if len(img.shape) == 3:
        gray_load = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    else:
        gray_load = img.copy()
    if WIN_SIZE != 1440:
        fx = WIN_SIZE / 1440
        gray_load = cv2.resize(gray_load, None, fx=fx, fy=fx, interpolation=cv2.INTER_AREA)
    # get_bbox: find non-zero region
    _, thresh = cv2.threshold(gray_load, 0, 255, cv2.THRESH_BINARY)
    coords = cv2.findNonZero(thresh)
    if coords is not None:
        x, y, w, h = cv2.boundingRect(coords)
        bbox = (x, y, x + w, y + h)
        cropped = gray_load[y:y+h, x:x+w]
    else:
        bbox = None
        cropped = gray_load
    return cropped, bbox


def match_template(screenshot_gray, template, bbox_from_template, model="clam"):
    """Exact port of ImageUtils.match_template."""
    height, width = screenshot_gray.shape[:2]
    bbox = deepcopy(bbox_from_template)
    if model == "normal" and bbox is not None:
        bbox = (
            max(bbox[0] - 100, 0),
            max(bbox[1] - 100, 0),
            min(bbox[2] + 100, width),
            min(bbox[3] + 100, height),
        )
    elif model != "aggressive" and bbox is not None:
        bbox = (
            max(bbox[0] - 30, 0),
            max(bbox[1] - 30, 0),
            min(bbox[2] + 30, width),
            min(bbox[3] + 30, height),
        )
    elif model == "aggressive":
        bbox = None

    if bbox is not None:
        sx1, sy1, sx2, sy2 = bbox
        sy1, sy2 = max(sy1,0), min(sy2,height)
        sx1, sx2 = max(sx1,0), min(sx2,width)
        if sy2 > sy1 and sx2 > sx1:
            search_region = screenshot_gray[sy1:sy2, sx1:sx2]
        else:
            search_region = screenshot_gray
    else:
        search_region = screenshot_gray

    result = cv2.matchTemplate(search_region, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
    h_t, w_t = template.shape[:2]
    if bbox is not None:
        cx = bbox[0] + max_loc[0] + w_t // 2
        cy = bbox[1] + max_loc[1] + h_t // 2
    else:
        cx = max_loc[0] + w_t // 2
        cy = max_loc[1] + h_t // 2
    return (cx, cy), max_val


# ---- main ----
scr_color = np.array(Image.open(SCREENSHOT))
scr_gray = cv2.cvtColor(scr_color, cv2.COLOR_RGB2GRAY)
print(f"Screenshot: {scr_gray.shape[1]}x{scr_gray.shape[0]}  ({scr_color.shape[1]}x{scr_color.shape[0]})")

assets = {
    "Problematic (zh_cn)": "assets/images/default/zh_cn/home/mirror_dungeons_assets.png",
    "Problematic (en)":     "assets/images/default/en/home/mirror_dungeons_assets.png",
    "Control drive":        "assets/images/default/share/home/drive_assets.png",
    "Control window":       "assets/images/default/share/home/window_assets.png",
    "Control inferno_bus":  "assets/images/default/share/home/inferno_bus_assets.png",
}

print(f"\n{'Asset':<25} {'Model':<12} {'Score':<8} {'Position':<18} {'Template shape':<16}")
print("-" * 85)
for label, path in assets.items():
    tpl, bbox = load_asset(path)
    if tpl is None:
        print(f"{label:<25} {'NOT FOUND':<12}")
        continue
    for model in ["clam", "normal", "aggressive"]:
        pos, score = match_template(scr_gray, tpl, bbox, model=model)
        tpl_shape = f"{tpl.shape[1]}x{tpl.shape[0]}"
        pos_str = f"({pos[0]},{pos[1]})"
        print(f"{label:<25} {model:<12} {score:<8.4f} {pos_str:<18} {tpl_shape:<16}")

# ---- multi-scale scan for the problematic asset ----
print("\n\n--- Multi-scale (aggressive) for mirror_dungeons_assets ---")
tpl, bbox = load_asset(assets["Problematic (zh_cn)"])
for sf in [0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20]:
    h, w = tpl.shape[:2]
    scaled = cv2.resize(tpl, (max(int(w*sf),1), max(int(h*sf),1)))
    pos, score = match_template(scr_gray, scaled, bbox, model="aggressive")
    print(f"  scale={sf:5.2f}  score={score:.4f}  at ({pos[0]},{pos[1]})")

# ---- try the raw (un-cropped) asset too ----
print("\n--- Raw uncropped asset (aggressive) ---")
full_path = os.path.join(os.getcwd(), "assets/images/default/zh_cn/home/mirror_dungeons_assets.png")
raw_img = np.array(Image.open(full_path))
# Only resize, don't crop
if len(raw_img.shape) > 2:
    raw_gray = cv2.cvtColor(raw_img, cv2.COLOR_RGB2GRAY)
else:
    raw_gray = raw_img.copy()
if WIN_SIZE != 1440:
    fx = WIN_SIZE / 1440
    raw_gray = cv2.resize(raw_gray, None, fx=fx, fy=fx, interpolation=cv2.INTER_AREA)
result = cv2.matchTemplate(scr_gray, raw_gray, cv2.TM_CCOEFF_NORMED)
_, best, _, best_loc = cv2.minMaxLoc(result)
print(f"  score={best:.4f}  at ({best_loc[0]+raw_gray.shape[1]//2},{best_loc[1]+raw_gray.shape[0]//2})")
print(f"  raw template shape: {raw_gray.shape[1]}x{raw_gray.shape[0]}")

# ---- also check: does drive_assets find the SAME region as mirror_dungeons? ----
# This would indicate the screenshot is NOT showing the mirror dungeon UI at all
print("\n--- Cross-reference: drive_assets match position vs mirror_dungeons ---")
tpl_drive, bbox_drive = load_asset(assets["Control drive"])
pos_drive, score_drive = match_template(scr_gray, tpl_drive, bbox_drive, model="aggressive")
print(f"  drive_assets: score={score_drive:.4f} at ({pos_drive[0]},{pos_drive[1]})")
tpl_mirror, bbox_mirror = load_asset(assets["Problematic (zh_cn)"])
pos_mirror, score_mirror = match_template(scr_gray, tpl_mirror, bbox_mirror, model="aggressive")
print(f"  mirror_dungeons_assets: score={score_mirror:.4f} at ({pos_mirror[0]},{pos_mirror[1]})")
print(f"  Position delta: dx={pos_mirror[0]-pos_drive[0]}, dy={pos_mirror[1]-pos_drive[1]}")
