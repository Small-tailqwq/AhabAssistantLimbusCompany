from time import sleep

from PySide6.QtCore import QT_TRANSLATE_NOOP, Qt, QThread
from PySide6.QtWidgets import QApplication, QPushButton, QWidget
from qfluentwidgets import (
    ExpandLayout,
    InfoBarPosition,
    ScrollArea,
    SettingCard,
)
from qfluentwidgets import FluentIcon as FIF

from app.base_combination import BasePushSettingCard, BaseSettingCardGroup
from app.card.messagebox_custom import BaseInfoBar
from app.language_manager import LanguageManager
from tasks import tools


class ScreenshotCard(SettingCard):
    def __init__(self, icon, title, content, parent=None):
        super().__init__(icon, title, content, parent)
        self._quick_text = QT_TRANSLATE_NOOP("ScreenshotCard", "快速截图")
        self._full_text = QT_TRANSLATE_NOOP("ScreenshotCard", "截图")

        self.quick_btn = QPushButton(self._quick_text, self)
        self.quick_btn.setFocusPolicy(Qt.NoFocus)
        self.hBoxLayout.addWidget(self.quick_btn, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(10)

        self.full_btn = QPushButton(self._full_text, self)
        self.full_btn.setFocusPolicy(Qt.NoFocus)
        self.hBoxLayout.addWidget(self.full_btn, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.title = title
        self.content = content

    def retranslateUi(self):
        self.titleLabel.setText(self.tr(self.title))
        self.contentLabel.setText(self.tr(self.content))
        self.quick_btn.setText(self.tr(self._quick_text))
        self.full_btn.setText(self.tr(self._full_text))


class ToolsInterface(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("ToolsInterface")
        self.tools = {}
        self.__init_widget()
        self.__init_card()
        self.__initLayout()
        self.set_style_sheet()
        self.__connect_signal()
        self.setWidget(self.scroll_widget)

        LanguageManager().register_component(self)

    def __init_widget(self):
        self.scroll_widget = QWidget()
        self.scroll_widget.setObjectName("scrollWidget")
        self.expand_layout = ExpandLayout(self.scroll_widget)
        self.setWidgetResizable(True)

    def __init_card(self):
        self.tools_group = BaseSettingCardGroup(QT_TRANSLATE_NOOP("BaseSettingCardGroup", "工具箱"), self.scroll_widget)
        self.auto_battle_card = BasePushSettingCard(
            QT_TRANSLATE_NOOP("BasePushSettingCard", "运行"),
            FIF.CAFE,
            QT_TRANSLATE_NOOP("BasePushSettingCard", "自动战斗"),
            QT_TRANSLATE_NOOP(
                "BasePushSettingCard",
                "这只是一个为你自动按下P键和Enter键的小工具，不要怀抱太多期待",
            ),
            parent=self.tools_group,
        )
        self.auto_production_card = BasePushSettingCard(
            QT_TRANSLATE_NOOP("BasePushSettingCard", "运行"),
            FIF.CAFE,
            QT_TRANSLATE_NOOP("BasePushSettingCard", "自动体力换饼"),
            QT_TRANSLATE_NOOP("BasePushSettingCard", "辅助自动换饼小工具，防止体力溢出"),
            parent=self.tools_group,
        )
        self.screenshot_card = ScreenshotCard(
            FIF.CAMERA,
            QT_TRANSLATE_NOOP("ScreenshotCard", "截图小工具"),
            QT_TRANSLATE_NOOP("ScreenshotCard", "直接截图或设置窗口后截图"),
            parent=self.tools_group,
        )
        self.issue_replay_card = BasePushSettingCard(
            QT_TRANSLATE_NOOP("BasePushSettingCard", "运行"),
            FIF.DEVELOPER_TOOLS,
            QT_TRANSLATE_NOOP("BasePushSettingCard", "日志复现工具"),
            QT_TRANSLATE_NOOP("BasePushSettingCard", "导入问题日志，热切换配置文件进行调试"),
            parent=self.tools_group,
        )
        self.asset_manager_card = BasePushSettingCard(
            QT_TRANSLATE_NOOP("BasePushSettingCard", "运行"),
            FIF.ALBUM,
            QT_TRANSLATE_NOOP("BasePushSettingCard", "资产管理"),
            QT_TRANSLATE_NOOP(
                "BasePushSettingCard",
                "可视化浏览、分类、替换游戏图片资产",
            ),
            parent=self.tools_group,
        )
        self.skip_tutorial_card = BasePushSettingCard(
            QT_TRANSLATE_NOOP("BasePushSettingCard", "运行"),
            FIF.EDUCATION,
            QT_TRANSLATE_NOOP("BasePushSettingCard", "新手提示工具"),
            QT_TRANSLATE_NOOP(
                "BasePushSettingCard",
                "直接修改游戏存档，关闭或恢复所有新手引导和红点提示",
            ),
            parent=self.tools_group,
        )

    def __initLayout(self):
        self.tools_group.addSettingCard(self.auto_battle_card)
        self.tools_group.addSettingCard(self.auto_production_card)
        self.tools_group.addSettingCard(self.screenshot_card)
        self.tools_group.addSettingCard(self.issue_replay_card)
        self.tools_group.addSettingCard(self.asset_manager_card)
        self.tools_group.addSettingCard(self.skip_tutorial_card)

        self.expand_layout.addWidget(self.tools_group)

    def set_style_sheet(self):
        self.setStyleSheet("""
                SettingInterface, #scrollWidget {
                    background-color: transparent;
                }
                QScrollArea {
                    background-color: transparent;
                    border: none;
                }
            """)

    def __connect_signal(self):
        self.auto_battle_card.clicked.connect(
            lambda: self._tool_start(
                "battle",
                self.auto_battle_card,
            )
        )
        self.auto_production_card.clicked.connect(lambda: self._tool_start("production", self.auto_production_card))
        self.screenshot_card.quick_btn.clicked.connect(lambda: self._start_screenshot_tool("quick_screenshot", self.screenshot_card.quick_btn))
        self.screenshot_card.full_btn.clicked.connect(lambda: self._start_screenshot_tool("screenshot", self.screenshot_card.full_btn))
        self.issue_replay_card.clicked.connect(lambda: self._tool_start("issue_replay", self.issue_replay_card))
        self.asset_manager_card.clicked.connect(lambda: self._tool_start("asset_manager", self.asset_manager_card))
        self.skip_tutorial_card.clicked.connect(lambda: self._tool_start("tutorial_skip", self.skip_tutorial_card))

    def _tool_start(self, tool_name: str, card: BasePushSettingCard):
        if tool_name in self.tools:
            tool = self.tools[tool_name]
            if isinstance(tool.w, QWidget):
                tool.w.activateWindow()
                tool.w.raise_()
            return
        tool = tools.start(tool_name)
        self.tools[tool_name] = tool
        while tool.initialized is False:
            QApplication.processEvents()
            sleep(0.01)
        if tool.initialized is None:
            self.tools.pop(tool_name, None)
            return
        self._update_running_button(card)
        tool.w.destroyed.connect(lambda _: self.tools.pop(tool_name, None))
        tool.w.destroyed.connect(lambda _: self._restore_button_style(card))
        if tool_name == "screenshot":
            tool.w.on_saved_timestr.connect(self._onScreenshotToolButtonPressed)
        if tool_name == "quick_screenshot":
            tool.w.on_saved_timestr.connect(self._onQuickScreenshotSaved)
            tool.w.on_error.connect(self._onQuickScreenshotError)
        if isinstance(tool.w, QThread):
            tool.w.start()

    def _update_running_button(self, card: BasePushSettingCard):
        card.button.setText(QT_TRANSLATE_NOOP("BasePushSettingCard", "运行中"))
        card.update_button(is_running=True)

    def _restore_button_style(self, card: BasePushSettingCard):
        card.button.setText(QT_TRANSLATE_NOOP("BasePushSettingCard", "运行"))
        card.update_button(is_running=False)

    def _start_screenshot_tool(self, tool_name: str, button: QPushButton):
        if tool_name in self.tools:
            tool = self.tools[tool_name]
            if isinstance(tool.w, QWidget):
                tool.w.activateWindow()
                tool.w.raise_()
            return
        tool = tools.start(tool_name)
        self.tools[tool_name] = tool
        while tool.initialized is False:
            QApplication.processEvents()
            sleep(0.01)
        if tool.initialized is None:
            self.tools.pop(tool_name, None)
            return

        original_text = button.text()
        button.setText(QT_TRANSLATE_NOOP("BasePushSettingCard", "运行中"))
        button.setEnabled(False)

        def on_destroyed():
            self.tools.pop(tool_name, None)
            button.setText(original_text)
            button.setEnabled(True)

        tool.w.destroyed.connect(on_destroyed)
        if tool_name == "screenshot":
            tool.w.on_saved_timestr.connect(self._onScreenshotToolButtonPressed)
        elif tool_name == "quick_screenshot":
            tool.w.on_saved_timestr.connect(self._onQuickScreenshotSaved)
            tool.w.on_error.connect(self._onQuickScreenshotError)
        if isinstance(tool.w, QThread):
            tool.w.start()

    def _onScreenshotToolButtonPressed(self, time_str: str):
        title = QT_TRANSLATE_NOOP("BaseInfoBar", "截图完成")
        msg = QT_TRANSLATE_NOOP("BaseInfoBar", "图片保存为 AALC > screenshot_{time_str}.png")
        BaseInfoBar.success(
            title=title,
            content=msg,
            content_kwargs={"time_str": time_str},
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=-1,
            parent=self,
        )

    def _onQuickScreenshotSaved(self, time_str: str):
        title = QT_TRANSLATE_NOOP("BaseInfoBar", "截图完成")
        msg = QT_TRANSLATE_NOOP("BaseInfoBar", "图片保存为 AALC > quick_screenshot_{time_str}.png")
        BaseInfoBar.success(
            title=title,
            content=msg,
            content_kwargs={"time_str": time_str},
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=-1,
            parent=self,
        )

    def _onQuickScreenshotError(self, msg: str):
        title = QT_TRANSLATE_NOOP("BaseInfoBar", "截图失败")
        BaseInfoBar.error(
            title=title,
            content=msg,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=-1,
            parent=self,
        )

    def retranslateUi(self):
        self.tools_group.retranslateUi()
        self.auto_battle_card.retranslateUi()
        self.auto_production_card.retranslateUi()
        self.screenshot_card.retranslateUi()
        self.issue_replay_card.retranslateUi()
        self.asset_manager_card.retranslateUi()
        self.skip_tutorial_card.retranslateUi()
