"""核对 logs/route_map_debug 的寻路结果与对应截图。

用途：
1. 统计每个样本的寻路结果（runtime_plan_found / analysis_plan_found）；
2. 比较成功与失败样本的地图区域灰度对比度，判断「未识别到节点/道路」是否与
   地图配色有关；
3. 输出节点类型序列，供人工与截图比对。

用法：
    uv run python debug_tools/verify_route_map_debug.py
    uv run python debug_tools/verify_route_map_debug.py --dump-classes
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from PIL import Image  # noqa: E402

DEBUG_DIR = REPO_ROOT / "logs" / "route_map_debug"
# 地图主体区域：避开顶部 HUD、左侧楼层标签与底部罪人栏
ROI_TOP, ROI_BOTTOM = 0.18, 0.78
ROI_LEFT, ROI_RIGHT = 0.05, 0.95


def load_samples() -> list[dict]:
    samples: list[dict] = []
    for path in sorted(DEBUG_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        image_path = DEBUG_DIR / f"{path.stem}.png"
        if not image_path.exists():
            continue
        with Image.open(image_path) as img:
            gray = np.array(img.convert("L"))
            rgb = np.array(img.convert("RGB"))
        height, width = gray.shape
        roi_gray = gray[
            int(ROI_TOP * height) : int(ROI_BOTTOM * height),
            int(ROI_LEFT * width) : int(ROI_RIGHT * width),
        ]
        roi_rgb = rgb[
            int(ROI_TOP * height) : int(ROI_BOTTOM * height),
            int(ROI_LEFT * width) : int(ROI_RIGHT * width),
        ]
        samples.append(
            {
                "stem": path.stem,
                "size": f"{width}x{height}",
                "runtime_ok": bool(payload.get("runtime_plan_found")),
                "analysis_ok": bool(payload.get("analysis_plan_found")),
                "directions": payload.get("directions") or [],
                "classes": payload.get("road_class_list") or [],
                "score": payload.get("score") or [],
                "std": float(roi_gray.std()),
                "p50": float(np.median(roi_gray)),
                "p99": float(np.percentile(roi_gray, 99)),
                "mean_rgb": tuple(int(v) for v in roi_rgb.reshape(-1, 3).mean(axis=0)),
            }
        )
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump-classes", action="store_true", help="打印每个样本的节点类型序列")
    args = parser.parse_args()

    samples = load_samples()
    ok = [s for s in samples if s["runtime_ok"]]
    bad = [s for s in samples if not s["runtime_ok"]]
    print(f"样本 {len(samples)} 个：成功 {len(ok)}，失败 {len(bad)}")
    print()

    if ok:
        print("成功样本：")
        print(f"  灰度 std 中位={statistics.median(s['std'] for s in ok):.1f}")
        print(f"  灰度 p50 中位={statistics.median(s['p50'] for s in ok):.1f}")
        print(f"  平均背景 RGB={tuple(int(np.mean([s['mean_rgb'][i] for s in ok])) for i in range(3))}")
    if bad:
        print("失败样本：")
        print(f"  灰度 std 中位={statistics.median(s['std'] for s in bad):.1f}")
        print(f"  灰度 p50 中位={statistics.median(s['p50'] for s in bad):.1f}")
        print(f"  平均背景 RGB={tuple(int(np.mean([s['mean_rgb'][i] for s in bad])) for i in range(3))}")
    print()

    print("=== 全部样本（按灰度 std 升序） ===")
    for s in sorted(samples, key=lambda x: x["std"]):
        flag = "OK " if s["runtime_ok"] else "FAIL"
        print(
            f"  {flag} {s['stem']:32s} {s['size']:9s} std={s['std']:5.1f} p50={s['p50']:5.1f} "
            f"p99={s['p99']:6.1f} rgb={s['mean_rgb']} score={s['score']}"
        )

    if args.dump_classes:
        print()
        print("=== 节点类型序列 ===")
        for s in samples:
            if not s["classes"]:
                continue
            print(f"  {s['stem']}: {','.join(s['classes'])}  dirs={''.join(s['directions'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
