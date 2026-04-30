"""
Limbus Company - Mirror Dungeon Theme Pack Image Extractor

一键提取所有镜牢主题包封面图 + E.G.O 礼物图标。

工作方式:
  - 从 Unity Caching 缓存 (AppData/LocalLow/Unity/ProjectMoon_LimbusCompany) 读取 CDN bundles
  - 用 UnityPy 解包提取 Texture2D
  - 解析主题包 JSON 数据并映射图片
    
用法:
  uv run python scripts/extract_card_pack.py
"""

import json
import shutil
from collections import Counter
from pathlib import Path

import UnityPy

# ── 路径 ──────────────────────────────────────────────────────────────
CACHING_DIR = Path(r"C:\Users\Ko_teiru\AppData\LocalLow\Unity\ProjectMoon_LimbusCompany")
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "extracted"

COVERS_DIR = OUTPUT_DIR / "theme_pack_covers"
GIFT_ICONS_DIR = OUTPUT_DIR / "ego_gift_icons"
BOSS_CARDS_DIR = OUTPUT_DIR / "boss_cards"
JSON_DIR = OUTPUT_DIR / "theme_pack_json"


def header(msg):
    print(f"\n\033[35m\033[1m=== {msg} ===\033[0m")
def ok(msg):
    print(f"  \033[32m✓\033[0m {msg}")
def info(msg):
    print(f"  \033[36m◇\033[0m {msg}")
def warn(msg):
    print(f"  \033[33m⚠\033[0m {msg}")


# ── Step 1: Parse theme pack JSON data ───────────────────────────────
def parse_theme_json() -> dict:
    """Parse theme pack JSON from already-extracted data."""
    all_themes = {}
    for f in sorted(JSON_DIR.glob("mirrordungeon-theme-floor-t*.json")):
        if "hidden" in f.name:
            continue
        try:
            data = json.loads(f.read_text("utf-8"))
        except:
            continue
        tier = f.name.replace("mirrordungeon-theme-floor-", "").replace(".json", "")
        for t in data.get("list", []):
            tid = t.get("id")
            all_themes[tid] = {
                "desc": t.get("desc", ""),
                "tier": tier,
                "giftIDs": t.get("giftIDs", []),
            }
    return all_themes


def extract_theme_json():
    """Extract theme pack JSON data from cache bundles."""
    header("Extract Theme Pack JSON")
    for dir1 in CACHING_DIR.iterdir():
        if not dir1.is_dir() or dir1.name == "__info":
            continue
        for dir2 in dir1.iterdir():
            df = dir2 / "__data"
            if not df.exists():
                continue
            try:
                env = UnityPy.load(str(df))
            except:
                continue
            for asset in env.assets:
                for obj in asset.objects.values():
                    if obj.type and obj.type.name == "TextAsset":
                        try:
                            data = obj.read()
                            name = data.m_Name
                            s = data.m_Script
                            if isinstance(s, str) and "theme-floor" in name and "hidden" not in name:
                                JSON_DIR.mkdir(parents=True, exist_ok=True)
                                (JSON_DIR / f"{name}.json").write_text(s, encoding="utf-8")
                                ok(f"{name} ({len(s)} chars)")
                        except:
                            pass


# ── Step 2: Extract all cover images from cardpack bundles ───────────
def extract_cover_images():
    """Extract all 380x690 theme pack cover images from cached cardpack bundles."""
    header("Extract Cover Images")

    season_label = {
        "8f19505a8b93b188025e1435e979bd48": "S4_Event_TKT",
        "c4cd530b2cc8ad79e8ed12dcc00d056e": "S4_Event_MoWE",
        "2b93a343144eb36c43a97a7af50deb72": "S4_Event_Walpu4",
        "a7df8af18da33747414ac2a1914a8c91": "S4_MD_Core",
        "e4567695a81371f85d77d22860a6d4b5": "S4_MD_Boss_240530",
        "f1d8303b3c11c057592666e69aec4910": "S4_MD_Boss",
        "66d88e31d2ba899855afed1b33750b98": "S5_MD_Core",
        "220c335991d82a3007ab523a37b7f13f": "S6_MD_Core",
        "e02b18906a39124c250f8b07df121a7c": "S7_MD_Core",
    }

    cardpack_hashes = set(season_label.keys())
    seen = set()

    for dir1 in CACHING_DIR.iterdir():
        if not dir1.is_dir() or dir1.name == "__info":
            continue
        for dir2 in dir1.iterdir():
            df = dir2 / "__data"
            if not df.exists():
                continue
            # Check if this is a cardpack bundle
            is_cardpack = any(h in dir2.name for h in cardpack_hashes)
            if not is_cardpack:
                continue

            # Determine label
            label = "Unknown"
            for h, lbl in season_label.items():
                if h in dir2.name:
                    label = lbl
                    break

            try:
                env = UnityPy.load(str(df))
            except:
                continue

            count = 0
            for key, obj in env.container.items():
                if obj.type and obj.type.name == "Texture2D":
                    try:
                        data = obj.read()
                        if data.m_Name in seen:
                            continue
                        seen.add(data.m_Name)
                        img = data.image
                        w, h = img.size

                        # Cover images are ~380x690, boss cards are ~391x432
                        if abs(w - 380) < 50 and abs(h - 690) < 50:
                            out_dir = COVERS_DIR / label
                            out_dir.mkdir(parents=True, exist_ok=True)
                            img.save(str(out_dir / f"{data.m_Name}.png"))
                            count += 1
                        elif abs(w - 391) < 50 and abs(h - 432) < 50:
                            out_dir = BOSS_CARDS_DIR / label
                            out_dir.mkdir(parents=True, exist_ok=True)
                            img.save(str(out_dir / f"{data.m_Name}.png"))
                    except:
                        pass

            if count:
                info(f"{label}: {count} covers")


# ── Step 3: Extract EGO gift icons ───────────────────────────────────
def extract_egogift_icons():
    """Extract EGO gift icons from egogift bundles."""
    header("Extract EGO Gift Icons")

    for dir1 in CACHING_DIR.iterdir():
        if not dir1.is_dir() or dir1.name == "__info":
            continue
        for dir2 in dir1.iterdir():
            df = dir2 / "__data"
            if not df.exists():
                continue
            if "egogift" not in dir2.name.lower() and "egogifticon" not in dir2.name.lower():
                continue
            try:
                env = UnityPy.load(str(df))
            except:
                continue

            count = 0
            for asset in env.assets:
                for obj in asset.objects.values():
                    if obj.type and obj.type.name == "Texture2D":
                        try:
                            data = obj.read()
                            name = data.m_Name
                            img = data.image
                            # Only save numbered gift icons (1001.png etc) or meaningful names
                            if name.isdigit() or "Gift" in name or "EgoGift" in name:
                                out = GIFT_ICONS_DIR / f"{name}.png"
                                out.parent.mkdir(parents=True, exist_ok=True)
                                img.save(str(out))
                                count += 1
                        except:
                            pass

            if count:
                info(f"  -> {count} icons")


# ── Step 4: Print summary ────────────────────────────────────────────
def print_summary(all_themes: dict):
    header("Summary")

    cover_count = sum(1 for _ in COVERS_DIR.rglob("*.png"))
    gift_count = sum(1 for _ in GIFT_ICONS_DIR.rglob("*.png"))
    boss_count = sum(1 for _ in BOSS_CARDS_DIR.rglob("*.png"))

    print(f"  Theme packs in JSON:    {len(all_themes)}")
    print(f"  Cover images found:     {cover_count}")
    print(f"  Boss card images:       {boss_count}")
    print(f"  EGO gift icons:         {gift_count}")

    tier_counts = Counter(t["tier"] for t in all_themes.values())
    print(f"\n  Theme packs by tier:")
    for tier, count in sorted(tier_counts.items()):
        print(f"    {tier}: {count} themes")

    print(f"\n  Covers by season:")
    for d in sorted(COVERS_DIR.iterdir()):
        if d.is_dir():
            c = len(list(d.glob("*.png")))
            print(f"    {d.name}: {c}")

    # Show cover-to-theme mapping
    print(f"\n  Sample cover images:")
    cover_names = set()
    for f in COVERS_DIR.rglob("*.png"):
        cover_names.add(f.stem)
    for n in sorted(cover_names)[:10]:
        print(f"    {n}.png")
    if len(cover_names) > 10:
        print(f"    ... and {len(cover_names)-10} more")


# ── Main ─────────────────────────────────────────────────────────────
def main():
    print("\033[35m\033[1m")
    print("╔══════════════════════════════════════════╗")
    print("║ Limbus Company - Theme Pack Extractor    ║")
    print("╚══════════════════════════════════════════╝")
    print("\033[0m")

    extract_theme_json()
    all_themes = parse_theme_json()
    extract_cover_images()
    extract_egogift_icons()
    print_summary(all_themes)

    print(f"\n  Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
