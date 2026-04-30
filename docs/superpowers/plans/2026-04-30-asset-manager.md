# Asset Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a visual asset management tool for AALC's 558 game images — browse, tag, annotate, replace with version history.

**Architecture:** Data layer (`AssetLibraryModel` + `RecycleManager`) is pure Python with YAML persistence. UI layers (`CategoryTree`, `AssetGrid`, `AssetDetailPanel`) are PySide6 widgets assembled in `AssetManager` window, launched via existing `ToolManager` pattern. Scanning runs in background `QThread` with two-level cache (mtime/size → SHA256 fallback).

**Tech Stack:** Python 3.12+, PySide6, qfluentwidgets, PyYAML, Pillow (via `QImageReader`)

---

### Task 1: Project Scaffolding

**Files:**
- Create: `tasks/tools/asset_library/__init__.py`
- Create: `data/asset_library/` directories

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p tasks/tools/asset_library
mkdir -p data/asset_library/library
mkdir -p data/asset_library/recycle/files
```

```bash
# Verify
ls tasks/tools/asset_library/
ls data/asset_library/
```

- [ ] **Step 2: Create asset_library __init__.py**

Write `tasks/tools/asset_library/__init__.py`:

```python
"""Asset management library for AALC image assets."""
```

- [ ] **Step 3: Verify syntax**

```bash
uv run python -m py_compile tasks/tools/asset_library/__init__.py
```

- [ ] **Step 4: Commit**

```bash
git add tasks/tools/asset_library/__init__.py
git commit -m "feat(asset_manager): create project scaffolding"
```

---

### Task 2: AssetLibraryModel — Core Data Layer

**Files:**
- Create: `tasks/tools/asset_library/model.py`

This is the heart of the tool — YAML I/O, category mapping, asset query/filter, dirty tracking with debounce, and scan result application. Pure Python (no Qt), usable from any thread.

The model runs in the main thread for reads but writes are guarded. Scanning (heavy I/O) is done by a separate `ScanWorker` (Task 4) which calls `scan()` on a background thread, then emits results to the main thread where `apply_scan_result()` runs.

- [ ] **Step 1: Write the model module with all classes**

Write `tasks/tools/asset_library/model.py`:

```python
"""Asset library model — YAML I/O, scanning, category mapping, filtering."""

import hashlib
import json
import os
import time

import yaml

from module.logger import log

ASSET_IMAGES_ROOT = "assets/images"
DATA_ROOT = "data/asset_library"
LIBRARY_DIR = os.path.join(DATA_ROOT, "library")
CACHE_FILE = os.path.join(DATA_ROOT, "scan_cache.json")


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
    # Remove theme/lang prefix: default/share/mirror/shop/xx.png -> mirror/shop/xx
    parts = normalized.split("/")
    if len(parts) >= 3:
        # Skip theme (default/dark) and lang (en/zh_cn/share)
        inner = "/".join(parts[2:])
    else:
        inner = normalized

    # Check mirror root png files first
    if inner.startswith("mirror/") and inner.endswith(".png") and "/" not in inner[7:].rstrip(".png"):
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
        self._assets_cache: dict[str, list] = {}
        self._dirty: set[str] = set()

    # --- YAML I/O ---

    def _load_yaml(self, category: str) -> list:
        if category in self._assets_cache:
            return self._assets_cache[category]
        yaml_name = _category_to_yaml(category)
        path = os.path.join(LIBRARY_DIR, yaml_name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                result = data.get("assets", []) if data else []
        else:
            result = []
        self._assets_cache[category] = result
        return result

    def _save_yaml(self, category: str) -> None:
        yaml_name = _category_to_yaml(category)
        path = os.path.join(LIBRARY_DIR, yaml_name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        assets = self._assets_cache.get(category, [])
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump({"assets": assets}, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # --- Query ---

    def get_assets(self, category: str | None = None, tags: list[str] | None = None, search: str | None = None) -> list[dict]:
        """Return filtered asset dicts with _category field added."""
        result = []
        if category:
            categories = [category]
        else:
            categories = list(_CATEGORY_YAMLS.keys())

        search_lower = search.lower() if search else None

        for cat in categories:
            for asset in self._load_yaml(cat):
                asset["_category"] = cat
                # Tag filter
                if tags:
                    asset_tags = set(asset.get("tags") or [])
                    if not asset_tags.issuperset(tags):
                        continue
                # Search filter
                if search_lower:
                    needle = search_lower
                    bn = (asset.get("business_name") or "").lower()
                    n = (asset.get("note") or "").lower()
                    f = (asset.get("file") or "").lower()
                    if needle not in bn and needle not in n and needle not in f:
                        continue
                result.append(asset)

        return result

    def get_asset(self, file_path: str) -> dict | None:
        """Get a single asset by file path."""
        for cat in _CATEGORY_YAMLS:
            for asset in self._load_yaml(cat):
                if asset.get("file") == file_path:
                    asset["_category"] = cat
                    return asset
        return None

    def get_all_categories(self) -> list[str]:
        return list(_CATEGORY_YAMLS.keys())

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
        """Scan assets/images/ and return a diff dict.

        Must be called from a background thread.
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

        total = 0
        for root, dirs, files in os.walk(ASSET_IMAGES_ROOT):
            for f in files:
                if f.lower().endswith((".png", ".webp", ".jpg", ".jpeg", ".bmp")):
                    total += 1

        count = 0
        for root, dirs, files in os.walk(ASSET_IMAGES_ROOT):
            for f in files:
                if not f.lower().endswith((".png", ".webp", ".jpg", ".jpeg", ".bmp")):
                    continue
                abspath = os.path.join(root, f)
                rel = os.path.relpath(abspath, ASSET_IMAGES_ROOT)
                rel_forward = rel.replace("\\", "/")
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
                        "category": category,
                        "note": "",
                        "checksum": checksum,
                    }
                    if category == "uncategorized":
                        all_scanned.append(asset)
                    else:
                        added.append(asset)
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

                count += 1
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
            cat = asset["category"]
            assets = self._load_yaml(cat)
            assets.append({k: v for k, v in asset.items() if k != "category"})
            self._dirty.add(cat)

        for item in diff.get("changed", []):
            file_path = item["old"].get("file", item["new_file"])
            file_path = item.get("new_file") or file_path
            for cat in _CATEGORY_YAMLS:
                assets = self._load_yaml(cat)
                for asset in assets:
                    if asset.get("file") == file_path:
                        old = item["old"]
                        old["status"] = "archived"
                        assets.append(old)
                        asset["checksum"] = item["new_checksum"]
                        self._dirty.add(cat)
                        break

        for asset in diff.get("deleted", []):
            self.mark_as_missing(asset["file"])

        uncategorized = diff.get("uncategorized", [])
        if uncategorized:
            uc_assets = self._load_yaml("uncategorized")
            for asset in uncategorized:
                uc_assets.append({k: v for k, v in asset.items() if k != "category"})
            self._dirty.add("uncategorized")

        self.flush_dirty()

    # --- Cache ---

    def _load_scan_cache(self) -> dict:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
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
        self._assets_cache.clear()
```

- [ ] **Step 2: Verify syntax**

```bash
uv run python -m py_compile tasks/tools/asset_library/model.py
```

- [ ] **Step 3: Commit**

```bash
git add tasks/tools/asset_library/model.py
git commit -m "feat(asset_manager): add AssetLibraryModel — YAML I/O, scan, cache, filtering"
```

---

### Task 3: RecycleManager — Version Chain Management

**Files:**
- Create: `tasks/tools/asset_library/recycle.py`

- [ ] **Step 1: Write RecycleManager**

Write `tasks/tools/asset_library/recycle.py`:

```python
"""Recycle bin with version chain for asset file replacement history."""

import os
import shutil
import uuid
from datetime import datetime, timezone

import yaml

from module.logger import log

DATA_ROOT = "data/asset_library"
RECYCLE_FILES_DIR = os.path.join(DATA_ROOT, "recycle", "files")


def _asset_key_from_path(original_path: str) -> str:
    """Derive a stable key from original_path e.g. 'mirror/shop/item_assets.png' -> 'mirror_shop_item_assets'."""
    p = original_path.replace("\\", "/").replace(" ", "_")
    p = p.rsplit(".", 1)[0]
    p = p.replace("/", "_")
    return p


def _recycle_dir(asset_key: str) -> str:
    return os.path.join(RECYCLE_FILES_DIR, asset_key)


def _meta_path(asset_key: str) -> str:
    return os.path.join(_recycle_dir(asset_key), "_meta.yaml")


def _load_meta(asset_key: str) -> dict | None:
    path = _meta_path(asset_key)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return None


def _save_meta(asset_key: str, meta: dict) -> None:
    os.makedirs(_recycle_dir(asset_key), exist_ok=True)
    with open(_meta_path(asset_key), "w", encoding="utf-8") as f:
        yaml.dump(meta, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


class RecycleManager:
    """Manages the recycle bin and version chain for replaced asset files."""

    def archive(self, original_path: str, reason: str = "Manual replacement") -> bool:
        """Move current file to recycle as a new version in the version chain.

        Returns True on success, False if source doesn't exist.
        """
        source = os.path.join("assets", "images", original_path)
        if not os.path.exists(source):
            log.warning(f"RecycleManager.archive: source not found: {source}")
            return False

        asset_key = _asset_key_from_path(original_path)
        meta = _load_meta(asset_key) or {
            "asset_key": asset_key,
            "original_path": original_path,
            "versions": [],
        }

        next_ver = len(meta["versions"]) + 1
        base_name = os.path.basename(original_path)
        dest_name = f"v{next_ver}_{base_name}"
        dest = os.path.join(_recycle_dir(asset_key), dest_name)

        os.makedirs(_recycle_dir(asset_key), exist_ok=True)
        shutil.copy2(source, dest)

        meta["versions"].append(
            {
                "version": next_ver,
                "file": dest_name,
                "added_at": datetime.now(timezone.utc).isoformat(),
                "reason": reason,
            }
        )
        meta["current_version"] = next_ver
        _save_meta(asset_key, meta)
        log.info(f"RecycleManager: archived {original_path} -> v{next_ver}")
        return True

    def restore(self, asset_key: str, version: int) -> str | None:
        """Restore a specific version to the original path.

        If current file exists, archive it first. If not, restore directly.
        Returns the path that was restored, or None on failure.
        """
        meta = _load_meta(asset_key)
        if not meta:
            log.warning(f"RecycleManager.restore: no meta for {asset_key}")
            return None

        ver_entry = None
        for v in meta.get("versions", []):
            if v["version"] == version:
                ver_entry = v
                break
        if not ver_entry:
            log.warning(f"RecycleManager.restore: version {version} not found for {asset_key}")
            return None

        src = os.path.join(_recycle_dir(asset_key), ver_entry["file"])
        if not os.path.exists(src):
            log.error(f"RecycleManager.restore: file missing in recycle: {src}")
            return None

        original_path = meta["original_path"]
        dest = os.path.join("assets", "images", original_path)

        source_exists = os.path.exists(dest)

        if source_exists:
            reason = f"Archiving current version before restoring v{version}"
            self.archive(original_path, reason=reason)
        else:
            log.info(f"RecycleManager.restore: original file missing, restoring from scratch")

        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(src, dest)

        meta["restored_from"] = {
            "version": version,
            "restored_at": datetime.now(timezone.utc).isoformat(),
            "source_was_missing": not source_exists,
        }
        _save_meta(asset_key, meta)
        log.info(f"RecycleManager: restored v{version} of {original_path}")
        return original_path

    def list_versions(self, asset_key: str) -> list[dict]:
        """List all versions for an asset. Returns empty list if none."""
        meta = _load_meta(asset_key)
        if not meta:
            return []
        return meta.get("versions", [])

    def get_version_count(self, asset_key: str) -> int:
        return len(self.list_versions(asset_key))

    def permanently_delete(self, asset_key: str, version: int) -> bool:
        """Delete a specific version from recycle permanently."""
        meta = _load_meta(asset_key)
        if not meta:
            return False

        ver_entry = None
        for i, v in enumerate(meta.get("versions", [])):
            if v["version"] == version:
                ver_entry = v
                meta["versions"].pop(i)
                break
        if not ver_entry:
            return False

        file_path = os.path.join(_recycle_dir(asset_key), ver_entry["file"])
        if os.path.exists(file_path):
            os.remove(file_path)

        if not meta["versions"]:
            # No more versions, remove the directory
            if os.path.exists(_meta_path(asset_key)):
                os.remove(_meta_path(asset_key))
            recycle_dir = _recycle_dir(asset_key)
            try:
                os.rmdir(recycle_dir)
            except OSError:
                pass
        else:
            _save_meta(asset_key, meta)

        return True

    def has_versions(self, asset_key: str) -> bool:
        meta = _load_meta(asset_key)
        return len(meta.get("versions", [])) > 0 if meta else False
```

- [ ] **Step 2: Verify syntax**

```bash
uv run python -m py_compile tasks/tools/asset_library/recycle.py
```

- [ ] **Step 3: Commit**

```bash
git add tasks/tools/asset_library/recycle.py
git commit -m "feat(asset_manager): add RecycleManager — version chain archive/restore"
```

---

### Task 4: ScanWorker — Background Scanning

**Files:**
- Create: `tasks/tools/asset_library/scan_worker.py`

- [ ] **Step 1: Write ScanWorker QThread**

Write `tasks/tools/asset_library/scan_worker.py`:

```python
"""Background scan worker — runs AssetLibraryModel.scan() on a QThread."""

from PySide6.QtCore import QThread, Signal


class ScanWorker(QThread):
    """Runs the heavy `model.scan()` on a background thread."""

    progress = Signal(int, int)  # current, total
    finished = Signal(object)  # diff result
    error = Signal(str)  # error message

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model

    def run(self):
        try:
            diff = self.model.scan(progress_callback=self._on_progress)
            self.finished.emit(diff)
        except Exception as e:
            self.error.emit(str(e))

    def _on_progress(self, current: int, total: int):
        self.progress.emit(current, total)
```

- [ ] **Step 2: Verify syntax**

```bash
uv run python -m py_compile tasks/tools/asset_library/scan_worker.py
```

- [ ] **Step 3: Commit**

```bash
git add tasks/tools/asset_library/scan_worker.py
git commit -m "feat(asset_manager): add ScanWorker — background scan thread"
```

---

### Task 5: Widgets — UI Components

**Files:**
- Create: `tasks/tools/asset_library/widgets.py`

This is a large file (~400 lines), containing:
- `CategoryTree` — QTreeWidget for category navigation
- `AssetGridWidget` — QListWidget in IconMode for thumbnail grid
- `AssetDetailPanel` — QWidget with preview, fields, drag-drop, replace button
- `VersionHistoryDialog` — QDialog for browsing and switching versions

- [ ] **Step 1: Write widgets.py**

Write `tasks/tools/asset_library/widgets.py`:

```python
"""UI widgets for the asset manager."""

import os
import subprocess
import sys

import pyperclip
from PySide6.QtCore import Qt, QMimeData, QUrl, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QApplication,
)

from module.logger import log
from tasks.tools.asset_library.model import AssetLibraryModel, ASSET_IMAGES_ROOT
from tasks.tools.asset_library.recycle import RecycleManager, _asset_key_from_path

ASSETS_ROOT = os.path.abspath(ASSET_IMAGES_ROOT)


class CategoryTree(QTreeWidget):
    category_selected = Signal(str)

    CATEGORIES = {
        "全部": None,
        "主界面": "home",
        "体力": "enkephalin",
        "战斗": "battle",
        "邮件": "mail",
        "场景/过场": "scenes",
        "基础通用": "base",
        "日常事件": "event",
        "镜牢": None,
        "  寻路": "mirror_road",
        "  商店": "mirror_shop",
        "  事件": "mirror_event",
        "  结算/奖励": "mirror_reward",
        "  主题包": "mirror_theme_pack",
        "  通用UI": "mirror_ui",
        "队伍": "teams",
        "通行证": "pass",
        "反射": "luxcavation",
        "未分类": "uncategorized",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(0)
        self.setMaximumWidth(180)

        for label, key in self.CATEGORIES.items():
            item = QTreeWidgetItem(self)
            item.setText(0, label)
            item.setData(0, Qt.UserRole, key or "")
            item.setFlags(item.flags() & ~Qt.ItemIsDropEnabled)

        self.currentItemChanged.connect(self._on_item_changed)

    def _on_item_changed(self, current, _previous):
        if current:
            key = current.data(0, Qt.UserRole) or None
            self.category_selected.emit(key)


class AssetGridWidget(QListWidget):
    asset_selected = Signal(dict)
    context_menu_requested = Signal(list, QListWidgetItem)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QPixmap(120, 120).size())
        self.setResizeMode(QListWidget.Adjust)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.itemSelectionChanged.connect(self._on_selection)

        self._assets: list[dict] = []
        self._batch_size = 100
        self._loaded = 0

        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def set_assets(self, assets: list[dict]):
        self.clear()
        self._assets = assets
        self._loaded = 0
        self._load_batch()

    def _load_batch(self):
        end = min(self._loaded + self._batch_size, len(self._assets))
        for i in range(self._loaded, end):
            asset = self._assets[i]
            item = QListWidgetItem()
            item.setData(Qt.UserRole, asset)

            abspath = os.path.join(ASSETS_ROOT, asset["file"])
            if os.path.exists(abspath):
                reader = QImageReader(abspath)
                reader.setScaledSize(QPixmap(120, 120).size())
                pixmap = QPixmap.fromImageReader(reader)
                icon = QIcon(pixmap)
                item.setIcon(icon)
            else:
                item.setText("[Missing]")

            name = asset.get("business_name") or os.path.basename(asset["file"])
            item.setText(name)
            item.setToolTip(
                f"{asset['file']}\n{asset.get('business_name', '')}\n{asset.get('note', '')}"
            )
            self.addItem(item)
        self._loaded = end

    def _on_scroll(self, value):
        scrollbar = self.verticalScrollBar()
        if value >= scrollbar.maximum() - 10 and self._loaded < len(self._assets):
            self._load_batch()

    def _on_selection(self):
        items = self.selectedItems()
        if items:
            asset = items[0].data(Qt.UserRole)
            self.asset_selected.emit(asset)

    def _context_menu(self, pos):
        item = self.itemAt(pos)
        if not item:
            return
        asset = item.data(Qt.UserRole)
        menu = QMenu(self)

        open_action = menu.addAction("在文件管理器中打开")
        copy_action = menu.addAction("复制路径")
        menu.addSeparator()
        mark_missing_action = menu.addAction("标记为已删除")
        restore_action = menu.addAction("从回收站恢复")

        chosen = menu.exec(self.mapToGlobal(pos))

        if chosen == open_action:
            abspath = os.path.join(ASSETS_ROOT, asset["file"])
            dirpath = os.path.dirname(os.path.abspath(abspath))
            if sys.platform == "win32":
                os.startfile(dirpath)
            else:
                subprocess.Popen(["xdg-open", dirpath])

        elif chosen == copy_action:
            pyperclip.copy(asset["file"])

        elif chosen == mark_missing_action:
            self.context_menu_requested.emit(["mark_missing", asset], item)

        elif chosen == restore_action:
            self.context_menu_requested.emit(["restore", asset], item)

    def refresh_item(self, asset: dict):
        """Update an existing item after metadata change (called externally)."""
        for i in range(self.count()):
            item = self.item(i)
            stored = item.data(Qt.UserRole)
            if stored.get("file") == asset.get("file"):
                name = asset.get("business_name") or os.path.basename(asset["file"])
                item.setText(name)
                item.setData(Qt.UserRole, asset)
                return


class ImageLabel(QLabel):
    """Clickable thumbnail label with drag-drop support."""

    clicked = Signal()
    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(150, 150)
        self.setStyleSheet("QLabel { border: 1px solid #555; border-radius: 4px; }")
        self.setScaledContents(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0]
            if url.toLocalFile().lower().endswith((".png", ".webp", ".jpg", ".jpeg", ".bmp")):
                event.acceptProposedAction()
                self.setStyleSheet("QLabel { border: 2px solid #9c080b; border-radius: 4px; }")
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet("QLabel { border: 1px solid #555; border-radius: 4px; }")

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet("QLabel { border: 1px solid #555; border-radius: 4px; }")
        if event.mimeData().hasUrls():
            filepath = event.mimeData().urls()[0].toLocalFile()
            self.file_dropped.emit(filepath)
            event.acceptProposedAction()


class AssetDetailPanel(QWidget):
    business_changed = Signal(str)
    note_changed = Signal(str)
    replace_requested = Signal(str)  # file path of replacement
    history_requested = Signal()
    tag_added = Signal(str)
    tag_removed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_asset: dict | None = None
        self._debounce_timer_id = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Preview thumbnail
        self.preview = ImageLabel()
        self.preview.clicked.connect(self._open_preview)
        self.preview.file_dropped.connect(self.replace_requested.emit)
        layout.addWidget(self.preview)

        # Business name
        layout.addWidget(QLabel("业务名:"))
        self.business_edit = QLineEdit()
        self.business_edit.textChanged.connect(lambda t: self.business_changed.emit(t))
        layout.addWidget(self.business_edit)

        # File name (read-only)
        layout.addWidget(QLabel("文件名:"))
        self.file_label = QLabel()
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)

        # Tags
        layout.addWidget(QLabel("标签:"))
        tags_layout = QHBoxLayout()
        self.tag_label = QLabel()
        self.tag_label.setWordWrap(True)
        tags_layout.addWidget(self.tag_label, 1)
        self.add_tag_btn = QPushButton("+")
        self.add_tag_btn.setFixedWidth(28)
        self.add_tag_btn.clicked.connect(lambda: self.tag_added.emit(""))
        self.remove_tag_btn = QPushButton("-")
        self.remove_tag_btn.setFixedWidth(28)
        self.remove_tag_btn.clicked.connect(lambda: self.tag_removed.emit(""))
        tags_layout.addWidget(self.add_tag_btn)
        tags_layout.addWidget(self.remove_tag_btn)
        layout.addLayout(tags_layout)

        # Note
        layout.addWidget(QLabel("备注:"))
        self.note_edit = QTextEdit()
        self.note_edit.setMaximumHeight(120)
        self.note_edit.textChanged.connect(lambda: self.note_changed.emit(self.note_edit.toPlainText()))
        layout.addWidget(self.note_edit)

        # Buttons
        btn_layout = QHBoxLayout()
        self.replace_btn = QPushButton("替换图片")
        self.replace_btn.clicked.connect(self._pick_replacement)
        btn_layout.addWidget(self.replace_btn)

        self.history_btn = QPushButton("历史版本")
        self.history_btn.clicked.connect(self.history_requested.emit)
        btn_layout.addWidget(self.history_btn)
        layout.addLayout(btn_layout)

        layout.addStretch()

    def _pick_replacement(self):
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self, "选择新图片", "", "Images (*.png *.webp *.jpg *.jpeg *.bmp)"
        )
        if path:
            self.replace_requested.emit(path)

    def set_asset(self, asset: dict | None):
        self._current_asset = asset
        if not asset:
            self.clear()
            return

        abspath = os.path.join(ASSETS_ROOT, asset["file"])
        if os.path.exists(abspath):
            reader = QImageReader(abspath)
            reader.setScaledSize(QPixmap(150, 150).size())
            pixmap = QPixmap.fromImageReader(reader)
            self.preview.setPixmap(pixmap)
        else:
            self.preview.setText("[Missing]")
            self.preview.setPixmap(QPixmap())

        self.business_edit.blockSignals(True)
        self.business_edit.setText(asset.get("business_name", ""))
        self.business_edit.blockSignals(False)

        self.file_label.setText(asset.get("file", ""))
        tags = asset.get("tags", [])
        self.tag_label.setText(", ".join(tags) if tags else "(无)")

        self.note_edit.blockSignals(True)
        self.note_edit.setText(asset.get("note", ""))
        self.note_edit.blockSignals(False)

        key = _asset_key_from_path(asset["file"])
        recycle = RecycleManager()
        count = recycle.get_version_count(key)
        self.history_btn.setEnabled(count > 0)
        self.history_btn.setText(f"历史版本 ({count})" if count > 0 else "历史版本 (0)")

        status = asset.get("status")
        if status == "missing":
            self.file_label.setText(f"[已丢失] {asset['file']}")

    def clear(self):
        self._current_asset = None
        self.preview.setPixmap(QPixmap())
        self.preview.setText("")
        self.business_edit.clear()
        self.file_label.clear()
        self.tag_label.clear()
        self.note_edit.clear()
        self.history_btn.setText("历史版本 (0)")
        self.history_btn.setEnabled(False)

    def _open_preview(self):
        if not self._current_asset:
            return
        abspath = os.path.join(ASSETS_ROOT, self._current_asset["file"])
        if os.path.exists(abspath):
            dialog = QDialog(self)
            dialog.setWindowTitle("图片预览")
            dialog.resize(800, 600)
            layout = QVBoxLayout(dialog)
            label = QLabel()
            pixmap = QPixmap(abspath)
            label.setPixmap(pixmap.scaled(780, 560, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
            dialog.exec()


class VersionHistoryDialog(QDialog):
    """Dialog showing version history with ability to switch/delete."""

    restore_requested = Signal(str, int)  # asset_key, version
    delete_requested = Signal(str, int)

    def __init__(self, asset, parent=None):
        super().__init__(parent)
        self.asset = asset
        self.asset_key = _asset_key_from_path(asset["file"])

        self.setWindowTitle(f"历史版本 — {asset.get('business_name', asset['file'])}")
        self.resize(500, 400)

        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._update_preview)
        layout.addWidget(self.list_widget)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(150)
        layout.addWidget(self.preview_label)

        btn_layout = QHBoxLayout()
        self.restore_btn = QPushButton("切换到此版本")
        self.restore_btn.clicked.connect(self._restore)
        btn_layout.addWidget(self.restore_btn)

        self.delete_btn = QPushButton("删除此版本")
        self.delete_btn.clicked.connect(self._delete)
        btn_layout.addWidget(self.delete_btn)

        btn_layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self._populate()

    def _populate(self):
        recycle = RecycleManager()
        self._versions = recycle.list_versions(self.asset_key)
        for ver in self._versions:
            item = QListWidgetItem(f"v{ver['version']} — {ver['added_at'][:19]} — {ver.get('reason', '')}")
            item.setData(Qt.UserRole, ver)
            self.list_widget.addItem(item)

    def _update_preview(self):
        item = self.list_widget.currentItem()
        if not item:
            self.preview_label.clear()
            return
        ver = item.data(Qt.UserRole)
        recycle_dir = os.path.join("data", "asset_library", "recycle", "files", self.asset_key)
        filepath = os.path.join(recycle_dir, ver["file"])
        if os.path.exists(filepath):
            pixmap = QPixmap(filepath)
            self.preview_label.setPixmap(pixmap.scaled(400, 140, Qt.KeepAspectRatio))
        else:
            self.preview_label.setText("[File missing in recycle]")

    def _restore(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        ver = item.data(Qt.UserRole)

        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            "确认切换版本",
            f"当前文件将存档为新版本，并恢复为 v{ver['version']}。是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.restore_requested.emit(self.asset_key, ver["version"])
            self.accept()

    def _delete(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        ver = item.data(Qt.UserRole)

        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.warning(
            self,
            "确认删除",
            f"将永久删除 v{ver['version']}，不可撤销。是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.delete_requested.emit(self.asset_key, ver["version"])
            self.accept()
```

- [ ] **Step 2: Verify syntax**

```bash
uv run python -m py_compile tasks/tools/asset_library/widgets.py
```

- [ ] **Step 3: Commit**

```bash
git add tasks/tools/asset_library/widgets.py
git commit -m "feat(asset_manager): add UI widgets — tree, grid, detail panel, version dialog"
```

---

### Task 6: AssetManager — Main Window Assembly

**Files:**
- Create: `tasks/tools/asset_manager.py`

- [ ] **Step 1: Write AssetManager window**

Write `tasks/tools/asset_manager.py`:

```python
"""Asset Manager — main floating window for browsing, tagging, and replacing game images."""

import os
import shutil

from PySide6.QtCore import QT_TRANSLATE_NOOP, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from module.logger import log
from tasks.tools.asset_library.model import AssetLibraryModel
from tasks.tools.asset_library.recycle import RecycleManager, _asset_key_from_path
from tasks.tools.asset_library.scan_worker import ScanWorker
from tasks.tools.asset_library.widgets import (
    AssetDetailPanel,
    AssetGridWidget,
    CategoryTree,
    VersionHistoryDialog,
    ASSETS_ROOT,
)


class AssetManager(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("资产管理")
        self.resize(1200, 750)
        self.setMinimumSize(900, 550)

        self.model = AssetLibraryModel()
        self.recycle = RecycleManager()
        self._current_asset: dict | None = None

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(1500)
        self._debounce_timer.timeout.connect(self._flush_model)

        self._init_ui()
        self._connect_signals()
        self._start_scan()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        # --- Top bar ---
        top_bar = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("搜索业务名/备注/路径...")
        self.search_bar.setClearButtonEnabled(True)
        top_bar.addWidget(self.search_bar, 1)

        self.tag_filter = QComboBox()
        self.tag_filter.addItems(["全部标签", "通用", "中", "英", "亮色", "暗色"])
        self.tag_filter.setCurrentIndex(0)
        top_bar.addWidget(self.tag_filter)

        self.refresh_btn = QPushButton("刷新扫描")
        top_bar.addWidget(self.refresh_btn)
        main_layout.addLayout(top_bar)

        # --- Progress ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # --- Main content: 3-panel splitter ---
        splitter = QSplitter(Qt.Horizontal)

        # Left: category tree
        self.tree = CategoryTree()
        splitter.addWidget(self.tree)

        # Center: thumbnail grid
        self.grid = AssetGridWidget()
        splitter.addWidget(self.grid)

        # Right: detail panel
        self.detail = AssetDetailPanel()
        splitter.addWidget(self.detail)

        splitter.setSizes([180, 700, 320])
        main_layout.addWidget(splitter, 1)

        # --- Status bar ---
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("就绪")
        main_layout.addWidget(self.status_bar)

    def _connect_signals(self):
        self.tree.category_selected.connect(self._on_category_selected)
        self.search_bar.textChanged.connect(self._on_search)
        self.tag_filter.currentIndexChanged.connect(self._on_tag_changed)

        self.grid.asset_selected.connect(self._on_asset_selected)
        self.grid.context_menu_requested.connect(self._on_context_menu)

        self.detail.business_changed.connect(self._on_business_changed)
        self.detail.note_changed.connect(self._on_note_changed)
        self.detail.replace_requested.connect(self._on_replace)
        self.detail.history_requested.connect(self._on_history)
        self.detail.tag_added.connect(self._on_tag_added)
        self.detail.tag_removed.connect(self._on_tag_removed)
        self.detail.replace_btn.clicked.connect(self._on_replace_from_file_dialog)

        self.refresh_btn.clicked.connect(self._start_scan)

    def _start_scan(self):
        self.refresh_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.status_bar.showMessage("正在扫描资产...")

        self.worker = ScanWorker(self.model)
        self.worker.progress.connect(self._on_scan_progress)
        self.worker.finished.connect(self._on_scan_finished)
        self.worker.error.connect(self._on_scan_error)
        self.worker.start()

    def _on_scan_progress(self, current, total):
        pct = int(current / total * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)

    def _on_scan_finished(self, diff):
        self.model.apply_scan_result(diff)
        added = len(diff.get("added", []))
        changed = len(diff.get("changed", []))
        deleted = len(diff.get("deleted", []))

        self._refresh_grid()
        self.progress_bar.setVisible(False)
        self.refresh_btn.setEnabled(True)

        msg_parts = []
        if added:
            msg_parts.append(f"新增 {added}")
        if changed:
            msg_parts.append(f"变更 {changed}")
        if deleted:
            msg_parts.append(f"丢失 {deleted}")

        if msg_parts:
            self.status_bar.showMessage(", ".join(msg_parts))
        else:
            self.status_bar.showMessage("扫描完成，无变化")

    def _on_scan_error(self, error_msg):
        self.progress_bar.setVisible(False)
        self.refresh_btn.setEnabled(True)
        self.status_bar.showMessage(f"扫描失败: {error_msg}")
        log.error(f"AssetManager scan error: {error_msg}")

    # --- Grid refresh ---

    def _refresh_grid(self):
        category = getattr(self, "_active_category", None)
        search = self.search_bar.text().strip() or None
        tags = self._active_tags()
        assets = self.model.get_assets(category=category, tags=tags, search=search)
        self.grid.set_assets(assets)

        total = self._total_count()
        self.status_bar.showMessage(f"共 {total} 个资产  |  筛选结果 {len(assets)}")

    def _total_count(self) -> int:
        count = 0
        for cat in self.model.get_all_categories():
            count += len(self.model._load_yaml(cat))
        return count

    # --- Filtering ---

    def _active_tags(self) -> list[str] | None:
        idx = self.tag_filter.currentIndex()
        text = self.tag_filter.currentText()
        if idx == 0 or not text:
            return None
        return [text]

    def _on_category_selected(self, category):
        self._active_category = category
        self._refresh_grid()

    def _on_search(self, _text):
        self._refresh_grid()

    def _on_tag_changed(self, _idx):
        self._refresh_grid()

    # --- Detail panel events ---

    def _on_asset_selected(self, asset: dict):
        self._flush_model()
        self._current_asset = asset
        self.detail.set_asset(asset)

    def _on_business_changed(self, text: str):
        if self._current_asset:
            self.model.update_asset(self._current_asset["file"], business_name=text)
            self._current_asset["business_name"] = text
            self._reset_debounce()

    def _on_note_changed(self, text: str):
        if self._current_asset:
            self.model.update_asset(self._current_asset["file"], note=text)
            self._current_asset["note"] = text
            self._reset_debounce()

    def _on_tag_added(self, _tag):
        if not self._current_asset:
            return
        existing = list(self._current_asset.get("tags") or [])

        from PySide6.QtWidgets import QInputDialog

        tag, ok = QInputDialog.getText(self, "添加标签", "输入新标签:")
        if ok and tag.strip():
            existing.append(tag.strip())
            self.model.update_asset(self._current_asset["file"], tags=existing)
            self._current_asset["tags"] = existing
            self.detail.tag_label.setText(", ".join(existing))
            self._reset_debounce()

    def _on_tag_removed(self, _tag):
        if not self._current_asset:
            return
        existing = list(self._current_asset.get("tags") or [])
        if not existing:
            return

        from PySide6.QtWidgets import QInputDialog

        tag, ok = QInputDialog.getItem(
            self, "删除标签", "选择要删除的标签:", existing, 0, False
        )
        if ok and tag in existing:
            existing.remove(tag)
            self.model.update_asset(self._current_asset["file"], tags=existing)
            self._current_asset["tags"] = existing
            self.detail.tag_label.setText(", ".join(existing))
            self._reset_debounce()

    def _on_replace(self, filepath: str):
        if not self._current_asset:
            return
        current_file = self._current_asset["file"]
        current_abspath = os.path.join(ASSETS_ROOT, current_file)
        dest_dir = os.path.dirname(current_abspath)
        dest_filename = os.path.basename(current_file)
        dest = os.path.join(dest_dir, dest_filename)

        reply = QMessageBox.question(
            self,
            "确认替换",
            f"将 \"{current_file}\" 替换为\n\"{filepath}\"?\n\n旧文件将存档到回收站。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Archive current
        self.recycle.archive(current_file, reason="Manual replacement")

        # Copy new over
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(filepath, dest)

        # Update model
        from tasks.tools.asset_library.model import _file_to_checksum

        new_checksum = _file_to_checksum(dest)
        self.model.update_asset(current_file, checksum=new_checksum)
        self._current_asset["checksum"] = new_checksum
        self._flush_model()

        # Refresh grid + detail
        self._refresh_grid()
        self.detail.set_asset(self._current_asset)

        self.status_bar.showMessage(f"已替换: {current_file}")

    def _on_replace_from_file_dialog(self):
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self, "选择新图片", "", "Images (*.png *.webp *.jpg *.jpeg *.bmp)"
        )
        if path:
            self._on_replace(path)

    def _on_history(self):
        if not self._current_asset:
            return
        dialog = VersionHistoryDialog(self._current_asset, self)
        dialog.restore_requested.connect(self._on_version_restore)
        dialog.delete_requested.connect(self._on_version_delete)
        dialog.exec()

    def _on_version_restore(self, asset_key: str, version: int):
        restored_path = self.recycle.restore(asset_key, version)
        if restored_path:
            # Clear cache + rescan for this asset
            self.model._assets_cache.clear()
            self._refresh_grid()
            updated = self.model.get_asset(restored_path)
            if updated:
                self.detail.set_asset(updated)
                self._current_asset = updated
            self.status_bar.showMessage(f"已恢复到 v{version}: {restored_path}")
        else:
            QMessageBox.warning(self, "恢复失败", "无法恢复指定的版本，文件可能已丢失。")

    def _on_version_delete(self, asset_key: str, version: int):
        self.recycle.permanently_delete(asset_key, version)
        self.status_bar.showMessage(f"已永久删除 v{version}")

    def _on_context_menu(self, action_data, _item):
        action, asset = action_data
        if action == "mark_missing":
            self.model.mark_as_missing(asset["file"])
            self._flush_model()
            self._refresh_grid()
        elif action == "restore":
            key = _asset_key_from_path(asset["file"])
            if self.recycle.has_versions(key):
                # Use the latest version
                versions = self.recycle.list_versions(key)
                latest = versions[-1]
                reply = QMessageBox.question(
                    self,
                    "从回收站恢复",
                    f"将恢复 v{latest['version']} ({latest.get('reason', '')})?\n当前 Missing 标记将被清除。",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    self._on_version_restore(key, latest["version"])

    # --- Debounce ---

    def _reset_debounce(self):
        self._debounce_timer.start()

    def _flush_model(self):
        """Write all pending changes to disk."""
        self._debounce_timer.stop()
        if self.model.has_dirty:
            self.model.flush_dirty()

    def closeEvent(self, event):
        self._flush_model()
        super().closeEvent(event)
```

- [ ] **Step 2: Verify syntax**

```bash
uv run python -m py_compile tasks/tools/asset_manager.py
```

- [ ] **Step 3: Commit**

```bash
git add tasks/tools/asset_manager.py
git commit -m "feat(asset_manager): add AssetManager main window with signal routing"
```

---

### Task 7: Project Integration

**Files:**
- Modify: `tasks/tools/__init__.py`
- Modify: `app/tools_interface.py`
- Modify: `.gitignore`

- [ ] **Step 1: Register asset_manager in ToolManager**

Edit `tasks/tools/__init__.py`:

Add import at top (after existing imports):
```python
from tasks.tools.asset_manager import AssetManager
```

Add tool dispatch in `run_tools()` method, after the `elif self.tool == "issue_replay":` block:
```python
                elif self.tool == "asset_manager":
                    self.w = AssetManager()
```

Update the `ToolManager.__init__` type hint and `start()` signature to include `"asset_manager"`:
```python
class ToolManager:
    def __init__(self, tool: Literal["battle", "production", "screenshot", "issue_replay", "asset_manager"]):
```

```python
def start(tool: Literal["battle", "production", "screenshot", "issue_replay", "asset_manager"]):
```

- [ ] **Step 2: Add card in tools_interface**

Edit `app/tools_interface.py`:

In `__init_card()`, add after the `self.issue_replay_card` block:
```python
        self.asset_manager_card = BasePushSettingCard(
            QT_TRANSLATE_NOOP("BasePushSettingCard", "运行"),
            FIF.ALBUM,
            QT_TRANSLATE_NOOP("BasePushSettingCard", "资产管理"),
            QT_TRANSLATE_NOOP(
                "BasePushSettingCard",
                "可视化浏览、分类、替换游戏图片资产",
            ),
            parent=self.tools_group,
        )
```

In `__initLayout()`, add after `self.tools_group.addSettingCard(self.issue_replay_card)`:
```python
        self.tools_group.addSettingCard(self.asset_manager_card)
```

In `__connect_signal()`, add after `self.issue_replay_card.clicked...`:
```python
        self.asset_manager_card.clicked.connect(lambda: self._tool_start("asset_manager", self.asset_manager_card))
```

- [ ] **Step 3: Update .gitignore**

Add at the end of `.gitignore`:
```
# Asset library recycle bin and scan cache (large binaries, local-only)
data/asset_library/recycle/
data/asset_library/scan_cache.json
```

- [ ] **Step 4: Verify syntax for all changed files**

```bash
uv run python -m py_compile tasks/tools/__init__.py
uv run python -m py_compile app/tools_interface.py
```

- [ ] **Step 5: Run lint**

```bash
uv run ruff check tasks/tools/asset_library/ tasks/tools/asset_manager.py tasks/tools/__init__.py app/tools_interface.py
```

Fix any lint issues.

- [ ] **Step 6: Commit**

```bash
git add tasks/tools/__init__.py app/tools_interface.py .gitignore
git commit -m "feat(asset_manager): integrate into tools launcher and .gitignore"
```

---

### Task 8: Manual Verification

No automated test suite exists. Verify manually:

- [ ] **Step 1: Launch the tool from UI**

Run the app and click "资产管理" in the tools tab. Verify:
- Window opens with category tree, empty grid, detail panel
- Progress bar appears during scan
- After scan, grid populates with thumbnails
- Status bar shows asset count

- [ ] **Step 2: Browse and filter**

- Click different category nodes → grid filters correctly
- Type in search bar → real-time filter by business_name/note/path
- Select a grid item → detail panel fills with data

- [ ] **Step 3: Edit metadata**

- Type a business name → switch to another item → switch back → name persisted
- Add/remove tags
- Write a note
- Close and reopen window → data persists

- [ ] **Step 4: Replace an image**

- Select an asset → click "替换图片" → choose a different PNG
- Confirm → original preserved in recycle, new image at original path
- Click "历史版本" → see version entry

- [ ] **Step 5: Version switching**

- In version history dialog → select v1 → "切换到此版本"
- Confirm → grid refreshes
- Open version history again → v2 added (current version archived), total versions incremented

- [ ] **Step 6: Right-click context menu**

- Right-click a grid item → "在文件管理器中打开" opens Explorer
- "复制路径" copies to clipboard (paste to verify)

- [ ] **Step 7: Drag & drop**

- Drag a PNG from Explorer into the detail panel thumbnail area → triggers replace flow

- [ ] **Step 8: External deletion resilience**

- Manually delete an image file from disk
- Click "刷新扫描" → asset shows as [Missing] with red placeholder
- Use right-click "从回收站恢复" → restored

- [ ] **Step 9: Second launch cache**

- Close and reopen
- Scan should complete much faster (mtime/size cache hits)
