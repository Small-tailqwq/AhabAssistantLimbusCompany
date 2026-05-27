# Match Viewer — 图片匹配诊断工具

## 目的

离线分析 AALC 模板匹配失败原因。用户上传游戏截图，选择业务资产模板，使用生产匹配流水线进行匹配，结果可视化叠加在截图上。

## 架构

```
.opencode/tools/match_viewer.py     # Python 服务器 + API + 匹配引擎
.opencode/tools/match_viewer/
  └── index.html                    # 纯静态前端（单文件，无构建依赖）
```

三栏布局：
- **左栏**：资产浏览器 — 主题/语言选择、分类树、搜索、资产网格（勾选 + 可见性开关）
- **右栏**：截图查看器 — Canvas 叠加层、阈值滑块、模型切换、低分辨率开关
- **底栏**：状态信息

## API

### `GET /api/categories?theme=default&lang=en`

返回 share/ + 语言目录下所有 `*assets.png` 资产列表，按分类分组，包含预计算 bbox 和尺寸（已缩放到 win_size）。

### `POST /api/match`

请求：screenshot (base64 PNG)、assets 列表、low_res_mode、models 列表
响应：每个资产 × 每个模型的 center、matchVal、search_bbox、template_size

### `GET /api/asset-image?key=X&path=Y&bbox=1`

返回裁剪后的资产 PNG 用于前端缩略图显示。

## 匹配流水线

直接复用 `ImageUtils._prepare_loaded_image` → `get_bbox` → `crop` → `match_template`，绕过 `automation.py` 的截图/输入层。

对每个资产：
1. 加载各路径变体的模板
2. 缩放到截图分辨率（或截图上采样到 1440p）
3. 获取 bbox 并裁剪
4. 分别在 clam/normal/aggressive 三种搜索范围和全图上执行 template matching
5. 返回 center + matchVal

## 前端交互

| 功能 | 行为 |
|------|------|
| 截图上传 | 文件选择器、拖放、Ctrl+V 粘贴 |
| 资产选择 | 复选框（是否参与匹配），眼睛图标（是否在 Canvas 显示矩形） |
| 阈值滑块 | 实时改变矩形颜色（≥绿 / <红），纯前端过滤 |
| 模型切换 | radio 按钮 clam/normal/aggressive，切换矩形数据源 |
| 低分辨率模式 | 开关，需重新运行匹配 |
| Canvas | 滚轮缩放、拖拽平移、矩形框 + 资产名 + 置信度标签 |
