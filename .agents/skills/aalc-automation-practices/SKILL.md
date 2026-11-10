---
name: aalc-automation-practices
description: 在 AAALC 中实现、调试或审阅 .NET 自动化、模板匹配、任务取消、Avalonia UI 和配置时使用。
---

# AAALC 自动化实践

修改前读取目标签名、调用方与同类实现。

## .NET 按任务读取

- 任务编排、取消与观察输入：[日常流程](../../../docs/daily-flow.md)、[Windows 运行接口](../../../docs/windows-runtime.md)，并读取 `src/AALC.Runtime/Automation/` 的实际契约。
- 游戏步骤、重试与分支：[流程证据](references/game-flow-evidence.md)。
- 镜牢阶段与地图：[镜牢流程](../../../docs/mirror-flow.md)、[地图与回放](../../../docs/mirror-route.md)。
- 模板与 OCR：[视觉接口](../../../docs/vision.md)；重放用户截图时读取 `replay-matching`。
- Avalonia 页面、样式与配置：[界面设计](../../../docs/ui-design.md)，核对 `MainViewModel.*.cs` 与 `SettingsStore`。
- 桌面分身：[分身接口](../../../docs/desktop-clone.md)，区分主窗口、分身 worker 与 net48 RDP 宿主。

只展开当前任务对应的文档。

## 核心工作流

1. 确认失败状态、窗口/页面层级与生产调用链。
2. 核对配置快照、资源键、搜索区域、模板裁剪、帧编号与默认值。
3. 对进入、动作、退出及下一阶段逐步核对；不凭一次偶然成功改动流程。
4. 保留 `CancellationToken`、有界重试、输入释放与窗口所有权。
5. 按根 AGENTS 的验证范围运行相关构建、现有测试或离线场景。
6. 只报告实际证据；离线场景、截图回放和实机运行分别标明。

Core 保持纯规则；设备和模型放在现有实现层。不要让 UI 直接绕过生产运行器执行游戏动作，不因重排文件引入新的服务层或配置选项。
