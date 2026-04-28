import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
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
    _format_time,
    find_config_snapshots,
    find_metadata,
)
from module.logger import log


class _MarkdownEditSidecar(QWidget):
    """Markdown 编辑侧窗：左源码右预览，类似 Typora 的编辑体验。"""

    def __init__(self, issue_id: str, initial_text: str, on_save, parent):
        super().__init__(parent, Qt.WindowType.Window)
        self._issue_id = issue_id
        self._on_save = on_save
        self._parent_window = parent
        self.setWindowTitle(f"编辑批注 — issue{issue_id}")
        self.setWindowIcon(QIcon("./assets/logo/canary.ico"))
        self.resize(760, 520)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Markdown 源码"))
        self._edit = QTextEdit()
        self._edit.setPlainText(initial_text)
        self._edit.textChanged.connect(self._on_text_changed)
        left_layout.addWidget(self._edit)
        splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("预览"))
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        right_layout.addWidget(self._preview)
        splitter.addWidget(right_widget)

        splitter.setSizes([380, 380])

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        btn_save = QPushButton("保存 (Ctrl+S)")
        btn_save.clicked.connect(self._do_save)
        bottom_row.addWidget(btn_save)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(splitter)
        main_layout.addLayout(bottom_row)

        self._on_text_changed()
        self._position_next_to_parent()

    def showEvent(self, event):
        super().showEvent(event)
        self._position_next_to_parent()

    def _position_next_to_parent(self):
        if self._parent_window and self._parent_window.isVisible():
            p_geo = self._parent_window.geometry()
            self.move(p_geo.right() + 8, p_geo.top())
            if self.height() > p_geo.height():
                self.resize(self.width(), p_geo.height())

    def _on_text_changed(self):
        text = self._edit.toPlainText()
        try:
            from markdown_it import MarkdownIt

            md = MarkdownIt()
            html = md.render(text)
        except ImportError:
            html = f"<pre>{text}</pre>"
        self._preview.setHtml(html)

    def _do_save(self):
        self._on_save(self._issue_id, self._edit.toPlainText())
        self.close()


class IssueReplay(QWidget):
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(False)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("日志复现工具")
        self.setWindowIcon(QIcon("./assets/logo/canary.ico"))
        self.resize(900, 640)

        self._manager = IssueManager()
        self._preview_snapshots: list[dict] = []
        self._preview_meta: dict = {}
        self._preview_text: str = ""
        self._replay_active = False

        self.setup_ui()
        self._refresh_issue_list()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(300, self._setup_win_file_drop)

    def _setup_win_file_drop(self):
        if os.name != "nt":
            return
        import ctypes
        from ctypes import wintypes

        hwnd_val = int(self.winId())
        if not hwnd_val:
            return

        hwnd = wintypes.HWND(hwnd_val)
        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32

        MSGFLT_ALLOW = 1
        for msg_id in (0x0233, 0x0049, 0x004A):
            try:
                user32.ChangeWindowMessageFilterEx(hwnd, msg_id, MSGFLT_ALLOW, None)
            except Exception:
                pass
        try:
            user32.ChangeWindowMessageFilter(0x0233, MSGFLT_ALLOW)
            user32.ChangeWindowMessageFilter(0x0049, MSGFLT_ALLOW)
            user32.ChangeWindowMessageFilter(0x004A, MSGFLT_ALLOW)
        except Exception:
            pass

        # 撤销 Qt 可能已注册的 OLE IDropTarget，用 DragAcceptFiles 替代
        try:
            ctypes.windll.ole32.RevokeDragDrop(hwnd_val)
        except Exception:
            pass
        shell32.DragAcceptFiles(hwnd_val, True)

    def nativeEvent(self, eventType, message):
        if os.name != "nt":
            return super().nativeEvent(eventType, message)

        try:
            import ctypes
            from ctypes import create_unicode_buffer, windll
            from ctypes.wintypes import HANDLE, MSG, UINT

            msg = MSG.from_address(int(message))
            if msg.message == 0x0233:
                hDrop = HANDLE(msg.wParam)
                shell32 = windll.shell32
                shell32.DragQueryFileW.argtypes = [HANDLE, UINT, ctypes.c_wchar_p, UINT]
                count = shell32.DragQueryFileW(hDrop, UINT(0xFFFFFFFF), None, 0)
                if count > 0:
                    buf_size = shell32.DragQueryFileW(hDrop, 0, None, 0) + 1
                    buf = create_unicode_buffer(buf_size)
                    shell32.DragQueryFileW(hDrop, 0, buf, buf_size)
                    shell32.DragFinish(hDrop)

                    path = buf.value
                    target = self._find_active_drop_target()
                    if target:
                        try:
                            with open(path, "r", encoding="utf-8") as f:
                                target.setPlainText(f.read())
                        except Exception:
                            log.warning(f"读取拖放文件失败: {path}")
                return True, 0
        except Exception:
            pass

        return super().nativeEvent(eventType, message)

    def _find_active_drop_target(self) -> QTextEdit | None:
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QApplication

        global_pos = QCursor.pos()
        widget = QApplication.widgetAt(global_pos)
        if isinstance(widget, QTextEdit) and widget.window() is self and not widget.isReadOnly():
            return widget
        return self.log_edit

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
        self.log_edit.setAcceptDrops(False)
        self.log_edit.viewport().setAcceptDrops(False)
        self.log_edit.setPlaceholderText("在此粘贴日志内容，或拖拽 .log / .txt 文件到此处...")
        self.log_edit.setMaximumHeight(120)
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

        self.issue_table = QTableWidget(0, 6)
        self.issue_table.setHorizontalHeaderLabels(
            ["#", "ID", "名称", "版本", "导入时间", "修改时间"]
        )
        self.issue_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.issue_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.issue_table.setAlternatingRowColors(True)
        self.issue_table.horizontalHeader().setStretchLastSection(True)
        self.issue_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.issue_table.verticalHeader().setVisible(False)
        self.issue_table.setColumnWidth(0, 36)
        self.issue_table.setColumnWidth(1, 40)
        self.issue_table.setColumnWidth(2, 180)
        self.issue_table.setColumnWidth(3, 64)
        self.issue_table.setColumnWidth(4, 128)
        self.issue_table.setMinimumHeight(180)
        self.issue_table.itemSelectionChanged.connect(self._on_issue_selected)
        self.issue_table.itemDoubleClicked.connect(self._on_issue_double_clicked)
        self.issue_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.issue_table.customContextMenuRequested.connect(self._on_issue_context_menu)
        layout.addWidget(self.issue_table)

        self.issue_notes_label = QLabel("开发者批注:")
        self.issue_notes_label.hide()
        layout.addWidget(self.issue_notes_label)

        self.issue_notes_edit = QTextEdit()
        self.issue_notes_edit.setReadOnly(True)
        self.issue_notes_edit.setMinimumHeight(60)
        self.issue_notes_edit.setMaximumHeight(160)
        self.issue_notes_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.issue_notes_edit.setStyleSheet(
            "QTextEdit { background-color: palette(base); border: 1px solid palette(mid);"
            " border-radius: 4px; padding: 6px; }"
        )
        self.issue_notes_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.issue_notes_edit.customContextMenuRequested.connect(self._on_notes_context_menu)
        self.issue_notes_edit.hide()
        layout.addWidget(self.issue_notes_edit)

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

        self.btn_append_log = QPushButton("追加日志")
        self.btn_append_log.clicked.connect(self._on_append_log)
        self.btn_append_log.setEnabled(False)

        layout.addWidget(self.btn_load_config)
        layout.addWidget(self.btn_rename)
        layout.addWidget(self.btn_delete)
        layout.addWidget(self.btn_notes)
        layout.addWidget(self.btn_append_log)
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
        item = self.issue_table.item(row, 1)
        return item.text() if item else None

    def _refresh_issue_list(self):
        self.issue_table.setRowCount(0)
        issues = self._manager.list_issues()
        for i, rec in enumerate(issues):
            row = self.issue_table.rowCount()
            self.issue_table.insertRow(row)

            num_item = QTableWidgetItem(str(i + 1))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            num_item.setForeground(QBrush(QColor("#888888")))
            self.issue_table.setItem(row, 0, num_item)

            id_item = QTableWidgetItem(rec.id)
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.issue_table.setItem(row, 1, id_item)

            self.issue_table.setItem(row, 2, QTableWidgetItem(rec.name))
            self.issue_table.setItem(row, 3, QTableWidgetItem(rec.aalc_version))
            self.issue_table.setItem(row, 4, QTableWidgetItem(_format_time(rec.created_at)))
            self.issue_table.setItem(row, 5, QTableWidgetItem(_format_time(rec.modified_at)))

        self._on_issue_selected()

    def _on_issue_selected(self):
        issue_id = self._current_issue_id()
        has_sel = issue_id is not None
        self.btn_load_config.setEnabled(has_sel)
        self.btn_rename.setEnabled(has_sel)
        self.btn_delete.setEnabled(has_sel)
        self.btn_notes.setEnabled(has_sel)
        self.btn_append_log.setEnabled(has_sel)

        if has_sel:
            notes = self._manager.get_notes(issue_id)
            if notes:
                try:
                    from markdown_it import MarkdownIt
                except ImportError:
                    MarkdownIt = None
                if MarkdownIt is not None:
                    md = MarkdownIt()
                    html = md.render(notes)
                    self.issue_notes_edit.setHtml(html)
                else:
                    self.issue_notes_edit.setPlainText(notes)
                self.issue_notes_label.show()
                self.issue_notes_edit.show()
            else:
                self.issue_notes_label.hide()
                self.issue_notes_edit.hide()
        else:
            self.issue_notes_label.hide()
            self.issue_notes_edit.hide()

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

    def _on_notes_context_menu(self, pos):
        issue_id = self._current_issue_id()
        if not issue_id:
            return
        menu = QMenu(self)
        action_edit = menu.addAction("编辑批注")
        action_edit.triggered.connect(self._on_edit_notes)
        menu.exec(self.issue_notes_edit.viewport().mapToGlobal(pos))

    def _on_edit_notes(self):
        issue_id = self._current_issue_id()
        if not issue_id:
            return
        current_notes = self._manager.get_notes(issue_id) or ""

        def save_notes(iid, text):
            self._manager.set_notes(iid, text)
            self._refresh_issue_list()
            self._on_issue_selected()

        sidecar = _MarkdownEditSidecar(issue_id, current_notes, save_notes, self)
        sidecar.show()

    def _on_append_log(self):
        issue_id = self._current_issue_id()
        if not issue_id:
            return
        rec = self._manager.get_issue(issue_id)
        if not rec:
            return

        dialog = QWidget(self, Qt.WindowType.Dialog)
        dialog.setWindowTitle("追加日志")
        dialog.setFixedSize(560, 340)
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("向 issue{} ({}) 追加日志:".format(issue_id, rec.name)))

        top_row = QHBoxLayout()
        btn_select = QPushButton("选择日志文件")
        top_row.addStretch()
        top_row.addWidget(btn_select)
        layout.addLayout(top_row)

        edit = QTextEdit()
        edit.setPlaceholderText("在此粘贴日志内容，或点击上方按钮选择 .log / .txt 文件...")
        layout.addWidget(edit)

        filename_label = QLabel("")
        filename_label.setStyleSheet("color: #888;")
        layout.addWidget(filename_label)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        btn_cancel.clicked.connect(dialog.close)

        def select_file():
            path, _ = QFileDialog.getOpenFileName(
                dialog,
                "选择日志文件",
                "",
                "日志文件 (*.log *.txt);;所有文件 (*)",
            )
            if not path:
                return
            try:
                with open(path, "r", encoding="utf-8") as f:
                    edit.setPlainText(f.read())
                filename_label.setText(f"已选择: {path}")
            except Exception as e:
                log.error(f"读取日志文件失败: {e}")
                QMessageBox.warning(dialog, "错误", f"读取日志文件失败:\n{e}")

        btn_select.clicked.connect(select_file)

        def do_append():
            text = edit.toPlainText().strip()
            if not text:
                QMessageBox.warning(dialog, "提示", "请先粘贴日志内容或选择日志文件")
                return
            self._manager.append_log(issue_id, text)
            self._refresh_issue_list()
            QMessageBox.information(dialog, "追加成功", f"已向 issue{issue_id} 追加日志")
            dialog.close()

        btn_ok.clicked.connect(do_append)
        dialog.show()

    def _on_issue_context_menu(self, pos):
        row = self.issue_table.rowAt(pos.y())
        if row < 0:
            return
        self.issue_table.selectRow(row)
        menu = QMenu(self)
        action_reimport = menu.addAction("重新导入日志")
        action_reimport.triggered.connect(self._on_reimport)
        menu.exec(self.issue_table.viewport().mapToGlobal(pos))

    def _on_reimport(self):
        issue_id = self._current_issue_id()
        if not issue_id:
            return
        rec = self._manager.get_issue(issue_id)
        if not rec:
            return

        snapshots_holder: list = []
        meta_holder: dict = {}

        dialog = QWidget(self, Qt.WindowType.Dialog)
        dialog.setWindowTitle("重新导入日志")
        dialog.setFixedSize(600, 400)
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("重新导入 issue{} ({}) 的日志:".format(issue_id, rec.name)))

        top_row = QHBoxLayout()
        btn_select = QPushButton("选择日志文件")
        top_row.addStretch()
        top_row.addWidget(btn_select)
        layout.addLayout(top_row)

        edit = QTextEdit()
        edit.setPlaceholderText("在此粘贴日志内容，或点击上方按钮选择 .log / .txt 文件...")
        edit.setMaximumHeight(150)
        layout.addWidget(edit)

        filename_label = QLabel("")
        filename_label.setStyleSheet("color: #888;")
        layout.addWidget(filename_label)

        preview_label = QLabel("")
        preview_label.setStyleSheet("color: #888;")
        preview_label.setWordWrap(True)
        layout.addWidget(preview_label)

        snapshot_widget = QWidget()
        snapshot_row = QHBoxLayout(snapshot_widget)
        snapshot_row.setContentsMargins(0, 0, 0, 0)
        snapshot_row.addWidget(QLabel("配置快照:"))
        snapshot_combo = QComboBox()
        snapshot_combo.setMinimumWidth(240)
        snapshot_combo.hide()
        snapshot_row.addWidget(snapshot_combo)
        snapshot_row.addStretch()
        layout.addWidget(snapshot_widget)
        snapshot_widget.hide()

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        btn_cancel.clicked.connect(dialog.close)

        def select_file():
            path, _ = QFileDialog.getOpenFileName(
                dialog,
                "选择日志文件",
                "",
                "日志文件 (*.log *.txt);;所有文件 (*)",
            )
            if not path:
                return
            try:
                with open(path, "r", encoding="utf-8") as f:
                    edit.setPlainText(f.read())
                filename_label.setText(f"已选择: {path}")
            except Exception as e:
                log.error(f"读取日志文件失败: {e}")
                QMessageBox.warning(dialog, "错误", f"读取日志文件失败:\n{e}")

        btn_select.clicked.connect(select_file)

        def on_text_changed():
            text = edit.toPlainText().strip()
            if not text:
                preview_label.setText("")
                snapshot_combo.hide()
                snapshot_widget.hide()
                return
            snapshots_holder.clear()
            snapshots_holder.extend(find_config_snapshots(text))
            meta_holder.clear()
            meta_holder.update(find_metadata(text))

            parts = []
            parts.append(f"AALC 版本: {meta_holder.get('version', '未知')}")
            parts.append(f"游戏分辨率: {meta_holder.get('resolution', '未知')}")
            parts.append(f"找到 {len(snapshots_holder)} 个配置快照")
            preview_label.setText("  ".join(parts))

            if len(snapshots_holder) > 1:
                snapshot_combo.clear()
                for i, snap in enumerate(snapshots_holder):
                    field_count = len(snap)
                    snapshot_combo.addItem(f"快照 #{i + 1} ({field_count} 个配置项)")
                snapshot_combo.show()
                snapshot_widget.setVisible(True)
            else:
                snapshot_combo.hide()
                snapshot_widget.setVisible(False)

        edit.textChanged.connect(on_text_changed)

        def do_reimport():
            text = edit.toPlainText().strip()
            if not text:
                QMessageBox.warning(dialog, "提示", "请先粘贴日志内容或选择日志文件")
                return
            config_index = 0
            if len(snapshots_holder) > 1:
                config_index = snapshot_combo.currentIndex()
            success, snapshots, meta, warnings = self._manager.reimport_issue(
                issue_id, text, config_index=config_index
            )
            if not success:
                QMessageBox.warning(dialog, "重新导入失败", warnings[0] if warnings else "未知错误")
                return
            msg = f"已刷新 issue{issue_id} 的日志和配置\nAALC 版本: {meta.get('version', '未知')}"
            if warnings:
                msg += "\n\n潜在问题:\n" + "\n".join(f"  [!] {w}" for w in warnings)
            QMessageBox.information(dialog, "重新导入成功", msg)
            self._refresh_issue_list()
            dialog.close()

        btn_ok.clicked.connect(do_reimport)
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
