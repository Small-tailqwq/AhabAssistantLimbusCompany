# Agent Note: 发行包在构建时压缩资源，源码保留可编辑格式

Status: implemented

## 问题

PyInstaller 打包的 AALC 带上了完整中文字体、未使用的科学计算库和大量 Qt 模块，7z 发行包约 146.7 MB、解包约 405.8 MB。直接在源码中替换为压缩格式会让模板截图和字体难以编辑与比对。

## 决策

源码保留开发者使用的格式，[build.py](../../../../scripts/build.py) 只在 `dist/AALC` 中做无损或可回归的压缩：

- 复制 `assets` 后，把 dist 中所有 PNG 无损转为 WebP 并删除 PNG。[ImageUtils](../../../../utils/image_utils.py) 的 `_resolve_image_path()` 与 `resolve_asset_path()` 先查找同名 `.webp`，再回退 `.png`；自动化中判断 `assets.png` 后缀的位置同时接受 `assets.webp`。
- 扫描源码中的 `.py`、`.ts`、`.yaml`、`.yml`、`.qss`、`.css` 收集 CJK 字符，加上 ASCII 与常用全角标点，对 dist 中的 `ChineseFont.ttf` 子集化；仓库保留完整字体。
- 删除 PyInstaller 带入的冗余 Qt DLL（3D、Quick/QML、Multimedia 等），列表维护在 `build.py`。
- [main.spec](../../../../main.spec) 排除 tkinter、scipy、sympy、mpmath、setuptools、反编译工具、PyInstaller 自身、ruff 与 watchdog。主程序与更新程序均关闭 `strip` 和 UPX。
- 镜牢道路识别模型 `assets/model/best.onnx` 以 INT8 动态量化后的文件提交（约 3.3 MB）；下游只使用分类 ID 与整数坐标。

## 曾考虑的替代方案

**在源码中直接保存 WebP 与子集字体。** 能省去构建步骤，但模板难以用常规工具查看和替换，新增文案还需要手动扩展字库；因此把转换放在构建阶段。

**`strip=True`。** 去除调试符号对 Windows PE 收益有限，且 PyInstaller 构建后出现启动报错，主程序关闭 strip。

## 后果

优化后 7z 约 104 MB、解包约 279 MB。dist 中只有 WebP 图片，运行时加载图片必须经过 `ImageUtils` 的回退逻辑，直接拼接 `.png` 路径的代码在发行包中会找不到文件。

字体只包含构建时源码出现过的字符，玩家输入或外部文本中的生僻字可能显示为缺字。模型量化是对源文件的一次性替换，更新模型时需要重新量化并对比道路识别结果。依赖或 Qt 版本变化后需要检查包体回归与 DLL 裁剪是否仍然安全。
