"""Asset Manager — main floating window for browsing, tagging, and replacing game images."""

import os
import shutil

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
    QFileDialog,
    QInputDialog,
)

from module.logger import log
from tasks.tools.asset_library.model import AssetLibraryModel, _file_to_checksum
from tasks.tools.asset_library.recycle import RecycleManager, _asset_key_from_path
from tasks.tools.asset_library.scan_worker import ScanWorker
from tasks.tools.asset_library.widgets import (
    AssetDetailPanel,
    AssetGridWidget,
    CategoryTree,
    VersionHistoryDialog,
    ASSETS_ROOT,
)


class AssetManager(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("资产管理")
        self.resize(1200, 750)
        self.setMinimumSize(900, 550)

        self.model = AssetLibraryModel()
        self.recycle = RecycleManager()
        self._current_asset: dict | None = None

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(1500)
        self._debounce_timer.timeout.connect(self._flush_model)

        self._init_ui()
        self._connect_signals()
        self._start_scan()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        # --- Top bar ---
        top_bar = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("搜索业务名/备注/路径...")
        self.search_bar.setClearButtonEnabled(True)
        top_bar.addWidget(self.search_bar, 1)

        self.tag_filter = QComboBox()
        self.tag_filter.addItems(["全部标签", "通用", "中", "英", "亮色", "暗色"])
        self.tag_filter.setCurrentIndex(0)
        top_bar.addWidget(self.tag_filter)

        self.refresh_btn = QPushButton("刷新扫描")
        top_bar.addWidget(self.refresh_btn)
        main_layout.addLayout(top_bar)

        # --- Progress ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # --- Main content: 3-panel splitter ---
        splitter = QSplitter(Qt.Horizontal)

        # Left: category tree
        self.tree = CategoryTree()
        splitter.addWidget(self.tree)

        # Center: thumbnail grid
        self.grid = AssetGridWidget()
        splitter.addWidget(self.grid)

        # Right: detail panel
        self.detail = AssetDetailPanel()
        splitter.addWidget(self.detail)

        splitter.setSizes([180, 700, 320])
        main_layout.addWidget(splitter, 1)

        # --- Status bar ---
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("就绪")
        main_layout.addWidget(self.status_bar)

    def _connect_signals(self):
        self.tree.category_selected.connect(self._on_category_selected)
        self.search_bar.textChanged.connect(self._on_search)
        self.tag_filter.currentIndexChanged.connect(self._on_tag_changed)

        self.grid.asset_selected.connect(self._on_asset_selected)
        self.grid.context_menu_requested.connect(self._on_context_menu)

        self.detail.business_changed.connect(self._on_business_changed)
        self.detail.note_changed.connect(self._on_note_changed)
        self.detail.replace_requested.connect(self._on_replace)
        self.detail.history_requested.connect(self._on_history)
        self.detail.tag_added.connect(self._on_tag_added)
        self.detail.tag_removed.connect(self._on_tag_removed)

        self.refresh_btn.clicked.connect(self._start_scan)

    def _start_scan(self):
        self.refresh_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.status_bar.showMessage("正在扫描资产...")

        self.worker = ScanWorker(self.model)
        self.worker.progress.connect(self._on_scan_progress)
        self.worker.finished.connect(self._on_scan_finished)
        self.worker.error.connect(self._on_scan_error)
        self.worker.start()

    def _on_scan_progress(self, current, total):
        pct = int(current / total * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)

    def _on_scan_finished(self, diff):
        self.model.apply_scan_result(diff)
        added = len(diff.get("added", []))
        changed = len(diff.get("changed", []))
        deleted = len(diff.get("deleted", []))

        self._refresh_grid()
        self.progress_bar.setVisible(False)
        self.refresh_btn.setEnabled(True)

        msg_parts = []
        if added:
            msg_parts.append(f"新增 {added}")
        if changed:
            msg_parts.append(f"变更 {changed}")
        if deleted:
            msg_parts.append(f"丢失 {deleted}")

        if msg_parts:
            self.status_bar.showMessage(", ".join(msg_parts))
        else:
            self.status_bar.showMessage("扫描完成，无变化")

    def _on_scan_error(self, error_msg):
        self.progress_bar.setVisible(False)
        self.refresh_btn.setEnabled(True)
        self.status_bar.showMessage(f"扫描失败: {error_msg}")
        log.error(f"AssetManager scan error: {error_msg}")

    # --- Grid refresh ---

    def _refresh_grid(self):
        category = getattr(self, "_active_category", None)
        search = self.search_bar.text().strip() or None
        tags = self._active_tags()
        assets = self.model.get_assets(category=category, tags=tags, search=search)
        self.grid.set_assets(assets)

        total = self._total_count()
        self.status_bar.showMessage(f"共 {total} 个资产  |  筛选结果 {len(assets)}")

    def _total_count(self) -> int:
        count = 0
        for cat in self.model.get_all_categories():
            count += len(self.model._load_yaml(cat))
        return count

    # --- Filtering ---

    def _active_tags(self) -> list[str] | None:
        idx = self.tag_filter.currentIndex()
        text = self.tag_filter.currentText()
        if idx == 0 or not text:
            return None
        return [text]

    def _on_category_selected(self, category):
        self._active_category = category
        self._refresh_grid()

    def _on_search(self, _text):
        self._refresh_grid()

    def _on_tag_changed(self, _idx):
        self._refresh_grid()

    # --- Detail panel events ---

    def _on_asset_selected(self, asset: dict):
        self._flush_model()
        self._current_asset = asset
        self.detail.set_asset(asset)

    def _on_business_changed(self, text: str):
        if self._current_asset:
            self.model.update_asset(self._current_asset["file"], business_name=text)
            self._current_asset["business_name"] = text
            self._reset_debounce()

    def _on_note_changed(self, text: str):
        if self._current_asset:
            self.model.update_asset(self._current_asset["file"], note=text)
            self._current_asset["note"] = text
            self._reset_debounce()

    def _on_tag_added(self, _tag):
        if not self._current_asset:
            return
        existing = list(self._current_asset.get("tags") or [])

        tag, ok = QInputDialog.getText(self, "添加标签", "输入新标签:")
        if ok and tag.strip():
            existing.append(tag.strip())
            self.model.update_asset(self._current_asset["file"], tags=existing)
            self._current_asset["tags"] = existing
            self.detail.tag_label.setText(", ".join(existing))
            self._reset_debounce()

    def _on_tag_removed(self, _tag):
        if not self._current_asset:
            return
        existing = list(self._current_asset.get("tags") or [])
        if not existing:
            return

        tag, ok = QInputDialog.getItem(
            self, "删除标签", "选择要删除的标签:", existing, 0, False
        )
        if ok and tag in existing:
            existing.remove(tag)
            self.model.update_asset(self._current_asset["file"], tags=existing)
            self._current_asset["tags"] = existing
            self.detail.tag_label.setText(", ".join(existing))
            self._reset_debounce()

    def _on_replace(self, filepath: str):
        if not self._current_asset:
            return
        current_file = self._current_asset["file"]
        current_abspath = os.path.join(ASSETS_ROOT, current_file)
        dest_dir = os.path.dirname(current_abspath)
        dest_filename = os.path.basename(current_file)
        dest = os.path.join(dest_dir, dest_filename)

        reply = QMessageBox.question(
            self,
            "确认替换",
            f"将 \"{current_file}\" 替换为\n\"{filepath}\"?\n\n旧文件将存档到回收站。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Archive current
        self.recycle.archive(current_file, reason="Manual replacement")

        # Copy new over
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(filepath, dest)

        # Update model
        new_checksum = _file_to_checksum(dest)
        self.model.update_asset(current_file, checksum=new_checksum)
        self._current_asset["checksum"] = new_checksum
        self._flush_model()

        # Refresh grid + detail
        self._refresh_grid()
        self.detail.set_asset(self._current_asset)

        self.status_bar.showMessage(f"已替换: {current_file}")

    def _on_history(self):
        if not self._current_asset:
            return
        dialog = VersionHistoryDialog(self._current_asset, self)
        dialog.restore_requested.connect(self._on_version_restore)
        dialog.delete_requested.connect(self._on_version_delete)
        dialog.exec()

    def _on_version_restore(self, asset_key: str, version: int):
        restored_path = self.recycle.restore(asset_key, version)
        if restored_path:
            self.model._assets_cache.clear()
            self._refresh_grid()
            updated = self.model.get_asset(restored_path)
            if updated:
                self.detail.set_asset(updated)
                self._current_asset = updated
            self.status_bar.showMessage(f"已恢复到 v{version}: {restored_path}")
        else:
            QMessageBox.warning(self, "恢复失败", "无法恢复指定的版本，文件可能已丢失。")

    def _on_version_delete(self, asset_key: str, version: int):
        self.recycle.permanently_delete(asset_key, version)
        self.status_bar.showMessage(f"已永久删除 v{version}")

    def _on_context_menu(self, action_data, _item):
        action, asset = action_data
        if action == "mark_missing":
            self.model.mark_as_missing(asset["file"])
            self._flush_model()
            self._refresh_grid()
        elif action == "restore":
            key = _asset_key_from_path(asset["file"])
            if self.recycle.has_versions(key):
                versions = self.recycle.list_versions(key)
                latest = versions[-1]
                reply = QMessageBox.question(
                    self,
                    "从回收站恢复",
                    f"将恢复 v{latest['version']} ({latest.get('reason', '')})?\n当前 Missing 标记将被清除。",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    self._on_version_restore(key, latest["version"])

    # --- Debounce ---

    def _reset_debounce(self):
        self._debounce_timer.start()

    def _flush_model(self):
        """Write all pending changes to disk."""
        self._debounce_timer.stop()
        if self.model.has_dirty:
            self.model.flush_dirty()

    def closeEvent(self, event):
        self._flush_model()
        super().closeEvent(event)
