import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

# 将 venv bin 目录加入 PATH，确保 pyside6-lrelease 等工具可被发现
_VENV_BIN = str(Path(sys.executable).parent)
if _VENV_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{_VENV_BIN}{os.pathsep}{os.environ.get('PATH', '')}"

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import PyInstaller.__main__


# 读取版本号
parser = argparse.ArgumentParser(description="Build AALC")
parser.add_argument("--version", default="dev", help="AALC Version")
args = parser.parse_args()
version = args.version
is_windows = sys.platform == "win32"

# 清理旧的构建文件
shutil.rmtree("./dist", ignore_errors=True)

# 构建应用程序
PyInstaller.__main__.run(
    [
        "main.spec",
        "--noconfirm",
    ]
)

# macOS 使用 .app bundle 内部路径
if is_windows:
    dist_app_root = Path("dist") / "AALC"
else:
    dist_app_root = Path("dist") / "AALC.app" / "Contents" / "MacOS"

# 拷贝必要的文件到dist目录
shutil.copy("README.md", str(dist_app_root / "README.md"))
shutil.copy("LICENSE", str(dist_app_root / "LICENSE"))
shutil.copytree("assets", str(dist_app_root / "assets"), dirs_exist_ok=True)

# 生成翻译文件
i18n_dst = dist_app_root / "i18n"
i18n_dst.mkdir(parents=True, exist_ok=True)
for ts_file in os.listdir("./i18n"):
    if ts_file.endswith(".ts"):
        qm_path = os.path.join("./i18n", ts_file.replace(".ts", ".qm"))
        subprocess.run(["pyside6-lrelease", os.path.join("./i18n", ts_file), "-qm", qm_path])
        print(f"Generated: {qm_path}")
        shutil.move(qm_path, str(i18n_dst / ts_file.replace(".ts", ".qm")))

# 注入版本号
assets_config = dist_app_root / "assets" / "config"
assets_config.mkdir(parents=True, exist_ok=True)
(assets_config / "version.txt").write_text(version, encoding="utf-8")

# Windows 清理冗余 Qt 文件，减小包体
if is_windows:
    bundled_internal_dir = str(dist_app_root / "_internal")
    redundant_files = [
        "PySide6/translations",
        "PySide6/Qt6Qml.dll", "PySide6/Qt6Quick.dll",
        "PySide6/Qt6QmlModels.dll", "PySide6/Qt6QmlWorkerScript.dll", "PySide6/Qt6QmlMeta.dll",
        "PySide6/Qt6OpenGL.dll", "PySide6/opengl32sw.dll",
        "PySide6/Qt6Pdf.dll", "PySide6/Qt6Network.dll", "PySide6/QtNetwork.pyd",
        "PySide6/Qt6Designer.dll", "PySide6/Qt6DesignerComponents.dll",
        "PySide6/Qt6Charts.dll", "PySide6/Qt6ChartsQml.dll",
        "PySide6/Qt6DataVisualization.dll", "PySide6/Qt6DataVisualizationQml.dll",
        "PySide6/Qt6Graphs.dll", "PySide6/Qt6GraphsWidgets.dll",
        "PySide6/Qt63DCore.dll", "PySide6/Qt63DRender.dll", "PySide6/Qt63DInput.dll",
        "PySide6/Qt63DLogic.dll", "PySide6/Qt63DAnimation.dll", "PySide6/Qt63DExtras.dll",
        "PySide6/Qt63DQuick.dll", "PySide6/Qt63DQuickExtras.dll", "PySide6/Qt63DQuickInput.dll",
        "PySide6/Qt63DQuickRender.dll", "PySide6/Qt63DQuickScene2D.dll", "PySide6/Qt63DQuickScene3D.dll",
        "PySide6/Qt63DQuickAnimation.dll",
        "PySide6/Qt6Quick3D.dll", "PySide6/Qt6Quick3DAssetImport.dll", "PySide6/Qt6Quick3DAssetUtils.dll",
        "PySide6/Qt6Quick3DEffects.dll", "PySide6/Qt6Quick3DGlslParser.dll",
        "PySide6/Qt6Quick3DHelpers.dll", "PySide6/Qt6Quick3DHelpersImpl.dll",
        "PySide6/Qt6Quick3DIblBaker.dll", "PySide6/Qt6Quick3DParticles.dll",
        "PySide6/Qt6Quick3DParticleEffects.dll", "PySide6/Qt6Quick3DRuntimeRender.dll",
        "PySide6/Qt6Quick3DSpatialAudio.dll", "PySide6/Qt6Quick3DUtils.dll", "PySide6/Qt6Quick3DXr.dll",
        "PySide6/Qt6Test.dll", "PySide6/Qt6Help.dll",
        "PySide6/Qt6Location.dll", "PySide6/Qt6Positioning.dll", "PySide6/Qt6PositioningQuick.dll",
        "PySide6/Qt6Sensors.dll", "PySide6/Qt6SensorsQuick.dll",
        "PySide6/Qt6SerialBus.dll", "PySide6/Qt6SerialPort.dll",
        "PySide6/Qt6Bluetooth.dll", "PySide6/Qt6Nfc.dll",
        "PySide6/Qt6VirtualKeyboard.dll", "PySide6/Qt6VirtualKeyboardSettings.dll", "PySide6/Qt6VirtualKeyboardQml.dll",
        "PySide6/Qt6TextToSpeech.dll",
        "PySide6/Qt6WebChannel.dll", "PySide6/Qt6WebChannelQuick.dll", "PySide6/Qt6WebSockets.dll",
        "PySide6/Qt6StateMachine.dll", "PySide6/Qt6StateMachineQml.dll",
        "PySide6/Qt6Sql.dll", "PySide6/plugins/sqldrivers/qsqlite.dll",
        "PySide6/Qt6Concurrent.dll", "PySide6/Qt6Scxml.dll", "PySide6/Qt6ScxmlQml.dll",
        "PySide6/Qt6RemoteObjects.dll", "PySide6/Qt6RemoteObjectsQml.dll",
        "PySide6/Qt6UiTools.dll", "PySide6/Qt6ShaderTools.dll",
        "PySide6/Qt6QuickWidgets.dll", "PySide6/Qt6QuickLayouts.dll", "PySide6/Qt6QuickShapes.dll",
        "PySide6/Qt6QuickTimeline.dll", "PySide6/Qt6QuickTimelineBlendTrees.dll",
        "PySide6/Qt6QuickParticles.dll", "PySide6/Qt6QuickEffects.dll",
        "PySide6/Qt6QuickTest.dll", "PySide6/Qt6QuickVectorImage.dll", "PySide6/Qt6QuickVectorImageGenerator.dll",
        "PySide6/Qt6PrintSupport.dll",
        "PySide6/Qt6Multimedia.dll", "PySide6/Qt6MultimediaQuick.dll", "PySide6/Qt6MultimediaWidgets.dll",
        "PySide6/Qt6SpatialAudio.dll",
        "PySide6/avcodec-61.dll", "PySide6/avformat-61.dll", "PySide6/avutil-59.dll",
        "PySide6/swscale-8.dll", "PySide6/swresample-5.dll",
        "PySide6/ffmpegmediaplugin.dll", "PySide6/windowsmediaplugin.dll",
        "rapidocr/models/ch_PP-OCRv5_rec_mobile_infer.onnx",
        "rapidocr/models/ch_PP-OCRv5_mobile_det.onnx",
        "rapidocr/models/FZYTK.TTF",
        "cv2/opencv_videoio_ffmpeg4110_64.dll",
        "PIL/_avif.cp313-win_amd64.pyd",
    ]
    for rel_path in redundant_files:
        abs_path = os.path.join(bundled_internal_dir, rel_path)
        if os.path.isdir(abs_path):
            shutil.rmtree(abs_path, ignore_errors=True)
        elif os.path.isfile(abs_path):
            os.remove(abs_path)
        else:
            print(f"Warning: {abs_path} not found.")

# 压缩构建产物
if is_windows:
    subprocess.run(["7z", "a", "-mx=7", f"../AALC_{version}.7z", "./*"], cwd="./dist/AALC", check=True)
    archive_path = os.path.join("dist", f"AALC_{version}.7z")
else:
    # macOS: PyInstaller BUNDLE 将 a.datas 放入 Contents/Resources/，
    # 但 frozen 模式下 __file__ 解析到 Contents/Frameworks/，数据文件不在那里。
    # 运行时由 main.py 中的路径修复逻辑处理（从 MacOS/ 复制到 Frameworks/），
    # 构建阶段不再做 post-build sync，避免硬链接和 zip 打包的兼容性问题。
    archive_base = os.path.join("dist", f"AALC_{version}_macos")
    archive_path = shutil.make_archive(archive_base, "zip", root_dir="./dist", base_dir="AALC.app")
    print(f"Created archive: {archive_path}")

# macOS: 添加文件后重新签名 .app bundle
if not is_windows:
    _app_bundle = str(dist_app_root.parent.parent)
    _cert = subprocess.run(
        ["security", "find-identity", "-v", "-p", "basic"],
        capture_output=True, text=True,
    )
    _sign_id = "-"
    for _line in _cert.stdout.splitlines():
        if "\"Apple Development:" in _line:
            _sign_id = _line.split('"')[1]
            break
    _sign_result = subprocess.run(
        ["codesign", "--force", "--deep", "--sign", _sign_id, _app_bundle],
        capture_output=True, text=True,
    )
    if _sign_result.returncode != 0:
        print(f"Warning: codesign failed (non-fatal): {_sign_result.stderr.strip()}")
    else:
        print(f"Signed .app bundle with: {_sign_id}")

    # 生成启动脚本 AALC.command（双击在终端运行，绕过 Gatekeeper）
    command_path = os.path.join("dist", "AALC.command")
    with open(command_path, "w") as f:
        f.write(
            '#!/bin/bash\n'
            'cd "$(dirname "$0")/AALC.app/Contents/MacOS"\n'
            './AALC\n'
        )
    os.chmod(command_path, 0o755)
    print(f"Created launch script: {command_path}")

    print("\n===== macOS 启动说明 =====")
    print("双击 dist/AALC.command 启动（会打开终端窗口）")
    print("或右键 dist/AALC.app → 打开（首次需在弹窗中确认）")
    print("或终端执行: open dist/AALC.app/Contents/MacOS/AALC")

# 生成SHA256哈希文件，供校验下载完整性
sha256 = hashlib.sha256()
with open(archive_path, "rb") as archive_file:
    for chunk in iter(lambda: archive_file.read(65536), b""):
        sha256.update(chunk)
hash_path = f"{archive_path}.sha256"
with open(hash_path, "w") as hash_file:
    hash_file.write(sha256.hexdigest())
print(f"SHA256: {hash_path}")
