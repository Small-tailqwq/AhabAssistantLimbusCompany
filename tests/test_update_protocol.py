import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from module.update.update_protocol import (
    INSTALLED_MANIFEST_META_PATH,
    INSTALLED_MANIFEST_PATH,
    DEFAULT_PROTECTED_PATHS,
    build_update_manifest,
    collect_managed_files,
    normalize_version_text,
    read_bootstrap_version,
    resolve_safe_child,
    select_compatible_release,
    validate_relative_manifest_path,
    version_at_least,
    version_at_most,
)
import updater as updater_module
from updater import Updater
from module.update.check_update import UpdateStatus, UpdateThread


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
            "C:evil.txt",
            "C:/evil.txt",
            r"C:\\evil.txt",
            "//server/share.txt",
            "config.yaml:evil",
            "logs/debug.log:stream",
            "assets/file.txt:$DATA",
            "assets/file.txt:",
        ]
        for value in bad_values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_relative_manifest_path(value, DEFAULT_PROTECTED_PATHS)

    def test_validate_relative_manifest_path_rejects_protected_targets(self):
        protected_values = [
            "logs/debugLog.log",
            "Logs/debugLog.log",
            "config.yaml",
            "CONFIG.YAML",
            "theme_pack_list.yaml",
            "Theme_Pack_List.yaml",
            "update_temp/AALC.7z",
            "Update_Temp/AALC.7z",
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

    def test_resolve_safe_child_rejects_escape_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                resolve_safe_child(root, "../escape.txt")


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

    def test_read_bootstrap_version_defaults_to_1_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(read_bootstrap_version(Path(tmp)), 1)

    def test_read_bootstrap_version_defaults_to_1_when_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_root = Path(tmp)
            (app_root / "assets" / "config").mkdir(parents=True)
            (app_root / "assets" / "config" / "bootstrap_version.txt").write_text("abc", encoding="utf-8")

            self.assertEqual(read_bootstrap_version(app_root), 1)

    def test_read_bootstrap_version_defaults_to_1_when_zero_or_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_root = Path(tmp)
            (app_root / "assets" / "config").mkdir(parents=True)
            version_file = app_root / "assets" / "config" / "bootstrap_version.txt"

            version_file.write_text("0", encoding="utf-8")
            self.assertEqual(read_bootstrap_version(app_root), 1)

            version_file.write_text("-2", encoding="utf-8")
            self.assertEqual(read_bootstrap_version(app_root), 1)

    def test_read_bootstrap_version_reads_valid_integer(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_root = Path(tmp)
            (app_root / "assets" / "config").mkdir(parents=True)
            (app_root / "assets" / "config" / "bootstrap_version.txt").write_text("2", encoding="utf-8")

            self.assertEqual(read_bootstrap_version(app_root), 2)


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

    def test_select_compatible_release_picks_newest_compatible_when_input_unsorted(self):
        bundles = [
            {
                "tag_name": "v1.5.0-canary.10",
                "archive_url": "https://example.test/10.7z",
                "manifest_url": "https://example.test/10.json",
                "manifest": {"bootstrap_version": 1},
            },
            {
                "tag_name": "v1.5.0-canary.8",
                "archive_url": "https://example.test/8.7z",
                "manifest_url": "https://example.test/8.json",
                "manifest": {"bootstrap_version": 1},
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

    def test_select_compatible_release_skips_invalid_tag_names(self):
        bundles = [
            {
                "tag_name": "latest",
                "archive_url": "https://example.test/latest.7z",
                "manifest_url": "https://example.test/latest.json",
                "manifest": {"bootstrap_version": 1},
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

    def test_select_compatible_release_requires_explicit_bootstrap_version(self):
        bundles = [
            {
                "tag_name": "v1.5.0-canary.12",
                "archive_url": "https://example.test/12.7z",
                "manifest_url": "https://example.test/12.json",
                "manifest": {},
            }
        ]

        self.assertIsNone(select_compatible_release(bundles, local_bootstrap_version=99))


class TestUpdateThreadReleaseSelection(unittest.TestCase):
    def _mock_json_response(self, payload):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        return response

    def _build_release(self, tag_name: str, bootstrap_version: int) -> dict:
        return {
            "tag_name": tag_name,
            "body": f"notes for {tag_name}",
            "assets": [
                {
                    "name": f"AALC_{tag_name}.7z",
                    "browser_download_url": f"https://example.test/{tag_name}/AALC_{tag_name}.7z",
                },
                {
                    "name": "AALC.update_manifest.json",
                    "browser_download_url": f"https://example.test/{tag_name}/AALC.update_manifest.json",
                },
            ],
            "manifest": {"bootstrap_version": bootstrap_version},
        }

    def test_check_update_info_github_prefers_latest_compatible_release(self):
        releases = [
            self._build_release("v1.5.0-canary.12", 1),
            self._build_release("v1.5.0-canary.11", 1),
        ]

        thread = UpdateThread(timeout=5, flag=False)
        thread._canary = True

        with mock.patch("module.update.check_update.read_bootstrap_version", return_value=1), mock.patch.object(
            thread,
            "_fetch_release_candidates_github",
            return_value=releases,
        ), mock.patch.object(thread, "fetch_remote_manifest", side_effect=lambda release: release["manifest"]):
            data = thread.check_update_info_github()

        self.assertEqual(data["tag_name"], "v1.5.0-canary.12")
        self.assertEqual(thread.get_assets_url(), "https://example.test/v1.5.0-canary.12/AALC_v1.5.0-canary.12.7z")

    def test_check_update_info_github_skips_incompatible_latest_release(self):
        releases = [
            self._build_release("v1.5.0-canary.12", 2),
            self._build_release("v1.5.0-canary.11", 1),
        ]

        thread = UpdateThread(timeout=5, flag=False)
        thread._canary = True

        with mock.patch("module.update.check_update.read_bootstrap_version", return_value=1), mock.patch.object(
            thread,
            "_fetch_release_candidates_github",
            return_value=releases,
        ), mock.patch.object(thread, "fetch_remote_manifest", side_effect=lambda release: release["manifest"]):
            data = thread.check_update_info_github()

        self.assertEqual(data["tag_name"], "v1.5.0-canary.11")
        self.assertEqual(thread.get_assets_url(), "https://example.test/v1.5.0-canary.11/AALC_v1.5.0-canary.11.7z")

    def test_check_update_info_github_skips_latest_release_when_manifest_lacks_bootstrap_version(self):
        releases = [
            self._build_release("v1.5.0-canary.12", 1),
            self._build_release("v1.5.0-canary.11", 1),
        ]
        releases[0]["manifest"] = {}

        thread = UpdateThread(timeout=5, flag=False)
        thread._canary = True

        with mock.patch("module.update.check_update.read_bootstrap_version", return_value=1), mock.patch.object(
            thread,
            "_fetch_release_candidates_github",
            return_value=releases,
        ), mock.patch.object(thread, "fetch_remote_manifest", side_effect=lambda release: release["manifest"]):
            data = thread.check_update_info_github()

        self.assertEqual(data["tag_name"], "v1.5.0-canary.11")
        self.assertEqual(thread.get_assets_url(), "https://example.test/v1.5.0-canary.11/AALC_v1.5.0-canary.11.7z")

    def test_check_update_info_github_skips_latest_release_when_manifest_fetch_fails(self):
        releases = [
            self._build_release("v1.5.0-canary.12", 1),
            self._build_release("v1.5.0-canary.11", 1),
        ]

        thread = UpdateThread(timeout=5, flag=False)
        thread._canary = True

        def side_effect(release):
            if release["tag_name"] == "v1.5.0-canary.12":
                raise ValueError("bad manifest payload")
            return release["manifest"]

        with mock.patch("module.update.check_update.read_bootstrap_version", return_value=1), mock.patch.object(
            thread,
            "_fetch_release_candidates_github",
            return_value=releases,
        ), mock.patch.object(thread, "fetch_remote_manifest", side_effect=side_effect):
            data = thread.check_update_info_github()

        self.assertEqual(data["tag_name"], "v1.5.0-canary.11")
        self.assertEqual(thread.get_assets_url(), "https://example.test/v1.5.0-canary.11/AALC_v1.5.0-canary.11.7z")

    def test_check_update_info_github_raises_when_no_compatible_release_exists(self):
        releases = [
            self._build_release("v1.5.0-canary.12", 3),
            self._build_release("v1.5.0-canary.11", 2),
        ]

        thread = UpdateThread(timeout=5, flag=False)
        thread._canary = True

        with mock.patch("module.update.check_update.read_bootstrap_version", return_value=1), mock.patch.object(
            thread,
            "_fetch_release_candidates_github",
            return_value=releases,
        ), mock.patch.object(thread, "fetch_remote_manifest", side_effect=lambda release: release["manifest"]):
            with self.assertRaises(RuntimeError):
                thread.check_update_info_github()

    def test_run_appends_bridge_hint_for_older_compatible_release(self):
        releases = [
            self._build_release("v1.5.0-canary.12", 2),
            self._build_release("v1.5.0-canary.11", 1),
        ]

        thread = UpdateThread(timeout=5, flag=False)
        thread._canary = True

        with mock.patch("module.update.check_update.read_bootstrap_version", return_value=1), mock.patch.object(
            thread,
            "_fetch_release_candidates_github",
            return_value=releases,
        ), mock.patch.object(
            thread,
            "fetch_remote_manifest",
            side_effect=lambda release: release["manifest"],
        ), mock.patch.object(
            thread,
            "tr",
            side_effect=lambda text, *args, **kwargs: text,
        ), mock.patch.object(
            thread,
            "remove_images_from_markdown",
            side_effect=lambda content: content,
        ), mock.patch(
            "module.update.check_update.cfg.version",
            "1.5.0-canary.10",
        ):
            thread.run()

        self.assertEqual(thread.new_version, "v1.5.0-canary.11")
        self.assertIn("当前引导器版本较旧，将先安装兼容桥接版本 v1.5.0-canary.11。", thread.content)

    def test_run_does_not_append_bridge_hint_when_latest_release_is_skipped_for_invalid_tag(self):
        releases = [
            self._build_release("latest", 1),
            self._build_release("v1.5.0-canary.11", 1),
        ]

        thread = UpdateThread(timeout=5, flag=False)
        thread._canary = True

        with mock.patch("module.update.check_update.read_bootstrap_version", return_value=1), mock.patch.object(
            thread,
            "_fetch_release_candidates_github",
            return_value=releases,
        ), mock.patch.object(
            thread,
            "fetch_remote_manifest",
            side_effect=lambda release: release["manifest"],
        ), mock.patch.object(
            thread,
            "tr",
            side_effect=lambda text, *args, **kwargs: text,
        ), mock.patch.object(
            thread,
            "remove_images_from_markdown",
            side_effect=lambda content: content,
        ), mock.patch(
            "module.update.check_update.cfg.version",
            "1.5.0-canary.10",
        ):
            thread.run()

        self.assertEqual(thread.new_version, "v1.5.0-canary.11")
        self.assertNotIn("当前引导器版本较旧，将先安装兼容桥接版本", thread.content)

    def test_run_appends_bridge_hint_when_first_release_is_invalid_but_newest_valid_release_needs_bridge(self):
        releases = [
            self._build_release("v1.5.0-canary.13", 1),
            self._build_release("v1.5.0-canary.12", 2),
            self._build_release("v1.5.0-canary.11", 1),
        ]
        releases[0]["assets"] = []

        thread = UpdateThread(timeout=5, flag=False)
        thread._canary = True

        with mock.patch("module.update.check_update.read_bootstrap_version", return_value=1), mock.patch.object(
            thread,
            "_fetch_release_candidates_github",
            return_value=releases,
        ), mock.patch.object(
            thread,
            "fetch_remote_manifest",
            side_effect=lambda release: release["manifest"],
        ), mock.patch.object(
            thread,
            "tr",
            side_effect=lambda text, *args, **kwargs: text,
        ), mock.patch.object(
            thread,
            "remove_images_from_markdown",
            side_effect=lambda content: content,
        ), mock.patch(
            "module.update.check_update.cfg.version",
            "1.5.0-canary.10",
        ):
            thread.run()

        self.assertEqual(thread.new_version, "v1.5.0-canary.11")
        self.assertIn("当前引导器版本较旧，将先安装兼容桥接版本 v1.5.0-canary.11。", thread.content)

    def test_run_reports_failure_when_no_compatible_release_exists(self):
        thread = UpdateThread(timeout=5, flag=False)
        statuses = []

        thread.updateSignal.connect(statuses.append)

        with mock.patch.object(
            thread,
            "check_update_info_github",
            side_effect=RuntimeError("未找到与当前更新引导器兼容的更新包"),
        ), mock.patch(
            "module.update.check_update.requests.get",
        ) as mock_get:
            thread.run()

        self.assertEqual(statuses, [UpdateStatus.FAILURE])
        mock_get.assert_not_called()

    def test_run_reports_failure_when_manifest_fetch_fails(self):
        releases = [
            self._build_release("v1.5.0-canary.12", 1),
        ]
        thread = UpdateThread(timeout=5, flag=False)
        statuses = []

        thread.updateSignal.connect(statuses.append)

        with mock.patch("module.update.check_update.read_bootstrap_version", return_value=1), mock.patch.object(
            thread,
            "_fetch_release_candidates_github",
            return_value=releases,
        ), mock.patch.object(
            thread,
            "fetch_remote_manifest",
            side_effect=ValueError("bad manifest payload"),
        ), mock.patch(
            "module.update.check_update.requests.get",
        ) as mock_get:
            thread.run()

        self.assertEqual(statuses, [UpdateStatus.FAILURE])
        mock_get.assert_not_called()

    def test_check_update_info_github_scans_older_stable_releases_for_compatibility(self):
        releases = [
            self._build_release("v1.5.0", 2),
            self._build_release("v1.4.9", 1),
        ]
        manifest_by_url = {
            "https://example.test/v1.5.0/AALC.update_manifest.json": {"bootstrap_version": 2},
            "https://example.test/v1.4.9/AALC.update_manifest.json": {"bootstrap_version": 1},
        }

        thread = UpdateThread(timeout=5, flag=False)
        thread._canary = False
        thread.user = "KIYI671"

        def fake_get(url, *args, **kwargs):
            if url.endswith("/releases/latest"):
                return self._mock_json_response(releases[0])
            if url.endswith("/releases"):
                return self._mock_json_response(releases)
            if url in manifest_by_url:
                return self._mock_json_response(manifest_by_url[url])
            raise AssertionError(f"unexpected url: {url}")

        with mock.patch("module.update.check_update.read_bootstrap_version", return_value=1), mock.patch(
            "module.update.check_update.requests.get",
            side_effect=fake_get,
        ):
            data = thread.check_update_info_github()

        self.assertEqual(data["tag_name"], "v1.4.9")
        self.assertEqual(thread.get_assets_url(), "https://example.test/v1.4.9/AALC_v1.4.9.7z")

    def test_check_update_info_github_ignores_prerelease_for_stable_channel(self):
        prerelease = self._build_release("v1.5.0-canary.12", 1)
        prerelease["prerelease"] = True
        stable_release = self._build_release("v1.4.9", 1)
        stable_release["prerelease"] = False
        releases = [prerelease, stable_release]
        manifest_by_url = {
            "https://example.test/v1.5.0-canary.12/AALC.update_manifest.json": {"bootstrap_version": 1},
            "https://example.test/v1.4.9/AALC.update_manifest.json": {"bootstrap_version": 1},
        }

        thread = UpdateThread(timeout=5, flag=False)
        thread._canary = False
        thread.user = "KIYI671"

        def fake_get(url, *args, **kwargs):
            if url.endswith("/releases"):
                return self._mock_json_response(releases)
            if url in manifest_by_url:
                return self._mock_json_response(manifest_by_url[url])
            raise AssertionError(f"unexpected url: {url}")

        with mock.patch("module.update.check_update.read_bootstrap_version", return_value=1), mock.patch(
            "module.update.check_update.requests.get",
            side_effect=fake_get,
        ):
            data = thread.check_update_info_github()

        self.assertEqual(data["tag_name"], "v1.4.9")
        self.assertEqual(thread.get_assets_url(), "https://example.test/v1.4.9/AALC_v1.4.9.7z")


class TestUpdaterInstallFlow(unittest.TestCase):
    def _write_payload(self, payload_root: Path, version: str, managed_files: dict[str, str], *, extra_manifest=None):
        for rel_path, content in managed_files.items():
            target = payload_root / Path(*rel_path.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        managed_list = sorted(managed_files)
        managed_manifest = "\n".join(managed_list) + "\n"
        (payload_root / "managed_files.txt").write_text(managed_manifest, encoding="utf-8")
        manifest = build_update_manifest(
            version=version,
            bootstrap_version=2,
            package_layout="root_dir",
            cleanup_mode="managed_only",
            min_source_version_for_cleanup="1.5.0-canary.11",
            managed_files_sha256=hashlib.sha256(managed_manifest.encode("utf-8")).hexdigest(),
            protected_paths=DEFAULT_PROTECTED_PATHS,
        )
        if extra_manifest:
            manifest.update(extra_manifest)
        (payload_root / "update_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_first_migration_preserves_logs_and_writes_installed_manifest_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            (base_dir / "logs").mkdir()
            (base_dir / "logs" / "debugLog.log").write_text("keep me", encoding="utf-8")

            payload_root = base_dir / "update_temp" / "pkg"
            self._write_payload(
                payload_root,
                "1.5.0-canary.11",
                {
                    "AALC.exe": "new exe",
                    "assets/config/version.txt": "1.5.0-canary.11",
                    "assets/config/bootstrap_version.txt": "2",
                },
            )

            updater = Updater(file_name="pkg.7z", base_dir=base_dir)
            updater.extract_folder_path = payload_root

            updater.apply_update_from_extracted_payload()

            self.assertEqual((base_dir / "logs" / "debugLog.log").read_text(encoding="utf-8"), "keep me")
            installed_manifest = (base_dir / INSTALLED_MANIFEST_PATH).read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                installed_manifest,
                [
                    "AALC.exe",
                    "assets/config/bootstrap_version.txt",
                    "assets/config/version.txt",
                ],
            )
            meta = json.loads((base_dir / INSTALLED_MANIFEST_META_PATH).read_text(encoding="utf-8"))
            self.assertEqual(meta["current_version"], "1.5.0-canary.11")
            self.assertEqual(meta["bootstrap_version"], 2)

    def test_cleanup_deletes_only_retired_managed_files_while_preserving_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            (base_dir / "logs").mkdir()
            (base_dir / "logs" / "debugLog.log").write_text("keep me", encoding="utf-8")
            (base_dir / "AALC.exe").write_text("old exe", encoding="utf-8")
            (base_dir / "obsolete.txt").write_text("remove me", encoding="utf-8")
            (base_dir / "user_note.txt").write_text("keep me", encoding="utf-8")
            installed_manifest_path = base_dir / INSTALLED_MANIFEST_PATH
            installed_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            installed_manifest_path.write_text("AALC.exe\nobsolete.txt\n", encoding="utf-8")
            (base_dir / INSTALLED_MANIFEST_META_PATH).write_text(
                json.dumps({"current_version": "1.5.0-canary.11", "bootstrap_version": 2}),
                encoding="utf-8",
            )

            payload_root = base_dir / "update_temp" / "pkg"
            self._write_payload(
                payload_root,
                "1.5.0-canary.12",
                {
                    "AALC.exe": "new exe",
                    "assets/config/version.txt": "1.5.0-canary.12",
                    "assets/config/bootstrap_version.txt": "2",
                },
                extra_manifest={"cleanup_mode": "manifest"},
            )

            updater = Updater(file_name="pkg.7z", base_dir=base_dir)
            updater.extract_folder_path = payload_root

            updater.apply_update_from_extracted_payload()

            self.assertFalse((base_dir / "obsolete.txt").exists())
            self.assertTrue((base_dir / "user_note.txt").exists())
            self.assertEqual((base_dir / "logs" / "debugLog.log").read_text(encoding="utf-8"), "keep me")

    def test_cleanup_skips_retired_historical_file_that_is_now_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            (base_dir / "AALC.exe").write_text("old exe", encoding="utf-8")
            legacy_dir = base_dir / "legacy"
            legacy_dir.mkdir()
            (legacy_dir / "old.txt").write_text("keep historical file", encoding="utf-8")

            installed_manifest_path = base_dir / INSTALLED_MANIFEST_PATH
            installed_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            installed_manifest_path.write_text("AALC.exe\nlegacy/old.txt\n", encoding="utf-8")
            (base_dir / INSTALLED_MANIFEST_META_PATH).write_text(
                json.dumps({"current_version": "1.5.0-canary.11", "bootstrap_version": 2}),
                encoding="utf-8",
            )

            payload_root = base_dir / "update_temp" / "pkg"
            self._write_payload(
                payload_root,
                "1.5.0-canary.12",
                {
                    "AALC.exe": "new exe",
                    "assets/config/version.txt": "1.5.0-canary.12",
                    "assets/config/bootstrap_version.txt": "2",
                },
                extra_manifest={"cleanup_mode": "manifest", "protected_paths": [*DEFAULT_PROTECTED_PATHS, "legacy/"]},
            )

            updater = Updater(file_name="pkg.7z", base_dir=base_dir)
            updater.extract_folder_path = payload_root

            updater.apply_update_from_extracted_payload()

            self.assertEqual((base_dir / "AALC.exe").read_text(encoding="utf-8"), "new exe")
            self.assertTrue((base_dir / "legacy" / "old.txt").exists())
            installed_manifest = (base_dir / INSTALLED_MANIFEST_PATH).read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                installed_manifest,
                [
                    "AALC.exe",
                    "assets/config/bootstrap_version.txt",
                    "assets/config/version.txt",
                ],
            )

    def test_legacy_dangerous_source_version_skips_cleanup_even_with_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            (base_dir / "AALC.exe").write_text("old exe", encoding="utf-8")
            (base_dir / "obsolete.txt").write_text("remove me", encoding="utf-8")
            installed_manifest_path = base_dir / INSTALLED_MANIFEST_PATH
            installed_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            installed_manifest_path.write_text("AALC.exe\nobsolete.txt\n", encoding="utf-8")
            (base_dir / INSTALLED_MANIFEST_META_PATH).write_text(
                json.dumps({"current_version": "1.5.0-canary.9", "bootstrap_version": 2}),
                encoding="utf-8",
            )

            payload_root = base_dir / "update_temp" / "pkg"
            self._write_payload(
                payload_root,
                "1.5.0-canary.12",
                {
                    "AALC.exe": "new exe",
                    "assets/config/version.txt": "1.5.0-canary.12",
                    "assets/config/bootstrap_version.txt": "2",
                },
                extra_manifest={"cleanup_mode": "manifest"},
            )

            updater = Updater(file_name="pkg.7z", base_dir=base_dir)
            updater.extract_folder_path = payload_root

            updater.apply_update_from_extracted_payload()

            self.assertEqual((base_dir / "AALC.exe").read_text(encoding="utf-8"), "new exe")
            self.assertTrue((base_dir / "obsolete.txt").exists())

    def test_load_installed_manifest_allows_historical_entry_that_matches_default_protected_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            installed_manifest_path = base_dir / INSTALLED_MANIFEST_PATH
            installed_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            installed_manifest_path.write_text("AALC.exe\nlogs/debugLog.log\n", encoding="utf-8")

            updater = Updater(file_name="pkg.7z", base_dir=base_dir)

            self.assertEqual(updater.load_installed_manifest(), {"AALC.exe", "logs/debugLog.log"})

    def test_payload_declaring_protected_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            payload_root = base_dir / "update_temp" / "pkg"
            self._write_payload(
                payload_root,
                "1.5.0-canary.11",
                {
                    "AALC.exe": "new exe",
                    "config.yaml": "forbidden",
                },
            )

            updater = Updater(file_name="pkg.7z", base_dir=base_dir)
            updater.extract_folder_path = payload_root

            with self.assertRaises(ValueError):
                updater.apply_update_from_extracted_payload()

    def test_payload_with_bad_managed_files_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            payload_root = base_dir / "update_temp" / "pkg"
            self._write_payload(
                payload_root,
                "1.5.0-canary.11",
                {
                    "AALC.exe": "new exe",
                    "assets/config/version.txt": "1.5.0-canary.11",
                },
                extra_manifest={"managed_files_sha256": "deadbeef"},
            )

            updater = Updater(file_name="pkg.7z", base_dir=base_dir)
            updater.extract_folder_path = payload_root

            with self.assertRaises(ValueError):
                updater.apply_update_from_extracted_payload()

    def test_manifest_cannot_relax_default_protected_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            (base_dir / "config.yaml").write_text("keep local config", encoding="utf-8")

            payload_root = base_dir / "update_temp" / "pkg"
            self._write_payload(
                payload_root,
                "1.5.0-canary.11",
                {
                    "AALC.exe": "new exe",
                    "config.yaml": "forbidden",
                },
                extra_manifest={"protected_paths": []},
            )

            updater = Updater(file_name="pkg.7z", base_dir=base_dir)
            updater.extract_folder_path = payload_root

            with self.assertRaises(ValueError):
                updater.apply_update_from_extracted_payload()

            self.assertEqual((base_dir / "config.yaml").read_text(encoding="utf-8"), "keep local config")
            self.assertFalse((base_dir / "AALC.exe").exists())

    def test_invalid_bootstrap_version_is_rejected_before_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            (base_dir / "AALC.exe").write_text("old exe", encoding="utf-8")

            payload_root = base_dir / "update_temp" / "pkg"
            self._write_payload(
                payload_root,
                "1.5.0-canary.11",
                {
                    "AALC.exe": "new exe",
                    "assets/config/version.txt": "1.5.0-canary.11",
                    "assets/config/bootstrap_version.txt": "2",
                },
                extra_manifest={"bootstrap_version": "bad"},
            )

            updater = Updater(file_name="pkg.7z", base_dir=base_dir)
            updater.extract_folder_path = payload_root

            with self.assertRaises(ValueError):
                updater.apply_update_from_extracted_payload()

            self.assertEqual((base_dir / "AALC.exe").read_text(encoding="utf-8"), "old exe")
            self.assertFalse((base_dir / INSTALLED_MANIFEST_PATH).exists())
            self.assertFalse((base_dir / INSTALLED_MANIFEST_META_PATH).exists())

    def test_payload_bootstrap_file_must_match_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            (base_dir / "AALC.exe").write_text("old exe", encoding="utf-8")

            payload_root = base_dir / "update_temp" / "pkg"
            self._write_payload(
                payload_root,
                "1.5.0-canary.11",
                {
                    "AALC.exe": "new exe",
                    "assets/config/version.txt": "1.5.0-canary.11",
                    "assets/config/bootstrap_version.txt": "3",
                },
                extra_manifest={"bootstrap_version": 2},
            )

            updater = Updater(file_name="pkg.7z", base_dir=base_dir)
            updater.extract_folder_path = payload_root

            with self.assertRaises(ValueError):
                updater.apply_update_from_extracted_payload()

            self.assertEqual((base_dir / "AALC.exe").read_text(encoding="utf-8"), "old exe")

    def test_cleanup_continues_when_one_retired_file_cannot_be_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            (base_dir / "AALC.exe").write_text("old exe", encoding="utf-8")
            (base_dir / "obsolete_a.txt").write_text("remove a", encoding="utf-8")
            (base_dir / "obsolete_b.txt").write_text("remove b", encoding="utf-8")
            installed_manifest_path = base_dir / INSTALLED_MANIFEST_PATH
            installed_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            installed_manifest_path.write_text("AALC.exe\nobsolete_a.txt\nobsolete_b.txt\n", encoding="utf-8")
            (base_dir / INSTALLED_MANIFEST_META_PATH).write_text(
                json.dumps({"current_version": "1.5.0-canary.11", "bootstrap_version": 2}),
                encoding="utf-8",
            )

            payload_root = base_dir / "update_temp" / "pkg"
            self._write_payload(
                payload_root,
                "1.5.0-canary.12",
                {
                    "AALC.exe": "new exe",
                    "assets/config/version.txt": "1.5.0-canary.12",
                    "assets/config/bootstrap_version.txt": "2",
                },
                extra_manifest={"cleanup_mode": "manifest"},
            )

            updater = Updater(file_name="pkg.7z", base_dir=base_dir)
            updater.extract_folder_path = payload_root

            original_unlink = Path.unlink

            def flaky_unlink(path_obj, *args, **kwargs):
                if path_obj == base_dir / "obsolete_a.txt":
                    raise OSError("locked")
                return original_unlink(path_obj, *args, **kwargs)

            with mock.patch.object(Path, "unlink", autospec=True, side_effect=flaky_unlink):
                updater.apply_update_from_extracted_payload()

            self.assertTrue((base_dir / "obsolete_a.txt").exists())
            self.assertFalse((base_dir / "obsolete_b.txt").exists())
            meta = json.loads((base_dir / INSTALLED_MANIFEST_META_PATH).read_text(encoding="utf-8"))
            self.assertEqual(meta["current_version"], "1.5.0-canary.12")

    def test_extract_file_stops_after_retry_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            exe_dir = base_dir / "assets" / "binary"
            exe_dir.mkdir(parents=True, exist_ok=True)
            (exe_dir / "7za.exe").write_text("stub", encoding="utf-8")
            updater = Updater(file_name="pkg.7z", base_dir=base_dir)

            with mock.patch.object(updater_module.subprocess, "run", side_effect=OSError("boom")) as run_mock, mock.patch.object(
                updater_module, "input", return_value=""
            ) as input_mock:
                self.assertFalse(updater.extract_file())

            self.assertEqual(run_mock.call_count, 5)
            self.assertEqual(input_mock.call_count, 5)

    def test_copy_payload_stops_after_retry_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            payload_root = base_dir / "update_temp" / "pkg"
            payload_root.mkdir(parents=True, exist_ok=True)
            (payload_root / "AALC.exe").write_text("new exe", encoding="utf-8")
            updater = Updater(file_name="pkg.7z", base_dir=base_dir)

            with mock.patch.object(updater_module.shutil, "copy2", side_effect=OSError("boom")) as copy_mock, mock.patch.object(
                updater_module, "input", return_value=""
            ) as input_mock:
                with self.assertRaises(OSError):
                    updater.copy_payload(payload_root, ["AALC.exe"])

            self.assertEqual(copy_mock.call_count, 5)
            self.assertEqual(input_mock.call_count, 5)


class TestUpdaterBootstrapFlow(unittest.TestCase):
    def test_run_relaunches_existing_app_when_payload_validation_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            (base_dir / "AALC.exe").write_text("old exe", encoding="utf-8")

            updater = Updater(file_name="pkg.7z", base_dir=base_dir)

            with mock.patch.object(updater, "extract_file", return_value=True), mock.patch.object(
                updater, "terminate_processes"
            ) as terminate_mock, mock.patch.object(
                updater, "apply_update_from_extracted_payload", side_effect=ValueError("invalid update manifest")
            ), mock.patch.object(
                updater, "cleanup"
            ) as cleanup_mock, mock.patch.object(
                updater_module.subprocess, "call", return_value=0
            ) as call_mock, mock.patch.object(
                updater_module.subprocess, "Popen"
            ) as popen_mock, mock.patch.object(
                updater_module, "input", return_value=""
            ) as input_mock:
                updater.run()

            terminate_mock.assert_called_once()
            cleanup_mock.assert_called_once()
            call_mock.assert_not_called()
            popen_mock.assert_called_once_with(str(base_dir / "AALC.exe"))
            input_mock.assert_called_once_with("更新失败，按回车键退出并重新打开软件")

    def test_check_temp_dir_and_run_keeps_update_exe_before_temp_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            source_dir = base_dir / "staging"
            source_dir.mkdir()
            source_path = source_dir / "Update.exe"
            source_path.write_text("source", encoding="utf-8")
            resident_update = base_dir / "Update.exe"
            resident_update.write_text("resident", encoding="utf-8")

            with mock.patch.object(updater_module.Path, "cwd", return_value=base_dir), mock.patch.object(
                updater_module.sys, "argv", [str(source_path), "pkg.7z"]
            ), mock.patch.object(updater_module.sys, "frozen", True, create=True), mock.patch.object(
                updater_module.shutil, "copy"
            ) as copy_mock, mock.patch.object(updater_module.subprocess, "Popen") as popen_mock, mock.patch.object(
                updater_module.sys, "exit", side_effect=SystemExit
            ):
                with self.assertRaises(SystemExit):
                    updater_module.check_temp_dir_and_run()

            self.assertTrue(resident_update.exists())
            copy_mock.assert_called_once_with(source_path, base_dir / "update_temp" / "Update.exe")
            popen_mock.assert_called_once()
