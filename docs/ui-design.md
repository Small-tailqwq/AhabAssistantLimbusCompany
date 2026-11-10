# 桌面界面设计规范

AAALC 桌面端基于 SukiUI 7.0.1 暗色主题。SukiUI 负责基础控件外观；项目自有的颜色、尺寸、层级和折叠动效集中在 `src/AALC.Desktop/Styles/`，页面只组合语义类名。

| 文件 | 内容 |
|---|---|
| `Styles/Tokens.axaml` | 颜色、圆角、间距、字号令牌 |
| `Styles/Logos.axaml` | 矢量 logo，由 `scripts/build_dotnet_logos.py` 生成 |
| `Styles/Controls.axaml` | 文本层级、卡片、配置行、按钮变体、选择块 |
| `Styles/Expander.axaml` | 折叠卡片主题，配合 `ExpandPresenter` |
| `Styles/Hyperlink.axaml` | 超链接主题与 `.pill` 胶囊变体 |
| `Styles/Button.axaml` | 页面按钮主题 |

## 硬性规则

- 页面 XAML 不写十六进制颜色，用 `{DynamicResource 令牌}` 或语义类名。例外：还原游戏内视觉的元素（罪人横幅琥珀/青色、卡包优选金框）保留在对应模型或控件代码里。
- 新增尺寸先找现有令牌；确实缺少时加到 `Tokens.axaml`，不在局部定义。
- 不在 `UserControl.Styles` 中重复全局规则；局部样式只用于该控件独有的结构（如星光按钮）。

## 布局

- 页面骨架：`Grid.page`，行为“标题 / 内容 / 底部操作栏”。外边距 `PagePadding`，卡片间距 16。
- 内容承载：`Border.card` 是唯一容器；画面、日志等内嵌区域用 `Border.inset`。卡片不嵌套卡片。
- 配置行：`Grid.option` + `ColumnDefinitions="160,*"`。开关靠右；数值框限宽 180、下拉框限宽 320，靠左。多行用 `StackPanel.options`。
- 底部操作栏：`Grid.actions`，左侧错误文本 `TextBlock.error`，右侧次要按钮在前、主按钮在最右。运行中显示“停止”。
- 外部链接用 `HyperlinkButton`：正文内为次要色文字加外链箭头，悬停时提亮并展开主色细线；页面主要外链用 `.pill` 描边胶囊。不使用默认蓝色下划线。
- 低频或成组的配置放进 `Expander`，它本身就是一张卡片，不再外包 `Border`。卡片内部的次级折叠用 `Expander.plain`。

## 按钮

| 类名 | 用途 |
|---|---|
| （默认） | 次要操作：卡片底色加描边 |
| `primary` | 每个操作区至多一个主操作；禁用时退为中性色 |
| `danger` | 停止等中断操作 |
| `small` | 卡片内的批量快捷操作，30 高 |
| `icon` | 40×40 方形图标按钮 |
| `choice` / `.active` | 游戏内选择块，选中为金色 |

悬停、按下统一由叠加层表现（6% / 12%），不替换底色；键盘焦点显示主色外框。不要再使用 SukiUI 的 `Flat`、`Basic` 等按钮类。

## 文本层级

| 类名 | 用途 |
|---|---|
| `heading` | 页面标题，24 SemiBold |
| `section` | 卡片小节标题，15 SemiBold |
| （默认） | 正文与配置标签，14 |
| `muted` | 辅助说明、次要数值 |
| `caption` | 12 号注脚，如帧信息、侧栏小标题 |
| `error` | 错误，仅用 `DangerTextBrush` |
| `highlight` | 游戏内金色强调（费用、选中描述） |

## 颜色语义

- Accent（蓝）：可操作、进行中。主按钮用 `Button.primary`。
- Highlight（金）：游戏内被选中的项目，例如星光、观测饰品、卡包。`Button.choice` + `.active/.selected`。
- Danger：只用于错误文本，不作装饰。

## 信息架构

- 游戏窗口选择与运行状态是全局上下文，只放在侧栏底部。任务页和工具页不再各自放窗口选择器。
- 画面与运行记录只在“运行监控”页出现。日常、镜牢、邮件开始时自动切换到该页；截图结果也显示在这里。
- 日常、镜牢页只负责配置，底部提供保存、开始与停止。
- 单次游戏操作（领取邮件、截图）归入工具箱的“快捷操作”。
- 桌面分身有独立页面，任务配置和开始按钮不变；分身窗口的颜色取自同一套令牌，见[桌面分身](desktop-clone.md#分身窗口)。

## 动效

- 折叠：220 ms CubicEaseOut 截取高度，内容 180 ms 淡入；箭头同步旋转 180°。不使用缩放或背景闪变。
- 悬停：120 ms 背景过渡，只使用 `SurfaceHoverBrush`。
- 不新增 `.no-transitions` 一类关闭动画的补丁；动画不顺时修主题本身。

`Styles/Expander.axaml` 整体替换 SukiUI 的 Expander 主题，原因记录在该文件头部注释。
