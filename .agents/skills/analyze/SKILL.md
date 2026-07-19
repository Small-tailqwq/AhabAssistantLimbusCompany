---
name: analyze
description: Diagnose AALC issue reports, local issue archives, logs, screenshots, stuck flows, crashes, misclicks, emulator failures, or asset-matching problems by separating configuration, version drift, runtime environment, missing evidence, template drift, and code defects. Use before proposing an issue fix or public diagnosis.
---

# AALC Issue and Log Analysis

Work evidence-first. Do not assume the report came from upstream, downstream, canary, a particular capture backend, or current `main`; establish those facts from issue metadata, config, logs, or release identifiers.

## Preserve evidence

Treat `issues/`, logs, screenshots, extracted config, analyzer reports, and attachments as user assets. Read them narrowly and never delete, move, overwrite, or sanitize them in place. Write derived reports only to the established analysis location.

Do not expose credentials, tokens, cookies, or private values found in logs or config. Redact them from summaries and public comments.

## Progressive references and tools

- Start with issue metadata and existing deterministic reports.
- For large logs, run `.opencode/tools/log_analyzer.py` rather than printing the entire file.
- For mirror-specific evidence, use `.opencode/tools/mirror_analyzer.py`.
- For a screenshot or template-matching claim, load `replay-matching`; it routes to `debug_tools/verify_matching.py` and its pipeline reference.
- Use `.opencode/tools/match_viewer.py` only when a visual question remains after deterministic replay.

Do not load matching references for issues unrelated to screenshots or templates.

## Phase 1: Inventory evidence

Record available and missing sources:

| Fact | Evidence rule |
|---|---|
| Repository/channel | Infer only from explicit version, build, remote, or feature evidence |
| Runtime version | Determine per relevant run/session; a later appended run must not overwrite the version of an earlier incident |
| Runtime mode | Extract capture/input/emulator/theme/language settings that explain this symptom |
| Feature path | Identify the actual task and stage from markers and call sites |
| User symptom | Preserve the user's wording, then map it to observable events |
| Timeline | Segment by timestamps, restarts, and separate executions |
| Config | Inspect only keys that can explain the symptom |

If issue text, comments, config, and logs conflict, state the contradiction and lower confidence.

## Phase 2: Check configuration and version

Before tracing code, ask:

- Does a relevant config value directly explain the behavior?
- Did the incident occur on a version older than a verified fix?
- Is the relevant code path different on that version or channel?
- Is the failure caused by emulator, window, capture, or external runtime state?

Compare against the release or tag that produced the evidence. Do not diagnose current-main code as though it generated an older log.

## Phase 3: Read logs narrowly

Use this order:

1. read a small head section for startup, version, and mode;
2. read the relevant tail for failure, stop, recovery, or final loop;
3. search exact timestamps, asset keys, file/line markers, exceptions, and stage markers;
4. run analyzers for large or repeated logs;
5. return to raw logs only around report anchors.

```powershell
uv run python .opencode/tools/log_analyzer.py <log_path>
```

Quote only the minimum lines needed to support a conclusion. Never generalize from one session to all appended sessions.

## Phase 4: Replay matching only when relevant

Load `replay-matching` when the issue includes a screenshot or depends on template matching. Common commands include:

```powershell
uv run python debug_tools/verify_matching.py <screenshot.png> --minimal --models clam aggressive
uv run python debug_tools/verify_matching.py <problem.png> --compare <normal.png> --minimal
uv run python debug_tools/verify_matching.py <screenshot.png> --pixel X Y W H
```

Use the project's complete matching pipeline. Do not replace it with raw `cv2.matchTemplate()`.

## Phase 5: Trace code after evidence points to it

1. map log markers to the exact source version;
2. read the smallest relevant call chain and direct callers;
3. inspect the actual API signatures and nearby patterns;
4. identify a behavioral oracle that fails before the fix;
5. propose the smallest behavior-preserving change.

Do not implement a fix unless the user's request includes implementation.

## Evidence patterns

| Pattern | Likely direction |
|---|---|
| Start/end markers at nearly the same timestamp | configuration skip or unmet precondition |
| Repeated identical file/line/asset markers | blocked escape condition or state detection |
| Context asset matches but action asset does not | UI/theme/language/resolution/overlay drift |
| Timeout followed by repeated restart | window, game, emulator, or capture instability |
| IPC disconnect and traceback | runtime failure; inspect intended recovery contract |
| Incident version predates a verified released fix | upgrade guidance before new code |

These are hypotheses, not conclusions. Tie each diagnosis to concrete evidence.

## Output

```markdown
## 问题概要

## 环境
- 仓库/通道与版本：
- 运行模式：
- 功能场景：
- 证据来源与缺口：

## 关键证据
- 文件、时间段和最小必要日志行：

## 根因分析
- 配置 / 版本 / 运行环境 / 模板匹配 / 代码路径：

## 修复或处置建议
- 最小修复、升级、配置、重试或补充证据：

## 置信度
- 高 / 中 / 低及原因：
```

For public issue comments, use exact GitHub blob links when source lines are cited and avoid leaking local paths or private log values.
