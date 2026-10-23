"""对比寻路失败与成功帧在不同最短线段阈值下的道路识别结果。

用法：
    uv run python debug_tools/diagnose_route_detection.py 20260525_181418_933_best_plan
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from PIL import Image  # noqa: E402

from module.config import cfg  # noqa: E402
from tasks.mirror import search_road as sr  # noqa: E402
from utils.path_manager import path_manager  # noqa: E402

DEBUG_DIR = REPO_ROOT / "logs" / "route_map_debug"


def load(stem: str) -> tuple[dict, np.ndarray, int]:
    payload = json.loads((DEBUG_DIR / f"{stem}.json").read_text(encoding="utf-8"))
    with Image.open(DEBUG_DIR / f"{stem}.png") as img:
        image = np.array(img.convert("RGB"))
        height = img.size[1]
    win_size = height if height in (720, 900, 1080, 1440) else 1080
    cfg.unsaved_set_value("set_win_size", win_size)
    path_manager.initialize_paths()
    return payload, image, win_size


def diagnose(stem: str) -> None:
    payload, image, win_size = load(stem)
    bus = payload["bus"]
    print(f"=== {stem}  bus={bus} win={win_size} runtime_ok={payload.get('runtime_plan_found')} ===")

    nodes = sr.identify_nodes(bus[0], screenshot_image=image) or []
    y_area = sr.divide_the_area_by_y(nodes) if nodes else []
    nodes_layer = sr.divide_the_area_by_x(nodes) if nodes else []
    print(f"  节点 {len(nodes)} 个: {nodes}")
    print(f"  Y 行 {len(y_area)}: {y_area}")
    print(f"  X 列 {len(nodes_layer)}: {nodes_layer}")
    print(f"  行中心: {sr._get_row_centers(y_area) if y_area else []}")

    primary_roads = sr.identify_road(bus[0], min_length=160, screenshot_image=image) or []
    primary_grouped = sr._group_roads_by_node_layers(primary_roads, bus[0], nodes_layer) if nodes_layer else []
    if y_area:
        print(f"  是否触发低阈值补检: {sr._should_retry_sparse_road_detection(y_area, nodes_layer, primary_grouped)}")
    else:
        print("  是否触发低阈值补检: n/a（没有识别到节点行）")

    for min_length in (160, 140, 120, 100, 80):
        roads = sr.identify_road(bus[0], min_length=min_length, screenshot_image=image) or []
        grouped = sr._group_roads_by_node_layers(roads, bus[0], nodes_layer) if nodes_layer else []
        non_empty = sum(1 for g in grouped if g)
        print(f"  min_length={min_length:3d}: 线段 {len(roads)} 条, 分组非空 {non_empty}/{len(grouped)}")
        for index, group in enumerate(grouped):
            if group:
                print(f"      层{index}: {group}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stems", nargs="+", help="样本文件名（不含扩展名）")
    args = parser.parse_args()

    stems = args.stems
    for stem in stems:
        if not (DEBUG_DIR / f"{stem}.json").exists():
            print(f"找不到样本: {stem}")
            continue
        diagnose(stem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
