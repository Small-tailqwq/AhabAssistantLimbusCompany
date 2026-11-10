---
name: desktop-ui-craft
description: 新增或审阅 AAALC 的 Avalonia 页面、按钮、文本、状态提示与交互细节时使用；按 docs/ui-design.md 与现有令牌保持层级、对齐、截断、焦点和文案一致，避免界面像拼装出来的。
---

# 桌面界面细节

来源：Emil Kowalski 的 emil-design-eng、apple-design、ui-cheatsheet（MIT，见文末），只保留能迁移到 Avalonia 桌面的部分。颜色、尺寸和控件的既有规则以 [界面设计](../../../docs/ui-design.md) 为准，本技能不覆盖它。

## 何时加载

- 新增或修改页面、卡片、按钮、配置行、状态提示、空状态。
- 审阅界面改动是否只“能跑”，缺少对齐、层级、截断或焦点处理。
- 用户说界面“糙”“挤”“乱”“不像一个应用”。

## 先读

- `docs/ui-design.md` 与 `src/AALC.Desktop/Styles/Tokens.axaml`。
- 要改的页面对应的现有 View，先从最近的同类页面复制结构。

## 硬规则

1. 页面不写十六进制颜色和零散尺寸；用 `{DynamicResource 令牌}` 或 `docs/ui-design.md` 定义的语义类。
2. `Border.card` 是唯一承载容器，卡片不嵌套卡片；内嵌画面、日志用 `Border.inset`。
3. 一个操作区最多一个 `primary`；危险操作才用 `danger`；不使用 SukiUI 的 `Flat`、`Basic` 按钮类。
4. 文案直接说明动作或状态，按钮用动词开头；不加副标题、说明性 slogan 或重复标签。
5. 所有可能变长的值都要决定换行、截断或完整值入口，不能默认“正常数据不会这么长”。

## 布局

- 页面骨架用 `Grid.page`，外边距 `PagePadding`，卡片间距 16；配置行用 `Grid.option` + `ColumnDefinitions="160,*"`。
- 开关靠右，数值框限宽 180，下拉框限宽 320；多行配置用 `StackPanel.options`。
- 底部操作栏 `Grid.actions`：左侧错误文本，右侧次要按钮在前、主按钮最右；运行中显示“停止”。
- 低频或成组的配置放进 `Expander`；它本身就是卡片，不再外包 `Border`。

## 按钮与反馈

- 悬停和按下由叠加层表达，不替换底色；键盘焦点立即显示主色外框。具体实现见 `Styles/Button.axaml`。
- 不要只靠颜色区分状态；选中另有形状、描边或文字。
- 按钮宽度从内容加 `MinWidth` 得来，不写死宽度，避免中文或长英文标签溢出。
- 破坏性操作需要确认时，确认文案说清后果；不要给每个按钮都加确认。

## 文本与数字

- 字号层级固定：标题 24、小节 15、正文 14、说明 12；用 `heading`、`section`、`muted`、`caption` 这些类，不在页面重复字号。
- 说明文本用 `TextWrapping="Wrap"`；单行元数据用 `TextTrimming`：路径用 `PathSegmentEllipsis`（`MainWindow.axaml` 的配置目录），窗口标题等普通文本用 `CharacterEllipsis`。
- 截断必须给完整值入口：现有做法是 `ToolTip.Tip` 绑定完整值，例如 `ThemeWeightEditorWindow.axaml` 的 `FullName`。
- 数字列保持右对齐或等宽呈现；值变化时不要引起整行宽度跳动。
- 日期超过一周就显示绝对时间，不显示“340 天前”这类会过期的相对时间。
- 不使用 `TextBlock` 拼接未转义的用户数据；文本层不做 HTML/Markdown 解释。

## 浮层与焦点

- `Popup`、`Flyout`、菜单从触发元素附近出现；居中对话框保持居中，并设置 `WindowStartupLocation="CenterScreen"`。
- 打开浮层时把初始焦点放在第一个可操作项；关闭后焦点回到触发元素。
- `Esc` 关闭当前浮层或对话框；不要和全局 `Esc` 停止冲突，先让浮层消费该键。
- 键盘 `Tab` 顺序与视觉顺序一致；`focus-visible` 样式不能依赖颜色单独表达。

## 状态与错误

- 错误文本用 `error` 类，只出现在操作栏或对应字段附近；不要用红色装饰。
- 空列表、未选择游戏窗口、未加载配置都要有明确状态，不留下空白区域。
- 运行中、已停止、失败三种状态在侧栏底部和对应页面保持一致，不各说各的。
- 长错误信息换行显示，保持可选中；不要把完整日志塞进一行。

## 高 DPI 与窗口尺寸

- `MainWindow` 最小 1040×700，编辑器窗口各自有 `MinWidth`/`MinHeight`；新窗口先定最小尺寸再排布局。
- 在 100%、150%、200% 缩放下检查：文字变大、行高变化、按钮标签是否仍完整。
- 不留固定像素高度去容纳会换行的文本；需要固定高度时同时指定 `TextTrimming` 或 `MaxLines`。

## 审查输出

用表格，一行一个 finding，按影响排序：

| 位置 | 现状 | 问题 | 修改 |
|---|---|---|---|

只报能指出具体控件或属性位置的问题；纯偏好不写。

## 来源

改编自 emilkowalski/skills（MIT，Copyright (c) 2026 Emil Kowalski）的 emil-design-eng、apple-design 与根目录 ui-cheatsheet，按 Avalonia 与项目令牌改写。原文：https://github.com/emilkowalski/skills ；许可全文：https://github.com/emilkowalski/skills/blob/main/LICENSE
