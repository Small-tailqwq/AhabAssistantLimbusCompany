"""UI widgets for the asset manager."""

import os
import subprocess
import sys

import pyperclip
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tasks.tools.asset_library.model import ASSET_IMAGES_ROOT
from tasks.tools.asset_library.recycle import RecycleManager, _asset_key_from_path

ASSETS_ROOT = os.path.abspath(ASSET_IMAGES_ROOT)


class CategoryTree(QTreeWidget):
    category_selected = Signal(str)

    CATEGORIES = {
        "全部": None,
        "主界面": "home",
        "体力": "enkephalin",
        "战斗": "battle",
        "邮件": "mail",
        "场景/过场": "scenes",
        "基础通用": "base",
        "日常事件": "event",
        "镜牢": None,
        "  寻路": "mirror_road",
        "  商店": "mirror_shop",
        "  事件": "mirror_event",
        "  结算/奖励": "mirror_reward",
        "  主题包": "mirror_theme_pack",
        "  通用UI": "mirror_ui",
        "队伍": "teams",
        "通行证": "pass",
        "反射": "luxcavation",
        "未分类": "uncategorized",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(0)
        self.setMaximumWidth(180)

        for label, key in self.CATEGORIES.items():
            item = QTreeWidgetItem(self)
            item.setText(0, label)
            item.setData(0, Qt.UserRole, key or "")
            item.setFlags(item.flags() & ~Qt.ItemIsDropEnabled)

        self.currentItemChanged.connect(self._on_item_changed)

    def _on_item_changed(self, current, _previous):
        if current:
            key = current.data(0, Qt.UserRole) or None
            self.category_selected.emit(key)


class AssetGridWidget(QListWidget):
    asset_selected = Signal(dict)
    context_menu_requested = Signal(list, QListWidgetItem)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QPixmap(120, 120).size())
        self.setResizeMode(QListWidget.Adjust)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.itemSelectionChanged.connect(self._on_selection)

        self._assets: list[dict] = []
        self._batch_size = 100
        self._loaded = 0

        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def set_assets(self, assets: list[dict]):
        self.clear()
        self._assets = assets
        self._loaded = 0
        self._load_batch()

    def _load_batch(self):
        end = min(self._loaded + self._batch_size, len(self._assets))
        for i in range(self._loaded, end):
            asset = self._assets[i]
            item = QListWidgetItem()
            item.setData(Qt.UserRole, asset)

            abspath = os.path.join(ASSETS_ROOT, asset["file"])
            if os.path.exists(abspath):
                reader = QImageReader(abspath)
                reader.setScaledSize(QPixmap(120, 120).size())
                pixmap = QPixmap.fromImageReader(reader)
                icon = QIcon(pixmap)
                item.setIcon(icon)
            else:
                item.setText("[Missing]")

            name = asset.get("business_name") or os.path.basename(asset["file"])
            item.setText(name)
            item.setToolTip(
                f"{asset['file']}\n{asset.get('business_name', '')}\n{asset.get('note', '')}"
            )
            self.addItem(item)
        self._loaded = end

    def _on_scroll(self, value):
        scrollbar = self.verticalScrollBar()
        if value >= scrollbar.maximum() - 10 and self._loaded < len(self._assets):
            self._load_batch()

    def _on_selection(self):
        items = self.selectedItems()
        if items:
            asset = items[0].data(Qt.UserRole)
            self.asset_selected.emit(asset)

    def _context_menu(self, pos):
        item = self.itemAt(pos)
        if not item:
            return
        asset = item.data(Qt.UserRole)
        menu = QMenu(self)

        open_action = menu.addAction("在文件管理器中打开")
        copy_action = menu.addAction("复制路径")
        menu.addSeparator()
        mark_missing_action = menu.addAction("标记为已删除")
        restore_action = menu.addAction("从回收站恢复")

        chosen = menu.exec(self.mapToGlobal(pos))

        if chosen == open_action:
            abspath = os.path.join(ASSETS_ROOT, asset["file"])
            dirpath = os.path.dirname(os.path.abspath(abspath))
            if sys.platform == "win32":
                os.startfile(dirpath)
            else:
                subprocess.Popen(["xdg-open", dirpath])

        elif chosen == copy_action:
            pyperclip.copy(asset["file"])

        elif chosen == mark_missing_action:
            self.context_menu_requested.emit(["mark_missing", asset], item)

        elif chosen == restore_action:
            self.context_menu_requested.emit(["restore", asset], item)

    def refresh_item(self, asset: dict):
        """Update an existing item after metadata change (called externally)."""
        for i in range(self.count()):
            item = self.item(i)
            stored = item.data(Qt.UserRole)
            if stored.get("file") == asset.get("file"):
                name = asset.get("business_name") or os.path.basename(asset["file"])
                item.setText(name)
                item.setData(Qt.UserRole, asset)
                return


class ImageLabel(QLabel):
    """Clickable thumbnail label with drag-drop support."""

    clicked = Signal()
    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(150, 150)
        self.setStyleSheet("QLabel { border: 1px solid #555; border-radius: 4px; }")
        self.setScaledContents(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0]
            if url.toLocalFile().lower().endswith((".png", ".webp", ".jpg", ".jpeg", ".bmp")):
                event.acceptProposedAction()
                self.setStyleSheet("QLabel { border: 2px solid #9c080b; border-radius: 4px; }")
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet("QLabel { border: 1px solid #555; border-radius: 4px; }")

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet("QLabel { border: 1px solid #555; border-radius: 4px; }")
        if event.mimeData().hasUrls():
            filepath = event.mimeData().urls()[0].toLocalFile()
            self.file_dropped.emit(filepath)
            event.acceptProposedAction()


class AssetDetailPanel(QWidget):
    business_changed = Signal(str)
    note_changed = Signal(str)
    replace_requested = Signal(str)  # file path of replacement
    history_requested = Signal()
    tag_added = Signal(str)
    tag_removed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_asset: dict | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Preview thumbnail
        self.preview = ImageLabel()
        self.preview.clicked.connect(self._open_preview)
        self.preview.file_dropped.connect(self.replace_requested.emit)
        layout.addWidget(self.preview)

        # Business name
        layout.addWidget(QLabel("业务名:"))
        self.business_edit = QLineEdit()
        self.business_edit.textChanged.connect(lambda t: self.business_changed.emit(t))
        layout.addWidget(self.business_edit)

        # File name (read-only)
        layout.addWidget(QLabel("文件名:"))
        self.file_label = QLabel()
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)

        # Tags
        layout.addWidget(QLabel("标签:"))
        tags_layout = QHBoxLayout()
        self.tag_label = QLabel()
        self.tag_label.setWordWrap(True)
        tags_layout.addWidget(self.tag_label, 1)
        self.add_tag_btn = QPushButton("+")
        self.add_tag_btn.setFixedWidth(28)
        self.add_tag_btn.clicked.connect(lambda: self.tag_added.emit(""))
        self.remove_tag_btn = QPushButton("-")
        self.remove_tag_btn.setFixedWidth(28)
        self.remove_tag_btn.clicked.connect(lambda: self.tag_removed.emit(""))
        tags_layout.addWidget(self.add_tag_btn)
        tags_layout.addWidget(self.remove_tag_btn)
        layout.addLayout(tags_layout)

        # Note
        layout.addWidget(QLabel("备注:"))
        self.note_edit = QTextEdit()
        self.note_edit.setMaximumHeight(120)
        self.note_edit.textChanged.connect(lambda: self.note_changed.emit(self.note_edit.toPlainText()))
        layout.addWidget(self.note_edit)

        # Buttons
        btn_layout = QHBoxLayout()
        self.replace_btn = QPushButton("替换图片")
        self.replace_btn.clicked.connect(self._pick_replacement)
        btn_layout.addWidget(self.replace_btn)

        self.history_btn = QPushButton("历史版本")
        self.history_btn.clicked.connect(self.history_requested.emit)
        btn_layout.addWidget(self.history_btn)
        layout.addLayout(btn_layout)

        layout.addStretch()

    def _pick_replacement(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择新图片", "", "Images (*.png *.webp *.jpg *.jpeg *.bmp)"
        )
        if path:
            self.replace_requested.emit(path)

    def set_asset(self, asset: dict | None):
        self._current_asset = asset
        if not asset:
            self.clear()
            return

        abspath = os.path.join(ASSETS_ROOT, asset["file"])
        if os.path.exists(abspath):
            reader = QImageReader(abspath)
            reader.setScaledSize(QPixmap(150, 150).size())
            pixmap = QPixmap.fromImageReader(reader)
            self.preview.setPixmap(pixmap)
        else:
            self.preview.setText("[Missing]")
            self.preview.setPixmap(QPixmap())

        self.business_edit.blockSignals(True)
        self.business_edit.setText(asset.get("business_name", ""))
        self.business_edit.blockSignals(False)

        self.file_label.setText(asset.get("file", ""))
        tags = asset.get("tags", [])
        self.tag_label.setText(", ".join(tags) if tags else "(无)")

        self.note_edit.blockSignals(True)
        self.note_edit.setText(asset.get("note", ""))
        self.note_edit.blockSignals(False)

        key = _asset_key_from_path(asset["file"])
        recycle = RecycleManager()
        count = recycle.get_version_count(key)
        self.history_btn.setEnabled(count > 0)
        self.history_btn.setText(f"历史版本 ({count})" if count > 0 else "历史版本 (0)")

        status = asset.get("status")
        if status == "missing":
            self.file_label.setText(f"[已丢失] {asset['file']}")

    def clear(self):
        self._current_asset = None
        self.preview.setPixmap(QPixmap())
        self.preview.setText("")
        self.business_edit.clear()
        self.file_label.clear()
        self.tag_label.clear()
        self.note_edit.clear()
        self.history_btn.setText("历史版本 (0)")
        self.history_btn.setEnabled(False)

    def _open_preview(self):
        if not self._current_asset:
            return
        abspath = os.path.join(ASSETS_ROOT, self._current_asset["file"])
        if os.path.exists(abspath):
            dialog = QDialog(self)
            dialog.setWindowTitle("图片预览")
            dialog.resize(800, 600)
            layout = QVBoxLayout(dialog)
            label = QLabel()
            pixmap = QPixmap(abspath)
            label.setPixmap(pixmap.scaled(780, 560, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
            dialog.exec()


class VersionHistoryDialog(QDialog):
    """Dialog showing version history with ability to switch/delete."""

    restore_requested = Signal(str, int)  # asset_key, version
    delete_requested = Signal(str, int)

    def __init__(self, asset, parent=None):
        super().__init__(parent)
        self.asset = asset
        self.asset_key = _asset_key_from_path(asset["file"])

        self.setWindowTitle(f"历史版本 — {asset.get('business_name', asset['file'])}")
        self.resize(500, 400)

        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._update_preview)
        layout.addWidget(self.list_widget)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(150)
        layout.addWidget(self.preview_label)

        btn_layout = QHBoxLayout()
        self.restore_btn = QPushButton("切换到此版本")
        self.restore_btn.clicked.connect(self._restore)
        btn_layout.addWidget(self.restore_btn)

        self.delete_btn = QPushButton("删除此版本")
        self.delete_btn.clicked.connect(self._delete)
        btn_layout.addWidget(self.delete_btn)

        btn_layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self._populate()

    def _populate(self):
        recycle = RecycleManager()
        self._versions = recycle.list_versions(self.asset_key)
        for ver in self._versions:
            item = QListWidgetItem(f"v{ver['version']} — {ver['added_at'][:19]} — {ver.get('reason', '')}")
            item.setData(Qt.UserRole, ver)
            self.list_widget.addItem(item)

    def _update_preview(self):
        item = self.list_widget.currentItem()
        if not item:
            self.preview_label.clear()
            return
        ver = item.data(Qt.UserRole)
        recycle_dir = os.path.join("data", "asset_library", "recycle", "files", self.asset_key)
        filepath = os.path.join(recycle_dir, ver["file"])
        if os.path.exists(filepath):
            pixmap = QPixmap(filepath)
            self.preview_label.setPixmap(pixmap.scaled(400, 140, Qt.KeepAspectRatio))
        else:
            self.preview_label.setText("[File missing in recycle]")

    def _restore(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        ver = item.data(Qt.UserRole)

        reply = QMessageBox.question(
            self,
            "确认切换版本",
            f"当前文件将存档为新版本，并恢复为 v{ver['version']}。是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.restore_requested.emit(self.asset_key, ver["version"])
            self.accept()

    def _delete(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        ver = item.data(Qt.UserRole)

        reply = QMessageBox.warning(
            self,
            "确认删除",
            f"将永久删除 v{ver['version']}，不可撤销。是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.delete_requested.emit(self.asset_key, ver["version"])
            self.accept()
