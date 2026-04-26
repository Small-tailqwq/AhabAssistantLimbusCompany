"""检查 i18n .ts 文件中是否存在未翻译的条目（空 <translation> 标签）。
返回码: 0=通过, 1=存在未翻译条目

用法: uv run python scripts/check_i18n.py
      uv run python scripts/check_i18n.py --update  # 先 lupdate 再检查
"""

import argparse
import os
import re
import subprocess
import sys


def run_lupdate():
    subprocess.run(["pyside6-project", "lupdate"], check=True)


def check_ts_file(ts_path: str) -> list[str]:
    with open(ts_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 按 <context> 分块，方便提示哪个类有问题
    contexts = re.split(r"(?=</?context>)", content)
    untranslated: list[str] = []

    current_context = ""
    for block in contexts:
        ctx_match = re.search(r'<name>(.*?)</name>', block)
        if ctx_match:
            current_context = ctx_match.group(1)

        # 匹配 <message> 块中 <translation></translation>（中间无内容）
        # type="vanished" 的条目不需要翻译，跳过
        if re.search(r'type="vanished"', block):
            continue

        msg_match = re.search(r'<source>(.*?)</source>', block)
        trans_empty = re.search(r'<translation\s*/>|<translation></translation>', block)
        if msg_match and trans_empty:
            untranslated.append(f"  [{current_context}] {msg_match.group(1)}")

    return untranslated


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description="检查 .ts 文件中未翻译的条目")
    parser.add_argument("--update", action="store_true", help="先运行 lupdate 提取新字符串再检查")
    args = parser.parse_args()

    i18n_dir = os.path.join(os.path.dirname(__file__), "..", "i18n")

    if args.update:
        print(">>> 运行 pyside6-project lupdate...")
        run_lupdate()

    failed = False
    for ts_file in sorted(os.listdir(i18n_dir)):
        if not ts_file.endswith(".ts"):
            continue
        ts_path = os.path.join(i18n_dir, ts_file)
        untranslated = check_ts_file(ts_path)
        if untranslated:
            failed = True
            print(f"\n[失败] {ts_file} 中存在 {len(untranslated)} 个未翻译条目:")
            for item in untranslated:
                print(item)
        else:
            print(f"[通过] {ts_file} — 所有条目均已翻译")

    if failed:
        print("\n[失败] i18n 检查未通过：存在未翻译的条目，请补充翻译后再提交。")
        sys.exit(1)
    else:
        print("\n[通过] i18n 检查通过。")


if __name__ == "__main__":
    main()
