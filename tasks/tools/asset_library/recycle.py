"""Recycle bin with version chain for asset file replacement history."""

import os
import shutil
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
            log.info("RecycleManager.restore: original file missing, restoring from scratch")

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
