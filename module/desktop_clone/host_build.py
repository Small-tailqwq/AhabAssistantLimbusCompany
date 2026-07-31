"""Build and locate the small .NET Framework RDP ActiveX host."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HOST_EXE_NAME = "AALC.DesktopCloneHost.exe"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
HOST_SOURCE_DIR = PROJECT_ROOT / "native" / "desktop_clone_host"
HOST_SOURCES = (
    HOST_SOURCE_DIR / "Program.cs",
    HOST_SOURCE_DIR / "AudioSessionController.cs",
)
HOST_ICON = PROJECT_ROOT / "assets" / "logo" / "canary.ico"
HOST_MANIFEST = HOST_SOURCE_DIR / "app.manifest"
DEVELOPMENT_OUTPUT = PROJECT_ROOT / "build" / "desktop_clone" / HOST_EXE_NAME


def _find_csharp_compiler() -> Path:
    candidates = [
        shutil.which("csc"),
        Path(os.environ.get("WINDIR", r"C:\Windows"))
        / "Microsoft.NET"
        / "Framework64"
        / "v4.0.30319"
        / "csc.exe",
        Path(os.environ.get("WINDIR", r"C:\Windows"))
        / "Microsoft.NET"
        / "Framework"
        / "v4.0.30319"
        / "csc.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise FileNotFoundError("未找到 .NET Framework C# 编译器 csc.exe")


def compile_desktop_clone_host(output: Path | None = None, *, force: bool = False) -> Path:
    if os.name != "nt":
        raise RuntimeError("桌面分身宿主仅支持 Windows 构建")

    destination = DEVELOPMENT_OUTPUT if output is None else Path(output)
    build_inputs = (*HOST_SOURCES, HOST_ICON, HOST_MANIFEST)
    if (
        not force
        and destination.is_file()
        and all(
            destination.stat().st_mtime >= source.stat().st_mtime
            for source in build_inputs
        )
    ):
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    compiler = _find_csharp_compiler()
    command = [
        str(compiler),
        "/nologo",
        "/target:winexe",
        "/optimize+",
        "/platform:anycpu",
        f"/out:{destination}",
        "/reference:System.dll",
        "/reference:System.Core.dll",
        "/reference:System.Drawing.dll",
        "/reference:System.Windows.Forms.dll",
        "/reference:Microsoft.CSharp.dll",
        f"/win32icon:{HOST_ICON}",
        f"/win32manifest:{HOST_MANIFEST}",
        *(str(source) for source in HOST_SOURCES),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not destination.is_file():
        detail = (result.stderr or result.stdout or "unknown csc error").strip()
        raise RuntimeError(f"编译桌面分身宿主失败: {detail}")
    return destination


def get_desktop_clone_host_executable() -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        executable = bundle_root / "desktop_clone" / HOST_EXE_NAME
        if not executable.is_file():
            raise FileNotFoundError(f"冻结包缺少桌面分身宿主: {executable}")
        return executable
    return compile_desktop_clone_host()
