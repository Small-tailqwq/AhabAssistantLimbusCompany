import sys
sys.path.insert(0, ".")

import cv2
import re
import numpy as np
from module.ocr import ocr

sc = cv2.imread("debug_enk_crop_raw.png", cv2.IMREAD_GRAYSCALE)
print(f"Raw crop: shape={sc.shape}, mean={sc.mean():.1f}, max={sc.max()}")

# Step 1: two-pass OCR (raw + th70)
raw_r = ocr.run(sc)
_, bi = cv2.threshold(sc, 70, 255, cv2.THRESH_BINARY)
bin_r = ocr.run(bi)

print(f"\nraw OCR: {list(raw_r.txts)}")
print(f"th70 OCR: {list(bin_r.txts)}")

regions = []
for arr, txts in [(raw_r, raw_r.txts), (bin_r, bin_r.txts)]:
    if txts is None:
        continue
    boxes = getattr(arr, "boxes", None)
    if boxes is None:
        boxes = getattr(arr, "dt_boxes", None)
    if boxes is not None and len(boxes) > 0:
        for box, txt in zip(boxes, txts):
            x = box[:, 0].mean()
            regions.append((txt, float(x)))
    else:
        regions.extend((t, 0.0) for t in txts if t)

regions.sort(key=lambda r: r[1])
for t, x in regions:
    print(f"  region: '{t}' at x={x:.1f}")

combined = "".join(t for t, _ in regions).lower().replace(" ", "")
print(f"\nCombined: '{combined}'")
m = re.search(r"(\d{1,3})\s*/\s*(\d{1,4})", combined)
print(f"Two-pass result: {int(m.group(1)) if m else 'NO MATCH'}")
if m:
    print(f"  current={m.group(1)}, max={m.group(2)}")

# Step 2: CLAHE fallback
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
enhanced = clahe.apply(sc)
_, th_enhanced = cv2.threshold(enhanced, 60, 255, cv2.THRESH_BINARY)
clahe_r = ocr.run(th_enhanced)
joined = "".join(str(t) for t in clahe_r.txts if t).lower().replace(" ", "")
print(f"\nCLAHE: {list(clahe_r.txts)}")
print(f"CLAHE joined: '{joined}'")
m2 = re.search(r"(\d{1,3})\s*/\s*(\d{1,4})", joined)
if m2:
    cur = int(m2.group(1))
    maxv = int(m2.group(2))
    print(f"  current={cur}, max={maxv}, valid={cur <= maxv}")
else:
    digits = re.sub(r"\D", "", joined)
    print(f"  no X/XXX pattern, all_digits='{digits}'")

# Also try: wider bbox shifted left by 10px
print("\n=== Try bbox shifted left 10px ===")
w = sc.shape[1]
shifted = sc[:, 10:]  # crop left 10px
print(f"Shifted shape: {shifted.shape}")
raw_s = ocr.run(shifted)
_, bi_s = cv2.threshold(shifted, 70, 255, cv2.THRESH_BINARY)
bin_s = ocr.run(bi_s)

regions_s = []
for arr, txts in [(raw_s, raw_s.txts), (bin_s, bin_s.txts)]:
    if txts is None: continue
    boxes = getattr(arr, "boxes", None)
    if boxes is None: boxes = getattr(arr, "dt_boxes", None)
    if boxes is not None and len(boxes) > 0:
        for box, txt in zip(boxes, txts):
            regions_s.append((txt, float(box[:, 0].mean())))
    else:
        regions_s.extend((t, 0.0) for t in txts if t)

regions_s.sort(key=lambda r: r[1])
comb_s = "".join(t for t, _ in regions_s).lower().replace(" ", "")
print(f"raw shifted: {list(raw_s.txts)}")
print(f"th70 shifted: {list(bin_s.txts)}")
print(f"Combined shifted: '{comb_s}'")
m3 = re.search(r"(\d{1,3})\s*/\s*(\d{1,4})", comb_s)
print(f"Result: {int(m3.group(1)) if m3 else 'NO MATCH'}")
if m3:
    print(f"  current={m3.group(1)}, max={m3.group(2)}")

# Show column profile for reference
print("\n=== Column profile ===")
for i in range(0, 130, 10):
    v = sc[:, i:i+10].mean()
    bar = "#" * max(1, int(v / 5))
    print(f"  col[{i:3d}]: {v:5.1f} {bar}")
