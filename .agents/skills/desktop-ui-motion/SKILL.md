---
name: desktop-ui-motion
description: 在 AAALC 的 Avalonia 桌面界面新增、审阅或删除动效时使用；判断是否该动画、选择 SplineEasing/SpringEasing 与时长、用 Transitions 保证可打断，并检查键盘操作、减少动效与交互阻塞。
---

# 桌面动效实践

来源：Emil Kowalski 的 emilkowalski/skills（MIT，见文末），按 Avalonia 12 与项目现有主题改写。原技能面向 Web，CSS、React、Motion 的 API 不照搬。

## 何时加载

- 改 `src/AALC.Desktop/Styles/` 的 `Transitions`、`Animation`，或自绘控件的 `RenderTransform`。
- 新增按钮、折叠、浮层、列表进入、状态反馈或加载动效。
- 用户说界面卡、慢、晃、动画太多，或要求审阅动效。

## 硬规则

1. 先回答“是否该动画”和“目的是什么”，过不了门槛就不写动画。
2. 优先 `Transitions`；只有它表达不了才用 `Animation` 关键帧；不引入动效库。
3. 只动 `RenderTransform` 与 `Opacity`；不改 `Width`、`Height`、`Margin`、`Padding`。折叠的高度截取由 `ExpandPresenter` 负责，是唯一例外。
4. 沿用 [界面设计](../../../docs/ui-design.md) 的 220/180/120 ms 与现有主题；不另建时长或缓动体系。
5. 加动画的同时处理打断、键盘触发和减少动效，不能留作后续。

## 决策顺序

### 1 频率

| 频率 | 决定 |
|---|---|
| 每天上百次（快捷键、Esc、运行/停止、日志滚动） | 不动画 |
| 每天几十次（悬停、侧栏切换、频繁开关） | 只允许几乎察觉不到的透明度或颜色变化 |
| 偶尔（对话框、浮层、通知、保存反馈） | 标准动画 |
| 首次或罕见（关于页、空状态、完成反馈） | 可以多一点，仍不阻塞操作 |

键盘触发的动作不加位移动画。项目的 `Esc` 停止、`Enter` 保存都属于这一类。

### 2 目的

只能从这些里选一个并说出来：反馈、空间连续、状态指示、避免突变、说明、愉悦（仅罕见场景）。说不出就删掉。“看起来酷”在常用界面上不成立。

### 3 工具

| 需求 | 做法 |
|---|---|
| 悬停、按下、颜色、选中态 | `BrushTransition`、`DoubleTransition`、`TransformOperationsTransition` |
| 折叠展开 | 现有 `ExpandPresenter` + `DoubleTransition`（`Progress` 220 ms，`Opacity` 180 ms） |
| 一次性入场、循环装饰 | `Animation` + `KeyFrame`，只在 Transitions 无法表达时用 |
| 窗口内拖拽 | 指针事件 1:1 跟随，释放用短过渡；桌面端没有触摸手势，不引手势库 |
| 页面切换 | 不加；Avalonia 没有内建页面转场，自建转场会阻塞导航 |

### 4 属性与原点

- 位移、缩放用 `RenderTransform`，透明度用 `Opacity`，颜色用画刷过渡；这些不触发重新测量。
- 不从 `scale(0)` 开始；入场用 `0.94–0.97` 加 `Opacity 0`。
- 浮层（`Popup`、`Flyout`、`ToolTip`）需要缩放起点时，把 `RenderTransformOrigin` 放在触发点一侧；居中对话框保持中心。
- 百分比位移相对于自身尺寸，不要写死像素来移动内容。

### 5 缓动与时长

Avalonia 12 有 `SplineEasing`（cubic-bezier）与内置 `CubicEaseOut`。

| 场景 | 缓动 |
|---|---|
| 进入、退出 | `SplineEasing X1=0.23 Y1=1 X2=0.32 Y2=1`；现有 `CubicEaseOut` 也可接受 |
| 屏内移动 | `SplineEasing X1=0.77 Y1=0 X2=0.175 Y2=1` 或 `CubicEaseInOut` |
| 悬停、颜色 | 现有 `BrushTransition`，默认线性即可 |
| 匀速 | `LinearEasing` |

不要用 `EaseIn` 做入场。时长：按下反馈 100–160 ms；小浮层、ToolTip 125–200 ms；下拉 150–250 ms；对话框、抽屉 200–500 ms；常规 UI 不超过 300 ms。`SpringEasing` 只用于可被打断、带物理感的交互；从 `Mass=1, Stiffness=100, Damping=10` 起步，默认不要回弹。

### 6 打断与退出

- 快速或重复触发的 UI 只用 `Transitions`：它从当前值重定向；`Animation` 关键帧会从头重放。关于页的 logo 波浪是无限关键帧，只适合该页，不要复制到其他界面。
- 入场与出场走同一方向；不要从右侧进、向下出。
- 关闭浮层或对话框时不等待动画结束；动画不能阻塞输入或延迟焦点返回。

### 7 键盘与减少动效

- 焦点移动、`Esc`、快捷键触发的操作不加位移或缩放。
- Avalonia 12 的 `IPlatformSettings` 没有动画开关。要读取 Windows 的“显示动画”设置必须单独实现并验证；实现前不声称支持减少动效，也不为单个动画引入该依赖。
- 需要少动一下时，优先删掉位移动画、保留短透明度变化，而不是整体禁用。

## 审查输出

审阅动效时用表格，一行一个 finding，按影响排序：

| 位置 | 现状 | 问题 | 修改 |
|---|---|---|---|

只报与当前改动相关的项；没有发现就直说。不要用“Before:/After:”分行的列表。

## 参考

- [standards.md](references/standards.md)：数值表、类型映射与十条审查标准。
- [recipes.md](references/recipes.md)：按钮、折叠、浮层、列表与循环装饰的 Avalonia 写法。

## 来源

改编自 emilkowalski/skills（MIT，Copyright (c) 2026 Emil Kowalski）的 emil-design-eng、animate、review-animations、find-animation-opportunities、remove-animations、choreograph、apple-design。原文：https://github.com/emilkowalski/skills ；许可全文：https://github.com/emilkowalski/skills/blob/main/LICENSE
