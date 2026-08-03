---
name: aalc-automation-practices
description: 在 AhabAssistantLimbusCompany 中实现、调试或审阅桌面自动化、图片或模板匹配、任务编排、协作式停止、PySide6 UI、配置、调试开关或代码结构时，应用 AALC 特有约定。
---

# AALC 自动化实践

修改前先读目标签名、调用方与仓库内同类实现。不要把通用软件设计偏好强加给针对真实 UI 调优过的桌面自动化行为。

## 按任务加载

- 涉及 `auto.*`、`ImageUtils.*`、OCR、UI 定位、重试或自动化流程：读 [references/automation-design.md](references/automation-design.md)。
- 涉及任务线程、启动/停止、模拟器等待、PySide6 UI、语言/主题或配置：读 [references/lifecycle-ui.md](references/lifecycle-ui.md)。
- 重放用户截图：加载 `replay-matching` 及其生产管线 reference。
- 新增或修改 `debug_*` 前：再读 `.opencode/tools/debug_model_constitution.md`。

只加载匹配的那份 reference。

## 核心工作流

1. 先确认真实的失败状态、UI 层级与调用链。
2. 检查 API 默认值、搜索区域、模板裁剪与同类代码。
3. 选择能解释根因的最小改动；不要靠堆参数试错。
4. 除非存在真实的复用需求或语义边界，否则保持调用图扁平。
5. 运行最相关的语法、lint、测试或重放验证。
6. 复核 diff 是否比故障本身更复杂，并移除改动引入的多余内容。

## 约束

- 不重新实例化项目单例。
- 不用用户 `config.yaml` 当模板或同步目标。
- 不用强制线程终止替代协作式停止。
- 没有重放证据时，不把通用图像匹配经验当作事实陈述。
- 不顺手修改无关的遗留代码。
