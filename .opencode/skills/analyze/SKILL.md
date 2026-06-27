---
name: analyze
description: Use when diagnosing AALC issue reports, local issue archives, logs, screenshots, stuck flows, crashes, misclicks, or asset-matching failures to distinguish configuration, known-version, evidence, and code defects.
license: AGPL-3.0
compatibility: opencode
metadata:
  audience: maintainers
  workflow: debugging
---

# AALC Issue and Log Analysis

## Core stance

Most archived issue data comes from released upstream builds. Do not assume canary-only
debug switches, special capture/input modes, custom themes, or local developer tooling
unless the issue body, config, or logs explicitly show them.

Treat every diagnosis as evidence-first:

1. Identify what data exists.
2. Extract runtime version and configuration from evidence.
3. Decide whether the symptom is configuration, already-fixed version drift, missing
   evidence, asset/template drift, or a code bug.
4. Only then trace code and propose a fix.

## Inputs to inspect

- Local archive: `issues/<id>/metadata.json`, `meta_info.txt`, `dev_notes.md`,
  `extracted_config.yaml`, logs, screenshots.
- GitHub issue: issue body, comments, attached logs, screenshots, and release version.
- Deterministic reports: files produced by `.opencode/tools/log_analyzer.py`,
  `.opencode/tools/mirror_analyzer.py`, or CI triage.

Never modify or delete issue archives, logs, screenshots, reports, or config snapshots.

## Progressive references

- Large logs: run `.opencode/tools/log_analyzer.py` instead of printing the whole log.
- Mirror-specific reports: use `.opencode/tools/mirror_analyzer.py` when present.
- User screenshots or template-matching claims: load the `replay-matching` skill which
  covers `debug_tools/verify_matching.py` usage, pipeline simulation, and links to
  `.opencode/reference/replay_matching.md` for technical details.
- Interactive inspection: use `.opencode/tools/match_viewer.py` only when a visual
  matching question remains after CLI checks.

Do not load replay-matching references when the issue has no screenshot or
template-matching question.

## Workflow

### 1. Build the evidence matrix

Record these facts before forming a conclusion:

| Fact | Rule |
|---|---|
| AALC version | Use the last version occurrence in logs, not only the header. |
| Runtime mode | Extract from config/logs; do not assume special capture/input modes. |
| Feature path | Identify mirror, luxcavation, daily task, synthesis, start-up, or updater. |
| User symptom | Preserve the user's wording, then map it to observable markers. |
| Config keys | Check only keys that explain this symptom, such as skip flags or input mode. |
| Timeline | Segment by timestamp and map each claim to the supporting segment. |

If issue text, logs, and prior comments conflict, call out the contradiction and lower
confidence.

### 2. Check configuration and version first

Before proposing code changes, ask:

- Does a config value directly explain the symptom?
- Is the user running a version older than the latest release that already contains a fix?
- Is the relevant code path absent or rewritten on current main?

If the answer is yes, report configuration guidance or upgrade guidance instead of a
code-fix plan.

### 3. Read logs narrowly

Use this order:

1. Head: read the first small chunk for version, config, and startup mode.
2. Tail: read the ending chunk for crash, stop, recovery, or the final loop.
3. Targeted search: grep the timestamp range, asset name, function, or marker.
4. Analyzer: for very large logs, generate a compact report:

```powershell
uv run python .opencode/tools/log_analyzer.py <log_path>
```

Do not paste huge terminal output. Read generated UTF-8 reports as files.

### 4. Replay template matching only with screenshots

If the user supplied a screenshot or the symptom depends on template matching, load the
`replay-matching` skill for full tool usage and pipeline instructions.

Key commands:

```powershell
uv run python debug_tools/verify_matching.py <screenshot.png> --minimal --models clam aggressive
uv run python debug_tools/verify_matching.py <problem.png> --compare <normal.png> --minimal
uv run python debug_tools/verify_matching.py <screenshot.png> --pixel X Y W H
```

Follow `.opencode/reference/replay_matching.md` for scale, bbox, crop, and
`ImageUtils.match_template()` rules. Do not substitute raw `cv2.matchTemplate()` for
project matching behavior.

### 5. Trace code only after evidence points to code

- Map log file/line markers to source.
- Read the smallest relevant function or call chain.
- Search for callers and same-pattern implementations.
- Prefer the smallest behavior-preserving fix.

If the user's version differs from current code, verify against the relevant release or
tag before calling current-main code a fix.

## Common evidence patterns

| Pattern | Evidence shape | Likely conclusion |
|---|---|---|
| Instant start/end | `开始执行 X` and `结束执行 X` have near-identical timestamps | Config skip or unmet precondition. |
| Tight polling loop | Same file/line/asset repeated many times | Loop escape condition blocked or wrong state detection. |
| Asset mismatch | High match for context asset but low action button match | UI/theme/font/resolution drift or overlay. |
| Recovery loop | Timeout triggers kill/restart/retry repeatedly | Game/window/screenshot source instability. |
| Emulator disconnect | IPC disconnect plus traceback | Runtime environment failure; code should recover gracefully if path supports it. |
| Version drift | User version older than latest fixed release | Recommend upgrade before writing code. |

## Output shape

Use this structure:

```markdown
## 问题概要

## 环境
- AALC 版本:
- 运行模式:
- 功能场景:
- 证据来源:

## 关键证据
- 日志/配置/截图证据，附具体行或文件名。

## 根因分析
- 配置、版本、模板匹配、运行环境或代码路径的判断。

## 修复建议
- 最小修复、升级建议、配置建议或需要补充的信息。

## 置信度
- 高 / 中 / 低，并说明缺口。
```

For code references in public issue comments, prefer GitHub blob links with exact lines.
