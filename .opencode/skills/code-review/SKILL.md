---
name: code-review
description: Use when reviewing AALC code changes, pull requests, commits, branches, staged diffs, or uncommitted work for defects, regressions, security risks, and maintainability issues.
license: AGPL-3.0
compatibility: opencode
metadata:
  audience: maintainers
  workflow: review
---

# AALC Code Review

## Goal

Review changed behavior first. Findings must lead the response, ordered by severity,
with file and line references. Do not fix code unless the user explicitly asks for a
separate fix step.

## Resolve the review target

| User intent | Context to collect |
|---|---|
| Current or uncommitted changes | `git status --short`, `git diff --stat`, `git diff`, plus staged diff. |
| Staged changes | `git diff --cached --stat`, `git diff --cached`. |
| Commit hash | `git show --stat <hash>`, `git show <hash>`. |
| Branch | `git log <base>..<branch>`, `git diff <base>...<branch> --stat`, full diff. |
| Pull request | `gh pr view`, `gh pr diff`, and any user-provided context. |

If no target is specified, review uncommitted and staged changes.

## Delegation

Use the OpenCode `code-reviewer` subagent when the current environment exposes subagent
or task delegation. The agent definition is project-local at `.opencode/agents/code-reviewer.md`.

If delegation is unavailable, perform the review synchronously with the same rubric. Do
not tell the user that an async review has started unless a subagent was actually
dispatched.

Subagent prompt should be self-contained:

```text
Review the following AALC changes.

Target: <review target>

<git status/stat/log/diff>

Extra context:
<user notes or constraints>
```

## Review rules

- Review only changed lines and behavior directly impacted by the change.
- Prioritize confirmed bugs, regressions, security issues, data loss, crashes, and
  missing tests.
- Separate confirmed defects from design observations.
- Calibrate severity: High requires a realistic user- or system-impacting failure.
- Do not critique unrelated legacy code unless the change now depends on it.
- Keep technical symbols, paths, functions, and class names unchanged.
- Use Chinese for the user-facing report.

## Output

Use this order:

```markdown
## 发现
- [严重度] 文件:行 — 问题、触发条件、影响、建议。

## 疑问或假设
- 只有在影响结论时列出。

## 变更概览
- 简短说明审阅范围。

## 验证缺口
- 未运行或仍需运行的测试、lint、构建。
```

If no issues are found, say so clearly and mention any remaining test gap or residual
risk.
