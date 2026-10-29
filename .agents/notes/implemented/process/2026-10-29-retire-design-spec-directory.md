# Agent Note: 历史设计目录整体迁入 Agent Notes 并禁止回流

Status: implemented

## 问题

`docs/superpowers/specs/` 中的设计文档混合了已落地的决定、实施步骤、未实现的计划和过期的行号引用。按主题逐步迁移时，同一决定同时存在于旧设计和笔记中，读者需要逐份判断哪份描述当前代码；未实现的方案也容易被当作待办或现行契约。

## 决策

`docs/superpowers/specs/` 已整体移除，并列入 [agent-notes.config.json](../../agent-notes.config.json) 的 `forbiddenRoots`，门禁拒绝新文件写回该目录。

仍约束当前代码的设计按实现核对后转写为 implemented 笔记：

- [启动后等待主界面](../bug-fix/2026-06-23-startup-main-menu-wait.md)
- [MuMu IPC 启动恢复](../bug-fix/2026-07-16-mumu-ipc-startup-recovery.md)
- [快速截图](../feature/2026-06-12-quick-screenshot.md)
- [雷蛇驱动输入](../feature/2026-06-22-razer-driver-input.md)
- [HDR 提示](../feature/2026-07-20-hdr-warning.md)，合并了独立检测工具与主程序提示两份设计
- [资产管理](../feature/2026-04-30-asset-manager.md)
- [发行包压缩](2026-04-30-bundle-size-optimization.md)

匹配诊断工具的设计只描述工具结构，没有长期取舍，不建笔记。图像匹配与 OCR 性能优化、主线 mini 镜牢节点识别两份设计没有在 Python 代码中实现，不建笔记；原文保留在 Git 历史中。

## 曾考虑的替代方案

**继续按相关主题维护时迁移。** 这是[采纳 Agent Notes](2026-10-23-adopt-agent-notes.md)时的范围。旧设计长期与笔记并存，读者仍需判断哪份是当前依据，因此一次性核对并移除目录。

**未实现的设计转为 proposed 或 rejected 笔记。** proposed 需要仍打算推进的提案和验收标准，rejected 需要真实的否决理由；两份设计均无继续推进的计划，也没有记录否决原因，转写只会制造无主提案或编造理由。

## 后果

当前依据只在活跃笔记中维护，设计目录的历史版本需要通过 Git 查看。未实现的性能与主线寻路方案只保存在 Git 历史中，重新考虑时需要从 Git 历史取回并按当前代码重新评估。
