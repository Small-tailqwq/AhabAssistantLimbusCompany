"""
AALC Mirror Dungeon Log Analyzer
=================================
Extracts per-run statistics from AALC debug logs:
  - Segment mirror runs by start/end markers
  - Battle-by-battle duration & match success rate
  - Time distribution (combat / events / shop / pathfinding)
  - Anomaly detection (spikes, crashes, route failures)

Usage:
    uv run python .opencode/tools/mirror_analyzer.py <log_path> [log_path2 ...]
    uv run python .opencode/tools/mirror_analyzer.py issues/9/supplement_2.log issues/9/original.log
"""

import re
import sys
from datetime import datetime
from pathlib import Path

TIMESTAMP_RE = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+)')
BATTLE_END_RE = re.compile(r'结束执行 一次战斗 耗时:(\d{2}:\d{2}:\d{2})')
MIRROR_START_RE = re.compile(r'开始执行 一次镜牢')
MIRROR_END_RE = re.compile(r'结束执行 一次镜牢')
MIRROR_END_DURATION_RE = re.compile(r'结束执行 一次镜牢 耗时:(\d{2}:\d{2}:\d{2})')
MATCH_FAILURE_RE = re.compile(r'匹配失败次数(\d+)\s+匹配总次数(\d+)\s+匹配成功率([\d.]+)%')
WARNING_RE = re.compile(r'\[WARNING\]')
ERROR_RE = re.compile(r'\[ERROR\]')
EVENT_COUNT_RE = re.compile(r'此次镜牢走的事件次数(\d+)')
SUMMARY_RE = re.compile(r'此次镜牢[中]?(在战斗|在事件|在商店|在寻路) 总耗时:(\d{2}:\d{2}:\d{2})')
ROUTE_FAIL_RE = re.compile(r'镜牢路线图未识别到任何节点')
RESTART_RE = re.compile(r'check_times\(\)|kill_game|restart_game|游戏进程重启|游戏路径不存在')
PLAYER_EXIT_RE = re.compile(r'玩家已退出')
WAKING_RE = re.compile(r'wake_event|skip_event|wake_event_selection')


def parse_timestamp(line: str) -> datetime | None:
    m = TIMESTAMP_RE.search(line)
    if m:
        return datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S,%f')
    return None


def parse_duration(dur_str: str) -> int:
    parts = dur_str.strip().split(':')
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])


def format_duration(seconds: int) -> str:
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f'{h:02d}:{m:02d}:{s:02d}'


def avg_duration(durations: list[int]) -> str:
    if not durations:
        return 'N/A'
    avg_s = sum(durations) / len(durations)
    return format_duration(int(avg_s))


class BattleRecord:
    def __init__(self):
        self.battles: list[dict] = []
        self.route_failures = 0
        self.warnings = 0
        self.errors = 0
        self.restarts = 0
        self.waking_events = 0
        self.event_count = 0
        self.summaries: dict[str, str] = {}
        self.total_duration_sec = 0
        self.run_start: datetime | None = None
        self.run_end: datetime | None = None

    def add_battle(self, ts: datetime, duration_str: str, failures: int = 0, total: int = 0, rate: float = 0):
        sec = parse_duration(duration_str)
        self.battles.append({
            'ts': ts,
            'duration_sec': sec,
            'duration_str': duration_str,
            'failures': failures,
            'total_matches': total,
            'success_rate': rate,
        })

    @property
    def total_combat_sec(self) -> int:
        return sum(b['duration_sec'] for b in self.battles)

    @property
    def avg_battle_sec(self) -> float:
        return self.total_combat_sec / len(self.battles) if self.battles else 0

    @property
    def total_failures(self) -> int:
        return sum(b['failures'] for b in self.battles if b['failures'] > 0)

    def get_anomalies(self, threshold_factor: float = 2.0) -> list[dict]:
        if not self.battles:
            return []
        avg_s = self.avg_battle_sec
        anomalies = []
        for b in self.battles:
            if b['duration_sec'] > avg_s * threshold_factor:
                anomalies.append({
                    'index': self.battles.index(b) + 1,
                    'duration': b['duration_str'],
                    'ts': b['ts'].strftime('%H:%M:%S'),
                    'failures': b['failures'],
                    'ratio': round(b['duration_sec'] / avg_s, 1),
                    'likely': self._classify_anomaly(b),
                })
        return anomalies

    def _classify_anomaly(self, b: dict) -> str:
        if b['duration_sec'] > 600:
            return '崩溃恢复/BOSS长时间结算'
        if b['failures'] >= 15:
            return '匹配失败过多 → 自适应等待膨胀'
        if b['duration_sec'] > 300:
            return 'BOSS战/轮次战'
        return '匹配波动'


def analyze_logs(file_paths: list[str]) -> list[BattleRecord]:
    records: list[BattleRecord] = []
    current: BattleRecord | None = None
    in_run = False
    pending_end = False

    def close_run(ts: datetime | None = None):
        nonlocal current, in_run, pending_end
        if current is not None:
            if ts:
                current.run_end = ts
            records.append(current)
        current = None
        in_run = False
        pending_end = False

    for file_path in file_paths:
        path = Path(file_path)
        if not path.exists():
            print(f'[SKIP] File not found: {file_path}')
            continue
        print(f'  Processing: {file_path}')

        lines = path.read_text(encoding='utf-8').splitlines()

        for line in lines:
            ts = parse_timestamp(line)
            if not ts:
                continue

            if MIRROR_END_DURATION_RE.search(line):
                m = MIRROR_END_DURATION_RE.search(line)
                dur_sec = parse_duration(m.group(1))
                if in_run and current is not None:
                    current.total_duration_sec = dur_sec
                    current.run_end = ts
                    close_run(ts)
                elif pending_end and current is not None:
                    current.total_duration_sec = dur_sec
                    close_run(ts)
                continue

            if MIRROR_END_RE.search(line):
                if in_run and current is not None:
                    current.run_end = ts
                    pending_end = True
                continue

            if MIRROR_START_RE.search(line):
                if in_run and current is not None:
                    close_run(ts)
                elif pending_end:
                    close_run(ts)
                current = BattleRecord()
                current.run_start = ts
                in_run = True
                continue

            if not in_run or current is None:
                continue

            m = BATTLE_END_RE.search(line)
            if m:
                dur_str = m.group(1)
                current.add_battle(ts, dur_str, 0, 0, 0.0)
                continue

            m = MATCH_FAILURE_RE.search(line)
            if m and current.battles:
                current.battles[-1]['failures'] = int(m.group(1))
                current.battles[-1]['total_matches'] = int(m.group(2))
                current.battles[-1]['success_rate'] = float(m.group(3))
                continue

            m = SUMMARY_RE.search(line)
            if m:
                current.summaries[m.group(1)] = m.group(2)

            m = EVENT_COUNT_RE.search(line)
            if m:
                current.event_count = int(m.group(1))

            if ROUTE_FAIL_RE.search(line):
                current.route_failures += 1

            if RESTART_RE.search(line):
                if not getattr(current, '_restart_checked', False):
                    current.restarts += 1
                    current._restart_checked = True

            if WAKING_RE.search(line):
                current.waking_events += 1

            if WARNING_RE.search(line):
                current.warnings += 1
            if ERROR_RE.search(line):
                current.errors += 1

    return records


def print_run_report(run: BattleRecord, index: int):
    print(f'\n{"="*60}')
    print(f'  RUN {index}')
    print(f'  Period:   {run.run_start.strftime("%H:%M:%S")} → {run.run_end.strftime("%H:%M:%S")}')
    print(f'  Duration: {format_duration(run.total_duration_sec)}')
    print(f'{"="*60}')

    print(f'\n  ⚔ Battles: {len(run.battles)}')
    print(f'     Avg:     {format_duration(int(run.avg_battle_sec))} / battle')
    print(f'     Total:   {format_duration(run.total_combat_sec)}')

    print('\n  📊 Time Distribution:')
    for key in ['在战斗', '在事件', '在商店', '在寻路']:
        if key in run.summaries:
            sec = parse_duration(run.summaries[key])
            pct = sec / run.total_duration_sec * 100 if run.total_duration_sec else 0
            print(f'     {"此次镜牢"+key:<12s} {run.summaries[key]:>8s}  ({pct:4.1f}%)')

    accounted = sum(parse_duration(v) for v in run.summaries.values())
    overhead = run.total_duration_sec - accounted
    if run.total_duration_sec and accounted > 0:
        overhead_pct = overhead / run.total_duration_sec * 100
        print(f'     开销/非活动       {format_duration(overhead):>8s}  ({overhead_pct:4.1f}%)')

    if run.event_count:
        print(f'\n  📅 Events: {run.event_count}')
    if run.route_failures:
        print(f'  🗺 Route failures: {run.route_failures}')
    if run.restarts:
        print(f'  🔄 Restarts/crashes: {run.restarts}')

    anomalies = run.get_anomalies()
    if anomalies:
        print(f'\n  🚨 ANOMALIES (>{run.avg_battle_sec*2:.0f}s 阈值):')
        for a in anomalies:
            print(f'     Battle #{a["index"]:>2d} | {a["ts"]} | {a["duration"]:>8s} | '
                  f'fail={a["failures"]:>2d} | {a["likely"]}')

    print('\n  📋 Battle Detail:')
    print(f'     {"#":>3s} {"Time":>8s} {"Dur":>8s} {"F":>3s} {"Tot":>4s} {"Rate":>6s}')
    print(f'     {"-"*35}')
    for i, b in enumerate(run.battles):
        rate_str = f'{b["success_rate"]:.1f}%' if b['success_rate'] > 0 else '-'
        tot_str = str(b['total_matches']) if b['total_matches'] > 0 else '-'
        flag = ' <<<' if b['duration_sec'] > run.avg_battle_sec * 2 else ''
        print(f'     {i+1:>3d} {b["ts"].strftime("%H:%M:%S"):>8s} '
              f'{b["duration_str"]:>8s} {b["failures"]:>3d} {tot_str:>4s} '
              f'{rate_str:>6s}{flag}')


def cross_compare(runs: list[BattleRecord]):
    print(f'\n{"="*60}')
    print('  CROSS-RUN COMPARISON')
    print(f'{"="*60}')

    if not runs:
        return

    for i, run in enumerate(runs):
        combat_pct = run.total_combat_sec / run.total_duration_sec * 100 if run.total_duration_sec else 0
        print(f'\n  Run {i+1}:')
        print(f'     Total:   {format_duration(run.total_duration_sec)}')
        print(f'     Battles: {len(run.battles)} x avg {format_duration(int(run.avg_battle_sec))}')
        print(f'     Combat:  {format_duration(run.total_combat_sec)} ({combat_pct:.1f}%)')
        print(f'     Failures: {run.total_failures} total')
        print(f'     Events:  {run.event_count}')
        print(f'     Route:   {run.route_failures} failures')
        if run.restarts:
            print(f'     ⚠ Crashes: {run.restarts}')

    avg_t = sum(r.total_duration_sec for r in runs) / len(runs)
    fastest = min(r.total_duration_sec for r in runs)
    slowest = max(r.total_duration_sec for r in runs)
    spread = slowest - fastest
    print('\n  Overall:')
    print(f'     Avg run: {format_duration(int(avg_t))}')
    print(f'     Range:   {format_duration(fastest)} → {format_duration(slowest)} (Δ{format_duration(spread)})')
    print(f'     Battle avg: {format_duration(int(sum(r.avg_battle_sec for r in runs) / len(runs)))}')


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    all_runs = analyze_logs(sys.argv[1:])

    # Filter out aborted runs (no battles)
    all_runs = [r for r in all_runs if len(r.battles) > 0]

    if not all_runs:
        print('\nNo mirror runs found in any file.')
        sys.exit(0)

    for i, run in enumerate(all_runs):
        print_run_report(run, i + 1)

    cross_compare(all_runs)


if __name__ == '__main__':
    main()
