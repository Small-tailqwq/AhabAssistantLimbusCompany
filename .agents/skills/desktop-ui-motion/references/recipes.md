# Avalonia 动效配方

先读项目里已有的同类实现，从它出发改，不要重写主题或另建一套值。

## 悬停与按下：Button.axaml

现有按钮用 `PART_Overlay`：悬停 `Opacity 0.06`、按下 `0.12`，`DoubleTransition` 120 ms；底色不变，`focus-visible` 立即显示焦点环。新增按钮沿用，不给按钮加缩放。

## 折叠卡片：Expander.axaml

`ExpandPresenter` 的 `Progress` 0→1 用 `DoubleTransition` 220 ms `CubicEaseOut`，`Opacity` 0→1 用 180 ms；箭头 `rotate(0)`→`rotate(180)` 220 ms，`RenderTransformOrigin="50%,50%"`。新增折叠直接复用该主题，不给内部内容再加 stagger。

## 浮层：Popup / Flyout

先确认 SukiUI 是否已为主题提供浮层外观。不要全局修改所有 Flyout。确需入场时，在浮层内容的 `Border` 上放：

```xml
<Border Opacity="0" RenderTransformOrigin="0.5,1">
  <Border.Transitions>
    <Transitions>
      <DoubleTransition Property="Opacity" Duration="0:0:0.16">
        <DoubleTransition.Easing>
          <SplineEasing X1="0.23" Y1="1" X2="0.32" Y2="1"/>
        </DoubleTransition.Easing>
      </DoubleTransition>
      <TransformOperationsTransition Property="RenderTransform" Duration="0:0:0.16" Easing="CubicEaseOut"/>
    </Transitions>
  </Border.Transitions>
</Border>
```

打开时把 `Opacity` 设为 1、`RenderTransform` 设为恒等；关闭立即隐藏，不等动画。`RenderTransformOrigin` 朝触发点。首次使用 `SplineEasing` 元素写法前先构建验证，解析器不接受时在 C# 主题里构造 `new SplineEasing(0.23, 1, 0.32, 1)`。

## ToolTip

保持 `ToolTip.ShowDelay` 的默认行为。不要给 ToolTip 加入场位移动画；同一组工具按钮在第一个显示后可以跳过延迟。

## 对话框与独立窗口

`ObserveGiftEditorWindow`、`ThemeWeightEditorWindow` 不自定义窗口入场，系统窗口管理已经处理。需要时只给内容做 150–200 ms 透明度淡入，不做位移，不改窗口尺寸。

## 列表进入

只对低频、一次出现的列表做，容器上放短透明度过渡；不要逐项 stagger。日志、窗口列表、卡包列表这类高频内容不加。

## 状态反馈

- 运行/停止：文字与颜色变化即可，不加动画；`Esc` 停止立即生效。
- 确定时长的进度用动画；不确定时长用不确定进度条，不伪造进度。
- 错误文本立即可见，不淡入。
- 保存成功反馈用短透明度或文字变化，不用弹跳。

## 循环装饰

关于页的 logo 波浪是唯一的长期循环，保留；其他页面不复制。空状态可以一次性淡入，不做无限循环。

## 减少动效

当前没有平台开关，不写“已支持”。删掉位移动画、保留透明度与颜色变化，是现阶段唯一可靠的做法。
