# 模板匹配重放要点

## 背景

分析 issue 时需要重放用户截图 vs 资产模板的匹配值，验证日志中的相似度是否符合预期。

## 必须复现的完整管道

`find_element()` → `find_image_element()` → `ImageUtils.match_template()` 的完整链路，不能跳过中间步骤。

```python
# 1. 确定截图原生比例
screenshot_h = screen_np.shape[0]
scale = screenshot_h / 1440.0  # 模板设计基准为 1440p

# 2. 加载并缩放模板
# 用截图高度算缩放，NOT cfg.set_win_size（截图分辨率≠游戏配置）
tpl_raw = cv2.imread(tpl_path, cv2.IMREAD_UNCHANGED)
if tpl_raw.shape[2] == 4:
    tpl_bgr = tpl_raw[:, :, :3].copy()
else:
    tpl_bgr = tpl_raw.copy()
if abs(scale - 1.0) > 1e-6:
    tpl_bgr = cv2.resize(tpl_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

# 3. 转灰度
tpl_gray = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY)

# 4. ★ 关键：_assets.png 后缀必须做 bbox 裁剪 ★
# 没有这一步，带透明/黑色背景的文字图片匹配值会被严重压低
bbox = None
if target_key.endswith("_assets.png"):
    bbox = ImageUtils.get_bbox(tpl_gray)
    tpl_gray = ImageUtils.crop(tpl_gray, bbox)

# 5. 使用 ImageUtils.match_template（含 bbox 搜索区域限制 + model 参数）
center, max_val = ImageUtils.match_template(screen_np, tpl_gray, bbox, model=model)
```

## 常见陷阱

### 陷阱 1：跳过 `_assets.png` bbox 裁剪（最高频 bug）

以 `event/very_high.png` 为例——图片有透明背景。
- **跳过 bbox 裁剪**：模板 = 小文字 + 大面积黑色背景 → 匹配值 ~0.39
- **正确裁剪**：模板 = 只有文字区域 → 匹配值 0.89

判断是否需要裁剪：`target.endswith("_assets.png")`。是则必须调用 `ImageUtils.get_bbox()` + `ImageUtils.crop()`。

### 陷阱 2：用 `cfg.set_win_size` 代替截图真实分辨率算缩放

用户提供的截图可能是 720p、1080p、1440p 甚至手机拍屏（任意分辨率）：

```python
# ❌ 错误：cfg.set_win_size 是用户配置，不一定等于截图分辨率
scale = cfg.set_win_size / 1440

# ✅ 正确：以截图实际高度为准
scale = screenshot_np.shape[0] / 1440
```

### 陷阱 3：直接用 `cv2.matchTemplate` 代替 `ImageUtils.match_template`

`ImageUtils.match_template` 做了以下关键处理，不能跳过：

1. **截图/模板通道数兼容**——`cv2.COLOR_RGB2GRAY` 自动转换
2. **model 参数决定搜索区域**——
   - `clam`（默认）：bbox 上下左右各扩 30px 范围内搜索
   - `normal`：bbox 各扩 100px
   - `aggressive`：无 bbox 限制，全屏搜索
3. **坐标还原**——匹配结果中心点 = `bbox偏移 + 匹配位置 + 模板半宽高`

## 调用顺序示例

```python
from utils.image_utils import ImageUtils

# 假设 tpl_gray、bbox 已按上文完成缩放、灰度化和裁剪
center, max_val = ImageUtils.match_template(screen_np, tpl_gray, bbox, model="clam")

# 需要完整重放 find_element 时，应通过 Automation 调用链注入截图，
# 适用于需要完整重放 find_element 逻辑的场景
```

## 相关代码入口

- `utils/image_utils.py` → `ImageUtils.load_image()`, `ImageUtils.get_bbox()`, `ImageUtils.crop()`, `ImageUtils.match_template()`, `normalize_screenshot_for_1440_matching()`
- `module/automation/automation.py` → `Automation.find_element()`, `Automation.find_image_element()`, `_load_template_for_path()`
