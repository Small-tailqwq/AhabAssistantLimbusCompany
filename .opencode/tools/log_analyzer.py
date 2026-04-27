"""
AALC Log Compression Analyzer
=============================
Compresses massive AALC debug logs into a concise report.
Saves output to <log_path>.report.txt (UTF-8).

Usage:
    python log_analyzer.py <log_path>
"""

import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


class LogCompressor:
    def __init__(self):
        self.pattern_stats: Counter = Counter()
        self.pattern_examples: dict[str, str] = {}

    def normalize(self, line: str) -> tuple[str, str]:
        raw = line.strip()
        body = re.sub(
            r'^\[\w+\] \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+ \[AALC\] ',
            '', raw
        )
        body = re.sub(r'\.\.[\\/]\.\.[\\/]', '', body)  # normalize ..\..\ to empty
        body_norm = re.sub(r'np\.int64\(\d+\)', 'np.int64(N)', body)
        body_norm = re.sub(r'\u76f8\u4f3c\u5ea6\uff1a[\d.]+', '\u76f8\u4f3c\u5ea6\uff1aS', body_norm)
        body_norm = re.sub(r'\u70b9\u51fb\u4f4d\u7f6e:\(\d+,\d+\)', '\u70b9\u51fb\u4f4d\u7f6e:(X,Y)', body_norm)
        body_norm = re.sub(r'\u70b9\u51fb\u4f4d\u7f6e:\(\d+,\d+,\d+\)', '\u70b9\u51fb\u4f4d\u7f6e:(X,Y,Z)', body_norm)
        body_norm = re.sub(r'\u8def\u5f84: \S+', '\u8def\u5f84: P', body_norm)
        body_norm = re.sub(r'\u7b49\u5f85\u65f6\u95f4[\d.]+', '\u7b49\u5f85\u65f6\u95f4T', body_norm)
        body_norm = re.sub(r'\u589e\u52a0\u4e3a[\d.]+', '\u589e\u52a0\u4e3aT', body_norm)
        body_norm = re.sub(r'\u76ee\u6807\u4f4d\u7f6e\uff1a\([\d., np.int64()]+\)', '\u76ee\u6807\u4f4d\u7f6e\uff1a(X,Y)', body_norm)
        summary = body_norm[:120] + "..." if len(body_norm) > 120 else body_norm
        return body_norm, summary

    def feed(self, line: str):
        key, summary = self.normalize(line)
        self.pattern_stats[key] += 1
        if key not in self.pattern_examples:
            self.pattern_examples[key] = summary

    def get_top_patterns(self, top_n: int = 40) -> list[tuple[str, int, str]]:
        result = []
        for key, cnt in self.pattern_stats.most_common(top_n):
            result.append((self.pattern_examples[key], cnt, self.pattern_examples[key]))
        return result


def extract_timestamps(lines: list[str]) -> list[datetime | None]:
    result = []
    for line in lines:
        m = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+', line)
        result.append(datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S") if m else None)
    return result


def detect_phases(lines: list[str], timestamps: list[datetime | None]) -> list[dict]:
    def get_module(body: str) -> str:
            # Handle both "tasks/foo.py:123" and "..\..\tasks\foo.py:123"
            m = re.search(r'(?:tasks|module|app|utils)[\\/](\S+?)\.py:\d+', body)
            if m:
                return m.group(0).rsplit(":", 1)[0]
            # Also check for full path
            m = re.search(r'\.\.[\\/]\.\.[\\/](?:tasks|module|app|utils)[\\/](\S+?)\.py:\d+', body)
            if m:
                return m.group(0).rsplit(":", 1)[0]
            return "unknown"

    normalized = []
    for line in lines:
        body = re.sub(r'^\[\w+\] \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+ \[AALC\] ', '', line)
        body = re.sub(r'np\.int64\(\d+\)', 'np.int64(N)', body)
        body = re.sub(r'\u76f8\u4f3c\u5ea6\uff1a[\d.]+', '\u76f8\u4f3c\u5ea6\uff1aS', body)
        body = re.sub(r'\u70b9\u51fb\u4f4d\u7f6e:\(\d+,\d+\)', '\u70b9\u51fb\u4f4d\u7f6e:(X,Y)', body)
        body = re.sub(r'\u76ee\u6807\u4f4d\u7f6e\uff1a\([\d., np.int64()]+\)', '\u76ee\u6807\u4f4d\u7f6e\uff1a(X,Y)', body)
        body = re.sub(r'\u8def\u5f84: \S+', '\u8def\u5f84: P', body)
        normalized.append((body, get_module(body)))

    phases = []
    if not lines:
        return phases

    phase_start = 0
    current_module_focus = None
    WINDOW = 100

    for i in range(0, len(lines), WINDOW):
        window = normalized[i:i+WINDOW]
        if not window:
            break
        module_counts = Counter(m for _, m in window)
        top_module = module_counts.most_common(1)[0][0] if module_counts else "unknown"
        top_ratio = module_counts.most_common(1)[0][1] / len(window) if module_counts else 0

        if top_module == "unknown" and len(module_counts) > 1:
            top_module = module_counts.most_common(2)[1][0]
            top_ratio = module_counts.most_common(2)[1][1] / len(window)

        if current_module_focus is None:
            current_module_focus = top_module
        elif top_module != current_module_focus and top_ratio > 0.3:
            phase_norms = normalized[phase_start:i]
            module_top = Counter(m for _, m in phase_norms).most_common(3)
            phases.append({
                "start": phase_start, "end": i,
                "lines": i - phase_start,
                "time_start": timestamps[phase_start] if phase_start < len(timestamps) else None,
                "time_end": timestamps[min(i-1, len(timestamps)-1)] if i > 0 else None,
                "main_module": current_module_focus,
                "module_breakdown": module_top,
            })
            phase_start = i
            current_module_focus = top_module

    if phase_start < len(lines):
        phase_norms = normalized[phase_start:]
        module_top = Counter(m for _, m in phase_norms).most_common(3)
        phases.append({
            "start": phase_start, "end": len(lines),
            "lines": len(lines) - phase_start,
            "time_start": timestamps[phase_start] if phase_start < len(timestamps) else None,
            "time_end": timestamps[-1] if timestamps else None,
            "main_module": current_module_focus,
            "module_breakdown": module_top,
        })

    return phases


def extract_key_events(lines: list[str]) -> list[tuple[int, str, str]]:
    result = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[ERROR]") or stripped.startswith("[WARNING]") or stripped.startswith("[INFO]") or stripped.startswith("[CRITICAL]"):
            level = stripped[1:].split("]")[0]
            result.append((i+1, level, stripped))
    return result


def extract_special_events(lines: list[str]) -> list[tuple[int, str]]:
    result = []
    for i, line in enumerate(lines):
        if "[DEBUG]" not in line:
            continue
        body = re.sub(r'^\[\w+\] \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+ \[AALC\] ', '', line)
        if re.match(r'^[\.\\/]*(?:tasks|module|app|utils)\S+\.py:\d+:', body):
            continue
        if body.strip():
            result.append((i+1, body.strip()))
    return result


def file_heatmap(lines: list[str]) -> list[tuple[str, int]]:
    counts: Counter = Counter()
    for line in lines:
        for m in re.finditer(r'(?:tasks|module|app|utils)[\\/]\S+?\.py:\d+', line):
            # normalize path separators
            path = m.group(0).replace("\\\\", "/").replace("\\", "/")
            # strip ..\..\ prefix
            path = re.sub(r'^(\.\./)+', '', path)
            counts[path] += 1
    return counts.most_common(30)


def generate_report(log_path: str) -> str:
    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    timestamps = extract_timestamps(lines)
    total_lines = len(lines)
    out = []

    def emit(s=""):
        out.append(s)

    # Header
    valid_ts = [t for t in timestamps if t is not None]
    emit("=" * 72)
    emit(f"  AALC Log Report: {log_path}")
    emit("=" * 72)
    if valid_ts:
        dur = (valid_ts[-1] - valid_ts[0]).total_seconds()
        emit(f"  Lines: {total_lines}  |  Duration: {dur:.0f}s ({dur/60:.1f}min)")
        emit(f"  {valid_ts[0]}  ~  {valid_ts[-1]}")
    else:
        emit(f"  Lines: {total_lines}")
    for i in range(min(4, len(lines))):
        emit(f"  CFG: {lines[i].strip()[:200]}")
    emit()

    # File heatmap
    emit("-" * 72)
    emit("  [File Heatmap]")
    emit("-" * 72)
    for fp, cnt in file_heatmap(lines)[:15]:
        emit(f"  {cnt:>6}x  {fp}")
    emit()

    # Global repeat patterns
    emit("-" * 72)
    emit("  [Global Repeat Patterns] (normalized, coords/timestamps stripped)")
    emit("-" * 72)
    compressor = LogCompressor()
    for line in lines:
        compressor.feed(line)
    for summary, cnt, _ in compressor.get_top_patterns(40):
        if cnt > 1:
            emit(f"  [{cnt:>5}x] {summary}")
    emit()

    # Phases
    emit("-" * 72)
    emit("  [Phases]")
    emit("-" * 72)
    phases = detect_phases(lines, timestamps)
    for idx, ph in enumerate(phases):
        dur_str = ""
        if ph["time_start"] and ph["time_end"]:
            d = (ph["time_end"] - ph["time_start"]).total_seconds()
            dur_str = f" | dur={d:.0f}s"
        emit(f"")
        emit(f"  >> Phase {idx+1}: {ph['main_module']} ({ph['lines']} lines{dur_str})")
        emit(f"     Modules: {ph['module_breakdown']}")

        # Show first few unique lines, then pattern summary
        slice_lines = lines[ph["start"]:ph["end"]]
        ph_comp = LogCompressor()
        for l in slice_lines:
            ph_comp.feed(l)

        # Show first 3 raw lines
        for j in range(min(3, len(slice_lines))):
            l = slice_lines[j].strip()
            emit(f"     |> {l[:160]}")
        if len(slice_lines) > 3:
            emit(f"     ... ({len(slice_lines)-3} more lines)")

        # Show top patterns
        top_ph = ph_comp.get_top_patterns(8)
        has_repeats = any(c > 1 for _, c, _ in top_ph)
        if has_repeats:
            emit(f"     Phase patterns:")
            for summary, cnt, _ in top_ph:
                if cnt > 1:
                    emit(f"       [{cnt:>4}x] {summary}")
    emit()

    # Key events
    emit("-" * 72)
    emit("  [Key Events - non-DEBUG]")
    emit("-" * 72)
    for lineno, level, body in extract_key_events(lines)[:50]:
        b = body[:200] if len(body) > 200 else body
        emit(f"  L{lineno:>6} [{level:>5}] {b}")
    emit()

    special = extract_special_events(lines)
    if special:
        emit("-" * 72)
        emit(f"  [Non-polling DEBUG events] ({len(special)} total, showing first 30)")
        emit("-" * 72)
        for lineno, body in special[:30]:
            b = body[:200] if len(body) > 200 else body
            emit(f"  L{lineno:>6} {b}")
        if len(special) > 30:
            emit(f"  ... ({len(special)-30} more)")
    emit()

    # Timeline: per-minute density
    if valid_ts:
        emit("-" * 72)
        emit("  [Per-minute line density]")
        emit("-" * 72)
        minute_counts = Counter()
        for ts in valid_ts:
            minute_counts[ts.strftime("%H:%M")] += 1
        for minute, cnt in sorted(minute_counts.items()):
            bar = "#" * min(cnt // 40, 80)
            if cnt > 40:
                emit(f"  {minute}  {cnt:>5}  {bar}")
    emit()

    # Footer
    emit("=" * 72)
    emit("  Report End")
    emit("=" * 72)

    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python log_analyzer.py <log_path>")
        sys.exit(1)

    log_path = sys.argv[1]
    report = generate_report(log_path)
    out_path = Path(log_path).with_suffix(".report.txt")
    out_path.write_text(report, encoding="utf-8")
    print(f"Report saved to: {out_path}")
