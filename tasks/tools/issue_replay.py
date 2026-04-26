from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app import mediator
from module.config import cfg
from module.issue_manager import (
    IssueManager,
    find_config_snapshots,
    find_metadata,
)
from module.logger import log


class IssueReplay(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("日志复现工具")
        self.setGeometry(100, 100, 780, 600)

        self._manager = IssueManager()
        self._preview_snapshots: list[dict] = []
        self._preview_meta: dict = {}
        self._preview_text: str = ""
        self._replay_active = False

        self.setup_ui()
        self._refresh_issue_list()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)

        main_layout.addWidget(self._build_import_area())
        main_layout.addWidget(self._build_issue_list())
        main_layout.addWidget(self._build_issue_actions())
        main_layout.addWidget(self._build_status_bar())

    def _build_import_area(self) -> QGroupBox:
        group = QGroupBox("导入日志")
        layout = QVBoxLayout(group)

        top_row = QHBoxLayout()
        btn_select = QPushButton("选择日志文件")
        btn_select.clicked.connect(self._on_select_log_file)
        btn_import = QPushButton("导入")

        btn_import.clicked.connect(self._on_import)
        top_row.addStretch()
        top_row.addWidget(btn_select)
        top_row.addWidget(btn_import)

        layout.addLayout(top_row)

        self.log_edit = QTextEdit()
        self.log_edit.setPlaceholderText("在此粘贴日志内容，或拖拽 .log / .txt 文件到此处...")
        self.log_edit.setMaximumHeight(120)
        self.log_edit.setAcceptDrops(True)
        self.log_edit.textChanged.connect(self._on_log_text_changed)
        layout.addWidget(self.log_edit)

        self.preview_label = QLabel("")
        self.preview_label.setStyleSheet("color: #888;")
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)

        self._snapshot_widget = QWidget()
        snapshot_row = QHBoxLayout(self._snapshot_widget)
        snapshot_row.setContentsMargins(0, 0, 0, 0)
        snapshot_row.addWidget(QLabel("配置快照:"))
        self.snapshot_combo = QComboBox()
        self.snapshot_combo.setMinimumWidth(240)
        self.snapshot_combo.hide()
        snapshot_row.addWidget(self.snapshot_combo)
        snapshot_row.addStretch()
        layout.addWidget(self._snapshot_widget)
        self._snapshot_widget.hide()

        return group

    def _build_issue_list(self) -> QGroupBox:
        group = QGroupBox("问题列表")
        layout = QVBoxLayout(group)

        self.issue_table = QTableWidget(0, 5)
        self.issue_table.setHorizontalHeaderLabels(
            ["ID", "名称", "版本", "导入时间", "修改时间"]
        )
        self.issue_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.issue_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.issue_table.horizontalHeader().setStretchLastSection(True)
        self.issue_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.issue_table.setMinimumHeight(150)
        self.issue_table.itemSelectionChanged.connect(self._on_issue_selected)
        self.issue_table.itemDoubleClicked.connect(self._on_issue_double_clicked)
        layout.addWidget(self.issue_table)

        self.issue_notes_label = QLabel("")
        self.issue_notes_label.setStyleSheet("color: #888;")
        self.issue_notes_label.setWordWrap(True)
        layout.addWidget(self.issue_notes_label)

        return group

    def _build_issue_actions(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.btn_load_config = QPushButton("加载此配置到AALC")
        self.btn_load_config.clicked.connect(self._on_load_config)
        self.btn_load_config.setEnabled(False)

        self.btn_rename = QPushButton("重命名")
        self.btn_rename.clicked.connect(self._on_rename)
        self.btn_rename.setEnabled(False)

        self.btn_delete = QPushButton("删除")
        self.btn_delete.clicked.connect(self._on_delete)
        self.btn_delete.setEnabled(False)

        self.btn_notes = QPushButton("编辑批注")
        self.btn_notes.clicked.connect(self._on_edit_notes)
        self.btn_notes.setEnabled(False)

        layout.addWidget(self.btn_load_config)
        layout.addWidget(self.btn_rename)
        layout.addWidget(self.btn_delete)
        layout.addWidget(self.btn_notes)
        layout.addStretch()

        return widget

    def _build_status_bar(self) -> QGroupBox:
        group = QGroupBox("状态")
        layout = QHBoxLayout(group)

        self.status_label = QLabel("● 当前使用: 开发者配置")
        self.status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        layout.addWidget(self.status_label)
        layout.addStretch()

        self.btn_restore = QPushButton("恢复我的配置")
        self.btn_restore.clicked.connect(self._on_restore_config)
        self.btn_restore.setVisible(False)
        layout.addWidget(self.btn_restore)

        return group

    def _current_issue_id(self) -> str | None:
        row = self.issue_table.currentRow()
        if row < 0:
            return None
        item = self.issue_table.item(row, 0)
        return item.text() if item else None

    def _refresh_issue_list(self):
        self.issue_table.setRowCount(0)
        issues = self._manager.list_issues()
        for rec in issues:
            row = self.issue_table.rowCount()
            self.issue_table.insertRow(row)
            self.issue_table.setItem(row, 0, QTableWidgetItem(rec.id))
            self.issue_table.setItem(row, 1, QTableWidgetItem(rec.name))
            self.issue_table.setItem(row, 2, QTableWidgetItem(rec.aalc_version))
            self.issue_table.setItem(row, 3, QTableWidgetItem(rec.created_at))
            self.issue_table.setItem(row, 4, QTableWidgetItem(rec.modified_at))

        self._on_issue_selected()

    def _on_issue_selected(self):
        issue_id = self._current_issue_id()
        has_sel = issue_id is not None
        self.btn_load_config.setEnabled(has_sel)
        self.btn_rename.setEnabled(has_sel)
        self.btn_delete.setEnabled(has_sel)
        self.btn_notes.setEnabled(has_sel)

        if has_sel:
            notes = self._manager.get_notes(issue_id)
            self.issue_notes_label.setText(f"批注: {notes}" if notes else "")
        else:
            self.issue_notes_label.setText("")

    def _on_issue_double_clicked(self, _):
        self._on_load_config()

    def _on_log_text_changed(self):
        text = self.log_edit.toPlainText().strip()
        if not text:
            self.preview_label.setText("")
            self.snapshot_combo.hide()
            return

        self._preview_text = text
        self._preview_meta = find_metadata(text)
        self._preview_snapshots = find_config_snapshots(text)

        parts = []
        ver = self._preview_meta.get("version", "未知")
        res = self._preview_meta.get("resolution", "未知")
        parts.append(f"AALC 版本: {ver}")
        parts.append(f"游戏分辨率: {res}")
        parts.append(f"找到 {len(self._preview_snapshots)} 个配置快照")

        self.preview_label.setText("  ".join(parts))

        if len(self._preview_snapshots) > 1:
            self.snapshot_combo.clear()
            for i, snap in enumerate(self._preview_snapshots):
                field_count = len(snap)
                self.snapshot_combo.addItem(f"快照 #{i + 1} ({field_count} 个配置项)")
            self.snapshot_combo.show()
            self._snapshot_widget.setVisible(True)
        else:
            self.snapshot_combo.hide()
            self._snapshot_widget.setVisible(False)

    def _on_select_log_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择日志文件",
            "",
            "日志文件 (*.log *.txt);;所有文件 (*)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            self.log_edit.setPlainText(text)
        except Exception as e:
            log.error(f"读取日志文件失败: {e}")
            QMessageBox.warning(self, "错误", f"读取日志文件失败:\n{e}")

    def _on_import(self):
        text = self.log_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "请先粘贴日志内容或选择日志文件")
            return

        config_index = 0
        if len(self._preview_snapshots) > 1:
            config_index = self.snapshot_combo.currentIndex()

        issue_id, snapshots, meta, warnings = self._manager.import_issue(
            text, config_index=config_index
        )

        if issue_id is None:
            QMessageBox.warning(self, "导入失败", "未能在日志中找到任何配置快照")
            return

        msg = f"已导入为 issue{issue_id}\nAALC 版本: {meta.get('version', '未知')}"
        if warnings:
            msg += "\n\n潜在问题:\n" + "\n".join(f"  [!] {w}" for w in warnings)

        QMessageBox.information(self, "导入成功", msg)
        self.log_edit.clear()
        self.preview_label.setText("")
        self.snapshot_combo.hide()
        self._snapshot_widget.hide()
        self._preview_snapshots = []
        self._preview_meta = {}
        self._preview_text = ""
        self._refresh_issue_list()

    def _on_load_config(self):
        issue_id = self._current_issue_id()
        if not issue_id:
            return

        config_path = self._manager.get_config_path(issue_id)
        if not config_path.exists():
            QMessageBox.warning(self, "错误", f"找不到 issue{issue_id} 的配置文件")
            return

        try:
            cfg.set_save_suspended(True, source=f"issue{issue_id}")
            cfg.just_load_config(str(config_path))
            self._replay_active = True
            self._update_status_for_replay(issue_id)
            mediator.config_reloaded.emit()
            log.info(f"已热加载 issue{issue_id} 的配置文件，写盘已暂停")
        except Exception as e:
            log.error(f"加载 issue 配置失败: {e}")
            QMessageBox.warning(self, "错误", f"加载配置文件失败:\n{e}")

    def _update_status_for_replay(self, issue_id: str):
        rec = self._manager.get_issue(issue_id)
        name = rec.name if rec else issue_id
        self.status_label.setText(f"● 当前使用: 重放模式 - {name}")
        self.status_label.setStyleSheet("color: #FF9800; font-weight: bold;")
        self.btn_restore.setVisible(True)

    def _update_status_for_dev(self):
        self.status_label.setText("● 当前使用: 开发者配置")
        self.status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        self.btn_restore.setVisible(False)

    def _on_restore_config(self):
        try:
            cfg.set_save_suspended(False)
            cfg.just_load_config("./config.yaml")
            self._replay_active = False
            self._update_status_for_dev()
            mediator.config_reloaded.emit()
            log.info("已恢复开发者配置文件，写盘已恢复")
        except Exception as e:
            log.error(f"恢复配置失败: {e}")
            QMessageBox.warning(self, "错误", f"恢复配置文件失败:\n{e}")

    def _on_rename(self):
        issue_id = self._current_issue_id()
        if not issue_id:
            return
        rec = self._manager.get_issue(issue_id)
        if not rec:
            return

        dialog = QWidget(self, Qt.WindowType.Dialog)
        dialog.setWindowTitle("重命名")
        dialog.setFixedSize(360, 120)
        layout = QVBoxLayout(dialog)

        edit = QLineEdit(rec.name)
        layout.addWidget(QLabel("新名称:"))
        layout.addWidget(edit)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        btn_cancel.clicked.connect(dialog.close)

        def do_rename():
            new_name = edit.text().strip()
            if new_name:
                self._manager.rename_issue(issue_id, new_name)
                self._refresh_issue_list()
            dialog.close()

        btn_ok.clicked.connect(do_rename)
        dialog.show()

    def _on_delete(self):
        issue_id = self._current_issue_id()
        if not issue_id:
            return
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除 issue{issue_id} 吗？\n此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._manager.delete_issue(issue_id)
        self._refresh_issue_list()

    def _on_edit_notes(self):
        issue_id = self._current_issue_id()
        if not issue_id:
            return

        current_notes = self._manager.get_notes(issue_id) or ""

        dialog = QWidget(self, Qt.WindowType.Dialog)
        dialog.setWindowTitle("编辑批注")
        dialog.setFixedSize(480, 300)
        layout = QVBoxLayout(dialog)

        edit = QTextEdit()
        edit.setPlainText(current_notes)
        layout.addWidget(QLabel("开发者批注:"))
        layout.addWidget(edit)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        btn_cancel.clicked.connect(dialog.close)

        def save_notes():
            self._manager.set_notes(issue_id, edit.toPlainText())
            self._refresh_issue_list()
            dialog.close()

        btn_ok.clicked.connect(save_notes)
        dialog.show()

    def closeEvent(self, event):
        if self._replay_active:
            try:
                cfg.set_save_suspended(False)
                cfg.just_load_config("./config.yaml")
                self._replay_active = False
                mediator.config_reloaded.emit()
                log.info("日志复现工具关闭，已自动恢复开发者配置")
            except Exception as e:
                log.error(f"关闭时恢复配置失败: {e}")
        super().closeEvent(event)
