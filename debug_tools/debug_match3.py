import sys, os
sys.path.insert(0, r'C:\Users\Ko_teiru\Documents\code\AhabAssistantLimbusCompany')

from utils.path_manager import path_manager
from utils.image_utils import ImageUtils
from module.config import cfg
import numpy as np
import cv2
from PIL import Image

base = r'C:\Users\Ko_teiru\Documents\code\AhabAssistantLimbusCompany'

# Manually initialize pic_path like the actual game would
# The cfg was loaded in config.py which calls path_manager.set_language
# Let's check what language the config has
lang = cfg.get_value("language_in_program", "en")
print(f"Config language: '{lang}'")

# The actual game flow: path_manager.set_language is called somewhere
# Let's try to set it
if not path_manager.pic_path:
    # Set to default paths
    path_manager.set_theme(cfg.get_value("theme_mode", "AUTO"))
    print(f"After set_theme, pic_path: {path_manager.pic_path}")

# Load screen
pil_img = Image.open(os.path.join(base, 'screenshot_20260524_215912.png')).convert('RGB')
screen_np = np.array(pil_img)

# Load template directly from the correct path
tpl_path = os.path.join(base, r'assets\images\default\share\mirror\shop\enhance_gifts\burn.png')
tpl_raw = cv2.imread(tpl_path, cv2.IMREAD_UNCHANGED)

# Apply the same preprocessing as ImageUtils._prepare_loaded_image
# Gray=True by default in load_image
# Resize to 1080/1440=0.75 if win_size=1080
win_size = cfg.set_win_size
print(f"win_size: {win_size}")

# Step 1: strip alpha
if tpl_raw.shape[2] == 4:
    tpl_rgb = tpl_raw[:, :, :3].copy()
else:
    tpl_rgb = tpl_raw.copy()

# Step 2: resize
scale = win_size / 1440
if scale != 1.0:
    tpl_rgb = cv2.resize(tpl_rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    print(f"Resized template to {tpl_rgb.shape[1]}x{tpl_rgb.shape[0]} (scale={scale:.3f})")

# Step 3: grayscale (gray=True default)
tpl_gray = cv2.cvtColor(tpl_rgb, cv2.COLOR_RGB2GRAY)
print(f"Template final: {tpl_gray.shape}")

# Run matching using ImageUtils.match_template_with_multiple_targets
for th in [0.85, 0.8, 0.75, 0.7, 0.65]:
    matches = ImageUtils.match_template_with_multiple_targets(screen_np, tpl_gray, th)
    print(f"\nthreshold={th}: {len(matches)} matches")
    for pt in matches:
        near8 = abs(pt[0]-1825)<30 and abs(pt[1]-580)<30
        tag = ' <-- #8 area' if near8 else ''
        print(f"  ({pt[0]:4d},{pt[1]:4d}){tag}")

# Raw score at specific positions
res = cv2.matchTemplate(
    cv2.cvtColor(screen_np, cv2.COLOR_RGB2GRAY),
    tpl_gray,
    cv2.TM_CCOEFF_NORMED
)

print(f"\nMax score: {res.max():.3f}, Min: {res.min():.3f}")
points_of_interest = [
    (1066,432,'#1'), (1204,432,'#2'), (1204,569,'#3'),
    (1616,707,'#4'), (1479,707,'#5'), (1066,707,'#6'),
    (1341,707,'#7'), (1825,580,'#8')
]
w = tpl_gray.shape[1]
h = tpl_gray.shape[0]
print(f"\nTemplate dimensions after resize: {w}x{h}")
for cx, cy, label in points_of_interest:
    x, y = cx - w//2, cy - h//2
    if 0 <= x < res.shape[1] and 0 <= y < res.shape[0]:
        print(f"  {label} ({cx},{cy}): score={res[y,x]:.3f}")
    else:
        print(f"  {label} ({cx},{cy}): out of bounds")
