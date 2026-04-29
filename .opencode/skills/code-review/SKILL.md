---
name: code-review
description: 异步代码审阅 — 通过 Task tool 派发子 agent 审阅代码，主 agent 不阻塞，审阅完成后汇报中文报告
---

# 异步代码审阅 Skill

## 触发条件

用户消息包含以下意图时触发：
- 明确请求：「审阅」「review」「代码审查」「检查代码」「帮我看看代码」「CR」
- 组合请求：「审阅当前改动」「review 这个分支」「检查最近的提交」「审阅 PR #123」
- `/review` 命令也可路由到此 skill（替代原有阻塞模式）

## 核心流程

```
1. 解析用户意图 → 确定审阅目标
2. 收集 git 上下文（diff、stat、log）
3. Task tool 派发 code-reviewer 子 agent
4. 告知用户「审阅已启动，可继续操作」
5. 子 agent 返回结果 → 主 agent 翻译汇报
```

## 第一步：解析审阅目标

从用户输入中提取审阅范围：

| 输入特征 | 动作 |
|---------|------|
| 提交 hash（40 字符或短 hash） | `git show <hash>` |
| 分支名（`fix/` `feature/` 等） | `git log main..<branch>` + `git diff main...<branch>` |
| PR 编号或 GitHub URL | `gh pr view` + `gh pr diff` |
| 「当前」「未提交」「暂存」 | `git diff` + `git diff --cached` |
| 空/无明确目标 | 默认审阅未提交改动 |

**自然语言识别（中文）：**
- 含「分支」+「检查/审阅/review」→ 提取分支名，按分支处理
- 含「提交」+ hash 片段 → 按提交处理
- 含「所有提交」+ 分支名 → `git log <base>..<branch>`，逐 commit 审阅
- 含「PR」+ 编号 → 按 PR 处理

## 第二步：收集 git 上下文

根据审阅目标，收集必要信息并填入模板变量：

```bash
# 示例：审阅未提交改动
git diff --stat
git diff
git diff --cached --stat
git diff --cached
git status --short

# 示例：审阅分支
git log --oneline main..feature/xxx
git diff main...feature/xxx --stat
git diff main...feature/xxx
```

## 第三步：Task tool 派发

使用 Task tool 派发 `code-reviewer` 专用子 agent：

- `description`: "代码审阅" 或 "Review: <简要描述>"
- `subagent_type`: "code-reviewer"
- `prompt`: 仅包含审阅上下文（agent 有独立系统提示词，无需重复）：

**prompt 示例：**
```
Review the following changes.

Target: {REVIEW_TARGET}

{GIT_STAT}

{GIT_LOG}

{GIT_DIFF}

{EXTRA_CONTEXT}
```

> **防递归保障**：`code-reviewer` agent 在 `permission` 中硬性配置了 `task: "*": deny`，无法派发子 agent。
> agent 的系统提示词替代了默认 provider prompt，不包含 skill 系统指令。

## 第四步：告知用户

派发成功后，输出简短提示：
```
审阅已启动（子 agent: <task_id>），你可以继续其他操作。完成后我会汇报结果。
```

## 第五步：结果汇报

子 agent 返回英文审阅报告后，主 agent 负责翻译并汇报：

1. **翻译审阅报告为中文**，保持技术符号（函数名、类名、文件路径）原文
2. **保留严重度标签**：High → 高，Medium → 中，Low → 低
3. **保留原始结构**：🧠 总体评估 / 🚨 严重问题 / ⚠️ 设计观察 / 💡 重构建议
4. 补充结论：
   - 无重大问题时：> ✅ 未发现严重问题，代码质量良好。
   - 有严重问题时：> ⚠️ 发现 <N> 个严重问题，建议优先修复。

## 语言规则

- 所有与用户的交互用中文
- 子 agent 输出英文（英文母版 prompt，模型兼容性最佳）
- 主 agent 将英文报告翻译为中文后汇报给用户
- 技术符号（函数名、类名、文件路径）保持原文不翻译

## 与旧 /review 命令的关系

- `/review` 命令（`commands/review.md`）保留作为同步备用（中文输出）
- 本 skill 提供更智能的异步路径：自动触发、不阻塞、主 agent 翻译汇报
- 本 skill 的子 agent 使用英文母版 prompt，审阅质量更高（含 CoT 推理链、严重度校准）

## 注意事项

- `code-reviewer` agent 有独立系统提示词，不继承主 agent 的 skill 系统
- `permission.task: "*": deny` 硬性禁止子 agent 派发下级 agent（防递归）
- `permission.edit: deny` 硬性禁止子 agent 修改文件
- 审阅结果是分析报告，不是修复任务
- 除非用户明确说「修复」「改」「应用」，否则主 agent 不做文件修改
- 如果用户在审阅期间提出新需求，主 agent 正常响应，审阅在后台继续
- 用户也可直接 `@code-reviewer` 调用此 agent
