"""Template matching verification tool for issue diagnosis.

Replays the full find_element -> find_image_element -> ImageUtils.match_template
pipeline against a screenshot using specific asset keys. Supports A/B comparison
against a second screenshot.

Usage:
    uv run python debug_tools/verify_matching.py <screenshot>
    uv run python debug_tools/verify_matching.py <screenshot> --minimal
    uv run python debug_tools/verify_matching.py <screenshot> --compare <screenshot2>
    uv run python debug_tools/verify_matching.py <screenshot> --assets KEY1 KEY2 ...
    uv run python debug_tools/verify_matching.py <screenshot> --pixel X Y W H
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.image_utils import ImageUtils  # noqa: E402

ASSETS_BASE = PROJECT_ROOT / "assets" / "images"

# Default assets for common issue diagnosis
DEFAULT_ASSETS = [
    "teams/identify_assets.png",
    "teams/12_sinner_live_assets.png",
    "teams/none_sinner_assets.png",
    "battle/chaim_to_battle_assets.png",
    "battle/normal_to_battle_assets.png",
    "battle/select_none_assets.png",
    "battle/more_information_assets.png",
    "battle/in_mirror_assets.png",
    "battle/win_rate_card.png",
    "mirror/road_to_mir/select_team_stars_assets.png",
    "mirror/road_in_mir/legend_assets.png",
    "mirror/road_in_mir/enter_assets.png",
    "mirror/road_in_mir/acquire_ego_gift_card.png",
    "mirror/road_in_mir/ego_gift_get_confirm_assets.png",
    "mirror/shop/shop_coins_assets.png",
    "mirror/road_in_mir/select_encounter_reward_card_assets.png",
    "event/skip_assets.png",
    "mirror/theme_pack/feature_theme_pack_assets.png",
    "mirror/claim_reward/claim_rewards_assets.png",
    "mirror/claim_reward/battle_statistics_assets.png",
    "home/drive_assets.png",
    "home/window_assets.png",
    "home/first_prompt_assets.png",
    "mirror/road_to_mir/enter_assets.png",
]

MINIMAL_ASSETS = [
    "teams/identify_assets.png",
    "battle/chaim_to_battle_assets.png",
    "battle/normal_to_battle_assets.png",
    "battle/more_information_assets.png",
    "battle/in_mirror_assets.png",
    "mirror/road_to_mir/select_team_stars_assets.png",
]


def find_asset(key):
    for lang in ["zh_cn", "en", "share"]:
        for theme in ["default", "dark"]:
            p = ASSETS_BASE / theme / lang / key
            if p.exists():
                return str(p), f"{theme}/{lang}"
    for theme in ["default", "dark"]:
        p = ASSETS_BASE / theme / "share" / key
        if p.exists():
            return str(p), f"{theme}/share"
    return None, None


def match_one(screen, key, model="clam"):
    """Replay the full matching pipeline for a single asset key."""
    tpl_path, _ = find_asset(key)
    if tpl_path is None:
        return None, None
    scale = screen.shape[0] / 1440.0
    tpl_raw = cv2.imread(tpl_path, cv2.IMREAD_UNCHANGED)
    if tpl_raw is None:
        return None, None
    if tpl_raw.shape[2] == 4:
        tpl_bgr = tpl_raw[:, :, :3].copy()
    else:
        tpl_bgr = tpl_raw.copy()
    if abs(scale - 1.0) > 1e-6:
        tpl_bgr = cv2.resize(tpl_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    tpl_gray = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY)
    bbox = None
    if key.endswith("_assets.png"):
        bbox = ImageUtils.get_bbox(tpl_gray)
        tpl_gray = ImageUtils.crop(tpl_gray, bbox)
    center, max_val = ImageUtils.match_template(screen, tpl_gray, bbox, model=model)
    return max_val, center


def print_asset_row(key, model, val, center):
    tag = " ***" if (val is not None and val >= 0.80) else ("  ! " if (val is not None and val >= 0.70) else "    ")
    vs = f"{val:.3f}" if val is not None else "N/A"
    cs = f"({center[0]:.0f},{center[1]:.0f})" if center else "N/A"
    print(f"  {key:58s} {model:8s} {vs:>8s} {cs:16s}{tag}")


def run_single(screenshot_path, assets, models):
    screen = cv2.imread(screenshot_path, cv2.IMREAD_COLOR)
    if screen is None:
        print(f"ERROR: 无法加载截图 {screenshot_path}")
        sys.exit(1)
    h, w = screen.shape[:2]
    print(f"截图: {screenshot_path}")
    print(f"分辨率: {w}x{h}  scale={h/1440:.3f}")
    print()
    print(f"{'资产':58s} {'model':8s} {'匹配值':>8s} {'位置':16s}")
    print("-" * 96)

    for key in assets:
        for model in models:
            val, center = match_one(screen, key, model)
            print_asset_row(key, model, val, center)


def run_compare(a_path, b_path, assets, models):
    a = cv2.imread(a_path, cv2.IMREAD_COLOR)
    b = cv2.imread(b_path, cv2.IMREAD_COLOR)
    for label, sc in [("A", a), ("B", b)]:
        if sc is None:
            print(f"ERROR: 无法加载截图 {a_path if label=='A' else b_path}")
            sys.exit(1)
    ha, wa = a.shape[:2]
    hb, wb = b.shape[:2]
    print(f"截图A: {a_path}")
    print(f"       {wa}x{ha}  scale={ha/1440:.3f}")
    print(f"截图B: {b_path}")
    print(f"       {wb}x{hb}  scale={hb/1440:.3f}")
    print()
    header = f"{'资产':30s} {'model':8s} {'  截图A':>8s} {'  截图B':>8s} {'  Δ':>5s} {'A_pos':15s} {'B_pos':15s}"
    print(header)
    print("-" * len(header))

    for key in assets:
        for model in models:
            va, ca = match_one(a, key, model)
            vb, cb = match_one(b, key, model)
            va_s = f"{va:.3f}" if va is not None else "N/A"
            vb_s = f"{vb:.3f}" if vb is not None else "N/A"
            dv_s = f"{va-vb:+.3f}" if (va is not None and vb is not None) else "N/A"
            ca_s = f"({ca[0]:.0f},{ca[1]:.0f})" if ca else "N/A"
            cb_s = f"({cb[0]:.0f},{cb[1]:.0f})" if cb else "N/A"
            print(f"  {key:30s} {model:8s} {va_s:>8s} {vb_s:>8s} {dv_s:>5s} {ca_s:15s} {cb_s:15s}")


def run_pixel(screenshot_path, x, y, w, h):
    """Analyze pixel statistics for a rectangular region."""
    screen = cv2.imread(screenshot_path, cv2.IMREAD_COLOR)
    if screen is None:
        print(f"ERROR: 无法加载截图 {screenshot_path}")
        sys.exit(1)
    region = screen[y:y+h, x:x+w]
    if region.size == 0:
        print(f"ERROR: 区域 ({x},{y})-({x+w},{y+h}) 超出截图范围")
        sys.exit(1)
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    mean_bgr = cv2.mean(region)[:3]
    print(f"截图: {screenshot_path}")
    print(f"区域: ({x},{y})-({x+w},{y+h}) 尺寸={region.shape[1]}x{region.shape[0]}")
    print(f"BGR 均值:     B={mean_bgr[0]:.1f}  G={mean_bgr[1]:.1f}  R={mean_bgr[2]:.1f}")
    print(f"灰度 均值/中位数/标准差:  {gray.mean():.1f} / {np.median(gray):.1f} / {gray.std():.1f}")
    print(f"灰度 最小值/最大值:       {gray.min()} / {gray.max()}")
    hist = cv2.calcHist([gray], [0], None, [10], [0, 256]).flatten()
    bins = [f"{i*25:3d}-{(i+1)*25-1:3d}" for i in range(10)]
    print("灰度直方图:")
    print(" bin:   " + " ".join(f"{b:8s}" for b in bins))
    print(" count: " + " ".join(f"{int(h):8d}" for h in hist))
    total = region.shape[0] * region.shape[1]
    dark_pct = hist[0] / total * 100
    bright_pct = hist[9] / total * 100
    print(f"暗区比(0-25): {dark_pct:.1f}%  亮区比(230-255): {bright_pct:.1f}%")


def main():
    parser = argparse.ArgumentParser(description="Template matching verification tool")
    parser.add_argument("screenshot", help="主截图路径")
    parser.add_argument("--minimal", action="store_true", help="仅测试关键资产子集")
    parser.add_argument("--models", nargs="+", default=["clam"], help="匹配模式: clam, normal, aggressive")
    parser.add_argument("--assets", nargs="*", help="自定义资产列表（覆盖默认）")
    parser.add_argument("--compare", help="A/B对照的第二张截图路径")
    parser.add_argument("--pixel", nargs=4, type=int, metavar=("X", "Y", "W", "H"), help="对指定矩形区域做像素分析")
    args = parser.parse_args()

    if args.pixel:
        run_pixel(args.screenshot, *args.pixel)
        return

    if args.assets:
        assets = args.assets
    elif args.minimal:
        assets = MINIMAL_ASSETS
    else:
        assets = DEFAULT_ASSETS

    if args.compare:
        run_compare(args.screenshot, args.compare, assets, args.models)
    else:
        run_single(args.screenshot, assets, args.models)


if __name__ == "__main__":
    main()
