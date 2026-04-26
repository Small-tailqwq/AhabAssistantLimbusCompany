#!/usr/bin/env python3
"""
从 AALC 日志文件中提取"案发"时的配置快照，输出为可加载的 config.yaml。

用法:
    uv run python scripts/extract_config_from_log.py <日志文件路径> [输出目录]

输出的 YAML 可以直接用作 config.yaml 来复现 issue 的配置状态。
"""

import io
import sys
from pathlib import Path

from module.issue_manager import (
    dict_to_yaml,
    find_config_snapshots,
    find_metadata,
    validate_config,
)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def main():
    if len(sys.argv) < 2:
        print(f"用法: python {sys.argv[0]} <日志文件路径> [输出目录]")
        sys.exit(1)

    log_path = Path(sys.argv[1])
    if not log_path.exists():
        print(f"错误: 找不到日志文件: {log_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)

    text = log_path.read_text(encoding="utf-8")
    meta = find_metadata(text)
    snapshots = find_config_snapshots(text)

    sep = "=" * 48
    print(f"\n{sep}")
    print(f"  来源日志: {log_path.name}")
    print(f"  AALC 版本: {meta.get('version', '未知')}")
    print(f"  配置文件版本: {meta.get('config_version', '未知')}")
    print(f"  游戏分辨率: {meta.get('resolution', '未知')}")
    print(f"  截图间隔: {meta.get('screenshot_interval', '未知')}")
    print(f"  鼠标间隔: {meta.get('mouse_interval', '未知')}")
    print(f"  找到配置快照: {len(snapshots)} 个")
    print(sep)

    if not snapshots:
        print("\n[错误] 无法提取配置字典", file=sys.stderr)
        sys.exit(1)

    if len(snapshots) > 1:
        print(f"\n检测到 {len(snapshots)} 个配置快照，将使用第一个。")

    config = snapshots[0]
    print(f"\n配置字段数: {len(config)}")
    print("关键配置项:")
    for key in (
        "game_path",
        "game_title_name",
        "language_in_game",
        "after_completion",
        "keep_after_completion",
        "daily_task",
        "mirror",
        "get_reward",
        "buy_enkephalin",
    ):
        if key in config:
            print(f"  {key}: {config[key]}")

    out_stem = f"config_{log_path.stem}"
    yaml_path = out_dir / f"{out_stem}.yaml"
    yaml_path.write_text(dict_to_yaml(config), encoding="utf-8")
    print(f"\n[OK] 配置文件已保存: {yaml_path}")

    meta_path = out_dir / f"meta_{log_path.stem}.txt"
    meta_lines = [
        f"来源日志: {log_path.name}",
        f"AALC 版本: {meta.get('version', '未知')}",
        f"配置文件版本: {meta.get('config_version', '未知')}",
        f"游戏分辨率: {meta.get('resolution', '未知')}",
        f"截图间隔: {meta.get('screenshot_interval', '未知')}",
        f"鼠标间隔: {meta.get('mouse_interval', '未知')}",
    ]
    meta_path.write_text("\n".join(meta_lines), encoding="utf-8")
    print(f"[OK] 元数据已保存:   {meta_path}")

    issues = validate_config(config)
    if issues:
        print("\n潜在问题:")
        for issue in issues:
            print(f"  [!] {issue}")


if __name__ == "__main__":
    main()
