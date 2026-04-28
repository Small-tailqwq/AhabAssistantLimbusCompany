#!/usr/bin/env python3
"""
代码风格检查与 LLM 可读性分析工具

扫描整个仓库，识别影响 LLM 阅读的代码风格问题，按修复 ROI 排序输出。

用法:
    uv run python scripts/code_style_check.py                # 完整扫描，输出报告
    uv run python scripts/code_style_check.py --json         # JSON 格式输出
    uv run python scripts/code_style_check.py --fix-safe     # 自动修复安全项
    uv run python scripts/code_style_check.py --verify       # 修复后验证
    uv run python scripts/code_style_check.py --path app/    # 只扫描指定目录

报告维度:
    1. 通配符导入链 — 最大噪音源，一修复消除数百警告
    2. 导入可读性 — 排序、位置、冗余
    3. 逻辑噪音 — 裸 except、裸 print
    4. 结构复杂度 — 超长文件 (>500 行)
    5. 综合可读性评分 — 按文件排序
"""

import io
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent

# ── 权重体系：影响 LLM 阅读的因素 ──
# 每出现一处就扣分，扣分越多越需要修复
WEIGHTS = {
    "wildcard_import": 15,    # 通配符导入 — 污染符号表，LLM 无法追踪
    "bare_except": 8,         # 裸 except — 隐藏错误，降低调试效率
    "debug_print": 5,         # 裸 print — 逻辑与调试混在一起
    "import_not_top": 6,      # 导入不在顶部 — 依赖关系模糊
    "unsorted_import": 3,     # 未排序导入 — 神经混乱
    "unused_import": 4,       # 未使用导入 — 增加 token 浪费
    "line_over_120": 1,       # 过长行（>500 行文件额外加权）
    "massive_file": 10,       # >500 行超大文件 — 上下文窗口压力
    "unused_variable": 2,     # 未使用变量
    "ambiguous_name": 2,      # 模糊变量名
}

# 哪些路径不需要检查
EXCLUDE_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    "dist", "build", "logs", "issues",
}

# 哪些路径只做基本检查（跳过 print、通配符导入等开发者工具相关）
DEV_DIRS = {".opencode", "test", "scripts"}


def find_python_files(target: Path) -> list[Path]:
    """递归查找 Python 文件，跳过排除目录。"""
    files = []
    for root, dirs, filenames in os.walk(target):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for f in filenames:
            if f.endswith(".py"):
                files.append(Path(root) / f)
    return files


def count_lines(path: Path) -> int:
    """快速计算文件行数（不加载全部内容）。"""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def run_ruff(target: Path, *, rules: str | None = None, fix: bool = False) -> str:
    """运行 ruff，返回 stdout。"""
    cmd = [
        sys.executable, "-m", "ruff", "check",
        str(target),
        "--output-format", "text",
    ]
    if rules:
        cmd += ["--select", rules]
    if fix:
        cmd.append("--fix")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(ROOT), timeout=60,
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        return ""


def parse_ruff_output(output: str) -> dict[str, list[tuple[int, str, str]]]:
    """解析 ruff 输出，返回 {filepath: [(lineno, code, message)]}。"""
    issues = defaultdict(list)
    for line in output.strip().splitlines():
        parts = line.split(":", 3)
        if len(parts) >= 4:
            filepath, lineno, _, rest = parts
            lineno = lineno.strip()
            rest = rest.strip()
            # 提取错误码（如 E722, F405）
            code = rest.split(" ", 1)[0] if rest else "???"
            msg = rest[len(code):].strip() if len(rest) > len(code) else rest
            issues[filepath].append((int(lineno) if lineno.isdigit() else 0, code, msg))
    return dict(issues)


def analyze_wildcard_chain(base_dir: Path) -> dict:
    """分析通配符导入链：找出源头与波及范围。"""
    chain = {"sources": [], "consumers": [], "affected_files": 0}
    for f in find_python_files(base_dir):
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "import *" in content:
            chain["sources"].append(str(f.relative_to(ROOT)))
    chain["sources"].sort()
    return chain


def analyze_file(path: Path) -> dict:
    """分析单个 Python 文件的风格问题。"""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"lines": 0, "issues": {}}

    lines = content.splitlines()
    result = {
        "lines": len(lines),
        "relative": str(path.relative_to(ROOT)),
        "issues": {
            "wildcard_import": content.count("import *"),
            "bare_except": sum(1 for l in lines if re.match(r'^\s*except\s*:\s*$', l)),
            "debug_print": sum(1 for l in lines if "print(" in l and not l.strip().startswith("#")),
            "unsorted_import": 0,   # 由 ruff 补充
            "unused_import": 0,     # 由 ruff 补充
            "line_over_120": sum(1 for l in lines if len(l.rstrip()) > 120),
            "massive_file": 1 if len(lines) > 500 else 0,
        },
    }
    return result


def compute_score(file_info: dict) -> int:
    """计算 LLM 可读性评分（0=完美，越高越差）。"""
    score = 0
    for issue, count in file_info.get("issues", {}).items():
        weight = WEIGHTS.get(issue, 1)
        score += count * weight
    return score


def build_report(base_dir: Path) -> dict:
    """构建完整分析报告。"""
    files = find_python_files(base_dir)
    file_infos = []

    for f in files:
        info = analyze_file(f)
        file_infos.append(info)

    # 运行 ruff 补充导入相关问题
    ruff_out = run_ruff(base_dir, rules="F401,F405,F403,E402,I001,F841,E741")
    ruff_issues = parse_ruff_output(ruff_out)

    # 将 ruff 结果合并到文件信息
    for path_key, issues in ruff_issues.items():
        for fi in file_infos:
            if fi["relative"] == path_key or fi["relative"].endswith(path_key):
                for _, code, _ in issues:
                    if code == "F405":
                        fi["issues"]["wildcard_import"] = fi["issues"].get("wildcard_import", 0) + 1
                    elif code == "F403":
                        fi["issues"]["wildcard_import"] = fi["issues"].get("wildcard_import", 0) + 5
                    elif code == "F401":
                        fi["issues"]["unused_import"] = fi["issues"].get("unused_import", 0) + 1
                    elif code == "E402":
                        fi["issues"]["import_not_top"] = fi["issues"].get("import_not_top", 0) + 1
                    elif code == "F841":
                        fi["issues"]["unused_variable"] = fi["issues"].get("unused_variable", 0) + 1
                    elif code == "E741":
                        fi["issues"]["ambiguous_name"] = fi["issues"].get("ambiguous_name", 0) + 1

    # 补充 I001（未排序导入）
    ruff_import_out = run_ruff(base_dir, rules="I001")
    for line in ruff_import_out.strip().splitlines():
        for fi in file_infos:
            if fi["relative"] in line:
                fi["issues"]["unsorted_import"] = fi["issues"].get("unsorted_import", 0) + 1
                break

    # 通配符导入链分析
    wildcard = analyze_wildcard_chain(base_dir)
    wildcard_affected = sum(
        max(fi["issues"].get("wildcard_import", 0), fi["issues"].get("import_not_top", 0))
        for fi in file_infos
        if fi["issues"].get("wildcard_import", 0) > 0
    )

    # 排序：按 LLM 阅读影响从大到小
    file_infos.sort(key=compute_score, reverse=True)

    # 统计汇总
    totals = {}
    for issue in WEIGHTS:
        totals[issue] = sum(fi["issues"].get(issue, 0) for fi in file_infos)

    # 建议修复
    fixes = []

    wildcard_sources = [s for s in wildcard.get("sources", [])]
    if wildcard_sources:
        fixes.append({
            "priority": "critical",
            "category": "通配符导入链",
            "impact": f"消除 ~{wildcard_affected} 个 F405 错误，覆盖 {len(wildcard_sources)} 个源头文件",
            "description": "将 `from X import *` 替换为显式具名导入",
            "sources": wildcard_sources,
        })

    if totals.get("unsorted_import", 0) > 0:
        fixes.append({
            "priority": "high",
            "category": "导入排序",
            "impact": f"修复 {totals['unsorted_import']} 处未排序导入",
            "description": "运行 `uv run ruff check --select I --fix .`",
            "command": "uv run ruff check --select I --fix .",
        })

    if totals.get("bare_except", 0) > 0:
        fixes.append({
            "priority": "medium",
            "category": "裸 except",
            "impact": f"修复 {totals['bare_except']} 处裸 except",
            "description": "手动将 `except:` 改为 `except Exception:` 或具体异常",
        })

    if totals.get("debug_print", 0) > 0:
        fixes.append({
            "priority": "low",
            "category": "调试 print",
            "impact": f"清理 {totals['debug_print']} 处调试 print",
            "description": "将业务逻辑中的 print() 替换为 log.xxx()",
        })

    return {
        "summary": totals,
        "fixes": fixes,
        "files": file_infos,
        "wildcard": wildcard,
    }


def print_human_report(report: dict):
    """打印人类可读报告。"""
    sep = "=" * 64

    print(f"\n{sep}")
    print("  AALC 代码风格 & LLM 可读性分析报告")
    print(sep)

    # ── 摘要 ──
    print("\n[统计]")
    totals = report["summary"]
    total_issues = sum(v for v in totals.values())
    print(f"  总计: {total_issues} 处问题")

    label_map = {
        "wildcard_import": "通配符导入 (F405/F403)",
        "bare_except": "裸 except (E722)",
        "debug_print": "调试 print (T201)",
        "import_not_top": "导入不在顶部 (E402)",
        "unsorted_import": "未排序导入 (I001)",
        "unused_import": "未使用导入 (F401)",
        "unused_variable": "未使用变量 (F841)",
        "ambiguous_name": "模糊变量名 (E741)",
        "line_over_120": "超长行 (>120字符)",
        "massive_file": "超大文件 (>500行)",
    }
    for issue, count in sorted(totals.items(), key=lambda x: x[1], reverse=True):
        if count > 0:
            label = label_map.get(issue, issue)
            print(f"  {count:>5}  {label}")

    # ── 修复建议 ──
    print(f"\n[修复建议] 按 ROI 排序:")
    for i, fix in enumerate(report.get("fixes", []), 1):
        icon = {"critical": "[!!!]", "high": "[!!]", "medium": "[!]", "low": "[*]"}.get(fix["priority"], "[?]")
        print(f"  {i}. {icon} [{fix['priority'].upper()}] {fix['category']}")
        print(f"     {fix['impact']}")
        if fix.get("command"):
            print(f"     $ {fix['command']}")
        if fix.get("sources"):
            for src in fix["sources"][:3]:
                print(f"       - {src}")
            if len(fix["sources"]) > 3:
                print(f"       ... 共 {len(fix['sources'])} 个文件")

    # ── Top 问题文件 ──
    print(f"\n[文件] LLM 可读性最差 Top 10（按扣分排序）:")
    print(f"   {'#':<4} {'扣分':<6} {'通配符':<8} {'裸exc':<7} {'print':<7} {'大小':<7} 文件路径")
    print(f"   {'-' * 70}")
    top = [f for f in report["files"] if compute_score(f) > 0][:10]
    for i, fi in enumerate(top, 1):
        sc = compute_score(fi)
        issues = fi["issues"]
        print(
            f"   {i:<4} {sc:<6} "
            f"{issues.get('wildcard_import', 0):<8} "
            f"{issues.get('bare_except', 0):<7} "
            f"{issues.get('debug_print', 0):<7} "
            f"{fi['lines']:>4}行  {fi['relative']}"
        )

    # ── 通配符导入链 ──
    wc = report.get("wildcard", {})
    if wc.get("sources"):
        print(f"\n[链] 通配符导入源头（共 {len(wc['sources'])} 个）:")
        for src in wc["sources"]:
            print(f"  ● {src}")

    print()


def print_json_report(report: dict):
    """JSON 格式输出。"""
    # 简化：移除路径，只保留关键数据
    for fi in report["files"]:
        fi["score"] = compute_score(fi)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))


def main():
    import argparse

    parser = argparse.ArgumentParser(description="代码风格与 LLM 可读性分析")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--fix-safe", action="store_true", help="自动修复安全项（I001, F541）")
    parser.add_argument("--verify", action="store_true", help="修复后验证（比较前后变化）")
    parser.add_argument("--path", type=str, default=None, help="限制扫描路径")
    args = parser.parse_args()

    base_dir = ROOT / args.path if args.path else ROOT

    if args.fix_safe:
        print("[修复建议] 执行安全修复...")
        out = run_ruff(base_dir, rules="I001,F541,F841", fix=True)
        if out:
            print(out)
        else:
            print("  无需修复。")
        return

    if args.verify:
        print("✅ 重新扫描验证...")
        report = build_report(base_dir)
        total = sum(v for v in report["summary"].values())
        if total == 0:
            print("  所有问题已解决！")
        else:
            print(f"  剩余 {total} 处问题。")
            print_human_report(report)
        return

    report = build_report(base_dir)

    if args.json:
        print_json_report(report)
    else:
        print_human_report(report)


if __name__ == "__main__":
    main()
