"""Summarize native .NET recordings without changing their source files."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

INPUT_ACTIONS = ("Click", "Key", "Drag")
REVIEW_RULE = re.compile(r"retry|recover|try.again", re.IGNORECASE)
TIMING_RULES = {
    "automation.observe": "截图与模板观察",
    "automation.ocr": "OCR",
    "automation.delay": "显式等待",
}


def read_jsonl(path: Path, warnings: list[str]) -> list[dict]:
    """Read one snapshot; only an invalid, unterminated final line is tolerated."""
    data = path.read_bytes()
    lines = data.splitlines(keepends=True)
    records = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            if number == len(lines) and not line.endswith((b"\n", b"\r")):
                warnings.append(f"{path}: 忽略最后一个未完成行（第 {number} 行）")
                break
            raise ValueError(f"{path}:{number}: JSON 无效") from None  # noqa: TRY003
        if not isinstance(record, dict):
            raise TypeError(f"{path}:{number}: 应为 JSON 对象")  # noqa: TRY003
        records.append(record)
    return records


def elapsed(event: dict) -> float | None:
    value = event.get("elapsedMilliseconds")
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def difference(start: float | None, end: float | None) -> float | None:
    return round(end - start, 4) if start is not None and end is not None and end >= start else None


def compact(event: dict) -> dict:
    return {key: event.get(key) for key in (
        "runId", "frameId", "stage", "rule", "action", "target", "elapsedMilliseconds", "detail"
    )}


def sequence_for(recording: Path) -> Path | None:
    for directory in (recording, *recording.parents):
        candidate = directory / "sequence.jsonl"
        if candidate.is_file():
            return candidate
    return None


def automation_timings(events: list[dict]) -> dict:
    timings = {}
    for rule in TIMING_RULES:
        selected = [event for event in events if event.get("rule") == rule]
        details = [json.loads(event["detail"]) for event in selected if event.get("detail")]
        fields = ["durationMilliseconds"]
        if rule == "automation.delay":
            fields.append("requestedMilliseconds")
        totals = {"eventCount": len(selected)}
        for field in fields:
            values = [detail[field] for detail in details if isinstance(detail, dict)
                      and isinstance(detail.get(field), (int, float))
                      and not isinstance(detail[field], bool)]
            totals[field] = {
                "total": round(sum(values), 4) if values else None,
                "sampleCount": len(values),
                "unmeasuredEventCount": len(selected) - len(values),
            }
        timings[rule] = totals
    return timings


def summarize(recording: Path) -> tuple[dict, list[dict]]:
    warnings: list[str] = []
    events = read_jsonl(recording / "events.jsonl", warnings)
    result_path = recording / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8-sig")) if result_path.is_file() else None
    sequence_path = sequence_for(recording)
    sequence = read_jsonl(sequence_path, warnings) if sequence_path else []
    actions: list[dict] = []
    pending = defaultdict(deque)
    unmatched_sent = []
    progress = []
    review = []
    for index, event in enumerate(events, 1):
        action = event.get("action")
        key = (event.get("runId"), event.get("frameId"), event.get("rule"), event.get("target"))
        if action in INPUT_ACTIONS:
            row = {
                "recording": str(recording), "eventIndex": index,
                **{name: event.get(name) for name in ("runId", "frameId", "stage", "rule", "action", "target")},
                "startMilliseconds": elapsed(event), "sentMilliseconds": None,
                "durationMilliseconds": None, "status": "unconfirmed",
            }
            actions.append(row)
            pending[key].append(row)
        elif action == "Sent":
            if pending[key]:
                row = pending[key].popleft()
                row["sentMilliseconds"] = elapsed(event)
                row["durationMilliseconds"] = difference(row["startMilliseconds"], elapsed(event))
                row["status"] = "sent"
            else:
                unmatched_sent.append({"eventIndex": index, **compact(event)})
        if action == "Progress":
            progress.append({"eventIndex": index, **compact(event)})
        if REVIEW_RULE.search(str(event.get("rule", ""))):
            review.append({"eventIndex": index, **compact(event)})

    observed_times = [value for event in events if (value := elapsed(event)) is not None]
    observed_until = max(observed_times, default=None)
    duration = elapsed(result) if result else None
    for index, stage in enumerate(progress):
        next_time = elapsed(progress[index + 1]) if index + 1 < len(progress) else duration
        stage["untilNextProgressMilliseconds"] = difference(elapsed(stage), next_time)
    durations = [row["durationMilliseconds"] for row in actions if row["durationMilliseconds"] is not None]
    counts = Counter(row["action"] for row in actions)
    summary = {
        "recording": str(recording), "result": result,
        "status": result.get("outcome", "unknown") if result else "unfinished",
        "durationMilliseconds": duration, "observedUntilMilliseconds": observed_until,
        "eventCount": len(events), "actionCounts": {name: counts[name] for name in INPUT_ACTIONS},
        "confirmedInputCount": sum(row["status"] == "sent" for row in actions),
        "unconfirmedInputs": [row for row in actions if row["status"] == "unconfirmed"],
        "unmatchedSent": unmatched_sent,
        "measuredInputMilliseconds": round(sum(durations), 4),
        "inputDurationSampleCount": len(durations),
        "automationTimings": automation_timings(events),
        "progress": progress, "retryRecoveryEvents": review,
        "sequencePath": str(sequence_path) if sequence_path else None, "sequence": sequence,
        "warnings": warnings,
    }
    return summary, actions


def seconds(value: float | None) -> str:
    return "未知" if value is None else f"{value / 1000:.3f} s"


def report_for(runs: list[dict], actions: list[dict]) -> str:
    lines = ["# .NET 运行日志统计", "",
             "耗时取自 elapsedMilliseconds。输入耗时为同 runId/frameId/rule/target 的输入到 Sent 的顺序配对差值；Sent 表示输入调用返回。",
             "Progress 区间截止下一条 Progress，末段仅在 result 提供耗时时结算。未结束记录只列已观测时间。", ""]
    for run in runs:
        lines.extend([f"## {run['recording']}", "",
                      f"- 结果：{run['status']}；总耗时：{seconds(run['durationMilliseconds'])}；已观测至：{seconds(run['observedUntilMilliseconds'])}",
                      f"- 输入：{run['actionCounts']}；未确认：{len(run['unconfirmedInputs'])}；未配对 Sent：{len(run['unmatchedSent'])}",
                      f"- 已测输入耗时合计：{seconds(run['measuredInputMilliseconds'])}（{run['inputDurationSampleCount']} 次）；重试/恢复事件：{len(run['retryRecoveryEvents'])}"])
        if run["result"] and run["result"].get("reason"):
            lines.append(f"- 原因：{run['result']['reason']}")
        for rule, label in TIMING_RULES.items():
            timing = run["automationTimings"][rule]
            measurement = timing["durationMilliseconds"]
            value = seconds(measurement["total"]) if measurement["sampleCount"] else "未采集"
            lines.append(f"- {label}耗时：{value}（已采集 {measurement['sampleCount']}/{timing['eventCount']} 条事件）")
            if rule == "automation.delay":
                requested = timing["requestedMilliseconds"]
                value = seconds(requested["total"]) if requested["sampleCount"] else "未采集"
                lines.append(f"- 显式等待请求时长：{value}（已采集 {requested['sampleCount']}/{timing['eventCount']} 条事件）")
        for stage in run["progress"]:
            lines.append(f"- 阶段 {stage['rule']}：{seconds(elapsed(stage))}；区间 {seconds(stage['untilNextProgressMilliseconds'])}")
        lines.extend(f"- 注意：{warning}" for warning in run["warnings"])
        longest = sorted((row for row in actions if row["recording"] == run["recording"]
                          and row["durationMilliseconds"] is not None),
                         key=lambda row: row["durationMilliseconds"], reverse=True)[:5]
        lines.extend(["", "耗时审查候选（输入调用耗时最大的 5 次）：", ""])
        lines.extend(f"- frame {row['frameId']} {row['rule']} {row['action']} {row['target']}：{seconds(row['durationMilliseconds'])}"
                     for row in longest)
        lines.append("")
    lines.extend(["重试/恢复事件按规则名 retry/recover/try.again 筛选，原事件保存在 summary.json，供人工审查。",
                  "输入耗时包含输入后等待；具体优化应结合阶段区间和原始事件核查。未知耗时保留 null。", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="原生录制目录或包含多轮录制的根目录")
    parser.add_argument("--output", required=True, type=Path, help="派生报告目录；已有报告不会覆盖")
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    paths = [output / name for name in ("summary.json", "actions.csv", "report.md")]
    if any(path.exists() for path in paths):
        parser.error("输出报告已存在，请指定新的输出目录")
    recordings = sorted({path.parent for path in source.rglob("events.jsonl")})
    if not recordings:
        parser.error(f"未找到 events.jsonl：{source}")
    runs, actions = [], []
    for recording in recordings:
        run, rows = summarize(recording)
        runs.append(run)
        actions.extend(rows)
    output.mkdir(parents=True, exist_ok=True)
    summary = {"generatedAt": datetime.now(timezone.utc).isoformat(), "source": str(source), "runs": runs}
    paths[0].write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fields = ["recording", "eventIndex", "runId", "frameId", "stage", "rule", "action", "target",
              "startMilliseconds", "sentMilliseconds", "durationMilliseconds", "status"]
    with paths[1].open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(actions)
    paths[2].write_text(report_for(runs, actions), encoding="utf-8")
    sys.stdout.write(f"{len(runs)} runs, {len(actions)} inputs: {output}\n")


if __name__ == "__main__":
    main()
