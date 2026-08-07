"""为 myapp_en.ts 中空 translation(unfinished) 条目补齐英文翻译。

按 XML 解析顺序与文件顺序对齐的方式定位空条目，避免 source 转义匹配问题。
"""
import re
import xml.etree.ElementTree as ET

TRANSLATIONS = {
    ("InfiniteBattles", "状态：初始化中..."): "Status: Initializing...",
    ("InfiniteBattles", "状态：已停止"): "Status: Stopped",
    ("InfiniteBattles", "状态：错误 - {0}..."): "Status: Error - {0}...",
    ("IssueReplay", "导入日志"): "Import Log",
    ("IssueReplay", "选择日志文件"): "Select Log File",
    ("IssueReplay", "在此粘贴日志内容，或拖拽 .log / .txt 文件到此处..."): "Paste log content here, or drag a .log / .txt file into this area...",
    ("IssueReplay", "配置快照:"): "Config Snapshot:",
    ("IssueReplay", "问题列表"): "Issue List",
    ("IssueReplay", "ID"): "ID",
    ("IssueReplay", "名称"): "Name",
    ("IssueReplay", "版本"): "Version",
    ("IssueReplay", "导入时间"): "Imported At",
    ("IssueReplay", "修改时间"): "Modified At",
    ("IssueReplay", "开发者批注:"): "Developer Notes:",
    ("IssueReplay", "加载此配置到AALC"): "Load This Config into AALC",
    ("IssueReplay", "重命名"): "Rename",
    ("IssueReplay", "编辑批注"): "Edit Notes",
    ("IssueReplay", "追加日志"): "Append Log",
    ("IssueReplay", "状态"): "Status",
    ("IssueReplay", "● 当前使用: 开发者配置"): "● Currently Using: Developer Config",
    ("IssueReplay", "恢复我的配置"): "Restore My Config",
    ("IssueReplay", "未知"): "Unknown",
    ("IssueReplay", "AALC 版本: {0}"): "AALC Version: {0}",
    ("IssueReplay", "游戏分辨率: {0}"): "Game Resolution: {0}",
    ("IssueReplay", "找到 {0} 个配置快照"): "Found {0} config snapshot(s)",
    ("IssueReplay", "快照 #{0} ({1} 个配置项)"): "Snapshot #{0} ({1} config items)",
    ("IssueReplay", "错误"): "Error",
    ("IssueReplay", "读取日志文件失败:\n{0}"): "Failed to read log file:\n{0}",
    ("IssueReplay", "提示"): "Notice",
    ("IssueReplay", "请先粘贴日志内容或选择日志文件"): "Please paste log content or select a log file first",
    ("IssueReplay", "未能在日志中找到任何配置快照"): "No config snapshots found in the log",
    ("IssueReplay", "已导入为 issue{0}\nAALC 版本: {1}"): "Imported as issue{0}\nAALC Version: {1}",
    ("IssueReplay", "\n\n潜在问题:\n{0}"): "\n\nPotential issues:\n{0}",
    ("IssueReplay", "找不到 issue{0} 的配置文件"): "Config file for issue{0} not found",
    ("IssueReplay", "加载配置文件失败:\n{0}"): "Failed to load config file:\n{0}",
    ("IssueReplay", "● 当前使用: 重放模式 - {0}"): "● Currently Using: Replay Mode - {0}",
    ("IssueReplay", "恢复配置文件失败:\n{0}"): "Failed to restore config file:\n{0}",
    ("IssueReplay", "新名称:"): "New name:",
    ("IssueReplay", "确定"): "OK",
    ("LLCLocalizationWindow", "当前版本: -"): "Current version: -",
    ("LLCLocalizationWindow", "最新版本: -"): "Latest version: -",
    ("LLCLocalizationWindow", "状态: 正在检查..."): "Status: Checking...",
    ("LLCLocalizationWindow", "更新日志将在这里显示..."): "Release notes will be shown here...",
    ("LLCLocalizationWindow", "更新日志:"): "Release Notes:",
    ("LLCLocalizationWindow", "日志:"): "Log:",
    ("LLCLocalizationWindow", "开始更新"): "Start Update",
    ("LLCLocalizationWindow", '汉化文件来自 <a href="https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany">LocalizeLimbusCompany</a>，采用 <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh-hans">CC BY-NC-SA 4.0</a> 协议'): 'Localization files from <a href="https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany">LocalizeLimbusCompany</a>, under the <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh-hans">CC BY-NC-SA 4.0</a> license',
    ("LLCLocalizationWindow", "当前版本: {0}"): "Current version: {0}",
    ("LLCLocalizationWindow", "最新版本: {0}"): "Latest version: {0}",
    ("LLCLocalizationWorker", "发生错误: {0}"): "An error occurred: {0}",
    ("LLCLocalizationWorker", "请先在设置中配置正确的游戏路径"): "Please configure the correct game path in Settings first",
    ("LLCLocalizationWorker", "未安装"): "Not installed",
    ("LLCLocalizationWorker", "网络错误，无法连接 GitHub"): "Network error, cannot connect to GitHub",
    ("LLCLocalizationWorker", "GitHub 返回了异常响应"): "GitHub returned an unexpected response",
    ("LLCLocalizationWorker", "✓ 已是最新版本 ({0})"): "✓ Already up to date ({0})",
    ("LLCLocalizationWorker", "⚡ 有新版本: {0}"): "⚡ New version available: {0}",
    ("LLCLocalizationWorker", "下载失败"): "Download failed",
    ("LLCLocalizationWorker", "解压失败"): "Extraction failed",
    ("LLCLocalizationWorker", "✓ 更新完成 ({0})"): "✓ Update complete ({0})",
    ("ProductionModule", "自动换饼"): "Auto Enkephalin Exchange",
    ("ProductionModule", "状态：初始化中..."): "Status: Initializing...",
    ("ProductionModule", "状态：工作中..."): "Status: Working...",
    ("ProductionModule", "状态：已停止"): "Status: Stopped",
    ("ProductionModule", "状态：正在生产..."): "Status: Producing...",
    ("ProductionModule", "状态：错误 - {0}..."): "Status: Error - {0}...",
    ("_DropableTextEdit", "已选择: {0}"): "Selected: {0}",
    ("_MarkdownEditSidecar", "编辑批注 — issue{0}"): "Edit Notes — issue{0}",
    ("_MarkdownEditSidecar", "Markdown 源码"): "Markdown Source",
    ("_MarkdownEditSidecar", "预览"): "Preview",
    ("_MarkdownEditSidecar", "保存 (Ctrl+S)"): "Save (Ctrl+S)",
    ("_MarkdownEditSidecar", "保存失败"): "Save Failed",
    ("_MarkdownEditSidecar", "保存批注失败:\n{0}"): "Failed to save notes:\n{0}",
}


def xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main():
    path = "i18n/myapp_en.ts"
    ts = open(path, encoding="utf-8").read()

    tree = ET.parse(path)
    root = tree.getroot()
    empty = []
    for ctx in root.findall("context"):
        ctx_name = ctx.findtext("name", "")
        for msg in ctx.findall("message"):
            if msg.get("type") == "vanished":
                continue
            tr_el = msg.find("translation")
            if tr_el is not None and tr_el.get("type") == "unfinished" and not (tr_el.text or "").strip():
                empty.append((ctx_name, msg.findtext("source", "")))

    print(f"空翻译条目: {len(empty)}")

    missing = [e for e in empty if e not in TRANSLATIONS]
    if missing:
        print(f"!! 翻译字典缺失 {len(missing)} 条:")
        for ctx, s in missing:
            print(f"  [{ctx}] {s!r}")
        return

    # 按顺序定位文件中第 n 个空翻译标签并替换
    empty_pattern = re.compile(r'<translation[^>]*type="unfinished"[^>]*>\s*</translation>')
    positions = [(m.start(), m.end()) for m in empty_pattern.finditer(ts)]
    if len(positions) != len(empty):
        print(f"!! 文件内空翻译数({len(positions)})与 XML 解析数({len(empty)})不一致")
        return

    parts = []
    prev = 0
    for (start, end), (ctx, src) in zip(positions, empty):
        parts.append(ts[prev:start])
        parts.append(f"<translation>{xml_escape(TRANSLATIONS[(ctx, src)])}</translation>")
        prev = end
    parts.append(ts[prev:])
    new_ts = "".join(parts)

    open(path, "w", encoding="utf-8", newline="\n").write(new_ts)
    print(f"已补齐 {len(empty)} 条翻译")


if __name__ == "__main__":
    main()
