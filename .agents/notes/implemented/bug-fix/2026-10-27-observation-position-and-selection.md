# Agent Note: 观测选择依据实际滚动位置和选择计数

Status: implemented

## 问题

观测列表触底时，实际内容位移可能小于鼠标拖动距离。按拖动距离直接修正目标坐标会选到其他位置；列表保留滚动位置时，仅向下查找也可能错过上方等级。重复点击同一件会取消选中，点击后直接提交则无法区分输入生效和目标未选中。

## 决策

[Python 观测流程](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/blob/ahab/tasks/mirror/mirror.py)与 [AAALC 观测流程](../../../../dotnet/src/AALC.Runtime/Mirror/MirrorRewardFlow.cs)在切换体系后重新定位等级。等级不在可见区时有界地向上、向下查找；每次滚动都获取新帧，优先用等级锚点重新计算位置。Python 几何计算使用实际截图高度。

等级滚出可见区时，[Python 位移测量](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/blob/ahab/tasks/mirror/observation.py)与 [C# 位移测量](../../../../dotnet/src/AALC.Runtime/Mirror/MirrorObservationScroll.cs)比较滚动前后的亮色卡框和文字，估计实际内容位移；不将固定深色底纹当作列表移动。无法可靠定位或列表不再移动时停止选择，不点击推测位置。

点击前读取游戏按钮的已选数量，点击一次后等待数量增加，再处理下一件。没有增加时停止，不重复切换选中状态，也不提交。旧版配置中的重复位置只处理一次；新版配置校验及编辑器禁止重复位置。两端最多选择三件，并校验等级和行列范围；新版配置同时校验体系键。输入继续使用各自既有会话与停止机制。

## 曾考虑的替代方案

按拖动指令累计坐标无需比较图像，但不能反映列表触底和滚动钳制。每次强制重新滚到顶部也会增加操作，并不能核对点击是否选中；因此以新观察确定位置，以游戏计数确认选择结果。

只复用等级模板不足以处理目标离等级标题较远的行；保留等级锚点作为优先依据，在其离开可见区后测量实际位移。

## 后果

[Python 回归](https://github.com/Small-tailqwq/AhabAssistantLimbusCompany/blob/ahab/tests/test_observe_ego_gift.py)和 [AAALC 回归](../../../../dotnet/tests/AALC.Core.Tests/MirrorObservationTests.cs)覆盖滚动钳制、向上查找、截图尺度、重复位置、计数未增加及像素位移等情况。编辑器和配置保存的原则见[界面设计笔记](../architecture/2026-10-27-aaalc-interface-design.md)。

定位和计数确认能发现未选中，无法证明位置仍对应某个特定饰品。游戏更新后某件饰品无法选中的报告尚缺当前游戏画面及配置证据；目录顺序与模板是否漂移仍需对应实机核对。
