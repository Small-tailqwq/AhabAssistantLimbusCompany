import argparse
import os
import shutil
import subprocess

import PyInstaller.__main__

# 读取版本号
parser = argparse.ArgumentParser(description="Build AALC")
parser.add_argument("--version", default="dev", help="AALC Version")
args = parser.parse_args()
version = args.version

# 清理旧的构建文件
shutil.rmtree("./dist", ignore_errors=True)

# 构建应用程序
PyInstaller.__main__.run(
    [
        "main.spec",
        "--noconfirm",
    ]
)

if is_windows:
    PyInstaller.__main__.run(
        [
            "updater.spec",
            "--noconfirm",
        ]
    )

# 移动更新程序到主程序目录
if is_windows:
    shutil.move(os.path.join("dist", "AALC Updater.exe"), os.path.join("dist", "AALC"))

# macOS 使用 .app bundle 内部路径
if is_windows:
    dist_app_root = Path("dist") / "AALC"
else:
    dist_app_root = Path("dist") / "AALC.app" / "Contents" / "MacOS"

# 拷贝必要的文件到dist目录
shutil.copy("README.md", str(dist_app_root / "README.md"))
shutil.copy("LICENSE", str(dist_app_root / "LICENSE"))
shutil.copytree("assets", str(dist_app_root / "assets"), dirs_exist_ok=True)

# 将 assets 中的 PNG 无损转换为 WebP（减小包体）
try:
    from PIL import Image
    assets_dist = str(dist_app_root / "assets")
    png_saved = 0
    png_converted = 0
    for root, dirs, files in os.walk(assets_dist):
        for f in files:
            if f.lower().endswith(".png"):
                png_path = os.path.join(root, f)
                webp_path = os.path.splitext(png_path)[0] + ".webp"
                before = os.path.getsize(png_path)
                with Image.open(png_path) as img:
                    if img.mode in ("RGBA", "LA", "PA"):
                        img.save(webp_path, "WEBP", lossless=True)
                    else:
                        img = img.convert("RGB")
                        img.save(webp_path, "WEBP", lossless=True)
                after = os.path.getsize(webp_path)
                png_saved += before - after
                png_converted += 1
                os.remove(png_path)
    if png_converted:
        print(f"PNG->WebP converted {png_converted} files, saved {png_saved / 1_000_000:.1f} MB")
except ImportError:
    print("Warning: Pillow not available, skipping PNG->WebP conversion")

# 字体子集化：扫描源码中的 CJK 字符，裁剪 dist 中的字体
try:
    from fontTools.subset import Subsetter, Options
    from fontTools.ttLib import TTFont

    font_path = str(dist_app_root / "assets" / "app" / "fonts" / "ChineseFont.ttf")
    if os.path.exists(font_path):
        # 收集源码中使用的 CJK 字符
        chars = set()
        cjk_re = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\u3000-\u303f\uff00-\uffef\u2000-\u206f]")
        for root, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in (".venv", "dist", "build", ".git", "__pycache__")]
            for f in files:
                if f.endswith((".py", ".ts", ".yaml", ".yml", ".qss", ".css")):
                    try:
                        with open(os.path.join(root, f), encoding="utf-8") as fh:
                            chars.update(cjk_re.findall(fh.read()))
                    except Exception:
                        pass

        # 添加常用标点符号
        for cp in range(0x0020, 0x007F):
            chars.add(chr(cp))
        chars.update("：，！？；（）＾～…—·「」『』【】《》〈〉、。：")

        # 子集化
        font = TTFont(font_path)
        cmap = font.getBestCmap() or {}
        to_keep = sorted(cp for cp in (ord(c) for c in chars) if cp in cmap)
        opts = Options()
        opts.layout_features = []
        opts.notdef_glyph = True
        opts.glyph_names = True
        subsetter = Subsetter(options=opts)
        subsetter.populate(unicodes=to_keep)
        subsetter.subset(font)
        font.save(font_path)
        print(f"Font subsetted: {len(to_keep)} glyphs, {os.path.getsize(font_path) / 1_000_000:.1f} MB")
    else:
        print("Warning: ChineseFont.ttf not found, skipping font subsetting")
except ImportError:
    print("Warning: fonttools not available, skipping font subsetting")

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
bootstrap_version_path = dist_app_root / Path(*BOOTSTRAP_VERSION_PATH.split("/"))
bootstrap_version_path.write_text(str(args.bootstrap_version), encoding="utf-8")

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

managed_files = collect_managed_files(dist_app_root, DEFAULT_PROTECTED_PATHS)
managed_files_text = "\n".join(managed_files)
if managed_files_text:
    managed_files_text += "\n"

managed_files_path = dist_app_root / "managed_files.txt"
managed_files_path.write_text(managed_files_text, encoding="utf-8")
managed_files_sha256 = hashlib.sha256(managed_files_text.encode("utf-8")).hexdigest()

package_layout = "root_dir" if args.bridge_updater else "flat"
update_manifest = build_update_manifest(
    version=version,
    bootstrap_version=args.bootstrap_version,
    package_layout=package_layout,
    cleanup_mode="manifest",
    min_source_version_for_cleanup="0",
    managed_files_sha256=managed_files_sha256,
    protected_paths=DEFAULT_PROTECTED_PATHS,
)
update_manifest_path = dist_app_root / UPDATE_MANIFEST_NAME
update_manifest_path.write_text(
    json.dumps(update_manifest, ensure_ascii=True, indent=2) + "\n",
    encoding="utf-8",
)
shutil.copyfile(update_manifest_path, Path("dist") / REMOTE_UPDATE_MANIFEST_ASSET)

# 压缩构建产物
if is_windows:
    if args.bridge_updater:
        subprocess.run(["7z", "a", "-mx=7", f"AALC_{version}.7z", "AALC/*"], cwd="./dist", check=True)
    else:
        subprocess.run(["7z", "a", "-mx=7", f"../AALC_{version}.7z", "./*"], cwd="./dist/AALC", check=True)
    archive_path = os.path.join("dist", f"AALC_{version}.7z")
else:
    if args.bridge_updater:
        raise SystemExit("--bridge-updater is supported on Windows only")

    # macOS: PyInstaller BUNDLE 将数据文件放入 Contents/Resources/，
    # 但 Python 模块在 Contents/MacOS/，某些包（如 rapidocr）通过
    # __file__ 相对路径查找数据文件，需将资源同步到 MacOS/ 目录。
    resources_dir = dist_app_root.parent / "Resources"
    macos_dir = dist_app_root / "Contents" / "MacOS"
    for data_dir in resources_dir.iterdir():
        if data_dir.is_dir():
            target = macos_dir / data_dir.name
            if not target.exists():
                shutil.copytree(data_dir, target, symlinks=True)
                print(f"Linked resources: {data_dir.name} -> MacOS/")

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
    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", _sign_id, _app_bundle],
        check=True,
        capture_output=True,
    )
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

    # 首次使用提示
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
