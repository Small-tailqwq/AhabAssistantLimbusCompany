import datetime

from PySide6.QtCore import QT_TRANSLATE_NOOP, QPoint, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QWidget,
)
from qfluentwidgets import (
    ExpandLayout,
    InfoBarPosition,
    ScrollArea,
    Theme,
    isDarkTheme,
    qconfig,
    setTheme,
)
from qfluentwidgets import FluentIcon as FIF

from app import win_input_type_options
from app.base_combination import (
    BasePrimaryPushSettingCard,
    BasePushSettingCard,
    BaseSettingCardGroup,
    ComboBoxSettingCard,
    DailySettingCard,
    HotkeySettingCard,
    PushSettingCardChance,
    PushSettingCardDate,
    SwitchSettingCard,
    VersionCard,
)
from app.card.messagebox_custom import BaseInfoBar, MessageBoxEdit
from app.common.ui_config import get_setting_interface_qss
from app.language_manager import SUPPORTED_LANG_NAME, LanguageManager
from app.theme_pack_setting_interface import ThemePackSettingDialog
from app.widget.setting_nav import SettingNav
from module.config import cfg, theme_list
from utils.schedule_helper import ScheduleHelper


class SettingInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.__init_widget()
        self.__init_card()
        self.__initLayout()
        self.__init_nav()

        self._apply_theme_style()
        qconfig.themeChanged.connect(self._apply_theme_style)

        self.__connect_signal()
        self.setObjectName("SettingInterface")

        LanguageManager().register_component(self)

    def __init_widget(self):
        # main container
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # left navigation frame
        self.setting_nav = SettingNav(self)

        # right scroll area with existing content
        self.content_scroll = ScrollArea(self)
        self.content_scroll.setObjectName("contentScroll")
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content_scroll.enableTransparentBackground()

        self.scroll_widget = QWidget()
        self.scroll_widget.setObjectName("scrollWidget")
        self.expand_layout = ExpandLayout(self.scroll_widget)
        self.content_scroll.setWidget(self.scroll_widget)

        # assemble
        self.main_layout.addWidget(self.setting_nav)
        self.main_layout.addWidget(self.content_scroll)
        self.main_layout.setStretch(0, 0)
        self.main_layout.setStretch(1, 1)

        # give nav a fixed width and prevent stretch
        self.setting_nav.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.content_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def __init_card(self):
        self.game_setting_group = BaseSettingCardGroup(
            QT_TRANSLATE_NOOP("BaseSettingCardGroup", "游戏设置"), self.scroll_widget
        )
        self.game_setting_card = ComboBoxSettingCard(
            "select_team_by_order",
            FIF.SEARCH,
            QT_TRANSLATE_NOOP("ComboBoxSettingCard", "选择队伍方式"),
            QT_TRANSLATE_NOOP(
                "ComboBoxSettingCard",
                "使用队伍名为识别“TEAMS#XX”/“编队#XX”的队伍，使用序号为使用从上到下第X个队伍",
            ),
            texts={
                QT_TRANSLATE_NOOP("ComboBoxSettingCard", "使用队伍名"): False,
                QT_TRANSLATE_NOOP("ComboBoxSettingCard", "使用队伍序号"): True,
            },
            parent=self.game_setting_group,
        )
        self.auto_hard_mirror_card = SwitchSettingCard(
            FIF.PLAY,
            QT_TRANSLATE_NOOP("SwitchSettingCard", "自动困难模式"),
            QT_TRANSLATE_NOOP(
                "SwitchSettingCard",
                "每周自动将前三场镜牢设置为困难模式执行，请确认启用了“困牢单次加成”功能",
            ),
            "auto_hard_mirror",
            parent=self.game_setting_group,
        )
        self.last_auto_hard_mirror_card = PushSettingCardDate(
            QT_TRANSLATE_NOOP("PushSettingCardDate", "修改"),
            FIF.DATE_TIME,
            QT_TRANSLATE_NOOP("PushSettingCardDate", "上次自动切换困难镜牢的时间戳"),
            "last_auto_change",
        )
        self.hard_mirror_chance_card = PushSettingCardChance(
            QT_TRANSLATE_NOOP("PushSettingCardChance", "修改"),
            FIF.UNIT,
            QT_TRANSLATE_NOOP("PushSettingCardChance", "困难模式剩余次数"),
            config_name="hard_mirror_chance",
            max_value=3,
            content=QT_TRANSLATE_NOOP("PushSettingCardChance", "第一次运行请手动设定，之后将自动修改"),
            on_confirm=self._on_hard_mirror_chance_confirm,
        )
        self.win_input_type_card = ComboBoxSettingCard(
            "win_input_type",
            FIF.CONNECT,
            QT_TRANSLATE_NOOP("ComboBoxSettingCard", "操控方式"),
            "  ",
            texts=win_input_type_options,
            parent=self.game_setting_group,
        )
        self.memory_protection = SwitchSettingCard(
            FIF.FRIGID,
            QT_TRANSLATE_NOOP("SwitchSettingCard", "内存占用保护"),
            QT_TRANSLATE_NOOP(
                "SwitchSettingCard",
                "自动检测电脑<font color=red>总内存占用</font>，超过90%执行内存清理，防止崩溃，可能略微影响脚本速度",
            ),
            "memory_protection",
            parent=self.game_setting_group,
        )
        self.screenshot_benchmark_card = BasePrimaryPushSettingCard(
            QT_TRANSLATE_NOOP("BasePrimaryPushSettingCard", "截图测试"),
            FIF.CAMERA,
            QT_TRANSLATE_NOOP("BasePrimaryPushSettingCard", "截图性能测试"),
            QT_TRANSLATE_NOOP("BasePrimaryPushSettingCard", "测试截图功能的性能"),
            parent=self.game_setting_group,
        )

        self.simulator_setting_group = BaseSettingCardGroup(
            QT_TRANSLATE_NOOP("BaseSettingCardGroup", "模拟器设置"), self.scroll_widget
        )
        self.simulator_setting_card = SwitchSettingCard(
            FIF.MINIMIZE,
            QT_TRANSLATE_NOOP("SwitchSettingCard", "使用模拟器"),
            "",
            "simulator",
            parent=self.simulator_setting_group,
        )
        self.simulator_type_setting_card = ComboBoxSettingCard(
            "simulator_type",
            FIF.APPLICATION,
            QT_TRANSLATE_NOOP("ComboBoxSettingCard", "模拟器连接配置"),
            QT_TRANSLATE_NOOP("ComboBoxSettingCard", "选择使用的模拟器"),
            texts={
                QT_TRANSLATE_NOOP("ComboBoxSettingCard", "MuMu模拟器(推荐)"): 0,
                QT_TRANSLATE_NOOP("ComboBoxSettingCard", "其他模拟器"): 10,
            },
            parent=self.simulator_setting_group,
        )
        self.simulator_port_chance_card = PushSettingCardChance(
            QT_TRANSLATE_NOOP("PushSettingCardChance", "修改"),
            FIF.TRAIN,
            QT_TRANSLATE_NOOP("PushSettingCardChance", "使用的模拟器端口号"),
            config_name="simulator_port",
            max_value=65535,
            content="",
            parent=self.simulator_setting_group,
        )
        self.start_emulator_timeout_chance_card = PushSettingCardChance(
            QT_TRANSLATE_NOOP("PushSettingCardChance", "修改"),
            FIF.TRAIN,
            QT_TRANSLATE_NOOP("PushSettingCardChance", "仅限MUMU模拟器——启动模拟器超时时间(秒)"),
            config_name="start_emulator_timeout",
            max_value=3600,
            content="",
            parent=self.simulator_setting_group,
        )

        self.game_path_group = BaseSettingCardGroup(
            QT_TRANSLATE_NOOP("BaseSettingCardGroup", "启动游戏"), self.scroll_widget
        )
        self.game_path_card = BasePushSettingCard(
            QT_TRANSLATE_NOOP("BasePushSettingCard", "修改"),
            FIF.FOLDER,
            QT_TRANSLATE_NOOP("BasePushSettingCard", "游戏路径"),
            cfg.game_path,
            parent=self.game_path_group,
        )
        self.autostart_card = SwitchSettingCard(
            FIF.POWER_BUTTON,
            QT_TRANSLATE_NOOP("SwitchSettingCard", "开机时启动 AALC"),
            "",
            "autostart",
            parent=self.game_path_group,
        )
        self.autodaily_group = BaseSettingCardGroup(
            QT_TRANSLATE_NOOP("BaseSettingCardGroup", "定时执行 AALC"),
            self.scroll_widget,
        )
        self.autodaily_card = DailySettingCard(
            FIF.HISTORY,
            QT_TRANSLATE_NOOP("DailySettingCard", "定时执行 1"),
            QT_TRANSLATE_NOOP("DailySettingCard", "如果计算机处于启动状态，将在指定时间执行 AALC 任务"),
            "autodaily",
            parent=self.autodaily_group,
        )
        self.autodaily_card_2 = DailySettingCard(
            FIF.HISTORY,
            QT_TRANSLATE_NOOP("DailySettingCard", "定时执行 2"),
            None,
            "autodaily2",
            parent=self.autodaily_group,
        )
        self.autodaily_card_3 = DailySettingCard(
            FIF.HISTORY,
            QT_TRANSLATE_NOOP("DailySettingCard", "定时执行 3"),
            None,
            "autodaily3",
            parent=self.autodaily_group,
        )
        self.autodaily_card_4 = DailySettingCard(
            FIF.HISTORY,
            QT_TRANSLATE_NOOP("DailySettingCard", "定时执行 4"),
            None,
            "autodaily4",
            parent=self.autodaily_group,
        )
        self.minimize_to_tray_card = SwitchSettingCard(
            FIF.REMOVE,
            QT_TRANSLATE_NOOP("SwitchSettingCard", "最小化到托盘"),
            QT_TRANSLATE_NOOP(
                "SwitchSettingCard",
                "开启后，最小化时将隐藏到系统托盘",
            ),
            "minimize_to_tray",
            parent=self.game_path_group,
        )

        self.personal_group = BaseSettingCardGroup(
            QT_TRANSLATE_NOOP("BaseSettingCardGroup", "个性化"), self.scroll_widget
        )
        self.language_card = ComboBoxSettingCard(
            "language_in_program",
            FIF.LANGUAGE,
            QT_TRANSLATE_NOOP("ComboBoxSettingCard", "语言"),
            QT_TRANSLATE_NOOP("ComboBoxSettingCard", "设置程序 UI 使用的语言"),
            texts=SUPPORTED_LANG_NAME,
            parent=self.personal_group,
        )
        self.theme_card = ComboBoxSettingCard(
            "theme_mode",
            FIF.BRUSH,
            QT_TRANSLATE_NOOP("ComboBoxSettingCard", "应用主题"),
            QT_TRANSLATE_NOOP("ComboBoxSettingCard", "调整应用的主题外观"),
            texts={
                QT_TRANSLATE_NOOP("ComboBoxSettingCard", "跟随系统"): "AUTO",
                QT_TRANSLATE_NOOP("ComboBoxSettingCard", "亮色模式"): "LIGHT",
                QT_TRANSLATE_NOOP("ComboBoxSettingCard", "深色模式"): "DARK",
            },
            parent=self.personal_group,
        )
        self.zoom_card = ComboBoxSettingCard(
            "zoom_scale",
            FIF.ZOOM,
            QT_TRANSLATE_NOOP("ComboBoxSettingCard", "缩放"),
            QT_TRANSLATE_NOOP("ComboBoxSettingCard", "设置程序 UI 使用的缩放"),
            texts={
                QT_TRANSLATE_NOOP("ComboBoxSettingCard", "跟随系统"): 0,
                "50%": 50,
                "75%": 75,
                "90%": 90,
                "100%": 100,
                "125%": 125,
                "150%": 150,
                "175%": 175,
                "200%": 200,
            },
            parent=self.personal_group,
        )
        self.hotkey_card = HotkeySettingCard(
            QT_TRANSLATE_NOOP("BasePushSettingCard", "修改"),
            FIF.EDIT,
            QT_TRANSLATE_NOOP("BasePushSettingCard", "快捷键设置"),
            {
                QT_TRANSLATE_NOOP("BasePushSettingCard", "结束运行的脚本"): "shutdown_hotkey",
                QT_TRANSLATE_NOOP("BasePushSettingCard", "暂停脚本运行"): "pause_hotkey",
                QT_TRANSLATE_NOOP("BasePushSettingCard", "恢复脚本运行"): "resume_hotkey",
            },
            parent=self.personal_group,
        )

        self.logs_group = BaseSettingCardGroup(QT_TRANSLATE_NOOP("BaseSettingCardGroup", "调试"), self.scroll_widget)
        self.debug_mode_card = SwitchSettingCard(
            FIF.DEVELOPER_TOOLS,
            QT_TRANSLATE_NOOP("SwitchSettingCard", "调试模式"),
            QT_TRANSLATE_NOOP(
                "SwitchSettingCard",
                "开启后显示调试子选项；关闭后会自动重置所有子调试开关",
            ),
            "debug_mode",
            parent=self.logs_group,
        )
        self.debug_mirror_route_card = SwitchSettingCard(
            FIF.GLOBE,
            QT_TRANSLATE_NOOP("SwitchSettingCard", "镜牢寻路调试"),
            QT_TRANSLATE_NOOP(
                "SwitchSettingCard",
                "记录镜牢寻路额外日志，并在 logs/route_map_debug 下保存调试截图和元数据",
            ),
            "debug_mirror_route",
            parent=self.logs_group,
        )
        self.debug_thread_dungeon_card = SwitchSettingCard(
            FIF.GLOBE,
            QT_TRANSLATE_NOOP("SwitchSettingCard", "纽本调试"),
            QT_TRANSLATE_NOOP(
                "SwitchSettingCard",
                "记录纽本匹配过程的截图到 logs/thread_dungeon_debug 目录",
            ),
            "debug_thread_dungeon",
            parent=self.logs_group,
        )
        self.debug_retry_card = SwitchSettingCard(
            FIF.GLOBE,
            QT_TRANSLATE_NOOP("SwitchSettingCard", "重试调试"),
            QT_TRANSLATE_NOOP(
                "SwitchSettingCard",
                "在尝试退出、重启镜牢时输出识别情况的日志断点",
            ),
            "debug_retry",
            parent=self.logs_group,
        )
        self.debug_shop_card = SwitchSettingCard(
            FIF.GLOBE,
            QT_TRANSLATE_NOOP("SwitchSettingCard", "商店调试"),
            QT_TRANSLATE_NOOP(
                "SwitchSettingCard",
                "输出商店各操作的详细识别和点击日志，保存调试截图",
            ),
            "debug_shop",
            parent=self.logs_group,
        )
        self.open_logs_card = BasePrimaryPushSettingCard(
            QT_TRANSLATE_NOOP("BasePrimaryPushSettingCard", "日志"),
            FIF.FOLDER_ADD,
            QT_TRANSLATE_NOOP("BasePrimaryPushSettingCard", "打开日志文件夹"),
            parent=self.logs_group,
        )

        self.about_group = BaseSettingCardGroup(QT_TRANSLATE_NOOP("BaseSettingCardGroup", "关于"), self.scroll_widget)
        self.github_card = BasePrimaryPushSettingCard(
            QT_TRANSLATE_NOOP("BasePrimaryPushSettingCard", "项目主页"),
            FIF.GITHUB,
            QT_TRANSLATE_NOOP("BasePrimaryPushSettingCard", "项目主页"),
            self._get_repo_url(),
        )
        self.discord_group_card = BasePrimaryPushSettingCard(
            QT_TRANSLATE_NOOP("BasePrimaryPushSettingCard", "加入群聊"),
            FIF.EXPRESSIVE_INPUT_ENTRY,
            QT_TRANSLATE_NOOP("BasePrimaryPushSettingCard", "discord群"),
            "https://discord.gg/vUAw98cEVe",
        )
        self.feedback_card = BasePrimaryPushSettingCard(
            QT_TRANSLATE_NOOP("BasePrimaryPushSettingCard", "提供反馈"),
            FIF.FEEDBACK,
            QT_TRANSLATE_NOOP("BasePrimaryPushSettingCard", "提供反馈"),
            QT_TRANSLATE_NOOP("BasePrimaryPushSettingCard", "帮助我们改进 AhabAssistantLimbusCompany"),
        )

        self.version_card = VersionCard(
            FIF.SYNC,
            QT_TRANSLATE_NOOP("VersionCard", "版本信息"),
            QT_TRANSLATE_NOOP("VersionCard", "当前版本: {version}").format(version=cfg.version),
            parent=self.about_group,
        )
        self.system_proxy_card = SwitchSettingCard(
            FIF.GLOBE,
            QT_TRANSLATE_NOOP("SwitchSettingCard", "使用系统代理"),
            QT_TRANSLATE_NOOP(
                "SwitchSettingCard",
                "启用后自动读取 Windows 系统代理设置（如 Clash），适用于有代理工具的网络环境",
            ),
            "update_use_system_proxy",
            parent=self.about_group,
        )

        self.theme_pack_group = BaseSettingCardGroup(
            QT_TRANSLATE_NOOP("BaseSettingCardGroup", "镜牢主题包设置"),
            self.scroll_widget,
        )
        self.theme_pack_card = BasePrimaryPushSettingCard(
            QT_TRANSLATE_NOOP("BasePrimaryPushSettingCard", "配置"),
            FIF.LIBRARY,
            QT_TRANSLATE_NOOP("BasePrimaryPushSettingCard", "主题包权重配置"),
            QT_TRANSLATE_NOOP(
                "BasePrimaryPushSettingCard",
                "配置镜牢主题包的选择优先级权重",
            ),
            parent=self.theme_pack_group,
        )

        self.experimental_group = BaseSettingCardGroup(
            QT_TRANSLATE_NOOP("BaseSettingCardGroup", "实验性内容"), self.scroll_widget
        )

        self.auto_lang_card = SwitchSettingCard(
            FIF.DEVELOPER_TOOLS,
            QT_TRANSLATE_NOOP("SwitchSettingCard", "自动检测并切换游戏语言"),
            "",
            config_name="experimental_auto_lang",
            parent=self.experimental_group,
        )
        self.low_res_match_card = SwitchSettingCard(
            FIF.ZOOM,
            QT_TRANSLATE_NOOP("SwitchSettingCard", "低分辨率优化"),
            QT_TRANSLATE_NOOP(
                "SwitchSettingCard",
                "提升 720P 等低分辨率下部分图片匹配率，但会增加匹配时间；2K/1080P 通常无需开启",
            ),
            config_name="experimental_low_res_match",
            parent=self.experimental_group,
        )
        self.logitech_switch_card = SwitchSettingCard(
            FIF.MOVE,
            QT_TRANSLATE_NOOP("SwitchSettingCard", "启用罗技驱动模拟"),
            QT_TRANSLATE_NOOP(
                "SwitchSettingCard",
                "使用独立 DLL 进行硬件级键鼠输入模拟，需要正确配置可用的罗技驱动 DLL 路径",
            ),
            config_name="lab_mouse_logitech",
            parent=self.experimental_group,
        )
        self.logitech_dll_path_card = BasePushSettingCard(
            QT_TRANSLATE_NOOP("BasePushSettingCard", "选择"),
            FIF.FOLDER,
            QT_TRANSLATE_NOOP("BasePushSettingCard", "罗技 DLL 路径"),
            cfg.get_value("logitech_dll_path", ""),
            parent=self.experimental_group,
        )
        self.logitech_bionic_trajectory_card = SwitchSettingCard(
            FIF.MOVE,
            QT_TRANSLATE_NOOP("SwitchSettingCard", "启用仿生轨迹"),
            QT_TRANSLATE_NOOP(
                "SwitchSettingCard",
                "启用后使用仿生鼠标轨迹与仿生点击偏移；关闭后回退为普通分段移动",
            ),
            config_name="logitech_bionic_trajectory",
            parent=self.experimental_group,
        )
        self.obs_switch_card = SwitchSettingCard(
            FIF.CAMERA,
            QT_TRANSLATE_NOOP("SwitchSettingCard", "启用 OBS 截图"),
            QT_TRANSLATE_NOOP(
                "SwitchSettingCard",
                "通过 OBS WebSocket 获取截图，规避直接调用系统截图接口",
            ),
            config_name="lab_screenshot_obs",
            parent=self.experimental_group,
        )
        self.obs_host_card = BasePushSettingCard(
            QT_TRANSLATE_NOOP("BasePushSettingCard", "修改"),
            FIF.HOME,
            QT_TRANSLATE_NOOP("BasePushSettingCard", "OBS WebSocket 地址"),
            cfg.get_value("obs_host", "localhost"),
            parent=self.experimental_group,
        )
        self.obs_port_card = PushSettingCardChance(
            QT_TRANSLATE_NOOP("PushSettingCardChance", "修改"),
            FIF.GLOBE,
            QT_TRANSLATE_NOOP("PushSettingCardChance", "OBS WebSocket 端口"),
            config_name="obs_port",
            max_value=65535,
            content="",
            parent=self.experimental_group,
        )
        self.obs_password_card = BasePushSettingCard(
            QT_TRANSLATE_NOOP("BasePushSettingCard", "修改"),
            FIF.EDIT,
            QT_TRANSLATE_NOOP("BasePushSettingCard", "OBS WebSocket 密码"),
            "",
            parent=self.experimental_group,
        )
        self.obs_source_name_card = BasePushSettingCard(
            QT_TRANSLATE_NOOP("BasePushSettingCard", "修改"),
            FIF.VIDEO,
            QT_TRANSLATE_NOOP("BasePushSettingCard", "OBS 截图源名称"),
            cfg.get_value("obs_source_name", ""),
            parent=self.experimental_group,
        )
        self.obs_image_format_card = ComboBoxSettingCard(
            "obs_image_format",
            FIF.PHOTO,
            QT_TRANSLATE_NOOP("ComboBoxSettingCard", "OBS 截图编码格式"),
            QT_TRANSLATE_NOOP("ComboBoxSettingCard", "推荐使用 jpg；png 更稳但通常更慢"),
            texts={
                "JPG": "jpg",
                "PNG": "png",
                "WEBP": "webp",
            },
            parent=self.experimental_group,
        )
        self.obs_image_quality_card = PushSettingCardChance(
            QT_TRANSLATE_NOOP("PushSettingCardChance", "修改"),
            FIF.SPEED_HIGH,
            QT_TRANSLATE_NOOP("PushSettingCardChance", "OBS 截图压缩质量"),
            config_name="obs_image_quality",
            max_value=100,
            content=QT_TRANSLATE_NOOP("PushSettingCardChance", "仅对有损格式生效，推荐 60~80"),
            parent=self.experimental_group,
        )
        self.keep_screen_awake_card = SwitchSettingCard(
            FIF.VIEW,
            QT_TRANSLATE_NOOP("SwitchSettingCard", "运行时保持屏幕唤醒"),
            QT_TRANSLATE_NOOP(
                "SwitchSettingCard",
                "任务运行中阻止系统休眠与锁屏；任务结束、停止或异常退出后会自动恢复系统默认策略",
            ),
            config_name="experimental_keep_screen_awake",
            parent=self.experimental_group,
        )
        self.simulator_chinese_patch_card = SwitchSettingCard(
            FIF.LANGUAGE,
            QT_TRANSLATE_NOOP("SwitchSettingCard", "模拟器已安装零协汉化"),
            QT_TRANSLATE_NOOP(
                "SwitchSettingCard",
                "开启后不强制英语，也许能够在零协汉化的模拟器版上运行，<font color=red>不做稳定性保证</font>",
            ),
            config_name="experimental_simulator_chinese_patch",
            parent=self.experimental_group,
        )
        self.__refreshExperimentalCardContents()

    def _on_hard_mirror_chance_confirm(self, _: int) -> None:
        """手动调整困难模式次数后，同步刷新自动切换时间戳。"""
        now = datetime.datetime.now()
        cfg.set_value("last_auto_change", now.timestamp())
        cfg.flush()
        self.last_auto_hard_mirror_card.config_value = now
        self.last_auto_hard_mirror_card.contentLabel.setText(now.strftime("%Y-%m-%d %H:%M"))

    def __initLayout(self):
        self.game_setting_group.addSettingCard(self.game_setting_card)
        self.game_setting_group.addSettingCard(self.auto_hard_mirror_card)
        self.game_setting_group.addSettingCard(self.last_auto_hard_mirror_card)
        self.game_setting_group.addSettingCard(self.hard_mirror_chance_card)
        self.game_setting_group.addSettingCard(self.win_input_type_card)
        self.game_setting_group.addSettingCard(self.memory_protection)
        self.game_setting_group.addSettingCard(self.screenshot_benchmark_card)

        self.theme_pack_group.addSettingCard(self.theme_pack_card)

        self.simulator_setting_group.addSettingCard(self.simulator_setting_card)
        self.simulator_setting_group.addSettingCard(self.simulator_type_setting_card)
        self.simulator_setting_group.addSettingCard(self.simulator_port_chance_card)
        self.simulator_setting_group.addSettingCard(self.start_emulator_timeout_chance_card)

        self.game_path_group.addSettingCard(self.game_path_card)
        self.game_path_group.addSettingCard(self.autostart_card)
        self.game_path_group.addSettingCard(self.minimize_to_tray_card)

        self.autodaily_group.addSettingCard(self.autodaily_card)
        self.autodaily_group.addSettingCard(self.autodaily_card_2)
        self.autodaily_group.addSettingCard(self.autodaily_card_3)
        self.autodaily_group.addSettingCard(self.autodaily_card_4)

        self.personal_group.addSettingCard(self.language_card)
        self.personal_group.addSettingCard(self.theme_card)
        self.personal_group.addSettingCard(self.zoom_card)
        self.personal_group.addSettingCard(self.hotkey_card)

        self.logs_group.addSettingCard(self.debug_mode_card)
        self.logs_group.addSettingCard(self.debug_mirror_route_card)
        self.logs_group.addSettingCard(self.debug_thread_dungeon_card)
        self.logs_group.addSettingCard(self.debug_retry_card)
        self.logs_group.addSettingCard(self.debug_shop_card)
        self.logs_group.addSettingCard(self.open_logs_card)

        self.about_group.addSettingCard(self.github_card)
        self.about_group.addSettingCard(self.discord_group_card)
        self.about_group.addSettingCard(self.feedback_card)
        self.about_group.addSettingCard(self.version_card)
        self.about_group.addSettingCard(self.system_proxy_card)

        self.experimental_group.addSettingCard(self.auto_lang_card)
        self.experimental_group.addSettingCard(self.low_res_match_card)
        self.experimental_group.addSettingCard(self.logitech_switch_card)
        self.experimental_group.addSettingCard(self.logitech_dll_path_card)
        self.experimental_group.addSettingCard(self.logitech_bionic_trajectory_card)
        self.experimental_group.addSettingCard(self.obs_switch_card)
        self.experimental_group.addSettingCard(self.obs_host_card)
        self.experimental_group.addSettingCard(self.obs_port_card)
        self.experimental_group.addSettingCard(self.obs_password_card)
        self.experimental_group.addSettingCard(self.obs_source_name_card)
        self.experimental_group.addSettingCard(self.obs_image_format_card)
        self.experimental_group.addSettingCard(self.obs_image_quality_card)
        self.experimental_group.addSettingCard(self.keep_screen_awake_card)
        self.experimental_group.addSettingCard(self.simulator_chinese_patch_card)

        self.expand_layout.addWidget(self.game_setting_group)
        self.expand_layout.addWidget(self.theme_pack_group)
        self.expand_layout.addWidget(self.simulator_setting_group)
        self.expand_layout.addWidget(self.game_path_group)
        self.expand_layout.addWidget(self.autodaily_group)
        self.expand_layout.addWidget(self.personal_group)
        self.expand_layout.addWidget(self.logs_group)
        self.expand_layout.addWidget(self.experimental_group)
        self.expand_layout.addWidget(self.about_group)

    def __init_nav(self):
        """初始化左侧导航栏组件"""
        # ordered navigation items: (key, title, widget)
        nav_items = [
            ("game", QT_TRANSLATE_NOOP("Nav", "游戏设置"), self.game_setting_group),
            (
                "theme_pack",
                QT_TRANSLATE_NOOP("Nav", "镜牢主题包"),
                self.theme_pack_group,
            ),
            (
                "simulator",
                QT_TRANSLATE_NOOP("Nav", "模拟器设置"),
                self.simulator_setting_group,
            ),
            ("game_path", QT_TRANSLATE_NOOP("Nav", "启动游戏"), self.game_path_group),
            ("autodaily", QT_TRANSLATE_NOOP("Nav", "定时执行"), self.autodaily_group),
            ("personal", QT_TRANSLATE_NOOP("Nav", "个性化"), self.personal_group),
            ("logs", QT_TRANSLATE_NOOP("Nav", "调试"), self.logs_group),
            (
                "experimental",
                QT_TRANSLATE_NOOP("Nav", "实验性"),
                self.experimental_group,
            ),
            ("about", QT_TRANSLATE_NOOP("Nav", "关于"), self.about_group),
        ]

        self.setting_nav.add_nav_items(nav_items)

        # connect scroll sync
        self.setting_nav.navClicked.connect(self.__on_nav_clicked)
        self.content_scroll.verticalScrollBar().valueChanged.connect(self.__on_content_scrolled)

    def __on_nav_clicked(self, key: str, widget):
        """导航栏点击，滚动到指定内容"""
        target_y = widget.mapTo(self.scroll_widget, QPoint(0, 0)).y()
        bar = self.content_scroll.verticalScrollBar()
        # Offset to prevent the card from sticking exactly to the top edge
        SCROLL_OFFSET_PX = 8
        bar.setValue(max(0, target_y - SCROLL_OFFSET_PX))

    def __on_content_scrolled(self, value: int):
        """内容区域滚动，同步高亮导航栏"""
        scroll_max = self.content_scroll.verticalScrollBar().maximum()
        self.setting_nav.process_content_scrolled(value, self.scroll_widget, scroll_max)

    def _apply_theme_style(self, *_):
        light_qss, dark_qss = get_setting_interface_qss()
        self.setStyleSheet(dark_qss if isDarkTheme() else light_qss)

    def __connect_signal(self):
        self.game_path_card.clicked.connect(self.__onGamePathCardClicked)
        self.open_logs_card.clicked.connect(self.__onOpenLogsCardClicked)
        self.screenshot_benchmark_card.clicked.connect(self.__onScreenshotBenchmarkCardClicked)
        self.theme_pack_card.clicked.connect(self.__onThemePackCardClicked)

        self.zoom_card.valueChanged.connect(self.__onZoomCardValueChanged)
        self.auto_lang_card.switchButton.checkedChanged.connect(self.__onAutoLangCardChecked)
        self.win_input_type_card.valueChanged.connect(self.__onWinInputTypeChanged)
        self.debug_mode_card.switchButton.checkedChanged.connect(self.__onDebugModeChanged)
        self.logitech_switch_card.switchButton.checkedChanged.connect(self.__onExperimentalDependencyChanged)
        self.obs_switch_card.switchButton.checkedChanged.connect(self.__onExperimentalDependencyChanged)
        self.logitech_dll_path_card.clicked.connect(self.__onLogitechDllPathCardClicked)
        self.obs_host_card.clicked.connect(self.__onObsHostCardClicked)
        self.obs_password_card.clicked.connect(self.__onObsPasswordCardClicked)
        self.obs_source_name_card.clicked.connect(self.__onObsSourceNameCardClicked)
        self.__onWinInputTypeChanged()
        self.__refreshDebugCardVisibility()
        self.__refreshExperimentalCardVisibility()
        self.autostart_card.switchButton.checkedChanged.connect(self.__onAutostartCardChanged)
        self.theme_card.valueChanged.connect(self.__onThemeCardChanged)

        self.github_card.clicked.connect(self.__openUrl(self._get_repo_url()))
        self.discord_group_card.clicked.connect(self.__openUrl("https://discord.gg/vUAw98cEVe"))
        self.feedback_card.clicked.connect(
            self.__openUrl(f"{self._get_repo_url()}/issues")
        )

    def _get_repo_url(self) -> str:
        _is_canary = cfg.update_channel == "canary" or "-canary" in cfg.version
        return (
            "https://github.com/Small-tailqwq/AhabAssistantLimbusCompany"
            if _is_canary
            else "https://github.com/KIYI671/AhabAssistantLimbusCompany"
        )

    def __onGamePathCardClicked(self):
        game_path, _ = QFileDialog.getOpenFileName(self, "选择游戏路径", "", "Game Executable (LimbusCompany.exe)")
        if not game_path or cfg.game_path == game_path or not game_path.endswith("LimbusCompany.exe"):
            return
        cfg.set_value("game_path", game_path)
        self.game_path_card.setContent(game_path)

    def __onOpenLogsCardClicked(self):
        import os

        os.startfile(os.path.abspath("./logs"))

    def __refreshDebugCardVisibility(self):
        debug_enabled = bool(cfg.get_value("debug_mode", False))
        self.debug_mirror_route_card.setVisible(debug_enabled)
        self.debug_thread_dungeon_card.setVisible(debug_enabled)
        self.debug_retry_card.setVisible(debug_enabled)
        self.debug_shop_card.setVisible(debug_enabled)

        self.logs_group.adjustSize()
        self.scroll_widget.adjustSize()

    def __onDebugModeChanged(self, is_checked: bool):
        if not is_checked:
            for key in ["debug_mirror_route", "debug_thread_dungeon", "debug_retry", "debug_shop"]:
                if cfg.get_value(key, False):
                    cfg.set_value(key, False)
            self.debug_mirror_route_card.setValue(False)
            self.debug_thread_dungeon_card.setValue(False)
            self.debug_retry_card.setValue(False)
            self.debug_shop_card.setValue(False)
        self.__refreshDebugCardVisibility()

    def __refreshExperimentalCardContents(self):
        self.logitech_dll_path_card.setContent(cfg.get_value("logitech_dll_path", ""))
        self.obs_host_card.setContent(cfg.get_value("obs_host", "localhost"))
        self.obs_password_card.setContent(
            QT_TRANSLATE_NOOP("BasePushSettingCard", "(已设置)") if cfg.get_value("obs_password", "") else QT_TRANSLATE_NOOP("BasePushSettingCard", "(未设置)")
        )
        self.obs_source_name_card.setContent(cfg.get_value("obs_source_name", ""))

    def __refreshExperimentalCardVisibility(self):
        logitech_enabled = bool(cfg.get_value("lab_mouse_logitech", False))
        obs_enabled = bool(cfg.get_value("lab_screenshot_obs", False))

        self.logitech_dll_path_card.setVisible(logitech_enabled)
        self.logitech_bionic_trajectory_card.setVisible(logitech_enabled)

        self.obs_host_card.setVisible(obs_enabled)
        self.obs_port_card.setVisible(obs_enabled)
        self.obs_password_card.setVisible(obs_enabled)
        self.obs_source_name_card.setVisible(obs_enabled)
        self.obs_image_format_card.setVisible(obs_enabled)
        self.obs_image_quality_card.setVisible(obs_enabled)

        self.experimental_group.adjustSize()
        self.scroll_widget.adjustSize()

    def __onExperimentalDependencyChanged(self, _: bool):
        self.__refreshExperimentalCardVisibility()

    def __onLogitechDllPathCardClicked(self):
        dll_path, _ = QFileDialog.getOpenFileName(self, "选择罗技驱动 DLL", "", "DLL Files (*.dll)")
        if not dll_path or cfg.get_value("logitech_dll_path") == dll_path:
            return
        cfg.set_value("logitech_dll_path", dll_path)
        self.logitech_dll_path_card.setContent(dll_path)

    def __openTextEditForConfig(self, title: str, config_name: str, card, password: bool = False):
        current_value = str(cfg.get_value(config_name, "") or "")
        message_box = MessageBoxEdit(self.tr(title), current_value, self.window())
        if password:
            message_box.lineEdit.setEchoMode(QLineEdit.Password)
        if message_box.exec():
            new_value = str(message_box.getText()).strip()
            cfg.set_value(config_name, new_value)
            if password:
                card.setContent(self.tr("(已设置)") if new_value else self.tr("(未设置)"))
            else:
                card.setContent(new_value)

    def __onObsHostCardClicked(self):
        self.__openTextEditForConfig("OBS WebSocket 地址", "obs_host", self.obs_host_card)

    def __onObsPasswordCardClicked(self):
        self.__openTextEditForConfig("OBS WebSocket 密码", "obs_password", self.obs_password_card, password=True)

    def __onObsSourceNameCardClicked(self):
        self.__openTextEditForConfig("OBS 截图源名称", "obs_source_name", self.obs_source_name_card)

    def __onScreenshotBenchmarkCardClicked(self):
        from module.automation.screenshot import ScreenShot

        flag, time = ScreenShot.screenshot_benchmark()
        if flag:
            msg = QT_TRANSLATE_NOOP("BaseInfoBar", "10次截图平均耗时 {time:.2f} ms")
            BaseInfoBar.success(
                title=QT_TRANSLATE_NOOP("BaseInfoBar", "截图测试结束"),
                content=msg,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=5000,
                parent=self,
                content_kwargs={"time": time},
            )
        else:
            msg = QT_TRANSLATE_NOOP("BaseInfoBar", "请确保LimbusCompany正在运行")
            BaseInfoBar.error(
                title=QT_TRANSLATE_NOOP("BaseInfoBar", "截图测试结束"),
                content=msg,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=5000,
                parent=self,
            )

    def __onWinInputTypeChanged(self):
        input_type = cfg.get_value("win_input_type")
        if input_type == "background":
            content = QT_TRANSLATE_NOOP(
                "ComboBoxSettingCard",
                "后台模式，游戏可以在后台运行，但是<font color=red>游戏不能处于最小化状态!!</font>",
            )
            cfg.set_value("background_click", True)
        elif input_type == "foreground":
            content = QT_TRANSLATE_NOOP("ComboBoxSettingCard", "前台模式，游戏必须在显示在最上方")
            cfg.set_value("background_click", False)
        elif input_type == "window_move":
            content = QT_TRANSLATE_NOOP(
                "ComboBoxSettingCard",
                "基于移动窗口的后台模式，有效规避了后台模式需要移动鼠标的情况，<br/>但是性能和稳定性较差，<font color=red>不推荐长时间无人使用</font>",
            )
            cfg.set_value("background_click", True)
        else:
            content = QT_TRANSLATE_NOOP("ComboBoxSettingCard", "未知的输入模式，发生了错误")

        self.win_input_type_card.content = content
        self.win_input_type_card.setContent(content)
        self.win_input_type_card.retranslateUi()

    def __onZoomCardValueChanged(self):
        BaseInfoBar.success(
            title=QT_TRANSLATE_NOOP("BaseInfoBar", "更改将在重新启动后生效"),
            content="",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=5000,
            parent=self,
        )

    def __onAutostartCardChanged(self, checked: bool):
        TASK_NAME = "AALC Autostart"
        helper = ScheduleHelper()
        if checked:
            helper.register_onstart_task(TASK_NAME, "")
        else:
            helper.unregister_task(TASK_NAME)

    def __onAutoLangCardChecked(self, Checked):
        BaseInfoBar.success(
            title=QT_TRANSLATE_NOOP("BaseInfoBar", "更改将在重新启动后生效"),
            content="",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=5000,
            parent=self,
        )
        if Checked:
            cfg.set_value("language_in_game", "-")
        else:
            cfg.set_value("language_in_game", "en")

    def __openUrl(self, url):
        return lambda: QDesktopServices.openUrl(QUrl(url))

    def __onThemePackCardClicked(self):
        """打开主题包权重配置对话框"""
        dialog = ThemePackSettingDialog(
            self,
            config_data=theme_list.config,
            save_path=theme_list.theme_pack_list_path,
        )
        dialog.exec()

    def retranslateUi(self):
        self.setting_nav.retranslateUi()

        self.game_setting_group.retranslateUi()
        self.game_setting_card.retranslateUi()
        self.auto_hard_mirror_card.retranslateUi()
        self.last_auto_hard_mirror_card.retranslateUi()
        self.hard_mirror_chance_card.retranslateUi()
        self.win_input_type_card.retranslateUi()
        self.minimize_to_tray_card.retranslateUi()
        self.memory_protection.retranslateUi()
        self.screenshot_benchmark_card.retranslateUi()
        self.theme_pack_group.retranslateUi()
        self.theme_pack_card.retranslateUi()
        self.simulator_setting_group.retranslateUi()
        self.simulator_setting_card.retranslateUi()
        self.simulator_type_setting_card.retranslateUi()
        self.simulator_port_chance_card.retranslateUi()
        self.start_emulator_timeout_chance_card.retranslateUi()
        self.game_path_card.retranslateUi()
        self.game_path_group.retranslateUi()
        self.autodaily_group.retranslateUi()
        self.personal_group.retranslateUi()
        self.language_card.retranslateUi()
        self.theme_card.retranslateUi()
        self.zoom_card.retranslateUi()
        self.hotkey_card.retranslateUi()
        self.autostart_card.retranslateUi()
        self.autodaily_card.retranslateUi()
        self.autodaily_card_2.retranslateUi()
        self.autodaily_card_3.retranslateUi()
        self.autodaily_card_4.retranslateUi()
        self.logs_group.retranslateUi()
        self.experimental_group.retranslateUi()
        self.about_group.retranslateUi()
        self.version_card.retranslateUi()
        self.system_proxy_card.retranslateUi()
        self.open_logs_card.retranslateUi()
        self.github_card.retranslateUi()
        self.discord_group_card.retranslateUi()
        self.feedback_card.retranslateUi()
        self.experimental_group.retranslateUi()
        self.auto_lang_card.retranslateUi()
        self.low_res_match_card.retranslateUi()
        self.logitech_switch_card.retranslateUi()
        self.logitech_dll_path_card.retranslateUi()
        self.logitech_bionic_trajectory_card.retranslateUi()
        self.obs_switch_card.retranslateUi()
        self.obs_host_card.retranslateUi()
        self.obs_port_card.retranslateUi()
        self.obs_password_card.retranslateUi()
        self.obs_source_name_card.retranslateUi()
        self.obs_image_format_card.retranslateUi()
        self.obs_image_quality_card.retranslateUi()
        self.__refreshExperimentalCardContents()
        self.__refreshExperimentalCardVisibility()
        self.keep_screen_awake_card.retranslateUi()
        self.simulator_chinese_patch_card.retranslateUi()

    def __onThemeCardChanged(self):
        theme_mode = cfg.get_value("theme_mode")
        if theme_mode == "AUTO":
            setTheme(Theme.AUTO)
        elif theme_mode == "LIGHT":
            setTheme(Theme.LIGHT)
        elif theme_mode == "DARK":
            setTheme(Theme.DARK)
