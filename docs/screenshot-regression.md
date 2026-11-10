# 截图驱动回归

测试集借鉴 [MaaEnd 的节点测试](https://github.com/MaaEnd/MaaEnd/blob/v2/docs/zh_cn/developers/node-testing.md)：原图与用例分开保存，用人工标注的正例、反例和位置范围约束识别结果。运行时调用 AAALC 自己的生产视觉与任务实现，不依赖 MaaFramework。

## 数据位置与运行

仓库只保存 `tests/screenshots/*.json` 用例定义；PNG 和录制目录位于 `D:\AALCData\testsets`。新实机录制默认写入 `D:\AALCData\recordings/{mirror,daily,mail}/时间戳`。`AALC_DATA_ROOT` 可以指定另一个本地非 C 盘目录；目录不可用时直接报错。截图写入会拒绝 C 盘路径及指向 C 盘的目录链接，没有自动回落。桌面 `--profile` 只影响设置，不改变截图目录。旧录制保留原位，选入测试集的帧复制到外部目录。

在仓库根目录执行：

```powershell
dotnet run --project src/AALC.Cli -c Release -- screenshot-test
```

参数：

```text
screenshot-test [--suite <用例.json>] [--data <非C盘测试集目录>]
                [--root <资源仓库>] [--models <OCR模型目录>] [--filter <用例ID片段>]
```

默认读取 `tests/screenshots/mirror.json`、`<AALC_DATA_ROOT>/testsets` 和仓库 `assets/models/ocr`。`--filter` 按 ID 子串筛选静态用例和录制用例；没有匹配用例会报错。克隆代码不包含本地截图，缺图会失败，不能被视为通过或跳过。

报告逐用例写入 `<AALC_DATA_ROOT>/reports/screenshots/时间戳/report.json`，包含预期、实际目标与位置、OCR 文本和置信度、地图节点/连接/计划、异常和耗时，以及模型、模板与执行程序集的 SHA256。全部通过退出码为 `0`，用例失败为 `1`，配置错误或取消为 `2`。Ctrl+C 协作取消，已完成的结果保留。

## 两层验证

静态截图经过 `TemplateMatcher`、`PageTextReader`、`MirrorMapReader` 原生管线。用例可以检查：

- 模板命中数量和完整识别框所在范围，数量 `0` 表示反例。
- 指定 ROI 和倍率的 OCR 文本，支持包含、排除、完全相等；`exact: ""` 检查区域没有达到最低置信度的文字。
- `MirrorRunner.IsCombatPage`、`MirrorEventFlow.HasEventPageEvidence` 和 `MirrorRewardFlow.IsReward` 的生产判定。它们是各自的页面证据规则，不是互斥的页面分类器。
- `pages.selectedGifts` 根据饰品选中边框检查数量；“已持有”文字不计为选中。
- 重新识别巴士、节点和路径，再通过 `MirrorRoutePlanner` 计算下一节点，核对其类型与位置。

录制用例使用 `MirrorScenarioReplay` 的真实视觉模式：从 PNG 重新生成模板、OCR 和图谱结果，执行当前 `MirrorRunner`，核验观察查询、OCR 区域、动作规则、坐标、按键、顺序与最终结果。输入只进入离线适配器，不创建游戏窗口或发送键鼠输入。虚拟时钟跳过实机等待；每帧 OCR 缓存复用相同 ROI，不复用录制中的识别输出。

也可以单独运行一份外部录制：

```powershell
dotnet run --project src/AALC.Cli -c Release -- mirror-replay --run D:\AALCData\testsets\mirror\runs\20261026-170440-492 --vision .
```

不带 `--vision` 的 `mirror-replay` 是日志结果回放，只验证编排契约。纯规则测试继续使用 `dotnet test tests/AALC.Core.Tests`，不加载模型和截图。

## 添加用例

1. 从真实录制中挑选能解释问题的原帧，保留分辨率、语言、主题和来源记录。原图复制到外部测试集，不缩放或二次压缩。
2. 目视确认正确页面、文字和目标位置，再编写预期；不要用当前程序输出自动生成正确答案。配一个易混淆的反例。
3. 用 `Get-FileHash <图片> -Algorithm SHA256` 填写哈希，编辑 JSON。位置使用原图像素，`within` 是容差范围，不要求浮点分数完全一致。
4. 运行筛选后的用例并检查报告。模板参数对应实际调用的阈值、搜索方式与多目标模式；修改流程参数时一起核对相关用例。

最小格式（示例哈希须替换为实际值）：

```json
{
  "version": 1,
  "cases": [{
    "id": "map-is-not-combat",
    "description": "来源录制与帧号；地图不可当成战斗页",
    "image": "mirror/images/map.png",
    "sha256": "填写原图的64位SHA256",
    "width": 1280,
    "height": 720,
    "pages": { "combat": false }
  }],
  "replays": []
}
```

完整字段见 [ScreenshotTestset.cs](../src/AALC.Runtime/Replay/ScreenshotTestset.cs)，现有标注见 [mirror.json](../tests/screenshots/mirror.json)。`language` 默认 `zh_cn`，`theme` 默认 `default`；OCR 默认 `scale: 1`、`minimumConfidence: 0.7`，比较时忽略空白和大小写。模板断言的 `query` 对应 `ImageQuery`。未知字段、空测试集、无断言和重复 ID 会被拒绝。

录制用例的 `directory` 相对 `testsets`，`sha256` 字典必须包含 `options.json`、`events.jsonl`、`result.json` 和全部观察帧。行为改变时，旧动作契约可能失败；应核对变化是否符合游戏流程，再标注新的成功片段，不能只修改旧动作使测试变绿。

## 当前边界

首批样本来自 1280×720 中文 Windows 客户端。截图测试可以拦截模板、OCR、分支判断与地图连接的回归；固定录制可以核对已有轨迹上的决策。物理鼠标干扰、窗口焦点、真实输入是否生效和未录制过的游戏分支仍需实机验证。耗时记录用于比较视觉实现，虚拟时钟结果不作为真实帧过期或启动性能的验收。

## 实机耗时分析

每次录制的 `events.jsonl` 保存输入规则、坐标、帧号及相对时间。`Click`、`Key`、`Drag` 与同帧同目标的 `Sent` 配对后可计算输入调用耗时；`Sent` 表示调用返回，页面变化由后续截图确认。`automation.observe`、`automation.ocr` 和 `automation.delay` 的 detail 分别保存截图与模板观察、OCR、主动等待的 `durationMilliseconds`，等待另记录 `requestedMilliseconds`。

```powershell
python tools/diagnostics/dotnet_run_metrics.py D:\AALCData\recordings\mirror --output D:\AALCData\reports\metrics
```

脚本生成 `summary.json`、`actions.csv` 和 `report.md`，汇总每轮结果、输入次数与耗时、Progress 阶段区间、重试和恢复事件。旧日志缺失的耗时显示“未采集”；运行中最后一个未完成行会忽略并注明。源日志保持不变，再次分析时指定新的输出目录。
