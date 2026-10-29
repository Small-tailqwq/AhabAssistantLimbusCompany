# 视觉接口与离线对照

`AALC.Vision` 使用 OpenCvSharp 4.11.0 和 ONNX Runtime 1.20.1，提供单目标／多目标模板检测、全帧／ROI 页面 OCR 和单条文字裁剪识别。离线命令读取文件，不连接游戏或发送输入。

```powershell
dotnet build dotnet/src/AALC.Cli/AALC.Cli.csproj
dotnet dotnet/src/AALC.Cli/bin/Debug/net10.0-windows/AAALC.Cli.dll match <截图> <资源键> [仓库目录] [zh_cn|en] [default|dark]
dotnet dotnet/src/AALC.Cli/bin/Debug/net10.0-windows/AAALC.Cli.dll read-text <截图> <模型目录> [x y width height scale]
dotnet dotnet/src/AALC.Cli/bin/Debug/net10.0-windows/AAALC.Cli.dll recognize <文字裁剪> <PP-OCRv4_rec.onnx> <字典.txt>
uv run python debug_tools/dotnet_vision_reference.py
```

`match` 每行输出一种搜索模式的 JSON，包括资源键、实际相对路径、分数、中心点和裁剪前 bbox。截图高度决定模板缩放；缩小时使用 AREA，放大时使用 LINEAR。截图灰度采用 Python 默认截图路径的 Pillow `convert("L")` 整数系数，模板采用生产加载器的 OpenCV RGB 灰度等价处理。`assets.png` 后缀资源先按非零灰度 bbox 裁剪。`Clam`、`Normal`、`Aggressive` 使用生产 `ImageUtils.match_template` 的搜索范围。

资源解析采用已知语言和主题的 `existing_image_paths` 规则，优先 WebP，再读取 PNG。`Match` 返回候选中的最高分供诊断；邮件观察器使用 0.8 阈值。Python 自动化在语言和主题已知时可以提前返回首个达标候选；未知语言/主题的状态推断和路径淘汰尚未迁移。

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

本机 RapidOCR 的 `preprocess_img` 先做尺寸预处理，`_add_letterbox` 对符合条件的图补上下边后继续 DB；它没有自动将短行切换为识别模型的分支。当前 C# 的短行直识别是独立的单行处理策略，30／8 阈值与输入长边 1600 取自仓库 OCR 参数。

`PageTextReader` 构造时只保存目录，首次 `Read` 加载识别模型，首次进入 DB 路径时才加载检测模型。应用首屏不加载 OCR 模型。当前复用 PP-OCRv4 模型是资产选择，模型目录由调用方指定，支持独立部署；运行时不调用 Python。目录包含 `ch_PP-OCRv4_det_infer.onnx`、`ch_PP-OCRv4_rec_infer.onnx` 和 `ppocr_keys_v1.txt`。

`recognize` 对一条水平文字裁剪执行实际识别，输出文字、置信度、输入张量尺寸和每个时间步的 CTC token/概率。输入为 BGR 图片；内部复现 `OCR.run` 的灰度和 CLAHE，二值图跳过 CLAHE，再转三通道，按 RapidOCR 的 `[3,48,320]` 基准等比缩放和右侧零填充。宽文字增加输入宽度。字符表优先读取 ONNX `character` metadata，否则读取指定 UTF-8 字典；CTC 删除 blank 和相邻重复 token，置信度按 RapidOCR 的五位舍入规则计算。

当前页面 OCR 的验证范围为正向游戏文字，不执行 180° 角度分类、批量宽度分组或单字框生成。模型和字典由调用方指定；仓库不复制模型。

## 页面 OCR 对照与性能

使用 `logs/daily_validation_debug/` 中的日常未领取、已领取、周常未领取和主页通行证入口四张真实截图，对照生产 Python `OCR.run`：17 个检测框坐标完全相同，16/17 条文本相同。唯一文字差异来自横幅七像素高的小字；进度文本、`CLEAR` 出口和主要 `SEASON` 入口判断一致。十条进度行的橙色比例及领取判定全部一致。逐框报告为 `logs/dotnet_daily_debug/ocr-native-20261025/comparison-21b2ad7e/comparison.json`。

性能样本取自 `logs/dotnet_daily_debug/desktop-20261025-144332/profile/runs/20261025-144817-744/` 的第 1、3、21 帧，分别输出 25、30、84 条文字。每组运行三轮，排除第一轮后的六次墙钟时间中位数如下：

| 阶段 | 连续缓冲区优化前 | 优化后 |
|---|---:|---:|
| 检测预处理 | 133.6 ms | 6.9 ms |
| 检测 ONNX 推理 | 82.6 ms | 83.4 ms |
| 检测后处理 | 98.3 ms | 3.7 ms |
| 识别预处理总计 | 34.5 ms | 38.0 ms |
| 识别 ONNX 推理总计 | 276.7 ms | 258.4 ms |
| CTC 解码总计 | 1256.0 ms | 6.4 ms |
| 全页 OCR | 1895.4 ms | 410.1 ms |

CTC 直接索引连续浮点缓冲区，检测输入直接写入 NCHW Span，输出概率整块复制到浮点 Mat。三张实帧的三轮输出共九次，文字、置信度和坐标框逐值完全一致；另五个文字裁剪的文本、token、概率、置信度和尺寸也逐值一致。默认 ORT 线程实测快于限制为 1、2、4 线程，因此使用默认设置。

性能汇总为 `logs/dotnet_daily_debug/ocr-perf-final-20261025/summary.json`，等价性记录为同目录 `output-equality.json`；原始分段计时在该目录与 `logs/dotnet_daily_debug/ocr-perf-20261025/`。测量使用离线临时源码探针，系统缓存和后台负载未受控，数值描述该组截图上的耗时。

## 小 ROI 检查

生产 `read-text` 命令对真实截图重复运行三次，耗时包含新进程启动和模型加载：

| ROI | 结果 | 进程耗时中位数 |
|---|---|---:|
| 选中队伍 `(87,336,87,27)` | 直识别前后均为“编队#2”，置信度 0.95278／0.90503 | 644.90／312.02 ms |
| 更贴近字边缘的 `(95,336,64,27)` | “编队#2”，0.97195 | 334.10 ms |
| 整列表 `(0,0,190,584)` | 包含“编队#1/#2/#3/#6”的十条文字 | 722.57 ms |
| 第三档购买后价格 `(565,255,95,75)`，scale 2 | 前后均为“104”，0.99411，检测框相同 | 491.83／515.27 ms |

原队伍条在改动前已经读到完整文字，本样本确认的是减少窄条 DB 放大和保留队伍编号。队伍截图来自 `desktop-20261025-144332/profile/runs/20261025-144817-744/frame-000021.png`，价格截图来自 `20261025-153856-131/frame-000042.png`，均位于 `logs/dotnet_daily_debug/`。

报告为 `logs/dotnet_daily_debug/ocr-small-crops-20261025/before.json` 和 `after.json`。同目录 `direct-checks.json` 确认短行仅提供识别模型即可成功读取。`coordinate-check.json` 使用偏移 `(100,100)`、1000×600 ROI、scale 2，实际进入 2000×1200→1600×960 的输入缩小分支；与同内容两倍裁剪图比较的 77 条文字及置信度全相同，坐标边界在两倍图上最多相差一像素。

四张历史截图重新对照后的结果仍为 17 框坐标一致、16/17 条文字一致、十行颜色及领取判断一致，报告为 `logs/dotnet_daily_debug/ocr-native-20261025/comparison-773c2709/comparison.json`。

## 模板与单裁剪证据

对照脚本在导入配置单例前，将模块配置路径指向 `logs/dotnet_milestone_debug/vision/<run>/profile` 的独立副本。截图、文字裁剪和 `comparison.json` 均保留在该次运行目录，不写入用户配置。Python 参照直接调用生产 `ImageUtils` 和现有 `ocr.engine.text_rec`，不重新实例化项目单例。

2026-10-25 的本地对照包含：

- 三张 1280×720 历史截图中的四个邮件资源，以及英文/深色路径选择；
- 主界面缩放到高度 360、1440、1800 的派生截图；
- 高度 360、720、1440、1800 下，模板位于 `Clam`/`Normal` 搜索边界和边界外一像素的合成样本；
- 主界面和通行证截图中的五个真实文字裁剪：“驾驶席”“放映室”“战斗通行证”“清剿经验采光1次”“击败10个敌人”。

150 个模板结果的分数、中心点、bbox 和资源路径均一致，分数最大绝对差为 0。五个文字裁剪的输出、CTC token、张量尺寸和五位置信度均一致，且都符合人工标注文字；时间步概率最大绝对差为 `2.874e-8`。Python 使用 OpenCV 4.11.0、ONNX Runtime 1.20.1；识别模型 SHA-256 为 `48fc40f24f6d2a207a2b1091d3437eb3cc3eb6b676dc3ef9c37384005483683b`。

首轮报告为 `logs/dotnet_milestone_debug/vision/819fc0841f45/comparison.json`。私有原图来自 `logs/daily_validation_debug/2026-09-27-{final-home,daily-unclaimed,mirror-clear}.png`，不纳入 Git。离线对照不覆盖实时截图后端和游戏输入。

中文邮箱关闭资源对应当前按钮的字形尺寸，保留 1440 基准画布和原 bbox；SHA-256 为 `7079666c349cede7296ec2ceb2987352f2890474d03967f76682cc5c815a6969`。同日对 9 张真实邮件流程截图、4 个模板、3 种模式新增 108 项对照，分数、中心、bbox、路径及按 0.8 阈值得到的控件集合全部一致。关闭模板在邮箱画面的分数为 0.9902～0.9923，在首尾主页约为 0.277；奖励浮层后的关闭按钮也会匹配，由流程的确认优先规则处理。

报告为本地 `logs/dotnet_milestone_debug/live-mail/vision-final-546fcb50bb57/comparison.json`，记录截图、资源和程序的 SHA-256，并区分原始运行事件与当前资源的离线重放。实机动作与结果范围见 [邮件流程](mail-flow.md#实机记录)。

日常奖励接口与验证范围见[体力、模块与通行证奖励](daily-rewards.md)。
