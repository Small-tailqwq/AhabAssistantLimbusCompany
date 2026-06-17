# 主线 mini 镜牢节点识别优化设计

## 背景

主线关卡自动战斗测试使用的 mini 镜牢地图无法复用常规镜牢寻路。当前 `tasks/main_story/main_story.py` 使用基于巴士位置的网格盲点击，效率低且不稳定。`debug_tools/extract_main_story_nodes.py` 作为分析脚本，依赖白线端点聚类 + 暗紫色连通区域，会产生大量误检（白线箭头、图标内部色块等）。

## 目标

1. 用图像识别替换 `MainStory._navigate_main_story` 的网格盲点击，提升寻路准确性。
2. 识别失败时 fallback 到现有网格点击。
3. 只需输出节点平台中心坐标，优先点击最右侧节点。

## 方案

采用"颜色+形态过滤"方案（方案 A）。

### 识别流程

1. **颜色掩码**：在 ROI 区域内同时提取暗紫色平台（H/S/V 范围覆盖普通/问号/战斗节点）和深红色 Boss 平台。
2. **形态学处理**：闭运算连接平台碎片，开运算去除细小噪声。
3. **连通区域过滤**：
   - 面积阈值（排除碎片和过大背景）。
   - 最小外接矩形长宽比（接近 1:1，排除长条白线/连线）。
   - 填充率（排除稀疏线段）。
4. **去重合并**：距离过近（< 80px）的候选合并为一点。
5. **排序**：按 x 坐标降序，优先点击最右侧节点。

### 集成点

- 新增 `tasks/main_story/main_story_navigation.py`，封装节点识别函数 `detect_main_story_nodes(screenshot)`。
- `tasks/main_story/main_story.py` 的 `_navigate_main_story` 改为：先识别节点 → 依次点击最右侧节点 → 用 `enter_assets` 反馈验证；识别为空或全部失败时 fallback 到网格点击。
- 更新 `debug_tools/extract_main_story_nodes.py` 复用新的识别函数，并输出叠加预览图。

### 验证

- 对两张原始截图跑识别，输出叠加预览图，确认无漏检、无显著误检。
- 运行 `uv run ruff check .` 和 `uv run python -m py_compile` 保证语法与 lint 通过。
