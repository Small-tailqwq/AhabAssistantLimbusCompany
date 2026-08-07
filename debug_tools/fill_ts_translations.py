"""为 myapp_en.ts 中空 translation(unfinished) 条目补齐英文翻译。

按 XML 解析顺序与文件顺序对齐的方式定位空条目，避免 source 转义匹配问题。
"""
import re
import xml.etree.ElementTree as ET

TRANSLATIONS = {
    ("AssetDetailPanel", "业务名:"): "Business name:",
    ("AssetDetailPanel", "文件名:"): "File name:",
    ("AssetDetailPanel", "标签:"): "Tags:",
    ("AssetDetailPanel", "备注:"): "Note:",
    ("AssetDetailPanel", "替换图片"): "Replace Image",
    ("AssetDetailPanel", "历史版本"): "Version History",
    ("AssetDetailPanel", "选择新图片"): "Select New Image",
    ("AssetDetailPanel", "(无)"): "(None)",
    ("AssetDetailPanel", "历史版本 ({0})"): "Version History ({0})",
    ("AssetDetailPanel", "[已丢失] {0}"): "[Missing] {0}",
    ("AssetDetailPanel", "历史版本 (0)"): "Version History (0)",
    ("AssetGridWidget", "在文件管理器中打开"): "Open in File Explorer",
    ("AssetGridWidget", "复制路径"): "Copy Path",
    ("AssetGridWidget", "标记为已删除"): "Mark as Missing",
    ("AssetGridWidget", "从回收站恢复"): "Restore from Recycle",
    ("AssetManager", "搜索业务名/备注/路径..."): "Search business name / note / path...",
    ("AssetManager", "全部标签"): "All Tags",
    ("AssetManager", "通用"): "General",
    ("AssetManager", "中"): "CN",
    ("AssetManager", "英"): "EN",
    ("AssetManager", "亮色"): "Light",
    ("AssetManager", "暗色"): "Dark",
    ("AssetManager", "刷新扫描"): "Rescan",
    ("AssetManager", "清除缩略图缓存"): "Clear Thumbnail Cache",
    ("AssetManager", "正在清除缩略图缓存..."): "Clearing thumbnail cache...",
    ("AssetManager", "缩略图缓存已清除，正在重新生成..."): "Thumbnail cache cleared, regenerating...",
    ("AssetManager", "正在扫描资产..."): "Scanning assets...",
    ("AssetManager", "正在加载缩略图..."): "Loading thumbnails...",
    ("AssetManager", "新增 {0}"): "{0} added",
    ("AssetManager", "变更 {0}"): "{0} changed",
    ("AssetManager", "丢失 {0}"): "{0} missing",
    ("AssetManager", "扫描失败: {0}"): "Scan failed: {0}",
    ("AssetManager", "共 {0} 个资产  |  筛选结果 {1}"): "{0} assets total  |  {1} filtered",
    ("AssetManager", "添加标签"): "Add Tag",
    ("AssetManager", "输入新标签:"): "Enter new tag:",
    ("AssetManager", "删除标签"): "Remove Tag",
    ("AssetManager", "选择要删除的标签:"): "Select tag to remove:",
    ("AssetManager", "确认替换"): "Confirm Replacement",
    ("AssetManager", '将 "{0}" 替换为\n"{1}"?\n\n旧文件将存档到回收站。'): 'Replace "{0}" with\n"{1}"?\n\nThe old file will be archived to the recycle bin.',
    ("AssetManager", "已替换: {0}"): "Replaced: {0}",
    ("AssetManager", "已恢复到 v{0}: {1}"): "Restored to v{0}: {1}",
    ("AssetManager", "恢复失败"): "Restore Failed",
    ("AssetManager", "无法恢复指定的版本，文件可能已丢失。"): "Unable to restore the specified version. The file may have been lost.",
    ("AssetManager", "已永久删除 v{0}"): "Permanently deleted v{0}",
    ("AssetManager", "从回收站恢复"): "Restore from Recycle",
    ("AssetManager", "将恢复 v{0} ({1})?\n当前 Missing 标记将被清除。"): "Restore v{0} ({1})?\nThe current Missing marker will be cleared.",
    ("CategoryTree", "全部"): "All",
    ("CategoryTree", "主界面"): "Main UI",
    ("CategoryTree", "体力"): "Enkephalin",
    ("CategoryTree", "战斗"): "Battle",
    ("CategoryTree", "场景/过场"): "Scenes/Cutscenes",
    ("CategoryTree", "基础通用"): "Base",
    ("CategoryTree", "日常事件"): "Daily Events",
    ("CategoryTree", "镜牢"): "Mirror Dungeon",
    ("CategoryTree", "  寻路"): "  Pathfinding",
    ("CategoryTree", "  商店"): "  Shop",
    ("CategoryTree", "  事件"): "  Events",
    ("CategoryTree", "  结算/奖励"): "  Rewards/Settlement",
    ("CategoryTree", "  主题包"): "  Theme Packs",
    ("CategoryTree", "  通用UI"): "  General UI",
    ("CategoryTree", "队伍"): "Teams",
    ("CategoryTree", "通行证"): "Pass",
    ("CategoryTree", "反射"): "Luxcavation",
    ("CategoryTree", "未分类"): "Uncategorized",
    ("PreviewDialog", "图片预览"): "Image Preview",
    ("PreviewDialog", "适应窗口"): "Fit to Window",
    ("PreviewDialog", "原始大小"): "Original Size",
    ("TutorialSkipWindow", "跳过新手提示"): "Skip Tutorial Prompts",
    ("TutorialSkipWindow", "操作选项"): "Action",
    ("TutorialSkipWindow", "关闭新手提示"): "Disable Tutorial Prompts",
    ("TutorialSkipWindow", "恢复新手提示"): "Restore Tutorial Prompts",
    ("TutorialSkipWindow", "目标平台"): "Target Platform",
    ("TutorialSkipWindow", "自动检测"): "Auto Detect",
    ("TutorialSkipWindow", "开始执行"): "Start",
    ("TutorialSkipWindow", "状态：就绪"): "Status: Ready",
    ("TutorialSkipWindow", "状态：处理中..."): "Status: Processing...",
    ("TutorialSkipWindow", "状态：完成"): "Status: Done",
    ("TutorialSkipWindow", "状态：失败"): "Status: Failed",
    ("VersionHistoryDialog", "历史版本 — {0}"): "Version History — {0}",
    ("VersionHistoryDialog", "切换到此版本"): "Switch to This Version",
    ("VersionHistoryDialog", "删除此版本"): "Delete This Version",
    ("VersionHistoryDialog", "确认切换版本"): "Confirm Version Switch",
    ("VersionHistoryDialog", "当前文件将存档为新版本，并恢复为 v{0}。是否继续？"): "The current file will be archived as a new version and restored to v{0}. Continue?",
    ("VersionHistoryDialog", "确认删除"): "Confirm Deletion",
    ("VersionHistoryDialog", "将永久删除 v{0}，不可撤销。是否继续？"): "v{0} will be permanently deleted and cannot be undone. Continue?",
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
