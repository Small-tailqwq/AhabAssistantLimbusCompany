"""离线重放 logs/route_map_debug 的截图，复现寻路识别结果。

对每张 *_best_plan.png 重新跑 `identify_nodes` / `identify_road` / 分组，
与同名 JSON 里记录的 `identified_road`、`grouped_road` 对比，用来判断
「计划为空」是画面本身导致，还是寻路时用的输入与存档截图不同。

用法：
    uv run python debug_tools/replay_route_map_frames.py
    uv run python debug_tools/replay_route_map_frames.py --only 20260525_181418_933
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


def replay(stem: str, win_size: int) -> dict:
    payload = json.loads((DEBUG_DIR / f"{stem}.json").read_text(encoding="utf-8"))
    bus = payload.get("bus")
    if not bus:
        return {"stem": stem, "error": "json 中没有 bus 坐标"}
    with Image.open(DEBUG_DIR / f"{stem}.png") as img:
        image = np.array(img.convert("RGB"))

    cfg.unsaved_set_value("set_win_size", win_size)
    path_manager.initialize_paths()

    nodes = sr.identify_nodes(bus[0], screenshot_image=image) or []
    y_area = sr.divide_the_area_by_y(nodes) if nodes else []
    nodes_layer = sr.divide_the_area_by_x(nodes) if nodes else []
    roads = sr.identify_road(bus[0], min_length=160, screenshot_image=image) or []
    grouped = sr._group_roads_by_node_layers(roads, bus[0], nodes_layer) if nodes_layer else []
    return {
        "stem": stem,
        "bus": bus,
        "nodes": nodes,
        "y_area": y_area,
        "node_layers": nodes_layer,
        "roads": roads,
        "grouped": grouped,
        "json_roads": payload.get("identified_road"),
        "json_grouped": payload.get("grouped_road"),
        "runtime_ok": bool(payload.get("runtime_plan_found")),
    }


def summarize(result: dict) -> None:
    if "error" in result:
        print(f"  {result['stem']}: {result['error']}")
        return
    nodes = result["nodes"]
    roads = result["roads"]
    grouped = result["grouped"]
    print(f"  {result['stem']}  runtime_ok={result['runtime_ok']}  bus={result['bus']}")
    print(f"    离线识别节点 {len(nodes)} 个，Y 行 {len(result['y_area'])}，X 列 {len(result['node_layers'])}")
    print(f"    离线识别线段 {len(roads)} 条，分组层 {len(grouped)}（非空 {sum(1 for g in grouped if g)}）")
    print(f"    JSON 记录线段 {len(result['json_roads'] or [])} 条，分组非空 {sum(1 for g in (result['json_grouped'] or []) if g)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="只处理文件名包含该前缀的样本")
    parser.add_argument("--win-size", type=int, default=1080, help="重放用的窗口高度基准（默认 1080）")
    args = parser.parse_args()

    # json 与 png 同名（形如 <时间戳>_best_plan / _scout_plan）
    stems = sorted(p.stem for p in DEBUG_DIR.glob("*.json"))
    if args.only:
        stems = [s for s in stems if args.only in s]
    if not stems:
        print("没有匹配的样本")
        return 1

    comparable = 0
    matched = 0
    for stem in stems:
        image_path = DEBUG_DIR / f"{stem}.png"
        if not image_path.exists():
            continue
        with Image.open(image_path) as img:
            _, height = img.size
        win_size = height if height in (720, 900, 1080, 1440, 1800, 2160) else args.win_size
        result = replay(stem, win_size)
        summarize(result)
        print()
        if "error" not in result and result.get("json_roads") is not None:
            comparable += 1
            if len(result["json_roads"]) == len(result["roads"]):
                matched += 1

    if comparable:
        print(f"与 JSON 可比对的样本 {comparable} 个，线段数一致 {matched} 个")
    else:
        print("没有可对比的 JSON identified_road（成功样本的 debug 帧在分析前保存，该字段为 null）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
