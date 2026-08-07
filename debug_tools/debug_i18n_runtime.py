"""离屏验证 i18n 运行时链路：加载 .qm → 构造卡片 → retranslateUi 是否变英文。"""
import os
import sys

sys.path.insert(0, os.getcwd())

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QTranslator
from PySide6.QtWidgets import QApplication

app = QApplication([])

t = QTranslator()
assert t.load("myapp_en", "i18n"), ".qm 加载失败"
app.installTranslator(t)

from app.base_combination import BaseSettingCardGroup, ComboBoxSettingCard

group = BaseSettingCardGroup("游戏设置")
print("切换前 group title:", group.titleLabel.text())
group.retranslateUi()
print("切换后 group title:", group.titleLabel.text())

card = ComboBoxSettingCard(
    "language_in_program",
    ":/qfluentwidgets/images/logo.png",
    "选择队伍方式",
    "使用队伍名为识别“TEAMS#XX”/“编队#XX”的队伍",
    texts={"使用队伍名": False, "使用队伍序号": True},
)
print("切换前 card title:", card.titleLabel.text())
card.retranslateUi()
print("切换后 card title:", card.titleLabel.text())
print("切换后 combo items:", [card.comboBox.itemText(i) for i in range(card.comboBox.count())])
