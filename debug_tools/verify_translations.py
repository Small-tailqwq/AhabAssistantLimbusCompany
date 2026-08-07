"""验证 .qm 中关键条目的翻译。"""
from PySide6.QtCore import QTranslator, QCoreApplication

app = QCoreApplication([])
t = QTranslator()
assert t.load("myapp_en", "i18n"), "load failed"
app.installTranslator(t)

tests = [
    ("GHubManager", "驱动 DLL 管理器"),
    ("GHubManager", "检测 DLL"),
    ("GHubManager", "DLL 状态：❓ 未检测"),
    ("GHubManager", "DLL 状态：{0} {1}"),
    ("GHubManager", "未找到 G HUB: {0}\n请先安装 Logitech G HUB"),
    ("_DllCheckWorker", "鼠标移动未生效"),
    ("TutorialSkipWindow", "跳过新手提示"),
    ("TutorialSkipWindow", "状态：处理中..."),
    ("AssetManager", "资产管理"),
    ("AssetManager", "共 {0} 个资产  |  筛选结果 {1}"),
    ("AssetManager", '将 "{0}" 替换为\n"{1}"?\n\n旧文件将存档到回收站。'),
    ("CategoryTree", "镜牢"),
    ("CategoryTree", "  寻路"),
    ("CategoryTree", "未分类"),
    ("AssetDetailPanel", "历史版本 ({0})"),
    ("AssetDetailPanel", "[已丢失] {0}"),
    ("AssetGridWidget", "在文件管理器中打开"),
    ("PreviewDialog", "适应窗口"),
    ("VersionHistoryDialog", "历史版本 — {0}"),
    ("VersionHistoryDialog", "当前文件将存档为新版本，并恢复为 v{0}。是否继续？"),
]
failed = 0
for ctx, s in tests:
    r = app.translate(ctx, s)
    ok = r != s
    failed += 0 if ok else 1
    print(f"{'OK  ' if ok else 'FAIL'} [{ctx}] {s[:30]!r} -> {r[:50]!r}")
print("全部通过" if failed == 0 else f"{failed} 条失败")

