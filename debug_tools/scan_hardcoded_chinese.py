"""按文件统计 UI 文本的 tr 覆盖率；--lines 模式列出指定文件未包裹的中文行。"""
import glob
import re
import sys

ts = open("i18n/myapp_en.ts", encoding="utf-8").read()
ts_sources = set(re.findall(r"<source>(.*?)</source>", ts))

files = glob.glob("app/**/*.py", recursive=True) + glob.glob("tasks/**/*.py", recursive=True)
files = sorted(f for f in files if "__pycache__" not in f)

rows = []
for f in files:
    src = open(f, encoding="utf-8").read()
    all_lit = set()
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("#") or s.startswith("import ") or s.startswith("from "):
            continue
        for m in re.finditer(r"""['"]([^'"]*[\u4e00-\u9fff][^'"]*)['"]""", line):
            s = m.group(1)
            if len(s) <= 60:
                all_lit.add(s)
    wrapped = set()
    for m in re.finditer(
        r"""(?:tr|QT_TRANSLATE_NOOP)\(\s*(?:['"][^'"]*['"]\s*,\s*)?['"]([^'"]*[\u4e00-\u9fff][^'"]*)['"]""",
        src,
    ):
        s = m.group(1)
        if len(s) <= 60:
            wrapped.add(s)
    missing = all_lit - wrapped
    rows.append((f, len(all_lit), len(wrapped), len(missing)))

print(f"{'文件':<55} {'总':>4} {'包裹':>4} {'缺失':>4}")
for f, total, wrapped, missing in sorted(rows, key=lambda x: -x[3]):
    if missing:
        print(f"{f:<55} {total:>4} {wrapped:>4} {missing:>4}")

if "--lines" in sys.argv:
    print()
    for f in sys.argv[2:]:
        src = open(f, encoding="utf-8").read()
        print(f"===== {f} =====")
        for i, line in enumerate(src.splitlines(), 1):
            if re.search(r"[\u4e00-\u9fff]", line) and "tr(" not in line and not line.strip().startswith("#"):
                if re.search(r'["\']', line) and len(line.strip()) < 130:
                    print(f"  {i}: {line.strip()}")
