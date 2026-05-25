import sys, os
sys.path.insert(0, r'C:\Users\Ko_teiru\Documents\code\AhabAssistantLimbusCompany')

from utils.image_utils import ImageUtils
from module.config import cfg
from PIL import Image
import numpy as np
import cv2

base = r'C:\Users\Ko_teiru\Documents\code\AhabAssistantLimbusCompany'
screenshot_path = os.path.join(base, 'screenshot_20260524_215912.png')

pil_img = Image.open(screenshot_path).convert('RGB')
screenshot_np = np.array(pil_img)
print(f'Screenshot: {screenshot_np.shape}, set_win_size={cfg.set_win_size}')

target = 'mirror/shop/enhance_gifts/burn.png'
template = ImageUtils.load_image(target, resize=True)
tpl_np = np.array(template)
print(f'Template shape: {tpl_np.shape}, dtype={tpl_np.dtype}')

w, h = ImageUtils.get_image_info(tpl_np)
print(f'Template w={w} h={h}')

for th in [0.8, 0.7, 0.6, 0.5]:
    matches = ImageUtils.match_template_with_multiple_targets(screenshot_np, tpl_np, th)
    print(f'\nthreshold={th}: {len(matches)} matches')
    for pt in matches:
        near8 = abs(pt[0]-1825)<30 and abs(pt[1]-580)<30
        tag = ' <-- #8 area' if near8 else ''
        print(f'  ({pt[0]:4d},{pt[1]:4d}){tag}')

gray_scr = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2GRAY)
if len(tpl_np.shape) == 3:
    gray_tpl = cv2.cvtColor(tpl_np, cv2.COLOR_RGB2GRAY)
else:
    gray_tpl = tpl_np

res = cv2.matchTemplate(gray_scr, gray_tpl, cv2.TM_CCOEFF_NORMED)
points_of_interest = [(1066,432,'#1'), (1204,432,'#2'), (1204,569,'#3'),
                      (1616,707,'#4'), (1479,707,'#5'), (1066,707,'#6'),
                      (1341,707,'#7'), (1825,580,'#8')]
print('\nScores at specific coordinates:')
for cx, cy, label in points_of_interest:
    x, y = cx - w//2, cy - h//2
    if 0 <= x < res.shape[1] and 0 <= y < res.shape[0]:
        print(f'  {label} ({cx},{cy}): {res[y,x]:.3f}')
    else:
        print(f'  {label} ({cx},{cy}): out of bounds')

print(f'\nMax match score overall: {res.max():.3f}')
print(f'Min match score overall: {res.min():.3f}')

# Save a heatmap visualization
heatmap = (res * 255).astype(np.uint8)
heatmap_color = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)
# overlay with original
vis = cv2.addWeighted(cv2.cvtColor(gray_scr, cv2.COLOR_GRAY2BGR), 0.5, heatmap_color, 0.5, 0)
cv2.imwrite(os.path.join(base, 'debug_heatmap.png'), vis)
print('\nSaved debug_heatmap.png')
