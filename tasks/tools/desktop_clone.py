"""Desktop-clone configuration and lifecycle tool window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import CheckBox, qconfig

from app.card.messagebox_custom import MessageBoxConfirm, MessageBoxConfirmScroll
from app.language_manager import LanguageManager
from module.config import cfg
from module.desktop_clone.controller import get_desktop_clone_controller
from module.desktop_clone.messages import translate_message
from module.desktop_clone.profile import child_profile_dir
from module.logger import log
from tasks.tools.ui_style import apply_tool_window_theme, center_window, get_status_label_style


def confirm_remote_control_risk(controller, parent=None) -> bool:
    """Ask once per start whether to ignore running remote-control software."""
    warning = controller.remote_control_warning()
    if warning is None:
        return True
    log.warning(warning)
    message_box = MessageBoxConfirmScroll(
        QCoreApplication.translate("DesktopCloneWindow", "远程控制软件风险提示"),
        warning,
        parent,
    )
    message_box.yesButton.setText(
        QCoreApplication.translate("DesktopCloneWindow", "无视风险继续")
    )
    if message_box.exec():
        return True
    log.info("用户取消了桌面分身启动（远程控制软件风险提示）")
    return False


class DesktopCloneShutdownWorker(QThread):
    completed = Signal(bool, str)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller

    def run(self):
        try:
            stopped = self.controller.shutdown_session(timeout=5.0)
            detail = (
                ""
                if stopped
                else translate_message(
                    "Windows 尚未确认 Child Session 已注销"
                )
            )
            self.completed.emit(stopped, detail)
        except Exception as exc:
            log.exception("停止并注销桌面分身失败")
            self.completed.emit(False, str(exc))


class DesktopCloneWindow(QWidget):
    _TOOL_IDS = ("mute", "input")

    def __init__(self):
        super().__init__()
        self.controller = get_desktop_clone_controller()
        self._shutdown_worker = None
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowIcon(QIcon("./assets/logo/canary.ico"))
        self.setWindowTitle(self.tr("AALC 桌面分身"))
        self.setMinimumSize(620, 460)
        self._shutdown_in_progress = False
        self._init_ui()
        self._apply_theme_style()
        qconfig.themeChanged.connect(self._apply_theme_style)
        self._connect_controller()
        self._refresh_config()
        LanguageManager().register_component(self)
        self.retranslateUi()
        center_window(self)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.description_label = QLabel(
            QT_TRANSLATE_NOOP(
                "DesktopCloneWindow",
                "在独立的 Windows Child Session 中运行第二个 AALC 与 Steam 游戏。"
                "主桌面启动按钮会在开启功能后自动转交给分身。",
            )
        )
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)

        self.enabled_box = CheckBox(
            QT_TRANSLATE_NOOP("DesktopCloneWindow", "从主界面启动时使用桌面分身"),
            self,
        )
        self.show_on_start_box = CheckBox(
            QT_TRANSLATE_NOOP("DesktopCloneWindow", "创建分身时自动显示桌面窗口"),
            self,
        )
        self.toolbar_label = QLabel(
            QT_TRANSLATE_NOOP("DesktopCloneWindow", "窗口顶部快捷工具")
        )
        self.mute_tool_box = CheckBox(
            QT_TRANSLATE_NOOP(
                "DesktopCloneWindow",
                "显示“关闭声音”",
            ),
            self,
        )
        self.input_tool_box = CheckBox(
            QT_TRANSLATE_NOOP(
                "DesktopCloneWindow",
                "显示“关闭输入”",
            ),
            self,
        )
        self.sync_logs_box = CheckBox(
            QT_TRANSLATE_NOOP(
                "DesktopCloneWindow",
                "将分身日志同步到主控日志面板",
            ),
            self,
        )
        self.ignore_remote_control_box = CheckBox(
            QT_TRANSLATE_NOOP(
                "DesktopCloneWindow",
                "不再提示远程控制软件风险（风险自负）",
            ),
            self,
        )
        layout.addWidget(self.enabled_box)
        layout.addWidget(self.show_on_start_box)
        layout.addWidget(self.ignore_remote_control_box)
        layout.addWidget(self.toolbar_label)
        layout.addWidget(self.mute_tool_box)
        layout.addWidget(self.input_tool_box)
        layout.addWidget(self.sync_logs_box)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        first_row = QHBoxLayout()
        self.check_button = QPushButton(QT_TRANSLATE_NOOP("DesktopCloneWindow", "兼容性检查"))
        self.start_button = QPushButton(QT_TRANSLATE_NOOP("DesktopCloneWindow", "启动分身"))
        self.show_button = QPushButton(QT_TRANSLATE_NOOP("DesktopCloneWindow", "显示桌面"))
        self.hide_button = QPushButton(QT_TRANSLATE_NOOP("DesktopCloneWindow", "隐藏桌面"))
        first_row.addWidget(self.check_button)
        first_row.addWidget(self.start_button)
        first_row.addWidget(self.show_button)
        first_row.addWidget(self.hide_button)
        layout.addLayout(first_row)

        self.logoff_button = QPushButton(QT_TRANSLATE_NOOP("DesktopCloneWindow", "停止任务并注销分身"))
        self.open_log_button = QPushButton(QT_TRANSLATE_NOOP("DesktopCloneWindow", "打开日志目录"))
        bottom_row = QHBoxLayout()
        bottom_row.addWidget(self.logoff_button)
        bottom_row.addWidget(self.open_log_button)
        layout.addLayout(bottom_row)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(220)
        layout.addWidget(self.log_text)

        self.enabled_box.stateChanged.connect(
            lambda _: cfg.set_value("desktop_clone_enabled", self.enabled_box.isChecked())
        )
        self.show_on_start_box.stateChanged.connect(
            lambda _: cfg.set_value("desktop_clone_show_on_start", self.show_on_start_box.isChecked())
        )
        self.mute_tool_box.stateChanged.connect(
            lambda _: self._save_toolbar_items()
        )
        self.input_tool_box.stateChanged.connect(
            lambda _: self._save_toolbar_items()
        )
        self.sync_logs_box.stateChanged.connect(
            lambda _: cfg.set_value(
                "desktop_clone_sync_logs",
                self.sync_logs_box.isChecked(),
            )
        )
        self.ignore_remote_control_box.stateChanged.connect(
            lambda _: cfg.set_value(
                "desktop_clone_ignore_remote_control_warning",
                self.ignore_remote_control_box.isChecked(),
            )
        )
        self.check_button.clicked.connect(self._check_compatibility)
        self.start_button.clicked.connect(self._start_session)
        self.show_button.clicked.connect(self.controller.show_desktop)
        self.hide_button.clicked.connect(self.controller.hide_desktop)
        self.logoff_button.clicked.connect(self._confirm_logoff)
        self.open_log_button.clicked.connect(self._open_log_directory)

    def _connect_controller(self):
        self.controller.state_changed.connect(self._update_status)
        self.controller.error_occurred.connect(self._append_error)
        self.controller.visibility_changed.connect(self._on_visibility_changed)

    def _refresh_config(self):
        config_boxes = (
            self.enabled_box,
            self.show_on_start_box,
            self.mute_tool_box,
            self.input_tool_box,
            self.sync_logs_box,
            self.ignore_remote_control_box,
        )
        for box in config_boxes:
            box.blockSignals(True)
        self.enabled_box.setChecked(bool(cfg.get_value("desktop_clone_enabled", False)))
        self.show_on_start_box.setChecked(bool(cfg.get_value("desktop_clone_show_on_start", True)))
        visible_tools = cfg.get_value(
            "desktop_clone_toolbar_items",
            list(self._TOOL_IDS),
        )
        if not isinstance(visible_tools, list):
            visible_tools = list(self._TOOL_IDS)
        self.mute_tool_box.setChecked("mute" in visible_tools)
        self.input_tool_box.setChecked("input" in visible_tools)
        self.sync_logs_box.setChecked(
            bool(cfg.get_value("desktop_clone_sync_logs", True))
        )
        self.ignore_remote_control_box.setChecked(
            bool(cfg.get_value("desktop_clone_ignore_remote_control_warning", False))
        )
        for box in config_boxes:
            box.blockSignals(False)

    def _save_toolbar_items(self):
        visible_tools = [
            tool_id
            for tool_id, box in (
                ("mute", self.mute_tool_box),
                ("input", self.input_tool_box),
            )
            if box.isChecked()
        ]
        cfg.set_value("desktop_clone_toolbar_items", visible_tools)
        for tool_id in self._TOOL_IDS:
            self.controller.set_toolbar_tool_visible(
                tool_id,
                tool_id in visible_tools,
            )

    def _start_session(self):
        if not confirm_remote_control_risk(self.controller, self):
            return
        self.controller.start_session()

    def _check_compatibility(self):
        supported, details, warnings = self.controller.compatibility_details()
        self.log_text.append(self.tr("=== 桌面分身兼容性检查 ==="))
        for detail in details:
            self.log_text.append(detail)
        for warning in warnings:
            self.log_text.append(self.tr("警告：{0}").format(warning))
        self.log_text.append(self.tr("结果：可用") if supported else self.tr("结果：不可用"))

    def _open_log_directory(self):
        child_logs = child_profile_dir() / "logs"
        root_logs = Path("logs").resolve()
        target = child_logs if child_logs.is_dir() else root_logs
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        self.log_text.append(
            self.tr("分身日志目录：{0}；主控日志目录：{1}").format(
                child_logs,
                root_logs,
            )
        )

    def _confirm_logoff(self):
        if self._shutdown_in_progress:
            return
        message_box = MessageBoxConfirm(
            self.tr("停止并注销桌面分身"),
            self.tr("此操作会停止分身任务并关闭分身桌面中的所有程序，确定继续吗？"),
            self,
        )
        if not message_box.exec():
            return
        self._shutdown_in_progress = True
        self._set_buttons_enabled(False)
        self._shutdown_worker = DesktopCloneShutdownWorker(self.controller, self)
        self._shutdown_worker.completed.connect(self._on_shutdown_completed)
        self._shutdown_worker.finished.connect(
            self._on_shutdown_worker_finished
        )
        self._shutdown_worker.start()

    def _on_shutdown_completed(self, success: bool, detail: str):
        self.log_text.append(
            self.tr("桌面分身已注销")
            if success
            else self.tr("桌面分身注销失败：{0}").format(detail)
        )

    def _on_shutdown_worker_finished(self):
        if self.sender() is not self._shutdown_worker:
            return
        self._shutdown_in_progress = False
        self._shutdown_worker = None
        self._update_status(self.controller.state.value, self.controller.status_text)

    def _set_buttons_enabled(self, enabled: bool):
        for button in (
            self.check_button,
            self.start_button,
            self.show_button,
            self.hide_button,
            self.logoff_button,
        ):
            button.setEnabled(enabled)

    def _update_status(self, state: str, text: str):
        self.status_label.setText(self.tr("状态：{0}").format(text))
        self.log_text.append(text)
        session_active = self.controller.is_session_active
        lifecycle_active = self.controller.is_lifecycle_active
        self.start_button.setEnabled(not lifecycle_active)
        self.show_button.setEnabled(session_active)
        self.hide_button.setEnabled(session_active)
        self.logoff_button.setEnabled(lifecycle_active)
        if self._shutdown_in_progress:
            self._set_buttons_enabled(False)
        self.enabled_box.setEnabled(not self.controller.is_task_active)

    def _append_error(self, message: str):
        self.log_text.append(self.tr("错误：{0}").format(message))

    def _on_visibility_changed(self, visible: bool):
        self.log_text.append(self.tr("分身桌面已显示") if visible else self.tr("分身桌面已隐藏"))

    def _apply_theme_style(self):
        apply_tool_window_theme(self, "DesktopCloneWindow")
        self.status_label.setStyleSheet(get_status_label_style())

    def retranslateUi(self):
        self.setWindowTitle(self.tr("AALC 桌面分身"))
        self.description_label.setText(
            self.tr(
                "在独立的 Windows Child Session 中运行第二个 AALC 与 Steam 游戏。"
                "主桌面启动按钮会在开启功能后自动转交给分身。"
            )
        )
        self.enabled_box.setText(self.tr("从主界面启动时使用桌面分身"))
        self.show_on_start_box.setText(self.tr("创建分身时自动显示桌面窗口"))
        self.toolbar_label.setText(self.tr("窗口顶部快捷工具"))
        self.mute_tool_box.setText(self.tr("显示“关闭声音”"))
        self.input_tool_box.setText(self.tr("显示“关闭输入”"))
        self.sync_logs_box.setText(self.tr("将分身日志同步到主控日志面板"))
        self.ignore_remote_control_box.setText(
            self.tr("不再提示远程控制软件风险（风险自负）")
        )
        self.check_button.setText(self.tr("兼容性检查"))
        self.start_button.setText(self.tr("启动分身"))
        self.show_button.setText(self.tr("显示桌面"))
        self.hide_button.setText(self.tr("隐藏桌面"))
        self.logoff_button.setText(self.tr("停止任务并注销分身"))
        self.open_log_button.setText(self.tr("打开日志目录"))
        # 只刷新状态文本，不追加日志：_update_status 会写 log_text，
        # 语言切换时重复调用会产生重复行。
        self.status_label.setText(
            self.tr("状态：{0}").format(self.controller.status_text)
        )

    def closeEvent(self, event):
        if self._shutdown_worker is not None and self._shutdown_worker.isRunning():
            event.ignore()
            return
        LanguageManager().unregister_component(self)
        super().closeEvent(event)
