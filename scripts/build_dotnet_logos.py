"""Build the AAALC desktop logo DrawingImage resources from their VTracer SVGs.

The 512px PNG logos looked jagged and blurry once the window scaled them down to
24/48px, so the app draws the logos as vector DrawingImage resources instead.
Window icons stay as the hand-tuned .ico files next to the SVGs.

    python scripts/build_dotnet_logos.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "src" / "AALC.Desktop"
LOGOS = ("Logo", "LogoAngelaIce", "LogoAngelaGold")

VIEW_BOX = re.compile(r'viewBox="0 0 (\d+) (\d+)"')
PATH = re.compile(r'<path d="([^"]+)" fill="(#[0-9A-Fa-f]{6})" transform="translate\(([-\d.]+),([-\d.]+)\)"/>')
TOKEN = re.compile(r"[MCZ]|-?\d+(?:\.\d+)?")


class UnsupportedSvgError(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(f"{name}.svg is not a plain VTracer export")


def _number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _translate(data: str, dx: float, dy: float) -> str:
    """VTracer only emits absolute M/C/Z commands, so the numbers are x/y pairs."""
    result, pending = [], None
    for token in TOKEN.findall(data):
        if token in "MCZ":
            result.append(token)
        elif pending is None:
            pending = float(token) + dx
        else:
            result.append(f"{_number(pending)},{_number(float(token) + dy)}")
            pending = None
    return " ".join(result)


def build_xaml() -> str:
    lines = [
        '<ResourceDictionary xmlns="https://github.com/avaloniaui" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">',
        " <!-- 由 scripts/build_dotnet_logos.py 从 Assets/*.svg 生成，勿手工编辑。 -->",
    ]
    for name in LOGOS:
        svg = (DESKTOP / "Assets" / f"{name}.svg").read_text(encoding="utf-8")
        view_box = VIEW_BOX.search(svg)
        paths = PATH.findall(svg)
        if view_box is None or len(paths) != svg.count("<path"):
            raise UnsupportedSvgError(name)
        width, height = view_box.groups()
        lines.append(f' <DrawingImage x:Key="{name}">')
        lines.append("  <DrawingGroup>")
        # 透明底框保留 SVG 画布留白，避免 DrawingImage 按内容包围盒裁切。
        lines.append(f'   <GeometryDrawing Brush="Transparent" Geometry="M0,0 H{width} V{height} H0 Z"/>')
        for data, fill, dx, dy in paths:
            geometry = "F1 " + _translate(data, float(dx), float(dy))
            lines.append(f'   <GeometryDrawing Brush="{fill.upper()}" Geometry="{geometry}"/>')
        lines.append("  </DrawingGroup>")
        lines.append(" </DrawingImage>")
    lines.append("</ResourceDictionary>")
    return "\n".join(lines) + "\n"


def main() -> int:
    (DESKTOP / "Styles" / "Logos.axaml").write_text(build_xaml(), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
