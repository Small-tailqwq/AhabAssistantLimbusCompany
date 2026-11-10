# 镜牢商店

入口为 `MirrorShopFlow.RunAsync(IGameSession, MirrorShopOptions, keyword, floor, cancellationToken)`。调用方进入商店后传入当前体系与楼层；方法复用同一个会话，不创建窗口、截图后端或输入实例。返回 `true` 需要观察到退出后的地图 `legend_assets.png`。取消向调用方传播，交易或页面状态无法确认时返回 `false`。

## 策略

`MirrorShopOptions` 使用下列有类型的策略；默认购买必买项和本体系饰品、治疗、升级，保留库存，不刷新、不替换技能。

| 字段 | 含义 |
| --- | --- |
| `Purchases` | `None`、`Keyword`、`EssentialsAndKeyword` |
| `Heal`、`Enhance` | 全体治疗、升级可见的体系饰品 |
| `Inventory` | `Keep`、`SellListedKeywords`、`KeywordRecipes` |
| `Keywords` | 附加体系，主 `keyword` 优先，然后按数组顺序去重处理 |
| `SellKeywords` | 明确允许出售的体系；主体系和 `Keywords` 中的体系始终排除 |
| `NormalRefreshLimit`、`KeywordRefreshLimit` | 两种刷新各自最多 0–10 次 |
| `ReserveFunds` | 刷新后保留的经费；不作为饰品、治疗、升级的预算上限 |
| `Skill` | `None`、`OneToThree`、`TwoToThree`、`OneToTwo` |
| `SkillSinners` | 允许替换技能的罪人编号，按李箱至格里高尔的 1–12 顺序；超级商店搜索按数组优先顺序尝试 |
| `SkipFloors` | 跳过业务处理并直接退出的楼层 |

体系值为 `burn`、`bleed`、`tremor`、`rupture`、`poise`、`sinking`、`charge`、`slash`、`pierce`、`blunt`。技能替换默认关闭，`SkillSinners` 默认仅包含 1。

处理顺序为技能替换、治疗、显式出售、购买及刷新、已知公式合成、升级、退出。`SellListedKeywords` 与 `KeywordRecipes` 是互斥的库存策略。

## 交易与确认

- 获得饰品弹窗优先关闭，弹窗未消失时不读取经费，也不点击背后的商品。
- 经费区域来自仓库 `my_money_bbox.png` 和 `my_money_heal_bbox.png` 的 2560 × 1440 非零边界，并随实际截图缩放。首次 OCR 无法确定时使用同一裁剪放大两倍重读。多个互相冲突的金额仍按未知处理。
- 经费未知时停止购买和刷新；治疗、升级、合成确认也需要已知经费。刷新预算按普通 200、关键词 300 检查，扣除后还需满足 `ReserveFunds`。
- 购买、刷新、治疗和升级确认后，只观察新帧并等待经费减少。出售等待经费增加，公式合成等待新的获得饰品弹窗。状态不变时停止，不重复发送消费确认。
- 关键词刷新先选择本次体系，再发送一次确认。技能替换需要购买标记，或确认窗口消失且经费减少；若有第二层确认，只有确认文字已变化、经费尚未变化时才发送一次第二确认。
- 点击离开后等待确认框；发送退出确认后等待页面推进，至少三秒后才允许重复输入，同时持续检查地图。
- 所有循环有次数上限，等待与输入通过会话检查取消。未确认的付款窗口会阻止切页和退出。

## 当前业务范围

购买依次查找五个必买项模板及体系商品模板，每笔交易后重新观察商品位置。流血体系遇到“白棉花”或 `gossypium` 时不购买。关键词刷新按配置中的体系轮流选择；普通刷新与关键词刷新分别计数。

治疗使用已识别的全体治疗按钮，一次消费后只返回商店，不继续点击其他恢复项。升级扫描使用相对区域：横向 0.5151–0.8844、纵向 0.3380–0.7130，优先体系四级和大饰品，再处理体系标记；每个可见位置最多升级两次。

出售只选择 `SellKeywords` 中的标记，排除全部保留体系，并保护与月之记忆模板重合的位置。确认收入后重新观察；必要时向下拖动库存一次。

已知公式数据来自 `mirror/shop/fusion_result/`。当前有烧伤、流血、震颤、破裂、呼吸、沉沦和充能的普通及困难模板。合成只选择公式区分界线上方的已知模板，选择后确认一次，并等待获得饰品结果。没有配方模板的体系会报告并跳过。该策略不执行随机素材合成或星光消费。

技能替换支持普通商店，以及超级商店的两个普通报价和指定罪人搜索。普通报价通过中英文罪人名称判断是否允许购买；指定搜索使用十二个罪人位置。三个转换选项按从左到右分别对应 1→2、2→3、1→3。未识别到三个选项或无法区分后续确认状态时停止。

当前范围不含库存多页全量升级、随机素材或激进合成、星光辅助合成，以及合成完成后的动态策略切换。附加体系统一由 `Keywords` 处理。

## 证据与验证

实现入口为 [MirrorShopFlow](../src/AALC.Runtime/Mirror/MirrorShopFlow.cs)，规则测试见 [MirrorShopTests](../tests/AALC.Core.Tests/MirrorShopTests.cs)。商品与配方名称由 `assets/images/` 下的模板定义。

```powershell
dotnet test tests/AALC.Core.Tests/AALC.Core.Tests.csproj --filter FullyQualifiedName~MirrorShop
```

`MirrorShopTests` 使用输入驱动的人工页面契约，核验未知经费、保留刷新预算、弹窗优先、交易停滞、单次治疗、升级、受保护出售、公式结果与普通/超级商店技能替换的动作顺序。这些契约验证生产流程对给定观察的行为；交易策略的模板命中、价格显示及动作后页面仍需实机验证。
