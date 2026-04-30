# 图像匹配与 OCR 性能优化设计文档

> 日期：2026-04-29
> 方案：A - 渐进式优化（5 个独立步骤）
> 预期收益：镜牢运行时间从 ~150s 降至 ~50-80s（提升 ~50-60%）

---

## 目录

1. [现状分析](#1-现状分析)
2. [优化 1：ONNX Session 持久化](#2-优化-1onnx-session-持久化)
3. [优化 2：截图感知哈希去重](#3-优化-2截图感知哈希去重)
4. [优化 3：帧内匹配结果缓存](#4-优化-3帧内匹配结果缓存)
5. [优化 4：多线程并行匹配](#5-优化-4多线程并行匹配)
6. [优化 5：OCR 系统优化](#6-优化-5ocr-系统优化)
7. [收益预估汇总](#7-收益预估汇总)
8. [实施顺序与依赖](#8-实施顺序与依赖)

---

## 1. 现状分析

### 1.1 图像匹配流水线

```
截图 → PIL → numpy → 预处理（灰度/1440归一化）→ matchTemplate / ORB / OCR → 结果
```

- 核心方法：`cv2.TM_CCOEFF_NORMED`，阈值 0.8
- 三种搜索模式：`clam`（收缩30px）、`normal`（扩展100px）、`aggressive`（全屏）
- 模板缓存：`Automation.img_cache`，仅缓存加载后的像素，不缓存匹配结果

### 1.2 OCR 子系统

- 引擎：RapidOCR（PaddleOCR 移动版 v4，ONNX）
- 每次调用：RGB→BGR→灰度（冗余2步）→ CLAHE → 推理
- 每次运行 ~350-400 次调用，总计 ~40-50 秒
- 无结果缓存，全同步阻塞

### 1.3 关键瓶颈

| 瓶颈 | 来源 | 每次运行损耗 |
|------|------|------------|
| 试探性 `find_element()` 瀑布（20-30次/帧，多数返回None） | 镜牢主循环 | ~70% 匹配时间 |
| 无截图去重（UI停滞时重复处理） | `ScreenShot` | ~30% 截图开销 |
| ONNX Session 每次重建 | `search_road.py` | ~1-1.5s |
| OCR 无缓存 | `OCR.run()` | ~30s |
| 楼层识别最多20次OCR | `get_which_floor()` | ~10s |
| 全屏事件OCR | `event_handling.py:46` | ~500ms/次 |
| RGB→BGR→灰度冗余转换 | `ocr.py:50-51` | ~1-3ms/次 |
| 对二值图仍跑CLAHE | `ocr.py:61-62` | ~5-10ms/次 |

---

## 2. 优化 1：ONNX Session 持久化

### 2.1 目标

消除 `identify_nodes()` 每次重新创建 `onnxruntime.InferenceSession` 的 200-500ms 开销。

### 2.2 现状

**文件**：`tasks/mirror/search_road.py`

```python
# 当前代码（每次调用都新建 session）
def identify_nodes(screenshot):
    session = onnxruntime.InferenceSession(model_path)
    # ... 推理 ...
```

镜牢每层调用 1-3 次 `identify_nodes()`，总计 ~10-30 次/运行。

### 2.3 改动方案

模块级惰性单例缓存：

```python
# tasks/mirror/search_road.py

_onnx_session: onnxruntime.InferenceSession | None = None
_onnx_model_path: str = ""

def _get_onnx_session(model_path: str) -> onnxruntime.InferenceSession:
    """惰性加载并缓存 ONNX 推理会话"""
    global _onnx_session, _onnx_model_path
    if _onnx_session is None or _onnx_model_path != model_path:
        _onnx_session = onnxruntime.InferenceSession(model_path)
        _onnx_model_path = model_path
    return _onnx_session

def identify_nodes(screenshot):
    session = _get_onnx_session(model_path)
    # ... 推理逻辑不变 ...
```

### 2.4 线程安全

ONNX Runtime 的 `InferenceSession.run()` 是线程安全的只读操作，无需加锁。

### 2.5 验证方式

- 在 `identify_nodes()` 入口打印 `id(session)`，确认后续调用复用同一对象
- 对比优化前后的寻路耗时日志

### 2.6 风险与回滚

- 风险：无
- 回滚：删除缓存函数，恢复直接创建

---

## 3. 优化 2：截图感知哈希去重

### 3.1 目标

UI 未变化时跳过重复截图 + 后续所有匹配/OCR 操作。

### 3.2 现状

**文件**：`module/automation/screenshot.py`

`ScreenShot.take_screenshot()` 每次执行完整流程：抓取 → PIL 解码 → numpy → 赋值 `self.screenshot`。`screenshot_interval`（0.85s）仅限制频率，不检测内容变化。

镜牢中 UI 停滞（等动画/加载/战斗结算）约占总时间 30-40%，这些帧内容完全相同。

### 3.3 改动方案

#### 3.3.1 dHash 计算

在 `ScreenShot` 类中添加轻量级感知哈希：

```python
class ScreenShot:
    _last_hash: bytes | None = None
    frame_duplicate: bool = False
    _frame_count: int = 0  # 每次截图自增，用作 frame_id

    def _compute_dhash(self, gray_array: np.ndarray) -> bytes:
        """计算 64-bit 感知哈希（8字节比较）"""
        small = cv2.resize(gray_array, (9, 8), interpolation=cv2.INTER_AREA)
        diff = small[:, 1:] > small[:, :-1]
        return diff.tobytes()

    def take_screenshot(self, gray=False, ...):
        """原有截图逻辑 + 哈希去重"""
        # ... 原有截图代码 ...
        screenshot_array = np.array(self.screenshot)

        # 哈希去重
        gray_for_hash = cv2.cvtColor(screenshot_array, cv2.COLOR_RGB2GRAY)
        current_hash = self._compute_dhash(gray_for_hash)
        self._frame_count += 1

        if current_hash == self._last_hash:
            self.frame_duplicate = True
        else:
            self.frame_duplicate = False
            self._last_hash = current_hash
            self.screenshot_array = screenshot_array  # 只在内容变化时更新

        return self.screenshot_array
```

#### 3.3.2 调用者适配

在 `Automation.find_element()` 入口添加快速返回：

```python
def find_element(self, target, ...):
    # 截图去重快速返回
    if screen.frame_duplicate and not kwargs.get('take_screenshot', False):
        return None
    # ... 原有逻辑 ...
```

### 3.4 dHash 参数选择

| 方案 | 精度 | 速度 | 选择 |
|------|------|------|------|
| aHash（平均值） | 低 | 极快 | 不采用 |
| **dHash（差值）** | **高** | **极快** | **采用** |
| pHash（DCT） | 最高 | 慢 | 不采用（过度） |

dHash 在 9x8 缩略图上运行，计算量忽略不计（<0.1ms），对游戏 UI 的检测精度足够。

### 3.5 边界条件

- 第一帧：`_last_hash = None` → `frame_duplicate = False` ✓
- `take_screenshot=True` 参数：强制重新截图，不受去重影响 ✓
- 需要读取最新像素的场景（绘图/调试）：通过 `force=True` 参数绕过 ✓

### 3.6 验证方式

- 在主循环打印 `frame_duplicate` 统计，确认去重率 ~30-40%
- 对比优化前后匹配/OCR 调用次数

### 3.7 风险与回滚

- 风险：极低（dHash 只读，不修改状态）
- 回滚：删除 `_compute_dhash` 相关代码，`frame_duplicate` 始终为 `False`

---

## 4. 优化 3：帧内匹配结果缓存

### 4.1 目标

同一帧上多次相同参数的 `find_element()` / `find_text_element()` 调用直接复用上次结果。

### 4.2 现状

`Automation.img_cache` 只缓存模板像素（加载后），不缓存匹配结果。同一帧上 `find_element("按钮A")` 被不同路径调用 2-3 次时，每次都重新执行 `matchTemplate`。

### 4.3 改动方案

#### 4.3.1 缓存数据结构

```python
class Automation:
    _match_result_cache: dict[tuple, Any] = {}
    _cache_frame_id: int = -1  # 缓存对应的帧号

    def _get_match_cache_key(self, target, find_type, bbox, threshold, **kwargs) -> tuple:
        """生成缓存键"""
        return (self._cache_frame_id, target, find_type,
                bbox, threshold, kwargs.get('model', 'normal'))

    def _invalidate_match_cache_if_needed(self):
        """帧变化时清空缓存"""
        current_id = screen._frame_count
        if current_id != self._cache_frame_id:
            self._match_result_cache.clear()
            self._cache_frame_id = current_id
```

#### 4.3.2 find_element 缓存集成

```python
def find_element(self, target, find_type="image", ...):
    # 帧重复快速返回（优化2）
    if screen.frame_duplicate and not take_screenshot:
        return None

    self._invalidate_match_cache_if_needed()

    # 缓存查询（优化3）
    cache_key = self._get_match_cache_key(target, find_type, bbox, threshold, model=model)
    if cache_key in self._match_result_cache:
        return self._match_result_cache[cache_key]

    # ... 原有匹配逻辑 ...
    result = self._do_match(...)

    self._match_result_cache[cache_key] = result
    return result
```

#### 4.3.3 OCR 缓存集成

`find_text_element()` 同样纳入此缓存，key 中加入 `only_text`、`my_crop` 等参数。

### 4.4 缓存键设计

```
(frame_id, target, find_type, bbox, threshold, model)
```

- `frame_id`：帧变化时自动失效
- `target`：匹配目标标识
- `find_type`：image / feature / text / image_with_multiple_targets
- `bbox`：搜索区域（tuple 或 None）
- `threshold`：匹配阈值
- `model`：搜索模式（clam / normal / aggressive）

### 4.5 验证方式

- 在缓存命中时打印日志，统计命中率
- 对比优化前后 `matchTemplate` 调用次数

### 4.6 风险与回滚

- 风险：低。纯读写字典
- 回滚：删除缓存相关代码，恢复直接匹配

---

## 5. 优化 4：多线程并行匹配

### 5.1 目标

同一帧上的多个独立 `find_element()` 调用并行执行，将串行 ~400ms 降至 ~100-150ms。

### 5.2 现状

镜牢主循环串行调用 20+ 个 `find_element()` 检查各种状态（战斗/商店/事件/寻路等），每个 ~10-30ms。这些调用之间无数据依赖。

### 5.3 改动方案

#### 5.3.1 批量并行接口

在 `Automation` 中新增：

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

class Automation:
    _match_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="match")
    _cache_lock = threading.Lock()

    def find_elements_batch(self, queries: list[dict]) -> list:
        """批量并行 find_element

        Args:
            queries: [{"target": "btn_a", "find_type": "image", ...}, ...]

        Returns:
            与 queries 一一对应的结果列表
        """
        futures = []
        for q in queries:
            futures.append(self._match_pool.submit(self.find_element, **q))

        results = []
        for f in futures:
            try:
                results.append(f.result(timeout=5))
            except Exception:
                results.append(None)
        return results
```

#### 5.3.2 缓存锁

帧内匹配缓存（优化3）的读写需加锁：

```python
def find_element(self, target, ...):
    # ...
    with self._cache_lock:
        if cache_key in self._match_result_cache:
            return self._match_result_cache[cache_key]

    result = self._do_match(...)

    with self._cache_lock:
        self._match_result_cache[cache_key] = result
    return result
```

#### 5.3.3 调用者迁移策略

**逐步迁移**，不一次性改动所有调用点：

1. **Phase 1**：新增 `find_elements_batch()` 接口，不改动任何现有代码
2. **Phase 2**：迁移镜牢主循环中的状态判断（最热路径）
3. **Phase 3**：迁移商店扫描、战斗检测等其他热路径

```python
# 镜牢主循环迁移示例（Phase 2）
# 改动前：
result_battle = auto.find_element("battle_btn", ...)
result_shop = auto.find_element("shop_btn", ...)
result_event = auto.find_element("event_btn", ...)

# 改动后：
results = auto.find_elements_batch([
    {"target": "battle_btn", "find_type": "image", ...},
    {"target": "shop_btn", "find_type": "image", ...},
    {"target": "event_btn", "find_type": "image", ...},
])
result_battle, result_shop, result_event = results
```

### 5.4 线程安全分析

| 资源 | 访问模式 | 安全性 |
|------|---------|--------|
| `cv2.matchTemplate` | GIL-releasing C 函数 | ✅ 真正并行 |
| `self.screenshot` | 只读引用 | ✅ 无需锁 |
| `img_cache` | 读多写少 | ✅ 加锁保护 |
| `_match_result_cache` | 读多写少 | ✅ 加锁保护 |
| `screen.take_screenshot()` | 不在并行路径中 | ✅ 无冲突 |

### 5.5 线程池配置

- `max_workers=4`：平衡 CPU 利用率与线程开销
- `thread_name_prefix="match"`：便于调试
- 池生命周期：跟随 `Automation` 单例，进程退出时自动清理

### 5.6 验证方式

- 对比串行/并行的总匹配耗时
- 在高负载下验证无死锁/竞态

### 5.7 风险与回滚

- 风险：中等。需验证 OpenCV 多线程稳定性
- 回滚：删除 `find_elements_batch()`，恢复串行调用

---

## 6. 优化 5：OCR 系统优化

### 6.1 OCR 结果缓存

复用优化 3 的 `_match_result_cache` 机制。

```python
def find_text_element(self, target, ...):
    # 缓存查询
    cache_key = (screen._frame_count, "text", target, str(my_crop), only_text)
    if cache_key in self._match_result_cache:
        return self._match_result_cache[cache_key]

    # ... 原有 OCR 逻辑 ...
    result = ...

    self._match_result_cache[cache_key] = result
    return result
```

预估收益：消除 ~60-70% 重复 OCR 调用，省 ~20-30 秒/运行。

### 6.2 楼层识别优化

**文件**：`tasks/mirror/mirror.py`，`get_which_floor()` 函数

**现状**：最多 5 轮迭代 × 4 种图像变体 = 20 次 OCR

**改动**：

```python
def get_which_floor(self):
    # 第 1 轮：原始裁剪 → OCR
    result = handle_ocr(current_crop, "current")
    if result: return result

    # 第 2 轮：放大 + 灰度 → OCR
    result = handle_ocr(current_scaled, "current_scaled")
    if result: return result

    # 第 3 轮：差值图 → OCR（跳过已失败的变体）
    result = handle_ocr(diff_gray, "diff_gray")
    if result: return result

    # 第 4 轮：二值图 → OCR
    result = handle_ocr(binary_img, "binary")
    if result: return result

    # 最多重试 2 次新截图（而非 5 次）
    for retry in range(2):
        auto.take_screenshot(gray=False)
        # ... 仅用最有效的 2 个变体 ...
```

从最多 20 次 OCR 降至最多 8 次。

### 6.3 全屏 OCR 替换

**文件**：`tasks/event/event_handling.py:46`

**现状**：
```python
ocr_data = auto.find_text_element("", only_text=True)  # 全屏 OCR，~500ms
```

**改动**：
```python
# 使用事件面板的已知区域裁剪
event_crop = ImageUtils.crop(screenshot, EVENT_PANEL_BBOX)
ocr_data = auto.find_text_element("", only_text=True, my_crop=event_crop)
```

从 ~500ms 降至 ~80ms。

### 6.4 预处理优化

**文件**：`module/ocr/ocr.py`

#### 6.4.1 消除冗余颜色转换

```python
# 改动前（2步）
img_cv = cv2.cvtColor(image_array, cv2.COLOR_RGB2BGR)
img_cv_gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)

# 改动后（1步）
img_cv_gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
```

每次调用省 ~1-3ms。

#### 6.4.2 CLAHE 条件跳过

```python
def run(self, image, ...):
    # ... 灰度转换 ...

    # 检测是否为二值图像
    is_binary = np.array_equal(np.unique(img_cv_gray), [0, 255]) or \
                (np.unique(img_cv_gray).size <= 2)

    if is_binary:
        processed_image = img_cv_gray  # 二值图跳过 CLAHE
    else:
        clahe = createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        processed_image = clahe.apply(img_cv_gray)
```

二值图调用省 ~5-10ms。

### 6.5 OCR 停止检查

**文件**：`module/ocr/ocr.py`

在 OCR 推理批次之间注入停止检查：

```python
def run(self, image, ...):
    # ... 预处理 ...

    for i, batch in enumerate(batches):
        auto.ensure_not_stopped()  # 每批次检查一次
        result = self.engine(batch)
```

避免长时间（最多 10 秒）无响应。

### 6.6 验证方式

- 统计优化前后 OCR 调用次数和总耗时
- 验证楼层识别准确率不下降
- 验证事件处理正确性

### 6.7 风险与回滚

- 风险：低。各子优化独立可回滚
- 特别注意：CLAHE 跳过需验证不影响文字识别准确率

---

## 7. 收益预估汇总

| # | 优化项 | 每次运行节省 | 实施难度 | 风险 |
|---|--------|------------|---------|------|
| 1 | ONNX Session 持久化 | ~1-1.5s | ⭐ | 🟢 |
| 2 | 截图哈希去重 | ~15-25s | ⭐⭐ | 🟢 |
| 3 | 帧内匹配缓存 | ~5-10s | ⭐⭐ | 🟢 |
| 4 | 多线程并行匹配 | ~10-20s | ⭐⭐⭐ | 🟡 |
| 5a | OCR 结果缓存 | ~20-30s | ⭐⭐ | 🟢 |
| 5b | 楼层识别优化 | ~10s | ⭐⭐ | 🟢 |
| 5c | 全屏 OCR 替换 | ~5s | ⭐ | 🟢 |
| 5d | 预处理优化 | ~2-3s | ⭐ | 🟢 |
| 5e | OCR 停止检查 | 0（体验改善） | ⭐ | 🟢 |
| | **总计** | **~70-105s** | | |

**预期效果**：镜牢运行从 ~150s 降至 ~50-80s。

---

## 8. 实施顺序与依赖

```
依赖图：

    ┌─────────────────┐
    │ 1. ONNX Session │ ← 无依赖，最先实施
    │    持久化        │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │ 2. 截图哈希去重  │ ← 无依赖，可与 1 并行
    └────────┬────────┘
             │ 依赖 frame_duplicate 标志
    ┌────────▼────────┐
    │ 3. 帧内匹配缓存 │ ← 依赖 2 的 frame_id
    └────────┬────────┘
             │ 依赖缓存机制
    ┌────────▼────────┐
    │ 5a. OCR 结果缓存│ ← 复用 3 的缓存框架
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │ 4. 多线程并行   │ ← 依赖 3 的缓存锁
    └─────────────────┘

    独立优化（可随时并行实施）：
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │ 5b. 楼层识别 │ │ 5c. 全屏OCR │ │ 5d. 预处理  │ │ 5e. 停止检查│
    └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
```

**推荐实施顺序**：

1. **Step 1**：1 + 5d + 5e（简单独立，快速见效）
2. **Step 2**：2 + 5c（截图去重 + 全屏OCR替换）
3. **Step 3**：3 + 5a + 5b（缓存体系 + OCR缓存 + 楼层优化）
4. **Step 4**：4（多线程并行，最后实施因为依赖最多）

每步完成后应进行手动验证，确认无回归后再进入下一步。

---

## 附录：关键文件索引

| 文件 | 涉及优化 |
|------|---------|
| `module/automation/screenshot.py` | 2 |
| `module/automation/automation.py` | 2, 3, 4, 5a |
| `module/ocr/ocr.py` | 5d, 5e |
| `tasks/mirror/search_road.py` | 1 |
| `tasks/mirror/mirror.py` | 5b |
| `tasks/event/event_handling.py` | 5c |
| `utils/image_utils.py` | 3 |
