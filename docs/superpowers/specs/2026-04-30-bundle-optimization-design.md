# AALC 编译包体优化实施文档

## 1. 概述

### 1.1 背景

AALC 使用 PyInstaller 打包 Python GUI 应用，基线 7z 压缩包 146.7 MB。通过多轮迭代优化，最终压缩至 104 MB。

### 1.2 目标

- 减小分发包体（7z 格式）
- 维持功能完整性
- 开发者体验优化：源码使用 PNG，构建时自动转为 WebP

### 1.3 最终结果

| 指标 | 基线 | 优化后 | 节省 |
|------|------|--------|------|
| 7z 压缩包 | 146.7 MB | 104 MB | 42.7 MB (-29%) |
| 解包大小 | 405.8 MB | 279 MB | 126.8 MB |

## 2. 架构原则

### 2.1 构建时 vs 源码时

- **源码**：保持开发者友好格式（PNG 图片、FP32 ONNX 模型、完整字体）
- **构建时**：自动应用无损优化（PNG→WebP、ONNX 量化、字体子集化）
- **运行时**：优先加载紧凑格式（.webp），回退原始格式（.png）

### 2.2 文件格式约定

| 层 | 图片 | 模型 | 字体 |
|----|------|------|------|
| 源码 (git) | .png | .onnx (FP32) | .ttf (完整) |
| 运行时 (dist) | .webp > .png | .onnx (INT8) | .ttf (子集) |

## 3. 优化明细

### 3.1 字体子集化

**文件**: `scripts/build.py`, `assets/app/fonts/ChineseFont.ttf`

**方法**:
1. 从代码库（.py/.ts/.yaml）提取所有使用到的 CJK 字符（1256 字）
2. 使用 `fonttools` 的 `pyftsubset` 保留 Basic Latin + 收集到的字符
3. 在构建时作为一次性操作执行

**效果**: 22.8 MB → 0.6 MB（-97%）

**风险**: 如需显示动态文本（玩家输入）中的生僻字会缺失，需回归扩展字库

### 3.2 ONNX 模型量化

**文件**: `scripts/build.py`, `assets/model/best.onnx`

**方法**:
1. 使用 `onnxruntime.quantization.quantize_dynamic` 将 FP32 量化为 INT8
2. 替换源文件（一次性操作，后续模型更新需重新量化）

**效果**: 12.3 MB → 3.3 MB（-73%）

**风险**: 精度轻微下降（YOLO 检测，下游仅用分类 ID 和整数坐标，容忍度极高）

### 3.3 运行时 WebP 回退机制

**文件**: `utils/image_utils.py`

`ImageUtils._resolve_image_path()` — 图片搜索链中优先查找 `.webp`，回退 `.png`

```python
webp_path = image_path
if image_path.endswith(".png"):
    webp_path = image_path[:-4] + ".webp"
for path in path_manager.pic_path:
    for candidate in (webp_path, image_path):
        ...
```

`ImageUtils.resolve_asset_path()` — 用于 QPixmap 直加载路径的 WebP 回退

### 3.4 构建时 PNG→WebP 转换

**文件**: `scripts/build.py`

在 `shutil.copytree("assets", ...)` 后，遍历 dist 中所有 PNG，无损转换：

```python
with Image.open(png_path) as img:
    img.save(webp_path, "WEBP", lossless=True)
```

**效果**: 30.8 MB → 18.2 MB（-41%）

### 3.5 scipy 排除

**文件**: `main.spec`

scipy 未被 AALC 或 rapidocr 任何代码 import，在 PyInstaller `excludes` 中排除。节省 ~50 MB 解包大小。

### 3.6 Qt 冗余模块裁剪

**文件**: `scripts/build.py` `redundant_files` 列表

PyInstaller 打包了大量不必要的 Qt 模块（3D、Charts、Multimedia、VirtualKeyboard 等），在构建后删除：

| 类别 | 数量 |
|------|------|
| Qt 3D | 14 个 DLL |
| Qt Quick/QML | 18 个 DLL |
| Qt Multimedia (FFmpeg) | 7 个 DLL |
| 其他 (Test/Help/Location 等) | 30+ 个 DLL |

### 3.7 依赖排除

**文件**: `main.spec`

```python
excludes=[
    'scipy', 'sympy', 'mpmath',
    'setuptools', 'pkg_resources',
    'decompyle3', 'spark_parser', 'xdis',
    'pyinstaller', 'pyinstaller-hooks-contrib',
    'ruff', 'watchdog',
],
```

### 3.8 strip 调试符号

**文件**: `main.spec`

`strip=True` — 去除二进制文件调试符号（Windows PE 文件收益有限但无害）。

## 4. 代码修改清单

| 文件 | 变更 |
|------|------|
| `main.spec` | 添加 excludes；`strip=True` |
| `updater.spec` | `upx=True` → `upx=False` |
| `scripts/build.py` | 冗余文件列表（80+ 条目）；PNG→WebP 转换；移除 UPX 后处理 |
| `utils/image_utils.py` | 新增 `_resolve_image_path()`；新增 `resolve_asset_path()`；更新 `check_default_path_exists()` 和 `load_from_specific_path()` |
| `module/automation/automation.py` | 三处 `endswith("assets.png")` 改为 `endswith(("assets.png", "assets.webp"))` |
| `app/base_combination.py` | QPixmap/CSS 路径包装 `resolve_asset_path()` |
| `app/theme_pack_setting_interface.py` | `get_image_path()` 使用 `resolve_asset_path()` |
| `assets/app/fonts/ChineseFont.ttf` | 子集化（22.8→0.6 MB） |
| `assets/model/best.onnx` | 量化 INT8（12.3→3.3 MB） |

## 5. 构建流程

```
源码 (PNG/FP32/完整字库)
  │
  ├─ PyInstaller 打包主程序
  ├─ PyInstaller 打包更新程序
  ├─ 复制 assets → dist
  ├─ PNG→WebP 转换（dist 中）
  ├─ 生成 .qm 翻译文件
  ├─ 注入版本号
  ├─ 删除冗余 Qt DLL（80+）
  └─ 7z 压缩 + SHA256
```

## 6. 验证要点

- **字体**：确认 UI 中所有汉字显示正常，无豆腐块
- **模型**：对比 INT8 vs FP32 的镜牢道路识别结果
- **WebP**：检查自动化图像匹配、主题包图片、UI 组件图是否正常加载
- **构建**：每次修改依赖后检查尺寸回归
