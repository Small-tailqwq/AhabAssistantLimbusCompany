---
name: replay-matching
description: Use when the user provides screenshots and asks to replay template matching against AALC asset images — verifying log similarity values, diagnosing match failures, or comparing match results across resolutions/models.
license: AGPL-3.0
compatibility: opencode
metadata:
  audience: maintainers
  workflow: issue-diagnosis
---

# AALC 模板匹配重放

## 工具

`debug_tools/verify_matching.py` — CLI 模板匹配验证工具。

```powershell
uv run python debug_tools/verify_matching.py <screenshot>                          # 默认资产集
uv run python debug_tools/verify_matching.py <screenshot> --minimal                  # 精简资产集
uv run python debug_tools/verify_matching.py <screenshot> --assets KEY1 KEY2 ...     # 指定资产
uv run python debug_tools/verify_matching.py <screenshot> --models clam aggressive   # 指定模式
uv run python debug_tools/verify_matching.py <screenshot> --compare <screenshot2>    # A/B 对照
uv run python debug_tools/verify_matching.py <screenshot> --pixel X Y W H             # 像素分析
```

## 工作流

1. **确定截图分辨率** — 工具会自动打印 `分辨率: WxH scale=N`
2. **选择资产** — 根据日志中记录的资产 key 指定 `--assets`
3. **运行重放** — 推荐 `--models clam aggressive` 同时跑，对比搜索区域受限 vs 全屏的结果
4. **分析结果** — 关注 `***` (≥0.80) / `! ` (≥0.70) 标签

## 必读参考

重放时需要完整模拟 `find_element()` → `find_image_element()` → `ImageUtils.match_template()` 管道。
详细信息参阅 `.opencode/reference/replay_matching.md`：

- `_assets.png` 后缀模板必须做 bbox 裁剪，否则匹配值会被严重压低
- 用截图实际高度算缩放：`scale = screenshot_np.shape[0] / 1440`（不用 `cfg.set_win_size`）
- 必须使用 `ImageUtils.match_template()`，不能直接用 `cv2.matchTemplate()`

## 常见诊断模式

| 症状 | 排查方向 |
|---|---|
| clam < 0.80 但 aggressive ≥ 0.80 | bbox 搜索区域未覆盖目标，可能是缩放导致位置偏移 |
| aggressive < 0.80 | 模板本身不匹配，检查游戏版本/主题/语言 |
| clam 和 aggressive 位置不同 | clam 在 bbox 区域内找到次优误匹配 |
| 日志中的匹配值与重放不一致 | 运行时截图质量（PrintWindow vs 手动保存 PNG）差异 |

## 相关代码

- `utils/image_utils.py` → `ImageUtils.match_template()`, `get_bbox()`, `crop()`
- `module/automation/automation.py` → `find_element()`, `find_image_element()`, `_load_template_for_path()`
- `debug_tools/verify_matching.py` → 直接封装上述管道用于命令行重放
