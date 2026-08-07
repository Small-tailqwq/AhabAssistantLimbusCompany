"""验证 .qm 中关键条目的翻译。"""
from PySide6.QtCore import QTranslator, QCoreApplication

app = QCoreApplication([])
t = QTranslator()
assert t.load("myapp_en", "i18n"), "load failed"
app.installTranslator(t)

html_src = '<div style="font-size: 15px; line-height: 1.6;">知道你们想要什么<br>2026-06 蜘蛛巢良秀专武在泛用-3级-4行-8列</div>'

tests = [
    ("SwitchSettingCard", "调试模式"),
    ("SwitchSettingCard", "镜牢寻路调试"),
    ("SwitchSettingCard", "启用罗技驱动模拟"),
    ("BasePushSettingCard", "零协汉化更新"),
    ("BasePushSettingCard", "(未设置)"),
    ("MainWindow", "停止超时"),
    ("MainWindow", "脚本仍在收尾，请稍后再尝试退出程序。"),
    ("Nav", "调试"),
    ("NormalTextButton", "暂停"),
    ("FarmingInterfaceLeft", "停止中..."),
    ("SettingInterface", "选择游戏路径"),
    ("CustomizeSettingsModule", "起始之星"),
    ("VersionCard", "最新版本: {version}"),
    ("PageMirror", "已成功从文件创建队伍 {0}"),
    ("ObserveEgoGiftModule", "启用观测"),
    ("ObserveEgoGiftModule", html_src),
    ("BaseCheckBox", "简单键盘寻路（始终按↑键，避免鼠标拖动）"),
    ("InfiniteBattles", "主线模式(测试)"),
]
failed = 0
for ctx, s in tests:
    r = app.translate(ctx, s)
    ok = r != s
    failed += 0 if ok else 1
    print(f"{'OK  ' if ok else 'FAIL'} [{ctx}] {s[:40]!r} -> {r[:70]!r}")
print("全部通过" if failed == 0 else f"{failed} 条失败")
