import hashlib
import json
import shutil
import subprocess
import sys
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
    """应用程序更新器，负责检查、下载、解压和安装最新版本的应用程序。"""

    RETRY_LIMIT = 5

    def __init__(self, file_name=None, base_dir=None):
        self.process_names = ["AALC.exe"]

        self.file_name = file_name
        self.base_dir = Path(base_dir) if base_dir is not None else Path.cwd()
        self.temp_path = self.base_dir / "update_temp"
        self.temp_path.mkdir(parents=True, exist_ok=True)

        archive_stem = Path(file_name).stem if file_name else "payload"
        self.cover_folder_path = self.base_dir
        self.exe_path = self.base_dir / "assets" / "binary" / "7za.exe"
        self.delete_folder_path = self.base_dir / "assets" / "images"
        self.extract_folder_path = self.temp_path / archive_stem
        self.download_file_path = self.temp_path / file_name if file_name else self.temp_path / "payload.7z"
        self.changes_file_path = self.extract_folder_path / "changes.json"

    def extract_file(self):
        """解压下载的文件。"""
        print("开始解压...")
        for _ in range(self.RETRY_LIMIT):
            try:
                if self.exe_path.exists():
                    subprocess.run(
                        [
                            str(self.exe_path),
                            "x",
                            str(self.download_file_path),
                            f"-o{self.extract_folder_path}",
                            "-aoa",
                        ],
                        check=True,
                    )
                else:
                    shutil.unpack_archive(str(self.download_file_path), str(self.extract_folder_path))
                print("解压完成")
                return True
            except Exception:
                input("解压失败，按回车键重新解压. . .多次失败请手动下载更新")
        return False

    def discover_payload_root(self):
        payload_root = self.extract_folder_path
        aalc_dir = payload_root / "AALC"
        if aalc_dir.is_dir():
            return aalc_dir
        return payload_root

    def load_managed_files(self, payload_root, manifest):
        managed_manifest_name = manifest.get("managed_files_manifest", MANAGED_FILES_NAME)
        if not isinstance(managed_manifest_name, str) or not managed_manifest_name.strip():
            raise ValueError("missing managed files manifest path")

        managed_manifest_path = resolve_safe_child(payload_root, managed_manifest_name.replace("\\", "/"))
        managed_manifest_bytes = managed_manifest_path.read_bytes()
        normalized_manifest_bytes = managed_manifest_bytes.replace(b"\r\n", b"\n")
        expected_hash = manifest.get("managed_files_sha256")
        if not isinstance(expected_hash, str) or not expected_hash.strip():
            raise ValueError("missing managed files hash")
        actual_hash = hashlib.sha256(normalized_manifest_bytes).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError("managed files hash mismatch")

        protected_paths = manifest.get("protected_paths", DEFAULT_PROTECTED_PATHS)
        if not isinstance(protected_paths, list) or not all(isinstance(item, str) for item in protected_paths):
            raise ValueError("invalid protected paths")
        declared_protected_paths = {path.replace("\\", "/").strip("/").lower() for path in protected_paths if path.strip()}
        required_protected_paths = {
            path.replace("\\", "/").strip("/").lower() for path in DEFAULT_PROTECTED_PATHS if path.strip()
        }
        if not required_protected_paths.issubset(declared_protected_paths):
            raise ValueError("manifest weakens required protected paths")

        managed_files = []
        seen = set()
        for raw_line in managed_manifest_bytes.decode("utf-8").splitlines():
            rel_path = raw_line.strip()
            if not rel_path:
                continue
            normalized = validate_relative_manifest_path(rel_path, protected_paths)
            if normalized in seen:
                continue
            source_path = resolve_safe_child(payload_root, normalized)
            if not source_path.is_file():
                raise ValueError(f"payload file missing: {normalized}")
            managed_files.append(normalized)
            seen.add(normalized)
        return managed_files, protected_paths

    def validate_manifest_metadata(self, manifest, payload_root):
        try:
            bootstrap_version = int(manifest.get("bootstrap_version"))
        except (TypeError, ValueError):
            raise ValueError("invalid bootstrap version") from None
        if bootstrap_version < 1:
            raise ValueError("invalid bootstrap version")

        payload_bootstrap_version = read_bootstrap_version(payload_root)
        if payload_bootstrap_version != bootstrap_version:
            raise ValueError(
                f"bootstrap metadata mismatch: manifest={bootstrap_version}, payload={payload_bootstrap_version}"
            )
        return {
            "current_version": manifest.get("current_version", ""),
            "bootstrap_version": bootstrap_version,
        }

    def load_installed_manifest(self):
        manifest_path = resolve_safe_child(self.base_dir, INSTALLED_MANIFEST_PATH)
        if not manifest_path.exists():
            return None

        installed_files = set()
        for raw_line in manifest_path.read_text(encoding="utf-8").splitlines():
            rel_path = raw_line.strip()
            if not rel_path:
                continue
            installed_files.add(validate_relative_manifest_path(rel_path, []))
        return installed_files

    def current_installed_version(self):
        meta_path = resolve_safe_child(self.base_dir, INSTALLED_MANIFEST_META_PATH)
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                meta = None
            if isinstance(meta, dict):
                current_version = meta.get("current_version")
                if isinstance(current_version, str) and current_version.strip():
                    return current_version.strip()

        version_path = resolve_safe_child(self.base_dir, "assets/config/version.txt")
        if version_path.exists():
            version_text = version_path.read_text(encoding="utf-8").strip()
            if version_text:
                return version_text
        return None

    def copy_payload(self, payload_root, managed_files):
        print("开始覆盖安装...")
        last_error = None
        for _ in range(self.RETRY_LIMIT):
            try:
                for rel_path in managed_files:
                    source_path = resolve_safe_child(payload_root, rel_path)
                    target_path = resolve_safe_child(self.base_dir, rel_path)
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, target_path)
                print("覆盖安装完成")
                return
            except Exception as e:
                last_error = e
                print(f"覆盖安装失败: {e}")
                input("按回车键重试. . . \n Press any key to continue")
        raise last_error or OSError("payload copy failed")

    def should_allow_cleanup(self, installed_manifest, manifest):
        if not installed_manifest:
            return False

        current_version = self.current_installed_version()
        if not current_version:
            return False
        if version_at_most(current_version, LEGACY_DANGEROUS_VERSION):
            return False

        cleanup_mode = manifest.get("cleanup_mode")
        if cleanup_mode not in {"managed_only", "manifest"}:
            return False

        min_source_version = manifest.get("min_source_version_for_cleanup")
        if isinstance(min_source_version, str) and min_source_version.strip():
            return version_at_least(current_version, min_source_version)
        return True

    def remove_retired_managed_files(self, installed_manifest, managed_files, protected_paths):
        retired_files = sorted(installed_manifest - set(managed_files))
        for rel_path in retired_files:
            if is_protected_path(rel_path, protected_paths):
                print(f"跳过受保护的历史文件: {rel_path}")
                continue
            target_path = resolve_safe_child(self.base_dir, rel_path)
            if target_path.exists() and target_path.is_file():
                try:
                    target_path.unlink()
                    print(f"删除旧残留文件: {rel_path}")
                except OSError as e:
                    print(f"删除旧残留文件失败: {rel_path}: {e}")

    def write_installed_manifest(self, managed_files, manifest):
        manifest_path = resolve_safe_child(self.base_dir, INSTALLED_MANIFEST_PATH)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_body = "\n".join(sorted(managed_files))
        manifest_path.write_text(f"{manifest_body}\n" if manifest_body else "", encoding="utf-8")

        meta_path = resolve_safe_child(self.base_dir, INSTALLED_MANIFEST_META_PATH)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")

    def apply_update_from_extracted_payload(self):
        payload_root = self.discover_payload_root()
        manifest_path = resolve_safe_child(payload_root, UPDATE_MANIFEST_NAME)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("invalid update manifest")
        manifest_metadata = self.validate_manifest_metadata(manifest, payload_root)

        managed_files, protected_paths = self.load_managed_files(payload_root, manifest)
        installed_manifest = self.load_installed_manifest()

        if not self.changes_file_path.exists():
            try:
                if self.delete_folder_path.exists():
                    shutil.rmtree(self.delete_folder_path)
            except Exception as e:
                print(f"删除旧资源文件失败: {e}")

        self.copy_payload(payload_root, managed_files)
        if self.should_allow_cleanup(installed_manifest, manifest):
            self.remove_retired_managed_files(installed_manifest, managed_files, protected_paths)
            print("旧残留清理完成")
        else:
            print("跳过旧残留清理")
        self.write_installed_manifest(managed_files, manifest_metadata)

    def terminate_processes(self):
        """终止相关进程以准备更新。"""
        print("开始终止进程...")
        for proc in psutil.process_iter(attrs=["pid", "name"]):
            proc_name = proc.info.get("name") or ""
            if proc_name in self.process_names or any(name in proc_name for name in self.process_names):
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except psutil.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
                except psutil.AccessDenied:
                    print(f"无权限终止进程 PID: {proc.info['pid']}")
                except psutil.NoSuchProcess:
                    print(f"进程 PID: {proc.info['pid']} 已退出")
        print("终止进程完成")

    def cleanup(self):
        """清理下载和解压的临时文件。"""
        print("开始清理...")
        try:
            if self.download_file_path.exists():
                self.download_file_path.unlink()
            if self.extract_folder_path.exists():
                shutil.rmtree(self.extract_folder_path)
            if self.changes_file_path.exists():
                self.changes_file_path.unlink()
            print("清理完成")
        except Exception as e:
            print(f"清理失败: {e}")

    def run(self):
        """运行更新流程。"""
        if not self.extract_file():
            input("解压多次失败，按回车键退出更新程序")
            return
        self.terminate_processes()
        app_path = self.base_dir / "AALC.exe"
        try:
            self.apply_update_from_extracted_payload()
        except Exception as e:
            print(f"更新失败: {e}")
            self.cleanup()
            if app_path.exists():
                subprocess.Popen(str(app_path))
            input("更新失败，按回车键退出并重新打开软件")
            return

        self.cleanup()
        input("已完成更新，按回车键退出并打开软件\nThe update is complete, press enter to exit and open the software")
        if subprocess.call(f'cmd /c start "" "{app_path}"', shell=True):
            subprocess.Popen(str(app_path))


def check_temp_dir_and_run():
    """检查临时目录并运行更新程序。"""
    if not getattr(sys, "frozen", False):
        print("更新程序只支持打包成exe后运行")
        sys.exit(1)

    base_dir = Path.cwd()
    temp_path = base_dir / "update_temp"
    file_path = Path(sys.argv[0]).resolve()
    destination_path = temp_path / file_path.name

    if file_path != destination_path:
        temp_path.mkdir(parents=True, exist_ok=True)
        shutil.copy(file_path, destination_path)
        args = [str(destination_path)] + sys.argv[1:]
        subprocess.Popen(args, creationflags=subprocess.DETACHED_PROCESS)
        sys.exit(0)

    file_name = sys.argv[1] if len(sys.argv) == 2 else None

    updater = Updater(file_name, base_dir=base_dir)
    updater.run()


if __name__ == "__main__":
    check_temp_dir_and_run()
