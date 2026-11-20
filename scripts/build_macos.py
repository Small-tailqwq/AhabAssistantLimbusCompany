"""Build a single-architecture, self-contained macOS desktop .app ZIP."""
import argparse
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "publish"
RIDS = {"arm64": "osx-arm64", "x86_64": "osx-x64"}


def build(arch: str) -> Path:
    rid = RIDS[arch]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    archive = OUTPUT / f"AAALC-{rid}.zip"
    with tempfile.TemporaryDirectory(dir=OUTPUT) as temporary:
        stage = Path(temporary)
        app = stage / "AAALC.app"
        contents = app / "Contents"
        binaries = contents / "MacOS"
        resources = contents / "Resources"
        resources.mkdir(parents=True)
        binaries.mkdir()
        subprocess.run(["dotnet", "publish", "src/AALC.Desktop", "-c", "Release", "-r", rid,
                        "--self-contained", "-p:PublishTrimmed=true", "-p:TrimMode=partial",
                        "-p:DebugType=None", "-o", resources], cwd=ROOT, check=True)
        (resources / "AAALC").rename(binaries / "AAALC")
        # apphost resolves its managed entry point before locating the bundled runtime.
        (binaries / "AAALC.dll").symlink_to("../Resources/AAALC.dll")
        shutil.copy2(ROOT / "LICENSE", resources)
        for lib in resources.glob("*.dylib"):
            archs = subprocess.check_output(["lipo", "-archs", lib], text=True).split()
            if arch not in archs:
                raise ValueError(f"{lib.name}: missing {arch}")
            if len(archs) > 1:
                thin = stage / lib.name
                subprocess.run(["lipo", lib, "-thin", arch, "-output", thin], check=True)
                thin.replace(lib)
                subprocess.run(["codesign", "--force", "--sign", "-", lib], check=True)
        with (contents / "Info.plist").open("wb") as file:
            plistlib.dump(dict(CFBundlePackageType="APPL", CFBundleName="AAALC",
                               CFBundleIdentifier="io.github.small-tailqwq.aaalc",
                               CFBundleExecutable="AAALC", NSHighResolutionCapable=True), file)
        subprocess.run(["codesign", "--force", "--sign", "-", app], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", app], check=True)
        files = [p for p in app.rglob("*") if p.is_file()]
        zipped = stage / archive.name
        subprocess.run(["zip", "-qry", "-6", zipped, app.name], cwd=stage, check=True)
        os.replace(zipped, archive)
        print(f"{rid}: host={(binaries / 'AAALC').stat().st_size:,} bytes, "
              f"app={sum(p.lstat().st_size for p in files):,} bytes, zip={archive.stat().st_size:,} bytes")
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=RIDS, default=platform.machine())
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("macOS is required (lipo and codesign)")
    print(build(args.arch))
