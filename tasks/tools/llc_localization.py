import tempfile
import zipfile
from contextlib import suppress
from pathlib import Path

import requests
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import qconfig

from module.config import cfg
from module.game_and_screen import game_process
from module.logger import log
from tasks.tools.ui_style import (
    apply_tool_window_theme,
    center_window,
    get_status_label_style,
)

LLC_REPO = "LocalizeLimbusCompany/LocalizeLimbusCompany"
GITHUB_API = f"https://api.github.com/repos/{LLC_REPO}/releases/latest"
LLC_VERSION_FILE = ".llc_version"


def _get_lang_dir() -> Path | None:
    game_path = Path(cfg.game_path)
    if not game_path.exists() or not game_path.is_file():
        return None
    return game_path.parent / "LimbusCompany_Data" / "Lang" / "LLC_zh-CN"


def _read_installed_version(lang_dir: Path) -> str:
    vf = lang_dir / LLC_VERSION_FILE
    if vf.exists():
        return vf.read_text(encoding="utf-8").strip()
    return ""


def _write_installed_version(lang_dir: Path, version: str):
    (lang_dir / LLC_VERSION_FILE).write_text(version, encoding="utf-8")


class LLCLocalizationWorker(QThread):
    log_message = Signal(str)
    current_version = Signal(str)
    latest_version = Signal(str)
    status_text = Signal(str)
    status_type = Signal(str)
    release_notes = Signal(str)
    operation_finished = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._do_update = False

    def request_update(self):
        self._do_update = True

    def run(self):
        try:
            self._check_and_update()
        except Exception as e:
            self.log_message.emit(f"错误: {e}")
            self.status_type.emit("error")
            self.status_text.emit(f"发生错误: {e}")
            self.operation_finished.emit(False)

    def _emit_log(self, msg: str):
        self.log_message.emit(msg)
        log.info(msg)

    def _check_and_update(self):
        lang_dir = _get_lang_dir()
        if lang_dir is None:
            self._emit_log(f"游戏路径无效: {cfg.game_path}")
            self._emit_log("请先在「设置」中正确配置游戏启动路径")
            self.status_type.emit("error")
            self.status_text.emit("请先在设置中配置正确的游戏路径")
            self.operation_finished.emit(False)
            return

        installed = _read_installed_version(lang_dir)
        if installed:
            self._emit_log(f"检测到已安装版本: {installed}")
        else:
            self._emit_log("未检测到已安装版本")
        self.current_version.emit(installed if installed else "未安装")

        self._emit_log("正在查询零协最新版本...")
        try:
            resp = requests.get(GITHUB_API, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            self._emit_log(f"查询 GitHub 失败: {e}")
            self.status_type.emit("error")
            self.status_text.emit("网络错误，无法连接 GitHub")
            self.operation_finished.emit(False)
            return
        try:
            data = resp.json()
        except ValueError as e:
            self._emit_log(f"解析 GitHub 响应失败: {e}")
            self.status_type.emit("error")
            self.status_text.emit("GitHub 返回了异常响应")
            self.operation_finished.emit(False)
            return

        latest_tag = data["tag_name"]
        body = data.get("body", "")
        self._emit_log(f"最新版本: {latest_tag}")
        self.latest_version.emit(latest_tag)
        if body:
            self.release_notes.emit(body)

        if installed == latest_tag:
            self._emit_log("已是最新版本，无需更新")
            self.status_type.emit("ok")
            self.status_text.emit(f"✓ 已是最新版本 ({latest_tag})")
            self.operation_finished.emit(True)
            return

        self.status_type.emit("update")
        self.status_text.emit(f"⚡ 有新版本: {latest_tag}")

        if not self._do_update:
            self.operation_finished.emit(True)
            return

        if game_process.check_game_alive():
            self._emit_log("游戏正在运行，更新后需重启游戏使汉化生效")

        self._do_download_and_extract(latest_tag, lang_dir)

    def _do_download_and_extract(self, tag: str, lang_dir: Path):
        zip_url = f"https://github.com/{LLC_REPO}/releases/download/{tag}/LimbusLocalize_{tag}.zip"
        self._emit_log(f"正在下载: {zip_url}")

        try:
            resp = requests.get(zip_url, stream=True, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as e:
            self._emit_log(f"下载失败: {e}")
            self.status_type.emit("error")
            self.status_text.emit("下载失败")
            self.operation_finished.emit(False)
            return

        game_dir = Path(cfg.game_path).parent
        game_dir.mkdir(parents=True, exist_ok=True)

        temp_dir = Path(tempfile.gettempdir()) / "AALC_LLC"
        temp_dir.mkdir(parents=True, exist_ok=True)
        zip_path = temp_dir / f"LimbusLocalize_{tag}.zip"
        self._cleanup_old_zips(temp_dir, tag)

        with open(zip_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        self._emit_log("下载完成，正在解压...")

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(game_dir)
        except Exception as e:
            self._emit_log(f"解压失败: {e}")
            self.status_type.emit("error")
            self.status_text.emit("解压失败")
            self.operation_finished.emit(False)
            return

        zip_path.unlink(missing_ok=True)
        _write_installed_version(lang_dir, tag)
        self._emit_log(f"更新完成！当前版本: {tag}")
        self.current_version.emit(tag)
        self.status_type.emit("ok")
        self.status_text.emit(f"✓ 更新完成 ({tag})")
        self.operation_finished.emit(True)

    @staticmethod
    def _cleanup_old_zips(temp_dir: Path, current_tag: str):
        for f in temp_dir.glob("LimbusLocalize_*.zip"):
            if current_tag not in f.name:
                with suppress(OSError):
                    f.unlink()


class LLCLocalizationWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.worker = None
        self._updating = False
        self.setup_ui()
        qconfig.themeChanged.connect(self._apply_theme_style)
        self._auto_check()

    def setup_ui(self):
        self.setWindowTitle("零协汉化更新")
        self.setWindowIcon(QIcon("./assets/logo/canary.ico"))
        self.resize(600, 400)
        self.setMinimumSize(480, 320)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        version_group = QGroupBox("版本信息")
        vg_layout = QVBoxLayout(version_group)

        self.current_label = QLabel("当前版本: -")
        self.latest_label = QLabel("最新版本: -")
        self.status_label = QLabel("状态: 正在检查...")

        vg_layout.addWidget(self.current_label)
        vg_layout.addWidget(self.latest_label)
        vg_layout.addWidget(self.status_label)
        layout.addWidget(version_group)

        self.notes_edit = QTextEdit()
        self.notes_edit.setReadOnly(True)
        self.notes_edit.setMaximumHeight(120)
        self.notes_edit.setPlaceholderText("更新日志将在这里显示...")
        layout.addWidget(QLabel("更新日志:"))
        layout.addWidget(self.notes_edit)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        layout.addWidget(QLabel("日志:"))
        layout.addWidget(self.log_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.update_btn = QPushButton("开始更新")
        self.update_btn.clicked.connect(self._on_update_clicked)
        self.update_btn.setVisible(False)
        btn_layout.addWidget(self.update_btn)
        layout.addLayout(btn_layout)

        self.attribution_label = QLabel(
            '汉化文件来自 <a href="https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany">'
            "LocalizeLimbusCompany</a>，采用 "
            '<a href="https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh-hans">'
            "CC BY-NC-SA 4.0</a> 协议"
        )
        self.attribution_label.setOpenExternalLinks(True)
        self.attribution_label.setAlignment(Qt.AlignCenter)
        self.attribution_label.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(self.attribution_label)

        self._apply_theme_style()
        center_window(self)

    def _apply_theme_style(self):
        apply_tool_window_theme(self, "LLCLocalizationWindow")
        self.status_label.setStyleSheet(get_status_label_style())

    def _auto_check(self):
        self._start_worker()

    def _start_worker(self):
        if self.worker and self.worker.isRunning():
            return
        self.worker = LLCLocalizationWorker()
        self.worker.log_message.connect(self._append_log)
        self.worker.current_version.connect(
            lambda v: self.current_label.setText(f"当前版本: {v}")
        )
        self.worker.latest_version.connect(
            lambda v: self.latest_label.setText(f"最新版本: {v}")
        )
        self.worker.status_text.connect(self.status_label.setText)
        self.worker.status_type.connect(self._on_status_type)
        self.worker.release_notes.connect(self.notes_edit.setPlainText)
        self.worker.operation_finished.connect(self._on_operation_finished)
        self.worker.start()

    def _on_status_type(self, st: str):
        if self._updating:
            return
        self.update_btn.setVisible(st == "update")

    def _on_update_clicked(self):
        self._updating = True
        self.update_btn.setVisible(False)
        self.update_btn.setEnabled(False)
        if self.worker and self.worker.isRunning():
            self.worker.request_update()
        else:
            self._start_worker()
            self.worker.request_update()

    def _on_operation_finished(self, success: bool):
        self._updating = False
        self.update_btn.setEnabled(True)

    def _append_log(self, msg: str):
        self.log_edit.append(msg)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            if not self.worker.wait(3000):
                self.worker.terminate()
                self.worker.wait(1000)
        super().closeEvent(event)
