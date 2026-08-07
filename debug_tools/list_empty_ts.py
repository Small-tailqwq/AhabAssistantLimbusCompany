"""列出 .ts 中所有空 translation(unfinished) 条目。"""
import xml.etree.ElementTree as ET

tree = ET.parse("i18n/myapp_en.ts")
root = tree.getroot()
untrans = []
for ctx in root.findall("context"):
    ctx_name = ctx.findtext("name", "")
    for msg in ctx.findall("message"):
        if msg.get("type") == "vanished":
            continue
        src = msg.findtext("source", "")
        tr_el = msg.find("translation")
        if tr_el is None:
            continue
        tval = (tr_el.text or "").strip()
        trtype = tr_el.get("type")
        if tval == "" and trtype == "unfinished":
            untrans.append((ctx_name, src))

print(f"空翻译条目: {len(untrans)}")
for ctx, s in untrans:
    print(f"[{ctx}] {s}")
