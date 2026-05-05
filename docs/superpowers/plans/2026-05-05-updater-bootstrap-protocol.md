# Updater Bootstrap Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a protocol-driven updater that copies only managed files, blocks path traversal and protected-path writes, persists installed manifests locally, and chooses a bridge release when the local updater bootstrap is too old.

**Architecture:** Add one shared pure-Python helper module for updater protocol constants, version comparison, path validation, manifest generation, and release compatibility selection. Wire that module into `scripts/build.py`, `updater.py`, and `module/update/check_update.py`, then cover the new behavior with `unittest` plus the existing local update flow script.

**Tech Stack:** Python 3.12+, PyInstaller, requests, packaging.version, unittest, pathlib, 7-Zip CLI, existing AALC update workflow

---

## File Structure

- Create: `module/update/update_protocol.py`
  Responsibility: protocol constants, version helpers, protected-path checks, safe relative-path validation, managed-file collection, manifest generation, release compatibility selection.

- Create: `tests/test_update_protocol.py`
  Responsibility: `unittest` coverage for protocol helpers, release selection, and updater install flow.

- Modify: `scripts/build.py`
  Responsibility: emit payload protocol files, emit release sidecar manifest asset, support bridge build layout, keep archive/hash generation working.

- Modify: `updater.py`
  Responsibility: load payload protocol files from extracted update payload, copy only declared managed files, refuse protected-path writes and path traversal, delete only retired managed files, persist `installed_manifest.txt` and its metadata.

- Modify: `module/update/check_update.py`
  Responsibility: scan release assets, fetch the sidecar manifest for each candidate release, read local bootstrap version, select the newest compatible release, and cache the compatible archive URL.

- Modify: `test_update_flow.py`
  Responsibility: manual regression harness for canary.9 directory simulation, log preservation checks, retired-file cleanup checks, and bootstrap/install-manifest inspection.

---

### Task 1: Create Shared Protocol Helpers

**Files:**
- Create: `module/update/update_protocol.py`
- Create: `tests/test_update_protocol.py`

- [ ] **Step 1: Write the failing helper tests**

Create `tests/test_update_protocol.py` with these first helper-level tests:

```python
import tempfile
import unittest
from pathlib import Path

from module.update.update_protocol import (
    DEFAULT_PROTECTED_PATHS,
    normalize_version_text,
    resolve_safe_child,
    validate_relative_manifest_path,
    version_at_least,
    version_at_most,
)


class TestUpdateProtocolHelpers(unittest.TestCase):
    def test_canary_versions_compare_with_packaging_rules(self):
        self.assertEqual(normalize_version_text("v1.5.0-canary.9"), "1.5.0dev9")
        self.assertTrue(version_at_most("1.5.0-canary.9", "1.5.0-canary.9"))
        self.assertTrue(version_at_least("1.5.0-canary.10", "1.5.0-canary.9"))
        self.assertFalse(version_at_least("1.5.0-canary.9", "1.5.0-canary.10"))

    def test_validate_relative_manifest_path_rejects_absolute_and_escape_paths(self):
        bad_values = [
            "../evil.txt",
            "..\\evil.txt",
            "/evil.txt",
            "C:/evil.txt",
            r"C:\\evil.txt",
            "//server/share.txt",
        ]
        for value in bad_values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_relative_manifest_path(value, DEFAULT_PROTECTED_PATHS)

    def test_validate_relative_manifest_path_rejects_protected_targets(self):
        protected_values = [
            "logs/debugLog.log",
            "config.yaml",
            "theme_pack_list.yaml",
            "update_temp/AALC.7z",
        ]
        for value in protected_values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_relative_manifest_path(value, DEFAULT_PROTECTED_PATHS)

    def test_resolve_safe_child_stays_under_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resolved = resolve_safe_child(root, "assets/config/version.txt")
            self.assertEqual(resolved, root / "assets" / "config" / "version.txt")
            self.assertTrue(str(resolved).startswith(str(root.resolve())))
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run: `uv run python -m unittest tests.test_update_protocol.TestUpdateProtocolHelpers -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'module.update.update_protocol'`.

- [ ] **Step 3: Implement the helper module**

Create `module/update/update_protocol.py` with this initial content:

```python
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from packaging.version import parse

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
    return re.sub(r"-canary[\.-]?", "dev", cleaned)


def version_at_least(current: str, minimum: str) -> bool:
    return parse(normalize_version_text(current)) >= parse(normalize_version_text(minimum))


def version_at_most(current: str, maximum: str) -> bool:
    return parse(normalize_version_text(current)) <= parse(normalize_version_text(maximum))


def is_protected_path(rel_path: str, protected_paths: list[str]) -> bool:
    normalized = str(PurePosixPath(rel_path.replace("\\", "/")))
    for protected in protected_paths:
        protected_norm = protected.replace("\\", "/").strip("/")
        if not protected_norm:
            continue
        if normalized == protected_norm or normalized.startswith(protected_norm + "/"):
            return True
    return False


def validate_relative_manifest_path(rel_path: str, protected_paths: list[str]) -> str:
    candidate = rel_path.replace("\\", "/").strip()
    if not candidate:
        raise ValueError("empty manifest path")
    if candidate.startswith("//") or re.match(r"^[A-Za-z]:/", candidate):
        raise ValueError(f"absolute manifest path is forbidden: {rel_path}")

    pure = PurePosixPath(candidate)
    if pure.is_absolute():
        raise ValueError(f"absolute manifest path is forbidden: {rel_path}")
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
```

- [ ] **Step 4: Run the helper tests again**

Run: `uv run python -m unittest tests.test_update_protocol.TestUpdateProtocolHelpers -v`

Expected: PASS for all 4 tests.

- [ ] **Step 5: Run syntax verification**

Run: `uv run python -m py_compile module/update/update_protocol.py tests/test_update_protocol.py`

Expected: command exits successfully with no output.

- [ ] **Step 6: Commit**

```bash
git add module/update/update_protocol.py tests/test_update_protocol.py
git commit -m "feat: 新增更新协议基础辅助模块"
```

---

### Task 2: Add Metadata Generation And Release Selection Helpers

**Files:**
- Modify: `module/update/update_protocol.py`
- Modify: `tests/test_update_protocol.py`

- [ ] **Step 1: Extend the test file with metadata and release-selection failures**

Append these tests to `tests/test_update_protocol.py`:

```python
from module.update.update_protocol import (
    DEFAULT_PROTECTED_PATHS,
    build_update_manifest,
    collect_managed_files,
    select_compatible_release,
)


class TestUpdateMetadataHelpers(unittest.TestCase):
    def test_collect_managed_files_skips_protected_and_control_plane_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_root = Path(tmp)
            (app_root / "AALC.exe").write_text("exe", encoding="utf-8")
            (app_root / "logs").mkdir()
            (app_root / "logs" / "debugLog.log").write_text("log", encoding="utf-8")
            (app_root / "assets" / "config").mkdir(parents=True)
            (app_root / "assets" / "config" / "version.txt").write_text("1.5.0-canary.11", encoding="utf-8")
            (app_root / "assets" / "config" / "bootstrap_version.txt").write_text("2", encoding="utf-8")
            (app_root / "update_manifest.json").write_text("{}", encoding="utf-8")
            (app_root / "managed_files.txt").write_text("", encoding="utf-8")

            managed_files = collect_managed_files(app_root, DEFAULT_PROTECTED_PATHS)

            self.assertEqual(
                managed_files,
                [
                    "AALC.exe",
                    "assets/config/bootstrap_version.txt",
                    "assets/config/version.txt",
                ],
            )

    def test_build_update_manifest_carries_required_protocol_fields(self):
        manifest = build_update_manifest(
            version="1.5.0-canary.11",
            bootstrap_version=2,
            package_layout="root_dir",
            cleanup_mode="managed_only",
            min_source_version_for_cleanup="1.5.0-canary.11",
            managed_files_sha256="abc123",
            protected_paths=DEFAULT_PROTECTED_PATHS,
        )

        self.assertEqual(manifest["format_version"], 1)
        self.assertEqual(manifest["bootstrap_version"], 2)
        self.assertEqual(manifest["package_layout"], "root_dir")
        self.assertEqual(manifest["managed_files_manifest"], "managed_files.txt")
        self.assertEqual(manifest["managed_files_sha256"], "abc123")
        self.assertEqual(manifest["protected_paths"], DEFAULT_PROTECTED_PATHS)


class TestReleaseSelection(unittest.TestCase):
    def test_select_compatible_release_prefers_latest_compatible_bundle(self):
        bundles = [
            {
                "tag_name": "v1.5.0-canary.12",
                "archive_url": "https://example.test/12.7z",
                "manifest_url": "https://example.test/12.json",
                "manifest": {"bootstrap_version": 2},
            },
            {
                "tag_name": "v1.5.0-canary.11",
                "archive_url": "https://example.test/11.7z",
                "manifest_url": "https://example.test/11.json",
                "manifest": {"bootstrap_version": 1},
            },
        ]

        selected = select_compatible_release(bundles, local_bootstrap_version=1)

        self.assertEqual(selected["tag_name"], "v1.5.0-canary.11")

    def test_select_compatible_release_returns_none_when_everything_is_incompatible(self):
        bundles = [
            {
                "tag_name": "v1.5.0-canary.12",
                "archive_url": "https://example.test/12.7z",
                "manifest_url": "https://example.test/12.json",
                "manifest": {"bootstrap_version": 3},
            }
        ]

        self.assertIsNone(select_compatible_release(bundles, local_bootstrap_version=1))
```

- [ ] **Step 2: Run the extended tests and verify they fail**

Run: `uv run python -m unittest tests.test_update_protocol.TestUpdateMetadataHelpers tests.test_update_protocol.TestReleaseSelection -v`

Expected: FAIL with `ImportError` or `AttributeError` for `collect_managed_files`, `build_update_manifest`, or `select_compatible_release`.

- [ ] **Step 3: Implement the new shared helpers**

Extend `module/update/update_protocol.py` with these functions below `resolve_safe_child()`:

```python
def collect_managed_files(app_root: Path, protected_paths: list[str]) -> list[str]:
    managed_files = []
    for file_path in sorted(app_root.rglob("*")):
        if not file_path.is_file():
            continue
        rel_path = file_path.relative_to(app_root).as_posix()
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
) -> dict:
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
    version_file = install_root / BOOTSTRAP_VERSION_PATH
    if not version_file.exists():
        return 1
    try:
        return int(version_file.read_text(encoding="utf-8").strip())
    except ValueError:
        return 1


def select_compatible_release(bundles: list[dict], local_bootstrap_version: int) -> dict | None:
    for bundle in bundles:
        required = int(bundle["manifest"].get("bootstrap_version", 1))
        if local_bootstrap_version >= required:
            return bundle
    return None
```

- [ ] **Step 4: Run the metadata and release-selection tests again**

Run: `uv run python -m unittest tests.test_update_protocol.TestUpdateMetadataHelpers tests.test_update_protocol.TestReleaseSelection -v`

Expected: PASS for all 4 tests.

- [ ] **Step 5: Re-run the full shared helper test file**

Run: `uv run python -m unittest tests.test_update_protocol -v`

Expected: PASS for all tests currently in `tests/test_update_protocol.py`.

- [ ] **Step 6: Commit**

```bash
git add module/update/update_protocol.py tests/test_update_protocol.py
git commit -m "feat: 新增更新协议元数据与兼容版本选择逻辑"
```

---

### Task 3: Generate Payload Metadata And Bridge Builds

**Files:**
- Modify: `scripts/build.py`

- [ ] **Step 1: Add bridge-mode arguments and metadata staging**

Update `scripts/build.py` imports and argument parsing to add bridge support and shared helper usage:

```python
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import PyInstaller.__main__

from module.update.update_protocol import (
    BOOTSTRAP_VERSION_PATH,
    DEFAULT_PROTECTED_PATHS,
    REMOTE_UPDATE_MANIFEST_ASSET,
    UPDATE_MANIFEST_NAME,
    build_update_manifest,
    collect_managed_files,
)

parser = argparse.ArgumentParser(description="Build AALC")
parser.add_argument("--version", default="dev", help="AALC Version")
parser.add_argument(
    "--bridge-updater",
    action="store_true",
    help="Build root_dir archive for legacy updater bridge releases",
)
parser.add_argument(
    "--bootstrap-version",
    type=int,
    default=2,
    help="Updater bootstrap protocol version bundled into the build",
)
args = parser.parse_args()
version = args.version
```

- [ ] **Step 2: Write protocol files into the payload root and release sidecar asset**

Insert this block after writing `dist/AALC/assets/config/version.txt` and before the redundant-file trimming loop:

```python
app_root = Path("dist") / "AALC"
bootstrap_version_path = app_root / Path(BOOTSTRAP_VERSION_PATH)
bootstrap_version_path.parent.mkdir(parents=True, exist_ok=True)
bootstrap_version_path.write_text(f"{args.bootstrap_version}\n", encoding="utf-8")

managed_files = collect_managed_files(app_root, DEFAULT_PROTECTED_PATHS)
managed_files_path = app_root / "managed_files.txt"
managed_files_path.write_text("\n".join(managed_files) + "\n", encoding="utf-8")
managed_files_sha256 = hashlib.sha256(managed_files_path.read_bytes()).hexdigest()

payload_manifest = build_update_manifest(
    version=version,
    bootstrap_version=args.bootstrap_version,
    package_layout="root_dir" if args.bridge_updater else "flat",
    cleanup_mode="managed_only",
    min_source_version_for_cleanup=version,
    managed_files_sha256=managed_files_sha256,
    protected_paths=DEFAULT_PROTECTED_PATHS,
)

payload_manifest_path = app_root / UPDATE_MANIFEST_NAME
payload_manifest_path.write_text(
    json.dumps(payload_manifest, indent=2, ensure_ascii=True) + "\n",
    encoding="utf-8",
)

shutil.copy(payload_manifest_path, Path("dist") / REMOTE_UPDATE_MANIFEST_ASSET)
```

This keeps the internal protocol files inside the payload root, which old bridge installs can actually copy, while still emitting a standalone sidecar manifest asset that the GUI can fetch from GitHub before downloading the whole archive.

- [ ] **Step 3: Keep normal builds flat and bridge builds root-dir compatible**

Replace the current 7z call at the end of `scripts/build.py` with this exact branch:

```python
if args.bridge_updater:
    subprocess.run(["7z", "a", "-mx=7", f"AALC_{version}.7z", "AALC/*"], cwd="./dist", check=True)
else:
    subprocess.run(
        ["7z", "a", "-mx=7", f"../AALC_{version}.7z", "./*"],
        cwd=os.path.join(".", "dist", "AALC"),
        check=True,
    )
```

- [ ] **Step 4: Run syntax verification**

Run: `uv run python -m py_compile scripts/build.py`

Expected: command exits successfully with no output.

- [ ] **Step 5: Build one normal protocol package**

Run: `uv run python .\scripts\build.py --version 1.5.0-canary.11 --bootstrap-version 2`

Expected: build succeeds and writes a flat archive plus sidecar assets into `dist`.

- [ ] **Step 6: Verify the normal build outputs**

Run:

```bash
uv run python -c "from pathlib import Path; assert Path('dist/AALC/update_manifest.json').exists(); assert Path('dist/AALC/managed_files.txt').exists(); assert Path('dist/AALC/assets/config/bootstrap_version.txt').read_text(encoding='utf-8').strip() == '2'; assert Path('dist/AALC.update_manifest.json').exists()"
```

Expected: command exits successfully with no output.

- [ ] **Step 7: Build one bridge package**

Run: `uv run python .\scripts\build.py --version 1.5.0-canary.11 --bootstrap-version 2 --bridge-updater`

Expected: build succeeds and writes a legacy-compatible bridge archive.

- [ ] **Step 8: Verify the bridge archive layout**

Run: `7z l dist\AALC_1.5.0-canary.11.7z`

Expected: archive listing contains `AALC\AALC.exe`, `AALC\update_manifest.json`, `AALC\managed_files.txt`, and `AALC\assets\config\bootstrap_version.txt`.

- [ ] **Step 9: Commit**

```bash
git add scripts/build.py
git commit -m "feat: 构建流程生成更新协议元数据与桥接包"
```

---

### Task 4: Rewrite Updater Installation Around Managed Files

**Files:**
- Modify: `updater.py`
- Modify: `tests/test_update_protocol.py`

- [ ] **Step 1: Add failing updater-flow tests**

Append these tests to `tests/test_update_protocol.py`:

```python
import json
import hashlib

from updater import Updater


class TestUpdaterInstallFlow(unittest.TestCase):
    def make_install_root(self, tmp: str) -> Path:
        install_root = Path(tmp)
        (install_root / "assets" / "config").mkdir(parents=True)
        (install_root / "assets" / "config" / "version.txt").write_text("1.5.0-canary.9\n", encoding="utf-8")
        (install_root / "logs").mkdir()
        (install_root / "logs" / "debugLog.log").write_text("legacy log\n", encoding="utf-8")
        (install_root / "_internal").mkdir()
        (install_root / "_internal" / "legacy_only.dll").write_text("old dll\n", encoding="utf-8")
        return install_root

    def stage_payload(self, install_root: Path, managed_files: list[str], *, package_layout: str, current_version: str):
        extract_root = install_root / "update_temp" / "AALC"
        payload_root = extract_root if package_layout == "flat" else extract_root / "AALC"
        payload_root.mkdir(parents=True, exist_ok=True)

        for rel_path in managed_files:
            target = payload_root / Path(rel_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rel_path + "\n", encoding="utf-8")

        manifest = {
            "format_version": 1,
            "bootstrap_version": 2,
            "current_version": current_version,
            "package_layout": package_layout,
            "cleanup_mode": "managed_only",
            "min_source_version_for_cleanup": "1.5.0-canary.11",
            "managed_files_manifest": "managed_files.txt",
            "protected_paths": DEFAULT_PROTECTED_PATHS,
        }
        managed_files_text = "\n".join(managed_files) + "\n"
        manifest["managed_files_sha256"] = hashlib.sha256(managed_files_text.encode("utf-8")).hexdigest()
        (payload_root / "update_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
        (payload_root / "managed_files.txt").write_text(managed_files_text, encoding="utf-8")
        return extract_root

    def test_first_migration_preserves_logs_and_writes_installed_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            install_root = self.make_install_root(tmp)
            managed_files = [
                "AALC.exe",
                "_internal/python313.dll",
                "assets/config/version.txt",
                "assets/config/bootstrap_version.txt",
            ]
            self.stage_payload(install_root, managed_files, package_layout="flat", current_version="1.5.0-canary.11")

            updater = Updater("AALC.7z", base_dir=install_root)
            updater.apply_update_from_extracted_payload()

            self.assertTrue((install_root / "logs" / "debugLog.log").exists())
            self.assertTrue((install_root / "assets" / "config" / "installed_manifest.txt").exists())
            self.assertTrue((install_root / "assets" / "config" / "installed_manifest_meta.json").exists())

    def test_cleanup_deletes_only_retired_managed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            install_root = self.make_install_root(tmp)
            installed_manifest = install_root / "assets" / "config" / "installed_manifest.txt"
            installed_manifest.write_text(
                "AALC.exe\n_internal/legacy_only.dll\nassets/config/version.txt\nassets/config/bootstrap_version.txt\n",
                encoding="utf-8",
            )

            managed_files = [
                "AALC.exe",
                "_internal/python313.dll",
                "assets/config/version.txt",
                "assets/config/bootstrap_version.txt",
            ]
            self.stage_payload(install_root, managed_files, package_layout="flat", current_version="1.5.0-canary.12")
            (install_root / "assets" / "config" / "version.txt").write_text("1.5.0-canary.11\n", encoding="utf-8")

            updater = Updater("AALC.7z", base_dir=install_root)
            updater.apply_update_from_extracted_payload()

            self.assertFalse((install_root / "_internal" / "legacy_only.dll").exists())
            self.assertTrue((install_root / "logs" / "debugLog.log").exists())

    def test_payload_declaring_protected_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            install_root = self.make_install_root(tmp)
            managed_files = [
                "AALC.exe",
                "logs/debugLog.log",
                "assets/config/version.txt",
                "assets/config/bootstrap_version.txt",
            ]
            self.stage_payload(install_root, managed_files, package_layout="flat", current_version="1.5.0-canary.11")

            updater = Updater("AALC.7z", base_dir=install_root)
            with self.assertRaises(ValueError):
                updater.apply_update_from_extracted_payload()

    def test_payload_with_bad_managed_files_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            install_root = self.make_install_root(tmp)
            extract_root = self.stage_payload(
                install_root,
                [
                    "AALC.exe",
                    "_internal/python313.dll",
                    "assets/config/version.txt",
                    "assets/config/bootstrap_version.txt",
                ],
                package_layout="flat",
                current_version="1.5.0-canary.11",
            )
            manifest_path = extract_root / "update_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["managed_files_sha256"] = "deadbeef"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

            updater = Updater("AALC.7z", base_dir=install_root)
            with self.assertRaises(ValueError):
                updater.apply_update_from_extracted_payload()
```

- [ ] **Step 2: Run the updater-flow tests and verify they fail**

Run: `uv run python -m unittest tests.test_update_protocol.TestUpdaterInstallFlow -v`

Expected: FAIL because `Updater` has no `base_dir` support and no `apply_update_from_extracted_payload()` method.

- [ ] **Step 3: Refactor `Updater` to use `Path` objects and testable install roots**

Replace the constructor and path setup in `updater.py` with this exact shape:

```python
import json
from pathlib import Path

import psutil

from module.update.update_protocol import (
    BOOTSTRAP_VERSION_PATH,
    DEFAULT_PROTECTED_PATHS,
    INSTALLED_MANIFEST_META_PATH,
    INSTALLED_MANIFEST_PATH,
    LEGACY_DANGEROUS_VERSION,
    MANAGED_FILES_NAME,
    UPDATE_MANIFEST_NAME,
    is_protected_path,
    read_bootstrap_version,
    resolve_safe_child,
    validate_relative_manifest_path,
    version_at_least,
    version_at_most,
)


class Updater:
    def __init__(self, file_name=None, base_dir=None):
        self.process_names = ["AALC.exe"]
        self.base_dir = Path(base_dir or ".").resolve()
        self.file_name = file_name
        self.install_root = self.base_dir
        self.temp_path = self.install_root / "update_temp"
        self.temp_path.mkdir(parents=True, exist_ok=True)
        self.exe_path = self.install_root / "assets" / "binary" / "7za.exe"
        self.extract_root = self.temp_path / Path(self.file_name).stem
        self.download_file_path = self.temp_path / self.file_name
```

- [ ] **Step 4: Replace the old scan-and-delete flow with protocol-driven install methods**

Delete `_build_manifest()`, `_remove_stale_files()`, and the old `cover_folder()` body. Replace them with these methods in `updater.py`:

```python
    def discover_payload_root(self) -> tuple[dict, Path]:
        candidate_paths = [
            self.extract_root / UPDATE_MANIFEST_NAME,
            self.extract_root / "AALC" / UPDATE_MANIFEST_NAME,
        ]
        manifests = [path for path in candidate_paths if path.is_file()]
        if len(manifests) != 1:
            raise ValueError("unable to uniquely locate update_manifest.json")

        manifest_path = manifests[0]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload_root = manifest_path.parent
        expected_root = self.extract_root if manifest["package_layout"] == "flat" else self.extract_root / "AALC"
        if payload_root != expected_root:
            raise ValueError("package_layout does not match extracted payload root")
        return manifest, payload_root

    def load_managed_files(self, payload_root: Path, manifest: dict) -> list[str]:
        managed_files_path = payload_root / manifest["managed_files_manifest"]
        if not managed_files_path.is_file():
            raise ValueError("managed_files.txt is missing")
        actual_sha256 = hashlib.sha256(managed_files_path.read_bytes()).hexdigest()
        if actual_sha256 != manifest["managed_files_sha256"]:
            raise ValueError("managed_files.txt hash mismatch")
        managed_files = []
        for raw_line in managed_files_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            managed_files.append(validate_relative_manifest_path(line, manifest["protected_paths"]))
        return managed_files

    def load_installed_manifest(self) -> set[str] | None:
        installed_manifest_path = self.install_root / INSTALLED_MANIFEST_PATH
        if not installed_manifest_path.is_file():
            return None
        return {
            line.strip()
            for line in installed_manifest_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }

    def current_installed_version(self) -> str:
        version_path = self.install_root / "assets" / "config" / "version.txt"
        if not version_path.is_file():
            return ""
        return version_path.read_text(encoding="utf-8").strip()

    def copy_payload(self, payload_root: Path, managed_files: list[str], protected_paths: list[str]) -> None:
        for rel_path in managed_files:
            validated = validate_relative_manifest_path(rel_path, protected_paths)
            source_path = resolve_safe_child(payload_root, validated)
            target_path = resolve_safe_child(self.install_root, validated)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)

    def should_allow_cleanup(self, manifest: dict, installed_manifest: set[str] | None) -> tuple[bool, str]:
        current_version = self.current_installed_version()
        if installed_manifest is None:
            return False, "first migration without installed_manifest.txt"
        if not current_version:
            return False, "current version is missing"
        if version_at_most(current_version, LEGACY_DANGEROUS_VERSION):
            return False, "legacy dangerous updater source version"
        minimum = manifest["min_source_version_for_cleanup"]
        if not version_at_least(current_version, minimum):
            return False, f"current version {current_version} is below cleanup floor {minimum}"
        return True, ""

    def remove_retired_managed_files(
        self,
        installed_manifest: set[str],
        managed_files: set[str],
        protected_paths: list[str],
    ) -> None:
        for rel_path in sorted(installed_manifest - managed_files):
            if is_protected_path(rel_path, protected_paths):
                continue
            validated = validate_relative_manifest_path(rel_path, [])
            target_path = resolve_safe_child(self.install_root, validated)
            if target_path.exists():
                target_path.unlink()
                print(f"删除旧托管文件: {validated}")

    def write_installed_manifest(self, manifest: dict, managed_files: list[str]) -> None:
        installed_manifest_path = self.install_root / INSTALLED_MANIFEST_PATH
        installed_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        installed_manifest_path.write_text("\n".join(managed_files) + "\n", encoding="utf-8")

        meta_path = self.install_root / INSTALLED_MANIFEST_META_PATH
        meta_path.write_text(
            json.dumps(
                {
                    "format_version": manifest["format_version"],
                    "bootstrap_version": manifest["bootstrap_version"],
                    "installed_version": manifest["current_version"],
                    "managed_files_sha256": manifest["managed_files_sha256"],
                    "package_layout": manifest["package_layout"],
                },
                indent=2,
                ensure_ascii=True,
            ) + "\n",
            encoding="utf-8",
        )

    def apply_update_from_extracted_payload(self) -> None:
        manifest, payload_root = self.discover_payload_root()
        protected_paths = manifest.get("protected_paths", DEFAULT_PROTECTED_PATHS)
        managed_files = self.load_managed_files(payload_root, manifest)
        installed_manifest = self.load_installed_manifest()

        self.copy_payload(payload_root, managed_files, protected_paths)

        allow_cleanup, reason = self.should_allow_cleanup(manifest, installed_manifest)
        if allow_cleanup:
            self.remove_retired_managed_files(installed_manifest, set(managed_files), protected_paths)
        else:
            print(f"跳过清理: {reason}")

        self.write_installed_manifest(manifest, managed_files)
```

Then change `run()` to call `apply_update_from_extracted_payload()` instead of `cover_folder()`.

- [ ] **Step 5: Update `extract_file()` and `cleanup()` to use the new `Path` fields**

Apply these edits in `updater.py`:

```python
    def extract_file(self):
        print("开始解压...")
        while True:
            try:
                if self.exe_path.exists():
                    subprocess.run(
                        [
                            str(self.exe_path),
                            "x",
                            str(self.download_file_path),
                            f"-o{self.extract_root}",
                            "-aoa",
                        ],
                        check=True,
                    )
                else:
                    shutil.unpack_archive(str(self.download_file_path), str(self.extract_root))
                print("解压完成")
                return True
            except Exception:
                input("解压失败，按回车键重新解压. . .多次失败请手动下载更新")
                return False

    def cleanup(self):
        print("开始清理...")
        try:
            if self.download_file_path.exists():
                self.download_file_path.unlink()
            if self.extract_root.exists():
                shutil.rmtree(self.extract_root)
            print("清理完成")
        except Exception as e:
            print(f"清理失败: {e}")
```

- [ ] **Step 6: Run the updater-flow tests again**

Run: `uv run python -m unittest tests.test_update_protocol.TestUpdaterInstallFlow -v`

Expected: PASS for all 4 tests.

- [ ] **Step 7: Re-run the full protocol test file**

Run: `uv run python -m unittest tests.test_update_protocol -v`

Expected: PASS for every helper and updater-flow test.

- [ ] **Step 8: Run syntax verification**

Run: `uv run python -m py_compile updater.py`

Expected: command exits successfully with no output.

- [ ] **Step 9: Commit**

```bash
git add updater.py tests/test_update_protocol.py
git commit -m "fix: updater 按托管清单安全安装并清理旧托管文件"
```

---

### Task 5: Select Compatible Releases In The GUI Update Checker

**Files:**
- Modify: `module/update/check_update.py`
- Modify: `tests/test_update_protocol.py`

- [ ] **Step 1: Add failing selection tests for `UpdateThread` integration**

Append these tests to `tests/test_update_protocol.py`:

```python
from unittest.mock import patch

from module.update.check_update import UpdateThread


class TestUpdateThreadReleaseSelection(unittest.TestCase):
    def make_release(self, tag_name: str, archive_name: str, manifest_name: str):
        return {
            "tag_name": tag_name,
            "name": tag_name,
            "body": tag_name,
            "assets": [
                {"name": archive_name, "browser_download_url": f"https://example.test/{archive_name}"},
                {"name": manifest_name, "browser_download_url": f"https://example.test/{manifest_name}"},
            ],
        }

    @patch("module.update.check_update.read_bootstrap_version", return_value=1)
    def test_select_release_bundle_prefers_latest_compatible_release(self, _mock_bootstrap):
        thread = UpdateThread(timeout=5, flag=False)
        releases = [
            self.make_release("v1.5.0-canary.12", "AALC_12.7z", "manifest-12.json"),
            self.make_release("v1.5.0-canary.11", "AALC_11.7z", "manifest-11.json"),
        ]
        manifest_by_url = {
            "https://example.test/manifest-12.json": {"bootstrap_version": 1},
            "https://example.test/manifest-11.json": {"bootstrap_version": 1},
        }

        with patch.object(thread, "fetch_remote_manifest", side_effect=lambda url: manifest_by_url[url]):
            selected = thread.select_release_bundle(releases)

        self.assertEqual(selected["tag_name"], "v1.5.0-canary.12")

    @patch("module.update.check_update.read_bootstrap_version", return_value=1)
    def test_select_release_bundle_skips_incompatible_latest_release(self, _mock_bootstrap):
        thread = UpdateThread(timeout=5, flag=False)
        releases = [
            self.make_release("v1.5.0-canary.12", "AALC_12.7z", "manifest-12.json"),
            self.make_release("v1.5.0-canary.11", "AALC_11.7z", "manifest-11.json"),
        ]
        manifest_by_url = {
            "https://example.test/manifest-12.json": {"bootstrap_version": 2},
            "https://example.test/manifest-11.json": {"bootstrap_version": 1},
        }

        with patch.object(thread, "fetch_remote_manifest", side_effect=lambda url: manifest_by_url[url]):
            selected = thread.select_release_bundle(releases)

        self.assertEqual(selected["tag_name"], "v1.5.0-canary.11")
```

- [ ] **Step 2: Run the new `UpdateThread` tests and verify they fail**

Run: `uv run python -m unittest tests.test_update_protocol.TestUpdateThreadReleaseSelection -v`

Expected: FAIL because `UpdateThread` has no compatibility-aware `select_release_bundle()` behavior yet.

- [ ] **Step 3: Import the shared release-selection helpers**

Update the top of `module/update/check_update.py` to import the new shared protocol helpers:

```python
from module.update.update_protocol import (
    REMOTE_UPDATE_MANIFEST_ASSET,
    read_bootstrap_version,
    select_compatible_release,
)
```

- [ ] **Step 4: Replace the one-release shortcut with explicit candidate scanning**

Replace `get_download_url_from_assets()` and add sidecar-fetch helpers inside `class UpdateThread`:

```python
    def get_download_url_from_assets(self, assets):
        matches = [
            asset["browser_download_url"]
            for asset in assets
            if asset["name"].startswith("AALC_") and asset["name"].endswith(".7z")
        ]
        if len(matches) != 1:
            return None
        return matches[0]

    def get_remote_manifest_url_from_assets(self, assets):
        for asset in assets:
            if asset["name"] == REMOTE_UPDATE_MANIFEST_ASSET:
                return asset["browser_download_url"]
        return None

    def fetch_remote_manifest(self, manifest_url):
        proxies = _get_proxies()
        response = requests.get(manifest_url, timeout=10, headers=cfg.useragent, proxies=proxies)
        response.raise_for_status()
        return response.json()

    def select_release_bundle(self, releases):
        local_bootstrap_version = read_bootstrap_version(Path("."))
        bundles = []
        for release in releases:
            archive_url = self.get_download_url_from_assets(release["assets"])
            manifest_url = self.get_remote_manifest_url_from_assets(release["assets"])
            if not archive_url or not manifest_url:
                continue
            manifest = self.fetch_remote_manifest(manifest_url)
            bundles.append(
                {
                    "tag_name": release["tag_name"],
                    "name": release.get("name") or release["tag_name"],
                    "body": release.get("body", ""),
                    "archive_url": archive_url,
                    "manifest_url": manifest_url,
                    "manifest": manifest,
                }
            )

        selected = select_compatible_release(bundles, local_bootstrap_version)
        if selected is None:
            raise RuntimeError("未找到与当前更新引导器兼容的更新包")
        return selected
```

- [ ] **Step 5: Use the selected compatible release for update messaging and download caching**

Update both `check_update_info_github()` and `_get_assets_url_github()` to stop assuming `releases[0]` is always the right payload. The new logic should look like this:

```python
    def check_update_info_github(self):
        proxies = _get_proxies()
        response = requests.get(
            f"https://api.github.com/repos/{self.user}/{self.repo}/releases",
            timeout=10,
            headers=cfg.useragent,
            proxies=proxies,
        )
        response.raise_for_status()
        releases = response.json() if self._github_use_releases_list else [response.json()]
        selected = self.select_release_bundle(releases)
        self._cached_assets_url = selected["archive_url"]
        self._selected_release = selected
        return {
            "tag_name": selected["tag_name"],
            "name": selected["name"],
            "body": selected["body"],
        }

    def _get_assets_url_github(self):
        if getattr(self, "_cached_assets_url", None):
            return self._cached_assets_url
        self.check_update_info_github()
        return self._cached_assets_url
```

Then, when constructing dialog text, append this bridge hint if the selected release is not the newest release in the list:

```python
if getattr(self, "_selected_release", None) and self.new_version != releases[0]["tag_name"].lstrip("Vv"):
    self.content += f"\n\n当前引导器版本较旧，将先安装兼容桥接版本 {self.new_version}。"
```

Keep the existing Qt signal flow unchanged; only replace the release selection rules.

- [ ] **Step 6: Run the `UpdateThread` integration tests again**

Run: `uv run python -m unittest tests.test_update_protocol.TestUpdateThreadReleaseSelection -v`

Expected: PASS for both tests.

- [ ] **Step 7: Run syntax verification**

Run: `uv run python -m py_compile module/update/check_update.py`

Expected: command exits successfully with no output.

- [ ] **Step 8: Run the full protocol test file as a regression check**

Run: `uv run python -m unittest tests.test_update_protocol -v`

Expected: PASS for all existing tests; this step ensures the shared selection helpers still behave as expected after the GUI wiring.

- [ ] **Step 9: Manual release-selection spot check**

Run:

```bash
uv run python -c "from module.update.update_protocol import select_compatible_release; bundles=[{'tag_name':'v1.5.0-canary.12','manifest':{'bootstrap_version':2}},{'tag_name':'v1.5.0-canary.11','manifest':{'bootstrap_version':1}}]; print(select_compatible_release(bundles, 1)['tag_name'])"
```

Expected: prints `v1.5.0-canary.11`.

- [ ] **Step 10: Commit**

```bash
git add module/update/check_update.py
git commit -m "feat: 更新检查按引导器版本选择兼容发布"
```

---

### Task 6: Expand Manual Update Regression Harness And Run Full Verification

**Files:**
- Modify: `test_update_flow.py`

- [ ] **Step 1: Replace the one-off script with a parameterized harness**

Rewrite `test_update_flow.py` to take the archive path from arguments and verify the new protocol artifacts explicitly. The core structure should become:

```python
import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from updater import Updater


def verify_dir(label: str, path: Path) -> list[str]:
    report = [f"--- {label}: {path} ---"]
    for rel_path in [
        "AALC.exe",
        "_internal/python313.dll",
        "assets/config/version.txt",
        "assets/config/bootstrap_version.txt",
        "assets/config/installed_manifest.txt",
        "logs/debugLog.log",
    ]:
        target = path / rel_path
        report.append(f"  {'OK' if target.exists() else 'MISSING'}: {rel_path}")
    report.append(f"  legacy_only.dll exists: {(path / '_internal/legacy_only.dll').exists()}")
    return report


def main():
    parser = argparse.ArgumentParser(description="Local updater protocol smoke test")
    parser.add_argument("--archive", required=True, help="Path to the .7z archive to install")
    args = parser.parse_args()

    archive = Path(args.archive).resolve()
    root = Path(__file__).resolve().parent
    dist_aalc = root / "dist" / "AALC"
    if not dist_aalc.exists() or not archive.exists():
        raise SystemExit("Build the app and provide a valid archive first")

    workspace = Path(tempfile.mkdtemp(prefix="aalc_update_test_"))
    dest = workspace / "AALC"
    shutil.copytree(dist_aalc, dest)

    (dest / "logs").mkdir(exist_ok=True)
    (dest / "logs" / "debugLog.log").write_text("legacy log\n", encoding="utf-8")
    (dest / "_internal").mkdir(exist_ok=True)
    (dest / "_internal" / "legacy_only.dll").write_text("legacy dll\n", encoding="utf-8")
    (dest / "update_temp").mkdir(exist_ok=True)
    shutil.copy(archive, dest / "update_temp" / "AALC.7z")

    for line in verify_dir("更新前状态", dest):
        print(line)

    updater = Updater("AALC.7z", base_dir=dest)
    updater.extract_file()
    updater.apply_update_from_extracted_payload()

    for line in verify_dir("更新后状态", dest):
        print(line)

    shutil.rmtree(workspace)
    print(f"已清理测试目录: {workspace}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the automated unit tests first**

Run: `uv run python -m unittest tests.test_update_protocol -v`

Expected: PASS for the full protocol test file.

- [ ] **Step 3: Run the manual harness against the current protocol build**

Run: `uv run python .\test_update_flow.py --archive .\dist\AALC_1.5.0-canary.11.7z`

Expected: the final report shows `OK` for `AALC.exe`, `_internal/python313.dll`, `assets/config/bootstrap_version.txt`, and `assets/config/installed_manifest.txt`; `logs/debugLog.log` still exists; `_internal/legacy_only.dll` is gone only after a cleanup-eligible run.

- [ ] **Step 4: Run syntax verification across all touched runtime files**

Run: `uv run python -m py_compile module/update/update_protocol.py updater.py module/update/check_update.py scripts/build.py test_update_flow.py`

Expected: command exits successfully with no output.

- [ ] **Step 5: Commit**

```bash
git add test_update_flow.py
git commit -m "test: 补充更新协议本地回归脚本"
```

---

### Task 7: Final Verification Sweep

**Files:**
- Modify: none

- [ ] **Step 1: Run the full protocol unit suite**

Run: `uv run python -m unittest tests.test_update_protocol -v`

Expected: PASS.

- [ ] **Step 2: Rebuild one final flat package**

Run: `uv run python .\scripts\build.py --version 1.5.0-canary.11 --bootstrap-version 2`

Expected: PASS, with `dist\AALC.update_manifest.json` regenerated.

- [ ] **Step 3: Rebuild one bridge package**

Run: `uv run python .\scripts\build.py --version 1.5.0-canary.11 --bootstrap-version 2 --bridge-updater`

Expected: PASS, with a root-dir bridge archive regenerated.

- [ ] **Step 4: Re-run the manual harness**

Run: `uv run python .\test_update_flow.py --archive .\dist\AALC_1.5.0-canary.11.7z`

Expected: PASS, with protocol files present and no protected-path damage.

- [ ] **Step 5: Review git status before any publish step**

Run: `git status --short`

Expected: only the intended updater-protocol files appear as modified/new.
