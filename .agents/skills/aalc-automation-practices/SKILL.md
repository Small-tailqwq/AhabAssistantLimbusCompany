---
name: aalc-automation-practices
description: Apply AALC-specific conventions when implementing, debugging, or reviewing desktop automation, image/template matching, task orchestration, cooperative stopping, PyQt UI/configuration, debug switches, or code structure in AhabAssistantLimbusCompany.
---

# AALC Automation Practices

在动手前先读目标函数签名、调用者和仓库内相似实现。不要把通用软件工程偏好强加给经过实机调优的桌面自动化代码。

## 按任务读取

- 修改 `auto.*`、`ImageUtils.*`、OCR、UI 定位、重试或自动化流程：读取 `references/automation-design.md`。
- 修改任务线程、启动/停止、模拟器等待、PyQt UI、语言/主题或配置：读取 `references/lifecycle-ui.md`。
- 重放用户截图与模板：加载 `replay-matching` skill（含 `debug_tools/verify_matching.py` 用法）。技术细节参阅 `.opencode/reference/replay_matching.md`。
- 新增或修改 `debug_*`：再读取仓库 `.opencode/tools/debug_model_constitution.md`。

只读取命中的 reference。

## 核心工作流

1. 确认真实失败状态、UI 层级和调用链。
2. 查目标 API 默认值、搜索区域、模板裁剪和同类代码。
3. 选择能解释根因的最小修改，不靠堆参数试错。
4. 保持调用栈平坦；没有现实复用需求时不新增抽象层。
5. 运行与改动最相关的语法、lint、测试或重放验证。
6. 审阅 diff 是否比问题本身复杂，删除仅由本次改动产生的冗余。

## 约束

- 不重新实例化项目单例。
- 不将用户 `config.yaml` 当作模板或同步目标。
- 不使用强制线程终止替代协作式停止。
- 不把“通常如此”的图片匹配经验当成未经验证的确定事实。
- 不修改与任务无关的遗留代码。
