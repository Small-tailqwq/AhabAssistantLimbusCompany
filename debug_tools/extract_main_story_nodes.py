"""从主线 mini 镜牢地图截图中提取节点位置（分析用）。

用法:
    uv run python debug_tools/extract_main_story_nodes.py <screenshot_path>

说明:
    由于主线节点平台为暗紫色，与背景接近，单纯颜色/模板匹配都不稳定。
    本脚本结合暗紫色掩码、白线端点聚类和圆形度进行候选提取，输出仅供参考。
    实际 AALC 寻路使用 tasks/main_story/main_story.py 中的网格点击 + enter_assets 反馈。
"""

import sys
from pathlib import Path

import cv2
import numpy as np


def extract_node_candidates(image_path: str):
    img = cv2.imread(str(image_path))
    if img is None:
        raise FileNotFoundError(f"无法读取图片: {image_path}")

    h, w = img.shape[:2]
    roi = img[150 : h - 250, 100 : w - 100]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    # 1. 暗紫色节点平台掩码
    lower_dark_purple = np.array([100, 100, 5])
    upper_dark_purple = np.array([140, 255, 80])
    purple_mask = cv2.inRange(hsv, lower_dark_purple, upper_dark_purple)

    # 2. 白线端点聚类
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, white = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    lsd = cv2.createLineSegmentDetector(0)
    lines, _, _, _ = lsd.detect(white)

    line_endpoints = []
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            if length > 50:
                line_endpoints.append((x1, y1))
                line_endpoints.append((x2, y2))

    # 合并掩码：在暗紫色区域附近的白线端点更有可能是节点
    candidates = []
    if line_endpoints:
        used = set()
        eps = 70
        for i, p1 in enumerate(line_endpoints):
            if i in used:
                continue
            cluster = [p1]
            used.add(i)
            queue = [i]
            while queue:
                idx = queue.pop(0)
                for j, p2 in enumerate(line_endpoints):
                    if j in used:
                        continue
                    if ((line_endpoints[idx][0] - p2[0]) ** 2 + (line_endpoints[idx][1] - p2[1]) ** 2) ** 0.5 < eps:
                        cluster.append(p2)
                        used.add(j)
                        queue.append(j)
            if len(cluster) >= 3:
                cx = int(sum(p[0] for p in cluster) / len(cluster)) + 100
                cy = int(sum(p[1] for p in cluster) / len(cluster)) + 150
                if 200 < cx < w - 200 and 250 < cy < h - 300:
                    candidates.append((cx, cy, len(cluster), "line_junction"))

    # 3. 暗紫色连通区域（具有一定面积和圆形度）
    kernel = np.ones((5, 5), np.uint8)
    purple_mask = cv2.morphologyEx(purple_mask, cv2.MORPH_CLOSE, kernel)
    purple_mask = cv2.morphologyEx(purple_mask, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(purple_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if 800 < area < 30000:
            perimeter = cv2.arcLength(cnt, True)
            circularity = 4 * np.pi * area / (perimeter**2) if perimeter > 0 else 0
            if circularity > 0.25:
                M = cv2.moments(cnt)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"]) + 100
                    cy = int(M["m01"] / M["m00"]) + 150
                    if 200 < cx < w - 200 and 250 < cy < h - 300:
                        candidates.append((cx, cy, int(area), "purple_blob"))

    # 去重：距离过近的候选合并
    merged = []
    for cand in sorted(candidates, key=lambda c: c[2], reverse=True):
        cx, cy, score, source = cand
        if not any(abs(cx - m[0]) < 80 and abs(cy - m[1]) < 80 for m in merged):
            merged.append((cx, cy, score, source))

    merged.sort(key=lambda c: (c[0], c[1]))
    return merged, img


def main():
    if len(sys.argv) < 2:
        print(f"用法: uv run python {Path(__file__).name} <screenshot_path>")
        sys.exit(1)

    image_path = sys.argv[1]
    candidates, img = extract_node_candidates(image_path)

    print(f"检测到 {len(candidates)} 个节点候选：")
    for cx, cy, score, source in candidates:
        print(f"  ({cx}, {cy})  来源={source}, 分数/面积={score}")

    # 保存可视化结果
    for cx, cy, score, source in candidates:
        color = (0, 255, 0) if source == "line_junction" else (255, 0, 0)
        cv2.circle(img, (cx, cy), 25, color, 2)
        cv2.putText(img, f"{source}:{score}", (cx + 20, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    out_path = str(Path(image_path).with_suffix("")) + "_nodes.png"
    cv2.imwrite(out_path, img)
    print(f"可视化结果已保存: {out_path}")


if __name__ == "__main__":
    main()
