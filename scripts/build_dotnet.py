"""构建并打包 .NET 版 AAALC。

模式：
  full      自带运行时（体积大，朋友无需安装 .NET）
  trimmed   自带运行时并裁剪未使用程序集（体积中等，需实测可启动）
  fdd       依赖框架（体积最小，需安装 .NET 10 运行时）

输出：artifacts/publish/<mode>/AAALC 与同级 AAALC-<mode>.7z（已忽略目录）。
产物根目录为 AAALC.exe、资源和 app（运行时与全部 DLL）。
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "src" / "AALC.Desktop" / "AALC.Desktop.csproj"
OCR_SOURCE = ROOT / "assets" / "models" / "ocr"
OCR_FILES = ["ch_PP-OCRv4_det_infer.onnx", "ch_PP-OCRv4_rec_infer.onnx", "ppocr_keys_v1.txt"]
RUNTIME_DIRECTORY = "app"
VC_RUNTIME_FILES = ["msvcp140.dll", "msvcp140_1.dll", "vcruntime140.dll", "vcruntime140_1.dll"]

MODES = {
    "full": ["--self-contained", "true"],
    "trimmed": ["--self-contained", "true", "-p:PublishTrimmed=true", "-p:TrimMode=partial", "-p:JsonSerializerIsReflectionEnabledByDefault=true", "-p:TrimmerSingleWarn=true", "-p:BuiltInComInteropSupport=true"],
    "fdd": ["--self-contained", "false"],
}


def publish(mode: str, out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    command = [
        "dotnet", "publish", str(PROJECT), "-c", "Release", "-r", "win-x64",
        "-o", str(out), "-p:DebugType=None", "-p:DebugSymbols=false", *MODES[mode],
    ]
    subprocess.run(command, check=True)


def strip_unused(out: Path) -> None:
    # 调试符号、转储与诊断组件、未启用的备用 GC、QUIC 及导入库，运行时均不加载
    patterns = (
        "*.pdb", "*.lib", "opencv_videoio_ffmpeg*.dll", "createdump.exe",
        "mscordaccore*.dll", "mscordbi.dll", "clrgc*.dll", "msquic.dll",
    )
    for pattern in patterns:
        for file in out.glob(pattern):
            file.unlink()


def publish_mcp(mode: str, out: Path) -> None:
    command = [
        "dotnet", "publish", str(ROOT / "src" / "AALC.Mcp" / "AALC.Mcp.csproj"),
        "-c", "Release", "-r", "win-x64", "-o", str(out / "mcp"),
        "-p:DebugType=None", "-p:DebugSymbols=false", *MODES["fdd" if mode == "fdd" else "full"],
    ]
    subprocess.run(command, check=True)


def relocate_runtime(out: Path) -> None:
    # 根目录只留 AAALC.exe：apphost 内嵌主程序的相对路径，指向 app 目录后基目录随之变为 app
    exe = out / "AAALC.exe"
    binding = b"AAALC.dll\0"
    relocated = RUNTIME_DIRECTORY.encode() + b"\\" + binding
    padded = binding.ljust(len(relocated), b"\0")
    content = exe.read_bytes()
    if content.count(padded) != 1:
        sys.exit("apphost binding not found")
    exe.write_bytes(content.replace(padded, relocated))
    runtime = out / RUNTIME_DIRECTORY
    runtime.mkdir()
    for item in list(out.iterdir()):
        if item not in (exe, runtime):
            shutil.move(item, runtime / item.name)


def copy_assets(out: Path) -> None:
    (out / "assets" / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "assets" / "config" / "config.example.yaml", out / "assets" / "config")
    shutil.copytree(ROOT / "assets" / "images", out / "assets" / "images", dirs_exist_ok=True)
    # assets/app 的 fonts、svgs 及 sinner 的 Logo、ID_Photo 只有 Python 版使用
    shutil.copytree(ROOT / "assets" / "app" / "status_effects", out / "assets" / "app" / "status_effects", dirs_exist_ok=True)
    shutil.copytree(ROOT / "assets" / "app" / "theme_packs", out / "assets" / "app" / "theme_packs", dirs_exist_ok=True)
    shutil.copytree(
        ROOT / "assets" / "app" / "sinner", out / "assets" / "app" / "sinner", dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("Logo.png", "*_ID_Photo_*.png"),
    )
    (out / "assets" / "model").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "assets" / "model" / "best.onnx", out / "assets" / "model")
    scenarios = out / "scenarios"
    scenarios.mkdir(parents=True, exist_ok=True)
    for scenario in (ROOT / "scenarios").glob("mail-*.json"):
        shutil.copy2(scenario, scenarios)
    # onnxruntime 依赖 VC++ 运行库，干净系统未必安装
    system32 = Path(os.environ["SYSTEMROOT"]) / "System32"
    for name in VC_RUNTIME_FILES:
        shutil.copy2(system32 / name, out / RUNTIME_DIRECTORY)
    models = out / "assets" / "models" / "ocr"
    models.mkdir(parents=True, exist_ok=True)
    source = OCR_SOURCE
    if not all((source / name).is_file() for name in OCR_FILES):
        sys.exit("OCR model files not found")
    for name in OCR_FILES:
        shutil.copy2(source / name, models)


def archive(out: Path, archive_path: Path) -> None:
    seven_zip = shutil.which("7z") or str(Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "7-Zip" / "7z.exe")
    archive_path.unlink(missing_ok=True)
    subprocess.run([seven_zip, "a", "-mx=9", "-md=64m", "-ms=on", str(archive_path), out.name], cwd=out.parent, check=True, stdout=subprocess.DEVNULL)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("modes", nargs="*", metavar="mode", default=list(MODES))
    args = parser.parse_args()
    for mode in args.modes:
        if mode not in MODES:
            parser.error(f"unknown mode: {mode}")
        base = ROOT / "artifacts" / "publish" / mode
        out = base / "AAALC"
        publish(mode, out)
        strip_unused(out)
        relocate_runtime(out)
        publish_mcp(mode, out)
        copy_assets(out)
        zip_path = base / f"AAALC-{mode}.7z"
        archive(out, zip_path)
        sys.stdout.write(f"{mode}: {zip_path} ({zip_path.stat().st_size / 1048576:.0f} MB)\n")


if __name__ == "__main__":
    sys.exit(main())
