# 模板匹配重放管线

## 必需的生产等价路径

复现 `find_element()` → `find_image_element()` → `ImageUtils.match_template()`，而不是调用裸 OpenCV 匹配。

```python
# 1. 从实际截图推导缩放。
scale = screenshot_np.shape[0] / 1440.0

# 2. 通过生产使用的同一语言/主题解析加载仓库资源。
# 3. 与生产加载器一致地缩放模板。
# 4. 按 ImageUtils 预期转换通道。
# 5. 用生产 bbox 规则裁剪透明/文字资源。
# 6. 调用 ImageUtils.match_template(screen_np, template, bbox, model=model)。
```

复现细节前先读当前实现：

- `utils/image_utils.py`：`load_image`、`get_bbox`、`crop`、`match_template` 与归一化辅助函数；
- `module/automation/automation.py`：`find_element`、`find_image_element` 与模板加载；
- `debug_tools/verify_matching.py`：支持的 CLI 重放路径。

代码与旧 issue 笔记不一致时以代码为准。

## 缩放

用截图高度，而不是配置的窗口尺寸：

```python
scale = screenshot_np.shape[0] / 1440.0
```

`cfg.set_win_size` 可能与采集的 PNG 或运行帧不同。记录非标准宽高比或额外边框，因为仅按高度缩放可能无法解释它们。

## `_assets.png` 的 bbox 行为

带透明或空白周边的模板必须走生产 bbox/裁剪路径。跳过它可能让背景主导相似度，也会改变报告的中心点。

不要盲目套用本 reference 复制的文件名规则。在事件发生的源版本中确认当前加载器的条件与返回的 bbox。

## 匹配模型

模型名控制 `ImageUtils.match_template()` 中的搜索区域：

- `clam`：在预期 bbox 附近窄搜索；
- `normal`：较宽的有界搜索；
- `aggressive`：无限制或最宽搜索。

诊断中不要硬编码记忆的像素值，读当前源码核验精确扩展值。

## 通道与采集差异

检查 RGB/BGR/灰度转换、alpha 移除、缩放插值、截图后端、压缩、DPI 缩放、模拟器边框与覆盖层。即使名义分辨率相同，手动保存的截图也可能不同于运行时 `PrintWindow`、OBS 或模拟器帧。

## 复现记录

记录：

```text
Incident version/source:
Screenshot path and dimensions:
Asset key and resolved asset path:
Scale and bbox:
Model and threshold:
Similarity and center:
Runtime log value and center:
Difference and supported explanation:
```
