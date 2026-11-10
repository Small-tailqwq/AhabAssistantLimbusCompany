# 镜牢主题、奖励与事件

运行期使用 `IGameSession` 的模板、OCR、输入与取消检查；不调用 Python。初始饰品由镜牢入口按界面可选上限处理，最终结算由镜牢 Runner 接手。

- `MirrorThemeFlow.RunAsync(session, options, ct)`：切换难度，识别主题标题，按目录别名找到稳定 ID 后取权重，在刷新预算用完后选择最高权重。第四层可优选或跳过最左活动包。拖动后须读到地图标题的目标楼层才成功；过渡中的旧地图、黑屏与读空继续等待。连续三帧仍见卡包时重新识别并重试，最多提交三次，加载与未知帧不计入连续次数。
- `MirrorRewardFlow.HandleAsync(session, frame, options, ct)`：返回 `(Handled, Failed)`。奖励卡四种优先级分别指定星光、饰品和经费顺序；选择后等待领取，五秒后才重试领取，最多三次。饰品按主副体系排序，可排除白棉花；以选择按钮定位右侧计数，识别一／二件选择数量，淡入期间读不到时最多等待八次新帧。单件奖励要求唯一卡片、拒绝按钮和完整的“选择”／“Select”按钮文字，不依赖不存在的数量分数。多个饰品和宝箱的后续选择均先重新观察并确认剩余目标。选择后不重复切换，确认后继续观察地图、主题、事件、战斗或商店出口。
- `MirrorRewardFlow.ObserveGiftsAsync(session, options.ObservedGifts, ct)`：按体系、等级、行和列选择观测目录位置，最多三件且位置不重复。现有等级资源为 I／II／III，含十种体系及泛用目录。切换目录和每次滚动后重新观察，支持向上查找等级；等级可见时重新锚定，离开可见区后用卡框与文字测量实际位移。每件只点击一次，确认游戏计数增加后继续；定位或计数无法确认则失败，不提交。选择与拒绝剩余饰品后确认退出。
- `MirrorEventFlow.RunAsync(session, ct)`：复用 `BattleEvents` 的选项、判定成功率及结果处理；镜牢补充未知／直接获取饰品优先项与开始战斗按钮。地图和战斗在没有事件控件时交接；明确的饰品选择／获得确认弹窗优先交给饰品流程，允许底层仍显示事件背景。未知页面和超时返回失败。

`MirrorThemeCatalog.All` 定义 87 个主题包、269 个中英文及 OCR 别名：53 个基础包适用于普通和困难，34 个仅适用于困难。每项包含稳定 ID、完整中文名、英文名、封面和两种模式默认权重。中文展示名按现有封面核对，旧 OCR 碎片仅用于别名匹配。匹配忽略空白与大小写，长别名优先；零协改名与常见 OCR 错字归于同一 ID。`MirrorThemeOptions.NormalWeights` 和 `HardWeights` 仅保存 ID 覆盖，两种模式独立；未知主题使用 `UnknownWeight`。权重与优选阈值范围为 -10～10。`MirrorRewardOptions.Keyword` 使用 `burn/bleed/tremor/rupture/poise/sinking/charge/slash/pierce/blunt` 资源键，`SecondaryKeyword` 可空。

桌面镜牢页编辑轮换队列、游戏编队、适用难度、运行次数、结算周奖励、商店、初始增益、主题权重和观测位置。配置保存到独立 profile 的 `settings.json` 的 `Mirror` 字段。任务成功轮转后由 Runner 回调保存新队列。OCR 与地图 ONNX 模型只在启动运行后创建，首屏不加载模型。

主题权重窗口按普通／困难筛选封面卡片，支持搜索、优选阈值、重置当前模式、当前模式全部设为 -5、普通覆盖同步到困难。同步保留困难专属包权重。达到阈值的卡片金色描边，负权重封面暗化。编辑先保存在窗口内存，应用后进入队伍草稿，主界面保存后写入 profile；取消不改队伍。封面按 240px 宽度异步解码并缓存，卡片使用 WrapPanel，每六项在后台调度优先级让出绘制与输入后继续加入；应用首屏不加载封面。

罪人顺序与商店技能替换共用 2×6 头像组件。出战顺序由选择数组派生紧凑编号，取消后重新选中会追加到队尾；前七位使用琥珀横幅，后五位使用青色横幅。头像与四种覆盖图片缓存复用，控件实例固定，悬停只改变渲染缩放与透明度。星光十项按游戏两行五列排列，标题、`+`、`++` 分别选择基础及两档升级，再次点击已选段会移除该段及后续等级。三档效果通过悬停查看，单项与总消耗共享 `MirrorStarBonusCatalog` 的成本定义。初始饰品优先顺序使用六种排列下拉框，跳过商店楼层使用五个勾选项。开始镜牢后自动切换到独立的“运行监控”页。

观测编辑器按游戏顺序显示体系图标，使用 III／II／I 等级页签和八列位置网格；右侧显示最多三件选择及顺序。它编辑 `Keyword/Level/Row/Column`，没有完整饰品名称和图片目录。应用后进入队伍草稿，保存后写入 profile，取消不改队伍。游戏更新后需核对位置与实际饰品的对应。界面原则与观测定位理由分别记录在[界面设计笔记](../.agents/notes/implemented/architecture/2026-10-27-aaalc-interface-design.md)和[观测修复笔记](../.agents/notes/implemented/bug-fix/2026-10-27-observation-position-and-selection.md)。

当前直接回归包含 `MirrorThemeCatalogTests`、`MirrorThemeTests`、`MirrorRewardTests`、`MirrorObservationTests`、`MirrorEventTests`，覆盖目录来源、别名与模式权重、拖拽重试、优先级、刷新预算、奖励等待不重选、拒绝确认、观测滚动钳制与选择计数、未知出口失败、取消和事件覆盖层。测试提供显式观察序列，验证流程契约。模板、OCR 和真实录制通过 [截图回归](screenshot-regression.md) 验证。
