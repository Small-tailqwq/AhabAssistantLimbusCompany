import os
import sys

sys.path.insert(0, r'C:\Users\Ko_teiru\Documents\code\AhabAssistantLimbusCompany')

import cv2
import numpy as np
from PIL import Image

from module.config import cfg
from utils.image_utils import ImageUtils
from utils.path_manager import path_manager

path_manager.initialize_paths()
path_manager.set_theme("default")
path_manager.set_language("en")

BASE = r'C:\Users\Ko_teiru\Documents\code\AhabAssistantLimbusCompany'

# 三张截图
SCREENSHOTS = {
    "主界面(205712)": "screenshot_20260526_205712.png",
    "Drive已开(204726)": "screenshot_20260526_204726.png",
    "高分辨率(223519)": "screenshot_20260508_223519.png",
}

# back_init_menu 关心的全部元素
TARGETS = [
    "home/window_assets.png",
    "home/mail_assets.png",
    "home/drive_assets.png",
    "home/back_assets.png",
    "battle/battle_finish_confirm_assets.png",
    "battle/setting_assets.png",
    "base/notification_close_assets.png",
    "base/clear_all_caches_assets.png",
    "base/only_option_assets.png",
    "base/waiting_assets.png",
    "base/waiting_2_assets.png",
    "home/close_anniversary_event_assets.png",
    "home/first_prompt_assets.png",
    "home/enkephalin_box_assets.png",
    "enkephalin/enkephalin_cancel_assets.png",
    "base/renew_confirm_assets.png",
    "home/luxcavation_assets.png",
    "home/inferno_bus_assets.png",
    "lxucavation/thread_enter_assets.png",
    "luxcavation/thread_assets.png",
    "luxcavation/exp_enter.png",
]

# 严格复现 AALC _load_template_for_path + match_template 流程
def aalc_match(scr_gray, target, model="clam"):
    paths = ImageUtils.existing_image_paths(target)
    if not paths:
        return None, None, None
    best_val = 0
    best_pos = None
    best_path = None
    for p in paths:
        tpl = ImageUtils.load_from_specific_path(target, p, resize=True)
        if tpl is None:
            continue
        bbox = ImageUtils.get_bbox(tpl)
        tpl_c = ImageUtils.crop(tpl, bbox)
        if tpl_c.size == 0:
            continue
        pos, val = ImageUtils.match_template(scr_gray, tpl_c, bbox, model=model)
        if val is not None and val > best_val:
            best_val = val
            best_pos = pos
            best_path = p
    return best_val, best_pos, best_path


for label, fname in SCREENSHOTS.items():
    path = os.path.join(BASE, fname)
    pil = Image.open(path).convert("RGB")
    scr_np = np.array(pil)
    scr_gray = cv2.cvtColor(scr_np, cv2.COLOR_RGB2GRAY)
    actual_h = scr_gray.shape[0]

    # 如果截图不是 set_win_size 的分辨率, 缩放到 set_win_size
    if actual_h != cfg.set_win_size:
        scale = cfg.set_win_size / actual_h
        scr_gray = cv2.resize(scr_gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        scr_np = cv2.resize(scr_np, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    print(f"\n{'='*80}")
    print(f"  {label}  → {scr_gray.shape[1]}x{scr_gray.shape[0]} (原始={actual_h})")
    print(f"{'='*80}")
    print(f"{'目标':<45} {'clam(bbox±30)':>13} {'aggressive(全屏)':>16} {'最优路径':>20}")
    print("-" * 96)

    for target in TARGETS:
        # model=clam (与 back_init_menu 前10轮一致)
        v1, p1, path1 = aalc_match(scr_gray, target, model="clam")
        # model=aggressive (后备)
        v2, p2, path2 = aalc_match(scr_gray, target, model="aggressive")

        s1 = f"{v1:.3f}" if v1 is not None else "N/A"
        s2 = f"{v2:.3f}" if v2 is not None else "N/A"
        best = max(filter(None, [v1, v2]), default=-1)
        mark = ""
        if best >= 0.8:
            mark = " ✓✓✓"
        elif best >= 0.7:
            mark = " ✓✓"
        elif best >= 0.6:
            mark = " ✓"

        best_path = path1 or path2 or ""
        print(f"{target:<45} {s1:>8} @ {str(p1 or ''):<12} {s2:>8} @ {str(p2 or ''):<12} {best_path or '':>20}{mark}")

print("\nmodel=clam = 在bbox±30px区域内搜索 (back_init_menu默认)")
print("model=aggressive = 全屏搜索")
