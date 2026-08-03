---
name: replay-matching
description: 用仓库资源重放用户截图上的 AALC 模板匹配，核验日志记录的相似度值、比较分辨率或匹配模型、诊断 bbox 与裁剪失败，并复现生产 ImageUtils 管线。仅在证据含截图或模板匹配问题时使用。
---

# AALC 模板匹配重放

用 `debug_tools/verify_matching.py` 复现项目行为。保留源截图与资源；派生图片一律写入已忽略的 `logs/<feature>_debug/` 目录。

## 先读必读的管线 reference

解读重放值之前，先读 [references/pipeline.md](references/pipeline.md)。它定义缩放、`_assets.png` 的 bbox 裁剪、通道处理与模型相关搜索行为。

## 命令

```powershell
uv run python debug_tools/verify_matching.py <screenshot>
uv run python debug_tools/verify_matching.py <screenshot> --minimal
uv run python debug_tools/verify_matching.py <screenshot> --assets KEY1 KEY2
uv run python debug_tools/verify_matching.py <screenshot> --models clam aggressive
uv run python debug_tools/verify_matching.py <problem.png> --compare <normal.png> --minimal
uv run python debug_tools/verify_matching.py <screenshot> --pixel X Y W H
```

## 工作流

1. 已知时记录截图尺寸、语言、主题、采集来源与 issue 版本。
2. 从相关日志或代码路径选择精确的资源键。
3. 诊断搜索区域漂移时同时跑 `clam` 与 `aggressive`。
4. 与日志对比的是重放值、中心点与包围盒，而不只是阈值通过/失败。
5. 值不一致时依次检查采集质量、缩放、模板版本、覆盖层、裁剪与运行/源版本不匹配。
6. 结论必须关联生产调用链与事件发生的源版本。

## 解读

| 模式 | 调查方向 |
|---|---|
| `clam < threshold`、`aggressive >= threshold` | bbox 搜索区域或缩放后位置漂移 |
| 两者都低于阈值 | 模板、UI 版本、语言、主题、覆盖层或采集质量不匹配 |
| 模型返回不同中心点 | 受限搜索找到了不同的局部最大值 |
| 重放与日志不一致 | 运行截图来源、压缩、缩放或版本不匹配 |

这些只是起点假设。声称根因前先检查实际图片与管线。

## 输出

报告截图、资源键、缩放、模型、阈值、返回值/中心点、生产路径，以及与运行证据之间未解决的差异。绝不用裸 OpenCV 匹配结果替代项目结果。
