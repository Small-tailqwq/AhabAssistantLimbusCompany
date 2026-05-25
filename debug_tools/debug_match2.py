import sys, os
sys.path.insert(0, r'C:\Users\Ko_teiru\Documents\code\AhabAssistantLimbusCompany')

from utils.path_manager import path_manager
from utils.image_utils import ImageUtils
from module.config import cfg
import numpy as np
import cv2
from PIL import Image

base = r'C:\Users\Ko_teiru\Documents\code\AhabAssistantLimbusCompany'

print(f"pic_path: {path_manager.pic_path}")
print(f"current_theme: {path_manager.current_theme}")
print(f"current_language: {path_manager.current_language}")

target = 'mirror/shop/enhance_gifts/burn.png'

# Resolve the exact path
from utils.image_utils import ImageUtils
img_path, selected_path = ImageUtils._resolve_image_path(target)
print(f"resolved path: {img_path}")
print(f"selected path: {selected_path}")
print(f"file exists: {os.path.exists(img_path) if img_path else False}")

# Load with the exact same code path
template = ImageUtils.load_image(target, resize=True)
if template is not None:
    print(f"template shape: {template.shape}, dtype={template.dtype}")
    
    # Check if it's grayscale
    if len(template.shape) == 2:
        print("template is grayscale (2D)")
    else:
        print(f"template has {template.shape[2]} channels")
else:
    print("template is None")
    # Fallback: load directly
    direct = cv2.imread(os.path.join(base, r'assets\images\default\share\mirror\shop\enhance_gifts\burn.png'), cv2.IMREAD_UNCHANGED)
    print(f"direct load shape: {direct.shape}")
