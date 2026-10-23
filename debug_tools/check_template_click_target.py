"""核对 AALC 模板的 bbox 与点击落点。

复现 `Automation._load_template_for_path` 的资源解析：在 `path_manager.pic_path`
搜索链里按语言/主题回退，`*_assets.png` 会按内容 bbox 裁剪，点击落点取裁剪后模板
在资源原图中的 bbox 中心。

用法：
    uv run python debug_tools/check_template_click_target.py
    uv run python debug_tools/check_template_click_target.py mirror/shop/leave_shop_confirm_assets.png
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from module.config import cfg  # noqa: E402
from utils.image_utils import ImageUtils  # noqa: E402
from utils.path_manager import path_manager  # noqa: E402

DEFAULT_KEYS = [
    "mirror/shop/leave_shop_confirm_assets.png",
    "mirror/shop/leave_assets.png",
    "mirror/shop/shop_coins_assets.png",
    "mirror/road_in_mir/legend_assets.png",
    "mirror/road_in_mir/enter_assets.png",
]


def describe(key: str, win_size: int) -> None:
    print(f"{key}   (win_size={win_size})")
    paths = ImageUtils.existing_image_paths(key)
    if not paths:
        print("  未找到资源")
        return
    for loaded_path in paths:
        template = ImageUtils.load_from_specific_path(key, loaded_path, resize=True)
        if template is None:
            print(f"  {loaded_path}: 加载失败")
            continue
        bbox = None
        if key.endswith("assets.png"):
            bbox = ImageUtils.get_bbox(template)
            template = ImageUtils.crop(template, bbox)
        h, w = template.shape[:2]
        print(f"  路径={loaded_path}")
        print(f"  缩放后尺寸={w}x{h}  bbox={bbox}")
        if bbox:
            cx = (bbox[0] + bbox[2]) / 2
            cy = (bbox[1] + bbox[3]) / 2
            print(f"  bbox 中心 @{win_size} 基准=({cx:.0f}, {cy:.0f})")
            print(f"  裁剪后模板尺寸={w}x{h}")


def main() -> int:
    args = sys.argv[1:]
    win_size = cfg.set_win_size
    keys: list[str] = []
    for arg in args:
        if arg.startswith("--win-size="):
            win_size = int(arg.split("=", 1)[1])
        else:
            keys.append(arg)
    cfg.unsaved_set_value("set_win_size", win_size)
    path_manager.initialize_paths()
    for key in keys or DEFAULT_KEYS:
        describe(key, win_size)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
