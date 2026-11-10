# 视觉接口

`AALC.Vision` 使用 OpenCvSharp 和 ONNX Runtime，提供单目标／多目标模板检测、全帧／ROI 页面 OCR 和单条文字裁剪识别。离线命令读取文件，不连接游戏或发送输入。

```powershell
dotnet build src/AALC.Cli/AALC.Cli.csproj
dotnet src/AALC.Cli/bin/Debug/net10.0-windows/AAALC.Cli.dll match <截图> <资源键> [仓库目录] [zh_cn|en] [default|dark]
dotnet src/AALC.Cli/bin/Debug/net10.0-windows/AAALC.Cli.dll read-text <截图> <模型目录> [x y width height scale]
dotnet src/AALC.Cli/bin/Debug/net10.0-windows/AAALC.Cli.dll recognize <文字裁剪> <PP-OCRv4_rec.onnx> <字典.txt>
```

`match` 每行输出一种搜索模式的 JSON，包括资源键、实际相对路径、分数、中心点和裁剪前 bbox。截图高度决定模板缩放；缩小时使用 AREA，放大时使用 LINEAR。截图与模板的灰度转换由 [TemplateMatcher](../src/AALC.Vision/TemplateMatcher.cs) 统一实现。`assets.png` 后缀资源先按非零灰度 bbox 裁剪。`Clam` 与 `Normal` 在 bbox 周围分别保留至少 30、100 像素的搜索边距，随截图高度缩放；`Aggressive` 搜索整帧。

资源解析按指定语言和主题查找候选，优先 WebP，再读取 PNG。`Match` 返回候选中的最高分供诊断；邮件观察器使用 0.8 阈值。

`TemplateMatcher.Find` 接收 `ImageQuery`，返回超过阈值的 `VisualTarget`。`Multiple=true` 时在整张截图上检测多个目标，以中心距离十像素抑制重复结果。经验入口的多候选阈值为 0.8，页面识别另要求至少一个候选达到 0.85；通过页面判断后，入口按中心 X 降序尝试，优先最右侧。实帧中约 0.834 的右侧入口仍属于可选候选。两个阈值分别承担页面识别与入口枚举的职责。

## 页面 OCR 与加载时机

```csharp
using var reader = new PageTextReader(modelsDirectory);
IReadOnlyList<RecognizedText> text = reader.Read(pixelFrame, region, scale, cancellationToken);
```

`region=null` 识别全帧；指定 `PixelRect` 时只处理该 ROI，`scale` 控制裁剪放大倍数。输出包含文字、置信度和全帧坐标框，已还原 ROI 偏移与缩放。`GameObserver` 按当前帧、ROI 和倍数缓存 OCR 结果，新帧清空缓存，同时保留 BGRA 帧供颜色判定。

页面识别在 C# 内执行灰度／CLAHE、PP-OCRv4 DB 文本检测、框扩张、透视裁剪和 CTC 识别。检测框使用最小矩形按面积／周长距离扩张，检测概率阈值为严格 `>0.3f`，继续执行 2×2 膨胀。竖长检测框旋转 90°。ONNX 推理通过 `RunOptions.Terminate` 响应取消。

短单行使用原 ROI 高度 `<=30` 或宽高比 `>8` 判断，绕过 DB，缩放后左右各补四像素黑边再直接识别，输出框覆盖原 ROI。这样靠近左右边缘的字符也保留输入边距。其余 ROI 保留 DB 检测与逐框识别。

长边 1600 是检测前输入的尺寸上限，超过时按比例缩小并对齐 32，文字框再按实际宽高比例还原到原帧。它不是 DB 网络长边上限：检测器仍按最短边 736 放大，窄竖列可以产生更长的网络输入。例如实帧整队伍列表 ROI 为 190×584，对应约 736×2272；150×600 则对应 736×2944。

`PageTextReader` 构造时只保存目录，首次 `Read` 加载识别模型，首次进入 DB 路径时才加载检测模型。应用首屏不加载 OCR 模型。当前复用 PP-OCRv4 模型是资产选择，模型目录由调用方指定，支持独立部署；运行时不调用 Python。目录包含 `ch_PP-OCRv4_det_infer.onnx`、`ch_PP-OCRv4_rec_infer.onnx` 和 `ppocr_keys_v1.txt`。

`recognize` 对一条水平文字裁剪执行实际识别，输出文字、置信度、输入张量尺寸和每个时间步的 CTC token/概率。输入为 BGR 图片；内部执行灰度和 CLAHE，二值图跳过 CLAHE，再转三通道，按 RapidOCR 的 `[3,48,320]` 基准等比缩放和右侧零填充。宽文字增加输入宽度。字符表优先读取 ONNX `character` metadata，否则读取指定 UTF-8 字典；CTC 删除 blank 和相邻重复 token，置信度按 RapidOCR 的五位舍入规则计算。

当前页面 OCR 的验证范围为正向游戏文字，不执行 180° 角度分类、批量宽度分组或单字框生成。模型和字典由调用方指定；默认文件位置和准备方式见 [模型说明](../assets/models/ocr/README.md)。

## 验证入口

模板、页面 OCR 与图谱使用 [截图回归](screenshot-regression.md) 中的真实图像用例。离线命令输出资源路径、位置、置信度与识别文字；具体游戏流程还需核对动作和后继帧。
