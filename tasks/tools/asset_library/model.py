"""Asset library model — YAML I/O, scanning, category mapping, filtering."""

import hashlib
import json
import os

import yaml

from module.logger import log

ASSET_IMAGES_ROOT = "assets/images"
DATA_ROOT = "data/asset_library"
LIBRARY_DIR = os.path.join(DATA_ROOT, "library")
CACHE_FILE = os.path.join(DATA_ROOT, "scan_cache.json")

_IMAGE_EXTENSIONS = (".png", ".webp", ".jpg", ".jpeg", ".bmp")


CATEGORY_MAP = {
    "home": "home",
    "enkephalin": "enkephalin",
    "battle": "battle",
    "mail": "mail",
    "scenes": "scenes",
    "base": "base",
    "mirror/road_in_mir": "mirror_road",
    "mirror/road_to_mir": "mirror_road",
    "mirror/shop": "mirror_shop",
    "mirror/event": "mirror_event",
    "mirror/claim_reward": "mirror_reward",
    "mirror/get_reward_card": "mirror_reward",
    "mirror/theme_pack": "mirror_theme_pack",
    "teams": "teams",
    "pass": "pass",
    "luxcavation": "luxcavation",
    "event": "event",
}

_CATEGORY_YAMLS = {
    "home": "home.yaml",
    "enkephalin": "enkephalin.yaml",
    "battle": "battle.yaml",
    "mail": "mail.yaml",
    "scenes": "scenes.yaml",
    "base": "base.yaml",
    "mirror_road": "mirror_road.yaml",
    "mirror_shop": "mirror_shop.yaml",
    "mirror_event": "mirror_event.yaml",
    "mirror_reward": "mirror_reward.yaml",
    "mirror_theme_pack": "mirror_theme_pack.yaml",
    "mirror_ui": "mirror_ui.yaml",
    "teams": "teams.yaml",
    "pass": "pass.yaml",
    "luxcavation": "luxcavation.yaml",
    "event": "event.yaml",
    "uncategorized": "uncategorized.yaml",
}


def _category_for_path(rel_path: str) -> str:
    """Map a file path (relative to assets/images/) to a category key."""
    normalized = rel_path.replace("\\", "/")
    parts = normalized.split("/")
    if len(parts) >= 3:
        inner = "/".join(parts[2:])
    else:
        inner = normalized

    if inner.startswith("mirror/") and inner.count("/") == 1 and inner.lower().endswith(_IMAGE_EXTENSIONS):
        return "mirror_ui"

    for prefix, category in CATEGORY_MAP.items():
        if inner.startswith(prefix + "/") or inner == prefix:
            return category
    return "uncategorized"


def _category_to_yaml(category: str) -> str:
    return _CATEGORY_YAMLS.get(category, f"{category}.yaml")


def _file_to_checksum(filepath: str) -> str:
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return f"sha256:{sha.hexdigest()}"


def _file_to_mtime_size(filepath: str) -> dict:
    stat = os.stat(filepath)
    return {"mtime": stat.st_mtime, "size": stat.st_size}


class AssetLibraryModel:
    """Thread-safe(ish) model for asset metadata management."""

    def __init__(self):
        self._assets_cache: dict[str, list[dict]] = {}
        self._dirty: set[str] = set()

    # --- YAML I/O ---

    def _load_yaml(self, category: str) -> list[dict]:
        if category in self._assets_cache:
            return self._assets_cache[category]
        yaml_name = _category_to_yaml(category)
        path = os.path.join(LIBRARY_DIR, yaml_name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict) and "assets" in data:
                    result = data["assets"]
                else:
                    log.warning(f"_load_yaml: {yaml_name} missing 'assets' key, returning empty")
                    result = []
        else:
            result = []
        self._assets_cache[category] = result
        return result

    def _save_yaml(self, category: str) -> None:
        yaml_name = _category_to_yaml(category)
        path = os.path.join(LIBRARY_DIR, yaml_name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        assets = self._assets_cache.get(category, [])
        clean = [{k: v for k, v in a.items() if k != "_category"} for a in assets]
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump({"assets": clean}, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # --- Query ---

    def get_assets(self, category: str | None = None, tags: list[str] | None = None, search: str | None = None) -> list[dict]:
        """Return filtered asset dicts with _category field (shallow copies, never mutates cache)."""
        result = []
        if category:
            categories = [category]
        else:
            categories = list(_CATEGORY_YAMLS.keys())

        search_lower = search.lower() if search else None

        for cat in categories:
            for asset in self._load_yaml(cat):
                copy = dict(asset, _category=cat)
                if tags:
                    asset_tags = set(copy.get("tags") or [])
                    if not asset_tags.issuperset(tags):
                        continue
                if search_lower:
                    needle = search_lower
                    bn = (copy.get("business_name") or "").lower()
                    n = (copy.get("note") or "").lower()
                    f = (copy.get("file") or "").lower()
                    if needle not in bn and needle not in n and needle not in f:
                        continue
                result.append(copy)

        return result

    def get_asset(self, file_path: str) -> dict | None:
        """Get a single asset by file path (shallow copy)."""
        for cat in _CATEGORY_YAMLS:
            for asset in self._load_yaml(cat):
                if asset.get("file") == file_path:
                    return dict(asset, _category=cat)
        return None

    def get_all_categories(self) -> list[str]:
        return list(_CATEGORY_YAMLS)

    # --- Mutation ---

    def update_asset(self, file_path: str, **fields) -> None:
        for cat in _CATEGORY_YAMLS:
            assets = self._load_yaml(cat)
            for asset in assets:
                if asset.get("file") == file_path:
                    asset.update(fields)
                    self._dirty.add(cat)
                    return

    def mark_as_missing(self, file_path: str) -> None:
        """Mark an asset as missing (file deleted externally)."""
        for cat in _CATEGORY_YAMLS:
            assets = self._load_yaml(cat)
            for asset in assets:
                if asset.get("file") == file_path:
                    asset["status"] = "missing"
                    self._dirty.add(cat)
                    return

    def remove_asset_record(self, file_path: str) -> None:
        """Soft-delete the YAML record for a file."""
        for cat in _CATEGORY_YAMLS:
            assets = self._load_yaml(cat)
            for i, asset in enumerate(assets):
                if asset.get("file") == file_path:
                    assets.pop(i)
                    self._dirty.add(cat)
                    return

    def flush_dirty(self) -> None:
        """Write all dirty categories to disk."""
        dirty = self._dirty.copy()
        self._dirty.clear()
        for cat in dirty:
            self._save_yaml(cat)

    @property
    def has_dirty(self) -> bool:
        return len(self._dirty) > 0

    # --- Scan ---

    def scan(self, progress_callback=None) -> dict:
        """Scan assets/images/ and return a diff dict. Must be called from background thread.

        Returns: {"added": [...], "changed": [...], "deleted": [...], "uncategorized": [...]}
        """
        cache = self._load_scan_cache()
        existing_files: dict[str, dict] = {}
        for cat in _CATEGORY_YAMLS:
            for asset in self._load_yaml(cat):
                existing_files[asset["file"]] = asset

        found = set()
        added = []
        changed = []
        deleted = []
        all_scanned = []

        image_files = []
        for root, dirs, files in os.walk(ASSET_IMAGES_ROOT):
            for f in files:
                if f.lower().endswith(_IMAGE_EXTENSIONS):
                    abspath = os.path.join(root, f)
                    rel = os.path.relpath(abspath, ASSET_IMAGES_ROOT)
                    image_files.append((abspath, rel.replace("\\", "/")))

        total = len(image_files)

        for count, (abspath, rel_forward) in enumerate(image_files, 1):
            found.add(rel_forward)

            ms = _file_to_mtime_size(abspath)
            cached = cache.get(rel_forward, {})
            if cached.get("mtime") == ms["mtime"] and cached.get("size") == ms["size"]:
                checksum = cached.get("checksum", "")
            else:
                checksum = _file_to_checksum(abspath)
                cache[rel_forward] = {**ms, "checksum": checksum}

            category = _category_for_path(rel_forward)

            if rel_forward not in existing_files:
                asset = {
                    "file": rel_forward,
                    "business_name": "",
                    "tags": [],
                    "note": "",
                    "checksum": checksum,
                }
                if category == "uncategorized":
                    all_scanned.append(asset)
                else:
                    added.append({**asset, "category": category})
            else:
                exc = existing_files[rel_forward]
                old_checksum = exc.get("checksum", "")
                if old_checksum and old_checksum != checksum:
                    changed.append(
                        {
                            "old": exc.copy(),
                            "new_checksum": checksum,
                            "new_file": rel_forward,
                        }
                    )
                    cache[rel_forward]["checksum"] = checksum

            if progress_callback:
                progress_callback(count, total)

        for rel, asset in existing_files.items():
            if rel not in found:
                deleted.append(asset)

        self._save_scan_cache(cache)
        return {"added": added, "changed": changed, "deleted": deleted, "uncategorized": all_scanned}

    def apply_scan_result(self, diff: dict) -> None:
        """Apply scan diff to YAML files. Called from main thread."""
        for asset in diff.get("added", []):
            cat = asset.pop("category")
            assets = self._load_yaml(cat)
            assets.append(asset)
            self._dirty.add(cat)

        for item in diff.get("changed", []):
            file_path = item.get("new_file") or item["old"].get("file", "")
            for cat in _CATEGORY_YAMLS:
                assets = self._load_yaml(cat)
                found_cat = False
                for asset in assets:
                    if asset.get("file") == file_path:
                        old = item["old"]
                        old["status"] = "archived"
                        assets.append(old)
                        asset["checksum"] = item["new_checksum"]
                        self._dirty.add(cat)
                        found_cat = True
                        break
                if found_cat:
                    break

        for asset in diff.get("deleted", []):
            self.mark_as_missing(asset["file"])

        uncategorized = diff.get("uncategorized", [])
        if uncategorized:
            uc_assets = self._load_yaml("uncategorized")
            for asset in uncategorized:
                uc_assets.append(asset)
            self._dirty.add("uncategorized")

        self.flush_dirty()

    # --- Cache ---

    def _load_scan_cache(self) -> dict:
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                log.warning("_load_scan_cache: cache file corrupted, ignoring")
        return {}

    def _save_scan_cache(self, cache: dict) -> None:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)

    def clear_cache(self) -> None:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)

    # --- Reload ---

    def reload(self) -> None:
        if self.has_dirty:
            log.warning("reload() called with unsaved changes, flushing first")
            self.flush_dirty()
        self._assets_cache.clear()
