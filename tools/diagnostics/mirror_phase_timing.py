"""Attribute one native mirror recording's wall time to phases, floors and battle turns."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PHASES = (
    (re.compile(r"^mirror\.route\."), "寻路"),
    (re.compile(r"^mirror\.theme\.|^mirror\.floor"), "主题包"),
    (re.compile(r"^mirror\.shop\."), "商店"),
    (re.compile(r"^mirror\.reward\."), "奖励"),
    (re.compile(r"^mirror\.event\.|^battle\.event\."), "事件"),
    (re.compile(r"^mirror\.formation\.|^battle\.start|^battle\.formation"), "编队开战"),
    (re.compile(r"^battle\.mirror-exit|^battle\.settlement|^battle\.confirm-settlement"), "战斗收尾"),
    (re.compile(r"^battle\."), "战斗"),
    (re.compile(r"^mirror\.settlement\."), "结算"),
    (re.compile(r"^mirror\.(run|entry|star|gift)"), "入口"),
)
SKIPPED = {"automation.observe", "automation.ocr", "automation.delay"}
INPUTS = {"Click", "Key", "Drag"}
FLOOR = re.compile(r"第\s*(\d+)\s*层")


def normalize(event: dict) -> dict:
    return {key[0].lower() + key[1:]: value for key, value in event.items()}


def read_events(recording: Path) -> list[dict]:
    with (recording / "events.jsonl").open(encoding="utf-8") as handle:
        return [normalize(json.loads(line)) for line in handle if line.strip()]


def phase_of(rule: str) -> str | None:
    return next((name for pattern, name in PHASES if pattern.search(rule)), None)


def duration_of(event: dict, field: str = "durationMilliseconds") -> float:
    try:
        value = json.loads(event.get("detail") or "{}").get(field)
    except json.JSONDecodeError:
        return 0.0
    return value if isinstance(value, (int, float)) else 0.0


def segments(events: list[dict]) -> list[dict]:
    """Split the run wherever the phase changes; each span ends at the next span's first event."""
    spans: list[dict] = []
    floor = None
    for event in events:
        rule, at = event["rule"], event["elapsedMilliseconds"]
        if event["action"] == "Progress" and rule == "mirror.floor" and (match := FLOOR.search(event.get("detail") or "")):
            floor = int(match[1])
        phase = None if rule in SKIPPED else phase_of(rule)
        if phase and (not spans or spans[-1]["phase"] != phase):
            spans.append({"phase": phase, "floor": floor, "start": at, "startFrame": event["frameId"], "end": at,
                          "frames": 0, "observe": 0.0, "ocr": 0.0, "ocrCalls": 0, "delay": 0.0, "inputs": Counter()})
        if not spans:
            continue
        span = spans[-1]
        span["end"] = at
        if rule == "automation.observe":
            span["frames"] += 1
            span["observe"] += duration_of(event)
        elif rule == "automation.ocr":
            span["ocr"] += duration_of(event)
            span["ocrCalls"] += 1
        elif rule == "automation.delay":
            span["delay"] += duration_of(event)
        if event["action"] in INPUTS:
            span["inputs"][rule] += 1
    for current, following in zip(spans, spans[1:]):
        current["end"] = following["start"]
    return spans


def battle_turns(events: list[dict]) -> list[dict]:
    """Per turn: decide = turn start to committed input; resolve = commit to next turn or battle exit."""
    marks = [event for event in events if event["rule"] in {"battle.turn", "battle.commit-turn", "battle.chain-commit", "battle.mirror-exit"}
             and event["action"] in {"Progress", "Sent"}]
    turns: list[dict] = []
    for event in marks:
        if event["rule"] == "battle.turn":
            turns.append({"start": event["elapsedMilliseconds"], "frame": event["frameId"], "commit": None, "end": None})
            if len(turns) > 1 and turns[-2]["end"] is None:
                turns[-2]["end"] = event["elapsedMilliseconds"]
        elif event["rule"] == "battle.mirror-exit":
            if turns and turns[-1]["end"] is None:
                turns[-1]["end"] = event["elapsedMilliseconds"]
        elif turns:
            turns[-1]["commit"] = event["elapsedMilliseconds"]
    return turns


def repeated_inputs(events: list[dict], window: float = 8000, limit: int = 3) -> list[dict]:
    """Same rule/target repeated within the window usually means a click that gave no feedback."""
    found, history = [], defaultdict(list)
    for event in events:
        if event["action"] not in INPUTS:
            continue
        key = (event["rule"], str(event.get("target")))
        times = history[key]
        times.append(event["elapsedMilliseconds"])
        recent = [at for at in times if event["elapsedMilliseconds"] - at <= window]
        if len(recent) >= limit:
            found.append({"rule": key[0], "target": key[1], "frame": event["frameId"],
                          "at": event["elapsedMilliseconds"], "count": len(recent)})
    return found


def seconds(value: float) -> str:
    return f"{value / 1000:.1f}"


def report(recording: Path, top: int) -> str:
    events = read_events(recording)
    spans = segments(events)
    result_path = recording / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8-sig")) if result_path.is_file() else {}
    result = normalize(result) if result else {}
    total = result.get("elapsedMilliseconds") or max(event["elapsedMilliseconds"] for event in events)
    if spans:
        spans[-1]["end"] = total
    lines = [f"# 镜牢耗时 {recording.name}", "",
             f"结果：{result.get('outcome', '未结束')} {result.get('reason', '')}；总耗时 {seconds(total)} s；帧 {sum(s['frames'] for s in spans)}；输入 {sum(sum(s['inputs'].values()) for s in spans)}", ""]
    totals = defaultdict(lambda: Counter())
    for span in spans:
        row = totals[span["phase"]]
        row["wall"] += span["end"] - span["start"]
        row["count"] += 1
        for name in ("frames", "observe", "ocr", "ocrCalls", "delay"):
            row[name] += span[name]
        row["inputs"] += sum(span["inputs"].values())
    lines += ["| 环节 | 次数 | 耗时 s | 占比 | 帧 | 观察 s | OCR s | OCR 次 | 显式等待 s | 输入 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for phase, row in sorted(totals.items(), key=lambda item: -item[1]["wall"]):
        lines.append(f"| {phase} | {row['count']} | {seconds(row['wall'])} | {row['wall'] / total:.1%} | {row['frames']} | {seconds(row['observe'])} | {seconds(row['ocr'])} | {row['ocrCalls']} | {seconds(row['delay'])} | {row['inputs']} |")
    floors = defaultdict(Counter)
    for span in spans:
        floors[span["floor"]][span["phase"]] += span["end"] - span["start"]
    lines += ["", "## 分层", "", "| 层 | 合计 s | 明细 s |", "|---|---:|---|"]
    for floor, row in sorted(floors.items(), key=lambda item: (item[0] is None, item[0] or 0)):
        detail = "、".join(f"{name} {seconds(value)}" for name, value in row.most_common())
        lines.append(f"| {floor if floor is not None else '首层/未知'} | {seconds(sum(row.values()))} | {detail} |")
    turns = [turn for turn in battle_turns(events) if turn["end"] is not None]
    if turns:
        decide = [turn["commit"] - turn["start"] for turn in turns if turn["commit"] is not None]
        resolve = [turn["end"] - turn["commit"] for turn in turns if turn["commit"] is not None]
        ordered = sorted(resolve)
        lines += ["", "## 战斗回合", "",
                  f"回合 {len(turns)}；操作段（回合判定到提交）合计 {seconds(sum(decide))} s，均值 {sum(decide) / max(len(decide), 1) / 1000:.2f} s；"
                  f"结算段（提交到下一回合或退出）合计 {seconds(sum(resolve))} s，均值 {sum(resolve) / max(len(resolve), 1) / 1000:.1f} s，P50 {ordered[len(ordered) // 2] / 1000 if ordered else 0:.1f} s，最大 {ordered[-1] / 1000 if ordered else 0:.1f} s"]
    observed = [event["elapsedMilliseconds"] for event in events if event["rule"] == "automation.observe"]
    gaps = sorted(((after - before, before) for before, after in zip(observed, observed[1:])), reverse=True)[:top]
    lines += ["", f"## 最长观察间隔 Top {top}", ""]
    lines += [f"- {gap / 1000:.1f} s，始于 {before / 1000:.1f} s" for gap, before in gaps]
    slow = sorted((span for span in spans if span["phase"] != "战斗"), key=lambda span: span["start"] - span["end"])[:top]
    lines += ["", f"## 非战斗最慢片段 Top {top}", ""]
    lines += [f"- {span['phase']}（层 {span['floor']}，帧 {span['startFrame']} 起，{seconds(span['start'])} s）：{seconds(span['end'] - span['start'])} s，帧 {span['frames']}，观察 {seconds(span['observe'])} s，OCR {seconds(span['ocr'])} s/{span['ocrCalls']} 次，等待 {seconds(span['delay'])} s，输入 {sum(span['inputs'].values())}"
              for span in slow]
    repeats = repeated_inputs(events)
    worst = {}
    for item in repeats:
        worst[(item["rule"], item["target"])] = max(item["count"], worst.get((item["rule"], item["target"]), 0))
    lines += ["", "## 8 秒内重复输入", ""]
    lines += [f"- {rule} {target}：{count} 次" for (rule, target), count in sorted(worst.items(), key=lambda item: -item[1])] or ["无"]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()
    sys.stdout.buffer.write(report(args.recording, args.top).encode("utf-8"))


if __name__ == "__main__":
    main()
