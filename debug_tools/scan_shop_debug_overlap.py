"""分析 logs/shop_debug 截图里经费 OCR 区域的亮度分布。

复现 `in_shop._get_cost` 的裁剪区域（`mirror/shop/my_money_bbox.png`），
按 ROI 内像素的 p99 区分「经费文字清晰」与「被全屏遮罩压暗」两类帧。

用法：
    uv run python debug_tools/scan_shop_debug_overlap.py          # 统计
    uv run python debug_tools/scan_shop_debug_overlap.py --export # 另存 ROI 裁剪图
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from PIL import Image  # noqa: E402

from module.config import cfg  # noqa: E402
from utils.image_utils import ImageUtils  # noqa: E402
from utils.path_manager import path_manager  # noqa: E402

SHOP_DEBUG = REPO_ROOT / "logs" / "shop_debug"
OUT_DIR = SHOP_DEBUG / "_money_roi"


def money_bbox(win_size: int) -> tuple[int, int, int, int] | None:
    cfg.unsaved_set_value("set_win_size", win_size)
    path_manager.initialize_paths()
    image = ImageUtils.load_image("mirror/shop/my_money_bbox.png")
    if image is None:
        return None
    return tuple(int(v) for v in ImageUtils.get_bbox(image))


def scaled_bbox(
    base: tuple[int, int, int, int], base_size: tuple[int, int], size: tuple[int, int]
) -> tuple[int, int, int, int]:
    sx = size[0] / base_size[0]
    sy = size[1] / base_size[1]
    return (
        int(round(base[0] * sx)),
        int(round(base[1] * sy)),
        int(round(base[2] * sx)),
        int(round(base[3] * sy)),
    )


def main() -> int:
    export = "--export" in sys.argv
    base = money_bbox(720)
    if base is None:
        print("无法解析经费 bbox")
        return 1
    print(f"经费 OCR 区域 @720p 基准: {base}")

    rows: list[dict] = []
    for path in sorted(SHOP_DEBUG.glob("*.png")):
        with Image.open(path) as img:
            size = img.size
            if size == (87, 48):
                continue
            bbox = scaled_bbox(base, (1280, 720), size)
            crop = img.crop(bbox)
            arr = np.array(crop.convert("L"))
        rows.append(
            {
                "name": path.name,
                "size": size,
                "mean": float(arr.mean()),
                "p99": float(np.percentile(arr, 99)),
                "crop": crop,
            }
        )
        if export:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            crop.resize((crop.width * 4, crop.height * 4), Image.NEAREST).save(OUT_DIR / path.name)

    rows.sort(key=lambda r: r["p99"])
    dim = [r for r in rows if r["p99"] <= 60]
    bright = [r for r in rows if r["p99"] >= 150]
    print(f"共 {len(rows)} 张（已排除 87x48 裁剪图）")
    print(f"  经费文字偏暗（p99<=60，疑似被全屏遮罩压暗）: {len(dim)}")
    print(f"  经费文字正常（p99>=150）: {len(bright)}")
    print()
    print("=== 偏暗帧明细 ===")
    for r in dim:
        print(f"  {r['name']:52s} {r['size'][0]}x{r['size'][1]}  p99={r['p99']:5.1f} mean={r['mean']:5.1f}")
    if export:
        print()
        print(f"ROI 裁剪图已导出到 {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
