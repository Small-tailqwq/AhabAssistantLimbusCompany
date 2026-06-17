# 零协汉化更新工具 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在"小功能"中添加一个新的工具窗口，用于检测/下载/更新零协汉化

**Architecture:** 新建 `tasks/tools/llc_localization.py` 包含 QWidget 窗口 + QThread 工作线程；读取 GitHub API 获取最新 Release，下载 zip 解压到游戏 Lang 目录；版本号读写 `.llc_version` 标记文件

**Tech Stack:** Python 3.12+, PySide6, requests (已有), zipfile (内置), GitHub REST API

---

### Task 1: 创建 `tasks/tools/llc_localization.py`

**Files:**
- Create: `tasks/tools/llc_localization.py`

**核心逻辑说明：**
- GitHub API: `GET https://api.github.com/repos/LocalizeLimbusCompany/LocalizeLimbusCompany/releases/latest`
- 返回 JSON 中取 `tag_name`（如 `2026061402`）作为最新版本号
- 下载 URL: `https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany/releases/download/{tag}/LimbusLocalize_{tag}.zip`
- 游戏 Lang 目录: 从 `os.path.dirname(cfg.game_path)` 获取游戏目录父路径，拼接 `LimbusCompany_Data/Lang/LLC_zh-CN/`
- 已安装版本: 读取 `{LangDir}/.llc_version` 文件内容（存储上一次下载的 tag_name）
- 更新后写入 `{LangDir}/.llc_version` 为最新 tag_name

- [ ] **Step 1: 编写 `LLCLocalizationWorker` 类**

```python
import json
import os
import zipfile
from pathlib import Path

import requests
from PySide6.QtCore import QThread, Signal

from module.config import cfg
from module.logger import log
from utils.utils import check_game_running


LLC_REPO = "LocalizeLimbusCompany/LocalizeLimbusCompany"
GITHUB_API = f"https://api.github.com/repos/{LLC_REPO}/releases/latest"
LLC_VERSION_FILE = ".llc_version"


def _get_lang_dir() -> Path:
    game_path = Path(cfg.game_path)
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
    status_type = Signal(str)  # "ok", "update", "error"
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
        installed = _read_installed_version(lang_dir)

        if installed:
            self._emit_log(f"检测到已安装版本: {installed}")
            self.current_version.emit(installed)
        else:
            self._emit_log("未检测到已安装版本")
            self.current_version.emit("未安装")

        self._emit_log("正在查询零协最新版本...")
        try:
            resp = requests.get(GITHUB_API, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            self._emit_log(f"查询 GitHub 失败: {e}")
            self.status_type.emit("error")
            self.status_text.emit("网络错误，无法连接 GitHub")
            self.operation_finished.emit(False)
            return

        latest_tag = data["tag_name"]
        body = data.get("body", "")
        self._emit_log(f"最新版本: {latest_tag}")
        self.latest_version.emit(latest_tag)
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

        if check_game_running():
            self._emit_log("游戏正在运行，请先关闭游戏后再更新汉化")
            self.status_type.emit("error")
            self.status_text.emit("请先关闭游戏后再更新汉化")
            self.operation_finished.emit(False)
            return

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

        zip_path = lang_dir / f"LimbusLocalize_{tag}.zip"
        lang_dir.mkdir(parents=True, exist_ok=True)
        with open(zip_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        self._emit_log("下载完成，正在解压...")

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(lang_dir)
        except Exception as e:
            self._emit_log(f"解压失败: {e}")
            self.status_type.emit("error")
            self.status_text.emit("解压失败")
            self.operation_finished.emit(False)
            return

        zip_path.unlink()
        _write_installed_version(lang_dir, tag)
        self._emit_log(f"更新完成！当前版本: {tag}")
        self.current_version.emit(tag)
        self.status_type.emit("ok")
        self.status_text.emit(f"✓ 更新完成 ({tag})")
        self.operation_finished.emit(True)
```

- [ ] **Step 2: 编写 `LLCLocalizationWindow` 类**

```python
from PySide6.QtCore import Qt
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

from tasks.tools.ui_style import (
    apply_tool_window_theme,
    center_window,
    get_status_label_style,
)


class LLCLocalizationWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.worker = None
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

        # 版本信息分组
        version_group = QGroupBox("版本信息")
        vg_layout = QVBoxLayout(version_group)

        self.current_label = QLabel("当前版本: -")
        self.latest_label = QLabel("最新版本: -")

        self.status_label = QLabel("状态: 正在检查...")

        vg_layout.addWidget(self.current_label)
        vg_layout.addWidget(self.latest_label)
        vg_layout.addWidget(self.status_label)
        layout.addWidget(version_group)

        # 更新日志
        self.notes_edit = QTextEdit()
        self.notes_edit.setReadOnly(True)
        self.notes_edit.setMaximumHeight(120)
        self.notes_edit.setPlaceholderText("更新日志将在这里显示...")
        layout.addWidget(QLabel("更新日志:"))
        layout.addWidget(self.notes_edit)

        # 日志输出
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        layout.addWidget(QLabel("日志:"))
        layout.addWidget(self.log_edit)

        # 更新按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.update_btn = QPushButton("开始更新")
        self.update_btn.clicked.connect(self._on_update_clicked)
        self.update_btn.setVisible(False)
        btn_layout.addWidget(self.update_btn)
        layout.addLayout(btn_layout)

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
        if st == "update":
            self.update_btn.setVisible(True)
        else:
            self.update_btn.setVisible(False)

    def _on_update_clicked(self):
        self.update_btn.setVisible(False)
        self.update_btn.setEnabled(False)
        if self.worker and self.worker.isRunning():
            self.worker.request_update()
        else:
            self._start_worker()
            self.worker.request_update()

    def _on_operation_finished(self, success: bool):
        self.update_btn.setEnabled(True)

    def _append_log(self, msg: str):
        self.log_edit.append(msg)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(3000)
        event.accept()
```

- [ ] **Step 3: 验证代码完整**

确认文件 `tasks/tools/llc_localization.py` 包含完整的 import、两个类定义、无语法错误。

```bash
uv run python -m py_compile tasks/tools/llc_localization.py
```

---

### Task 2: 注册到 `ToolManager`

**Files:**
- Modify: `tasks/tools/__init__.py`

- [ ] **Step 1: 添加 import + 注册分支**

在第 16 行（`from tasks.tools.tutorial_skip import TutorialSkipWindow`）之后添加：

```python
from tasks.tools.llc_localization import LLCLocalizationWindow
```

在 `ToolManager.__init__` 的 `Literal` 中添加 `"llc_localization"`：

```python
def __init__(self, tool: Literal["battle", "production", "screenshot", "issue_replay", "asset_manager", "tutorial_skip", "quick_screenshot", "ghub_manager", "llc_localization"]):
```

在 `run_tools` 的 `create_and_show` 中添加 elif 分支（在第 58 行 `elif self.tool == "ghub_manager":` 之后）：

```python
                elif self.tool == "llc_localization":
                    self.w = LLCLocalizationWindow()
```

在 `start()` 函数的 `Literal` 中添加 `"llc_localization"`：

```python
def start(tool: Literal["battle", "production", "screenshot", "issue_replay", "asset_manager", "tutorial_skip", "quick_screenshot", "ghub_manager", "llc_localization"]):
```

- [ ] **Step 2: 验证语法**

```bash
uv run python -m py_compile tasks/tools/__init__.py
```

---

### Task 3: 在 UI 界面添加卡片

**Files:**
- Modify: `app/tools_interface.py`

- [ ] **Step 1: 在 `__init_card` 中添加汉化更新卡片**

在 `self.ghub_manager_card` 初始化之后（第 127 行之后）添加：

```python
        self.llc_localization_card = BasePushSettingCard(
            QT_TRANSLATE_NOOP("BasePushSettingCard", "运行"),
            FIF.LANGUAGE,
            QT_TRANSLATE_NOOP("BasePushSettingCard", "零协汉化更新"),
            QT_TRANSLATE_NOOP(
                "BasePushSettingCard",
                "检测零协汉化版本，自动下载更新汉化文件",
            ),
            parent=self.tools_group,
        )
```

- [ ] **Step 2: 在 `__initLayout` 中添加卡片**

在 `self.tools_group.addSettingCard(self.ghub_manager_card)` 之后（第 136 行之后）添加：

```python
        self.tools_group.addSettingCard(self.llc_localization_card)
```

- [ ] **Step 3: 在 `__connect_signal` 中添加信号连接**

在 `self.ghub_manager_card.clicked.connect(...)` 之后（第 164 行之后）添加：

```python
        self.llc_localization_card.clicked.connect(
            lambda: self._tool_start("llc_localization", self.llc_localization_card)
        )
```

- [ ] **Step 4: 在 `retranslateUi` 中添加 retranslate**

在 `self.ghub_manager_card.retranslateUi()` 之后（第 282 行之前）添加：

```python
        self.llc_localization_card.retranslateUi()
```

- [ ] **Step 5: 验证语法**

```bash
uv run python -m py_compile app/tools_interface.py
```

---

### Task 4: 验证整体

- [ ] **Step 1: 代码检查**

```bash
uv run ruff check tasks/tools/llc_localization.py tasks/tools/__init__.py app/tools_interface.py
```

- [ ] **Step 2: 更新 i18n 翻译文件**

运行编译脚本提取新翻译条目：

```bash
uv run python scripts/translation_files_build.py
```

确认 `i18n/myapp_en.ts` 中包含新添加的翻译条目：
- "零协汉化更新"
- "检测零协汉化版本，自动下载更新汉化文件"

- [ ] **Step 3: 最终确认**

```bash
uv run python -m py_compile tasks/tools/llc_localization.py
uv run python -m py_compile tasks/tools/__init__.py
uv run python -m py_compile app/tools_interface.py
```
