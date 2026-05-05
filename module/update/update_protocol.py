from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from packaging.version import InvalidVersion, parse

UPDATE_MANIFEST_NAME = "update_manifest.json"
MANAGED_FILES_NAME = "managed_files.txt"
REMOTE_UPDATE_MANIFEST_ASSET = "AALC.update_manifest.json"
INSTALLED_MANIFEST_PATH = "assets/config/installed_manifest.txt"
INSTALLED_MANIFEST_META_PATH = "assets/config/installed_manifest_meta.json"
BOOTSTRAP_VERSION_PATH = "assets/config/bootstrap_version.txt"
LEGACY_DANGEROUS_VERSION = "1.5.0-canary.9"

DEFAULT_PROTECTED_PATHS = [
    "config.yaml",
    "theme_pack_list.yaml",
    "logs/",
    "update_temp/",
    "3rdparty/",
    "theme_pack_weight/",
    "__pycache__/",
]


def normalize_version_text(version: str) -> str:
    cleaned = version.strip().lstrip("Vv")
    return re.sub(r"-canary[\\.-]?", "dev", cleaned)


def version_at_least(current: str, minimum: str) -> bool:
    return parse(normalize_version_text(current)) >= parse(normalize_version_text(minimum))


def version_at_most(current: str, maximum: str) -> bool:
    return parse(normalize_version_text(current)) <= parse(normalize_version_text(maximum))


def is_protected_path(rel_path: str, protected_paths: list[str]) -> bool:
    normalized = str(PurePosixPath(rel_path.replace("\\", "/"))).lower()
    for protected in protected_paths:
        protected_norm = protected.replace("\\", "/").strip("/").lower()
        if not protected_norm:
            continue
        if normalized == protected_norm or normalized.startswith(protected_norm + "/"):
            return True
    return False


def validate_relative_manifest_path(rel_path: str, protected_paths: list[str]) -> str:
    candidate = rel_path.replace("\\", "/").strip()
    if not candidate:
        raise ValueError("empty manifest path")
    if candidate.startswith("//") or re.match(r"^[A-Za-z]:(?:/|$|[^/])", candidate):
        raise ValueError(f"absolute manifest path is forbidden: {rel_path}")

    pure = PurePosixPath(candidate)
    if pure.is_absolute():
        raise ValueError(f"absolute manifest path is forbidden: {rel_path}")
    if any(":" in part for part in pure.parts):
        raise ValueError(f"unsafe manifest path: {rel_path}")
    if any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"unsafe manifest path: {rel_path}")

    normalized = str(pure)
    if normalized in {"", "."}:
        raise ValueError(f"unsafe manifest path: {rel_path}")
    if is_protected_path(normalized, protected_paths):
        raise ValueError(f"protected path is forbidden: {rel_path}")
    return normalized


def resolve_safe_child(root: Path, rel_path: str) -> Path:
    candidate = root / Path(*rel_path.split("/"))
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()
    resolved_candidate.relative_to(resolved_root)
    return resolved_candidate


def collect_managed_files(app_root: Path, protected_paths: list[str]) -> list[str]:
    managed_files: list[str] = []
    for path in sorted(app_root.rglob("*")):
        if not path.is_file():
            continue
        rel_path = path.relative_to(app_root).as_posix()
        if rel_path in {UPDATE_MANIFEST_NAME, MANAGED_FILES_NAME}:
            continue
        if is_protected_path(rel_path, protected_paths):
            continue
        managed_files.append(rel_path)
    return managed_files


def build_update_manifest(
    *,
    version: str,
    bootstrap_version: int,
    package_layout: str,
    cleanup_mode: str,
    min_source_version_for_cleanup: str,
    managed_files_sha256: str,
    protected_paths: list[str],
) -> dict[str, object]:
    return {
        "format_version": 1,
        "bootstrap_version": bootstrap_version,
        "current_version": version,
        "package_layout": package_layout,
        "cleanup_mode": cleanup_mode,
        "min_source_version_for_cleanup": min_source_version_for_cleanup,
        "managed_files_manifest": MANAGED_FILES_NAME,
        "managed_files_sha256": managed_files_sha256,
        "protected_paths": protected_paths,
    }


def read_bootstrap_version(install_root: Path) -> int:
    try:
        value = resolve_safe_child(install_root, BOOTSTRAP_VERSION_PATH).read_text(encoding="utf-8").strip()
        parsed = int(value)
    except (OSError, ValueError):
        return 1
    return parsed if parsed >= 1 else 1


def select_compatible_release(
    bundles: list[dict[str, object]], local_bootstrap_version: int
) -> dict[str, object] | None:
    best_bundle: dict[str, object] | None = None
    best_version = None
    for bundle in bundles:
        manifest = bundle.get("manifest")
        if not isinstance(manifest, dict):
            continue
        if "bootstrap_version" not in manifest:
            continue
        required_bootstrap_version = manifest.get("bootstrap_version")
        try:
            required_bootstrap_version = int(required_bootstrap_version)
        except (TypeError, ValueError):
            continue
        if required_bootstrap_version < 1:
            continue
        if required_bootstrap_version <= local_bootstrap_version:
            tag_name = bundle.get("tag_name")
            if not isinstance(tag_name, str) or not tag_name.strip():
                continue
            try:
                bundle_version = parse(normalize_version_text(tag_name))
            except InvalidVersion:
                continue
            if best_version is None or bundle_version > best_version:
                best_bundle = bundle
                best_version = bundle_version
    return best_bundle
