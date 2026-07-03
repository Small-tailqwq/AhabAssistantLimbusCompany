import cv2
import numpy as np

img = cv2.imread("debug_enkephalin_crop.png", cv2.IMREAD_GRAYSCALE)
if img is None:
    print("ERROR: debug_enkephalin_crop.png not found")
    exit(1)

print(f"Shape: {img.shape}, mean={img.mean():.1f}, min={img.min()}, max={img.max()}")

# Threshold experiments
print("\n=== THRESH_BINARY experiments ===")
for th in [60, 80, 100, 110, 130, 150]:
    _, bin_img = cv2.threshold(img, th, 255, cv2.THRESH_BINARY)
    white_pct = (bin_img > 127).mean() * 100
    print(f"  th={th:3d}: white={white_pct:4.1f}%")

print("\n=== THRESH_BINARY_INV experiments ===")
for th in [60, 80, 100, 110, 130, 150]:
    _, bin_img = cv2.threshold(img, th, 255, cv2.THRESH_BINARY_INV)
    white_pct = (bin_img > 127).mean() * 100
    print(f"  th={th:3d}: white={white_pct:4.1f}% (inverted)")

print("\n=== Adaptive threshold ===")
for block in [11, 15, 21]:
    adapt = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 2)
    white_pct = (adapt > 127).mean() * 100
    print(f"  block={block}: white={white_pct:4.1f}%")

# Save some test outputs
import os
out_dir = "debug_enkephalin_outputs"
os.makedirs(out_dir, exist_ok=True)

# Current approach: th=110 THRESH_BINARY
_, cur = cv2.threshold(img, 110, 255, cv2.THRESH_BINARY)
cv2.imwrite(os.path.join(out_dir, "current_th110_binary.png"), cur)

# Try th=60 THRESH_BINARY_INV (light text on dark bg → text becomes white)
_, inv60 = cv2.threshold(img, 60, 255, cv2.THRESH_BINARY_INV)
cv2.imwrite(os.path.join(out_dir, "test_th60_binary_inv.png"), inv60)

# Try th=80 THRESH_BINARY_INV
_, inv80 = cv2.threshold(img, 80, 255, cv2.THRESH_BINARY_INV)
cv2.imwrite(os.path.join(out_dir, "test_th80_binary_inv.png"), inv80)

# Try adaptive
adapt15 = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 2)
cv2.imwrite(os.path.join(out_dir, "test_adaptive15.png"), adapt15)

# Column intensity profile
col_means = img.mean(axis=0)
print("\n=== Column profile (brightness, left→right) ===")
for i in range(0, 130, 5):
    v = col_means[i : i + 5].mean()
    bar = "#" * max(1, int(v / 5))
    print(f"  col[{i:3d}]: {v:5.1f} {bar}")

# Also show row profile
row_means = img.mean(axis=1)
print("\n=== Row profile (brightness, top→bottom) ===")
for i in range(45):
    print(f"  row[{i:2d}]: {row_means[i]:5.1f}")

print(f"\nSaved test outputs to {out_dir}/")
print("Files: current_th110_binary.png, test_th60_binary_inv.png, test_th80_binary_inv.png, test_adaptive15.png")
