---
name: replay-matching
description: 用 AAALC 的 .NET 生产视觉管线重放截图、模板匹配和录制，核对资源键、区域、相似度及动作。
---

# AAALC 截图与匹配重放

先确认截图对应的源版本、分辨率、语言、主题与采集来源。保留原图，派生结果遵循数据根和用户授权。

## .NET 管线

读取 [视觉接口](../../../docs/vision.md)；涉及测试集或真实录制时再读 [截图回归](../../../docs/screenshot-regression.md)。

实现入口为 `src/AALC.Vision/TemplateMatcher.cs`、`GameObserver.cs` 与 `MirrorScenarioVision.cs`。匹配值必须来自相应生产路径，不能用裸 OpenCV 匹配替代。

在仓库根目录运行：

```powershell
dotnet run --project src/AALC.Cli -c Release -- match <截图> <资源键> . zh_cn default
dotnet run --project src/AALC.Cli -c Release -- screenshot-test --filter <用例ID片段>
dotnet run --project src/AALC.Cli -c Release -- mirror-replay --run <录制目录> --vision . --models assets/models/ocr
```

截图测试集定义位于 `tests/screenshots/`，图像位于外部数据目录。缺少本地证据时报告缺口，不将缺图当作通过。

## 工作流

1. 从日志或调用点选择资源键、区域、阈值与帧。
2. 核对缩放、bbox 裁剪、主题/语言及 OCR 输入区域。
3. 比较返回值、中心点和包围盒，不只比较是否超过阈值。
4. 值不一致时依次核对模板版本、采集质量、覆盖层、裁剪与源版本。
5. 结论关联生产调用链；只有日志回放时说明未重新运行视觉识别。

不带 `--vision` 的录制回放验证日志编排；合成 `scenarios/` 验证人工观察下的动作契约，两者与实机识别分开报告。

## 输出

说明截图、资源键、区域、模型、阈值、返回值/中心点、生产版本与未解释的差异。