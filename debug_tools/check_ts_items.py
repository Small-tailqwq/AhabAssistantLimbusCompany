"""检查关键字符串在 .ts 中的状态。"""
import re

ts = open("i18n/myapp_en.ts", encoding="utf-8").read()
tests = [
    ("InfiniteBattles", "自动战斗"),
    ("InfiniteBattles", "开始战斗"),
    ("IssueReplay", "日志复现工具"),
    ("IssueReplay", "导入"),
    ("IssueReplay", "删除"),
    ("IssueReplay", "取消"),
    ("IssueReplay", "重命名"),
    ("IssueReplay", "导入成功"),
    ("IssueReplay", "保存批注失败:\n{0}"),
]
for ctx, s in tests:
    m = re.search(rf"<name>{ctx}</name>(.*?)</context>", ts, re.S)
    if not m:
        print(f"FAIL [{ctx}] {s!r}: 无 context")
        continue
    mm = re.search(
        rf"<source>({re.escape(s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))})</source>\s*<translation([^>]*)>(.*?)</translation>",
        m.group(1),
        re.S,
    )
    if mm:
        print(f"OK   [{ctx}] {s!r}: attrs={mm.group(2)!r} tr={mm.group(3)[:40]!r}")
    else:
        print(f"MISS [{ctx}] {s!r}")
