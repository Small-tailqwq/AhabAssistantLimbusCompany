import sys

sys.path.insert(0, r'C:\Users\Ko_teiru\Documents\code\AhabAssistantLimbusCompany')
import cv2
import numpy as np

from utils.image_utils import ImageUtils
from utils.path_manager import path_manager

path_manager.initialize_paths()
path_manager.set_theme("default")
path_manager.set_language("en")

for target in ["home/window_assets.png", "home/mail_assets.png", "home/drive_assets.png",
               "home/luxcavation_assets.png", "luxcavation/thread_enter_assets.png"]:
    print(f"\n=== {target} ===")

    for label, resize in [("1440p", False), ("720p", True)]:
        tpl = ImageUtils.load_image(target, resize=resize, gray=False)
        if tpl is None:
            print(f"  {label}: N/A")
            continue
        bbox = ImageUtils.get_bbox(tpl)
        crop = ImageUtils.crop(tpl, bbox)
        # convert to grayscale for content analysis
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        non_zero = np.count_nonzero(gray > 0)
        total = gray.size
        print(f"  {label}: 原始={tpl.shape[1]}x{tpl.shape[0]}  bbox={bbox}  裁剪后={crop.shape[1]}x{crop.shape[0]}  有效像素={non_zero}/{total}")

    paths = ImageUtils.existing_image_paths(target)
    print(f"  存在路径: {paths}")
