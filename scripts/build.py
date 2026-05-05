import argparse
import hashlib
import os
import re
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

PyInstaller.__main__.run(
    [
        "updater.spec",
        "--noconfirm",
    ]
)

# 移动更新程序到主程序目录
shutil.move(os.path.join("dist", "AALC Updater.exe"), os.path.join("dist", "AALC"))

# 拷贝必要的文件到dist目录
shutil.copy("README.md", os.path.join("dist", "AALC", "README.md"))
shutil.copy("LICENSE", os.path.join("dist", "AALC", "LICENSE"))
shutil.copytree("assets", os.path.join("dist", "AALC", "assets"), dirs_exist_ok=True)

# 将 assets 中的 PNG 无损转换为 WebP（减小包体）
try:
    from PIL import Image
    assets_dist = os.path.join("dist", "AALC", "assets")
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

    font_path = os.path.join("dist", "AALC", "assets", "app", "fonts", "ChineseFont.ttf")
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
        cmap = font.getBestCmap()
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
os.makedirs(os.path.join("dist", "AALC", "i18n"), exist_ok=True)
for ts_file in os.listdir("./i18n"):
    if ts_file.endswith(".ts"):
        qm_path = os.path.join("./i18n", ts_file.replace(".ts", ".qm"))
        subprocess.run(["pyside6-lrelease", os.path.join("./i18n", ts_file), "-qm", qm_path])
        print(f"Generated: {qm_path}")
        shutil.move(qm_path, os.path.join("dist", "AALC", "i18n", ts_file.replace(".ts", ".qm")))

# 注入版本号到./dist/AALC/assets/config/version.txt
os.makedirs(os.path.join("dist", "AALC", "assets", "config"), exist_ok=True)
with open(
    os.path.join("dist", "AALC", "assets", "config", "version.txt"),
    "w",
    encoding="utf-8",
) as f:
    f.write(version)

# 裁剪多余的文件
bundled_internal_dir = os.path.join("dist", "AALC", "_internal")
redundant_files = [
    # qt6自带的翻译文件，体积较大且不需要
    "PySide6/translations",
    # QML相关，我们用的是QtWidgets并不需要
    "PySide6/Qt6Qml.dll",
    "PySide6/Qt6Quick.dll",
    "PySide6/Qt6QmlModels.dll",
    "PySide6/Qt6QmlWorkerScript.dll",
    "PySide6/Qt6QmlMeta.dll",
    # opengl相关，我们用的是QtWidgets并不需要
    "PySide6/Qt6OpenGL.dll",
    "PySide6/opengl32sw.dll",  # 软件渲染库，没GPU的机器才需要
    # 其他不需要的Qt模块
    "PySide6/Qt6Pdf.dll",  # pdf文件
    "PySide6/Qt6Network.dll",  # 网络相关
    "PySide6/QtNetwork.pyd",
    # Qt Designer（设计器，运行时不需要）
    "PySide6/Qt6Designer.dll",
    "PySide6/Qt6DesignerComponents.dll",
    # Qt 图表相关（AALC 不用）
    "PySide6/Qt6Charts.dll",
    "PySide6/Qt6ChartsQml.dll",
    "PySide6/Qt6DataVisualization.dll",
    "PySide6/Qt6DataVisualizationQml.dll",
    "PySide6/Qt6Graphs.dll",
    "PySide6/Qt6GraphsWidgets.dll",
    # Qt 3D 全套（AALC 不用）
    "PySide6/Qt63DCore.dll",
    "PySide6/Qt63DRender.dll",
    "PySide6/Qt63DInput.dll",
    "PySide6/Qt63DLogic.dll",
    "PySide6/Qt63DAnimation.dll",
    "PySide6/Qt63DExtras.dll",
    "PySide6/Qt63DQuick.dll",
    "PySide6/Qt63DQuickExtras.dll",
    "PySide6/Qt63DQuickInput.dll",
    "PySide6/Qt63DQuickRender.dll",
    "PySide6/Qt63DQuickScene2D.dll",
    "PySide6/Qt63DQuickScene3D.dll",
    "PySide6/Qt63DQuickAnimation.dll",
    "PySide6/Qt6Quick3D.dll",
    "PySide6/Qt6Quick3DAssetImport.dll",
    "PySide6/Qt6Quick3DAssetUtils.dll",
    "PySide6/Qt6Quick3DEffects.dll",
    "PySide6/Qt6Quick3DGlslParser.dll",
    "PySide6/Qt6Quick3DHelpers.dll",
    "PySide6/Qt6Quick3DHelpersImpl.dll",
    "PySide6/Qt6Quick3DIblBaker.dll",
    "PySide6/Qt6Quick3DParticles.dll",
    "PySide6/Qt6Quick3DParticleEffects.dll",
    "PySide6/Qt6Quick3DRuntimeRender.dll",
    "PySide6/Qt6Quick3DSpatialAudio.dll",
    "PySide6/Qt6Quick3DUtils.dll",
    "PySide6/Qt6Quick3DXr.dll",
    # Qt 测试/帮助/文档（运行时不需要）
    "PySide6/Qt6Test.dll",
    "PySide6/Qt6Help.dll",
    # Qt 位置/定位/传感器
    "PySide6/Qt6Location.dll",
    "PySide6/Qt6Positioning.dll",
    "PySide6/Qt6PositioningQuick.dll",
    "PySide6/Qt6Sensors.dll",
    "PySide6/Qt6SensorsQuick.dll",
    # Qt 串口/蓝牙/NFC
    "PySide6/Qt6SerialBus.dll",
    "PySide6/Qt6SerialPort.dll",
    "PySide6/Qt6Bluetooth.dll",
    "PySide6/Qt6Nfc.dll",
    # Qt 虚拟键盘
    "PySide6/Qt6VirtualKeyboard.dll",
    "PySide6/Qt6VirtualKeyboardSettings.dll",
    "PySide6/Qt6VirtualKeyboardQml.dll",
    # Qt 语音合成
    "PySide6/Qt6TextToSpeech.dll",
    # Qt WebChannel / WebSockets
    "PySide6/Qt6WebChannel.dll",
    "PySide6/Qt6WebChannelQuick.dll",
    "PySide6/Qt6WebSockets.dll",
    # Qt 状态机
    "PySide6/Qt6StateMachine.dll",
    "PySide6/Qt6StateMachineQml.dll",
    # Qt 数据库（AALC 不用）
    "PySide6/Qt6Sql.dll",
    "PySide6/plugins/sqldrivers/qsqlite.dll",
    # Qt 其他不用的模块
    "PySide6/Qt6Concurrent.dll",
    "PySide6/Qt6Scxml.dll",
    "PySide6/Qt6ScxmlQml.dll",
    "PySide6/Qt6RemoteObjects.dll",
    "PySide6/Qt6RemoteObjectsQml.dll",
    "PySide6/Qt6UiTools.dll",
    "PySide6/Qt6ShaderTools.dll",
    # Qt Quick 相关剩余
    "PySide6/Qt6QuickWidgets.dll",
    "PySide6/Qt6QuickLayouts.dll",
    "PySide6/Qt6QuickShapes.dll",
    "PySide6/Qt6QuickTimeline.dll",
    "PySide6/Qt6QuickTimelineBlendTrees.dll",
    "PySide6/Qt6QuickParticles.dll",
    "PySide6/Qt6QuickEffects.dll",
    "PySide6/Qt6QuickTest.dll",
    "PySide6/Qt6QuickVectorImage.dll",
    "PySide6/Qt6QuickVectorImageGenerator.dll",
    # Qt 打印支持
    "PySide6/Qt6PrintSupport.dll",
    # Qt 多媒体相关
    "PySide6/Qt6Multimedia.dll",
    "PySide6/Qt6MultimediaQuick.dll",
    "PySide6/Qt6MultimediaWidgets.dll",
    "PySide6/Qt6SpatialAudio.dll",
    "PySide6/avcodec-61.dll",
    "PySide6/avformat-61.dll",
    "PySide6/avutil-59.dll",
    "PySide6/swscale-8.dll",
    "PySide6/swresample-5.dll",
    "PySide6/ffmpegmediaplugin.dll",
    "PySide6/windowsmediaplugin.dll",
    # rapidocr自带的模型文件，我们只用PPV4模型，可以删掉V5的
    "rapidocr/models/ch_PP-OCRv5_rec_mobile_infer.onnx",
    "rapidocr/models/ch_PP-OCRv5_mobile_det.onnx",
    # rapidocr用来可视化识别结果的字体，我们不用这个功能
    "rapidocr/models/FZYTK.TTF",
    # opencv的videoio插件，我们不需要
    "cv2/opencv_videoio_ffmpeg4110_64.dll",
    # PIL AVIF 支持（7.5MB），不需要
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

# 压缩为7z文件
subprocess.run(["7z", "a", "-mx=7", f"AALC_{version}.7z", "AALC/*"], cwd="./dist")

# 生成SHA256哈希文件，供更新程序校验下载完整性
archive_path = os.path.join("dist", f"AALC_{version}.7z")
sha256 = hashlib.sha256()
with open(archive_path, "rb") as f:
    for chunk in iter(lambda: f.read(65536), b""):
        sha256.update(chunk)
hash_path = f"{archive_path}.sha256"
with open(hash_path, "w") as f:
    f.write(sha256.hexdigest())
print(f"SHA256: {hash_path}")
