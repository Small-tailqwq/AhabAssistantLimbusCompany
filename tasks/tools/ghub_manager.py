import ctypes
import os
import shutil
import subprocess
from time import sleep

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import qconfig

from module.config import cfg
from module.logger import log
from tasks.tools.ui_style import apply_tool_window_theme, center_window, get_status_label_style


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _probe_mouse_move(dll) -> bool:
    """发一次相对移动并校验光标位移。

    `device_open()` 成功、`move()` 返回 True 都只说明 IOCTL 被驱动接受了；
    总线枚举器下没有虚拟 HID 子设备时驱动会吞掉请求，光标不动但调用依旧成功。
    """
    move = dll.move
    move.argtypes = [ctypes.c_byte, ctypes.c_byte]
    move.restype = ctypes.c_bool

    get_cursor_pos = ctypes.windll.user32.GetCursorPos
    get_cursor_pos.restype = ctypes.c_bool

    before = _POINT()
    if not get_cursor_pos(ctypes.byref(before)):
        return False
    # 贴近屏幕右缘时 +3 会被系统钳制，改用向左移动，避免误判为不可用。
    dx = -3 if before.x >= ctypes.windll.user32.GetSystemMetrics(0) - 3 else 3

    if not move(dx, 0):
        return False
    sleep(0.05)
    p2 = _POINT()
    if not get_cursor_pos(ctypes.byref(p2)):
        return False
    return p2.x == before.x + dx and p2.y == before.y


def _find_ghub_dir() -> str:
    try:
        import winreg
        for access in (winreg.KEY_READ, winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\lghub.exe", access=access) as key:
                    path = winreg.QueryValue(key, None)
                    if path and os.path.exists(path):
                        return os.path.dirname(path)
            except OSError:
                continue
    except ImportError:
        pass
    for candidate in (
        os.path.join(os.environ.get("PROGRAMFILES", ""), "LGHUB"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "LGHUB"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "LGHUB"),
        os.path.join(os.environ.get("PROGRAMDATA", ""), "LGHUB"),
    ):
        exe = os.path.join(candidate, "lghub.exe")
        if os.path.exists(exe):
            return candidate
    return os.path.join(os.environ.get("PROGRAMFILES", "C:\\Program Files"), "LGHUB")


_GHUB_DIR = _find_ghub_dir()
LGHUB_EXE = os.path.join(_GHUB_DIR, "lghub.exe")
HOSTS_PATH = os.path.join(os.environ["WINDIR"], "System32", "drivers", "etc", "hosts")
HOSTS_BLOCK_RULES = [
    "127.0.0.1 updates.ghub.logitechg.com",
    "127.0.0.1 logitechg.com",
]

_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(_TOOL_DIR, "..", "..", "data")
HOSTS_BACKUP = os.path.join(BACKUP_DIR, "hosts.ghub.backup")


class GHubWorker(QThread):
    log_line = Signal(str)
    result_ready = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_requested = False

    def request_stop(self):
        """请求协作式停止：worker 在可中断的等待点检查该标志。"""
        self._stop_requested = True

    def _log(self, msg: str):
        self.log_line.emit(msg)

    def _run_cmd(self, args: list[str], label: str = "") -> subprocess.CompletedProcess:
        result = subprocess.run(args, capture_output=True, text=True, check=False)
        if result.returncode != 0 and label:
            self._log(f"  {label}失败: {result.stderr.strip()}")
        return result

    def _kill_ghub_processes(self):
        for name in ("lghub.exe", "lghub_agent.exe", "lghub_updater.exe"):
            r = self._run_cmd(["taskkill", "/F", "/IM", name], f"终止 {name}")
            if r.returncode != 0 and "not found" not in r.stderr.lower():
                self._log(f"  终止 {name} 失败: {r.stderr.strip()}")

    def _is_dll_ready(self) -> bool:
        dll_path = cfg.get_value("logitech_dll_path", "")
        if not dll_path or not os.path.exists(dll_path):
            return False
        dll = None
        try:
            dll = ctypes.CDLL(dll_path)
            device_open = dll.device_open
            device_open.restype = ctypes.c_bool
            if not device_open():
                return False
            # device_open 只能证明驱动设备在：总线枚举器下缺少虚拟 HID 子设备时
            # move() 返回成功但光标不动，必须按真实位移判定。
            return _probe_mouse_move(dll)
        except Exception as e:
            log.warning(f"DLL 就绪检测异常: {e}")
            return False
        finally:
            if dll is not None:
                try:
                    dll.device_close()
                except Exception as e:
                    log.warning(f"DLL 关闭异常: {e}")

    def _wait_for_dll(self, timeout: int = 30) -> bool:
        for i in range(timeout):
            if self._stop_requested:
                return False
            if self._is_dll_ready():
                return True
            if i < timeout - 1:
                self._log(f"等待 DLL 就绪 {timeout - i}s...")
            sleep(1)
        return False

    def _backup_hosts(self):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        if os.path.exists(HOSTS_PATH) and not os.path.exists(HOSTS_BACKUP):
            shutil.copy2(HOSTS_PATH, HOSTS_BACKUP)
            self._log("  HOSTS 已备份")

    def _restore_hosts_or_clean(self):
        if os.path.exists(HOSTS_BACKUP):
            shutil.copy2(HOSTS_BACKUP, HOSTS_PATH)
            self._log("  HOSTS 已从备份恢复")
            return
        if os.path.exists(HOSTS_PATH):
            self._remove_hosts_blocks()

    def _add_hosts_blocks(self):
        if not os.path.exists(HOSTS_PATH):
            raise FileNotFoundError(2, os.strerror(2), HOSTS_PATH)
        try:
            with open(HOSTS_PATH, "r") as f:
                existing = {line.strip() for line in f}
            added = False
            with open(HOSTS_PATH, "a") as f:
                for rule in HOSTS_BLOCK_RULES:
                    if rule not in existing:
                        f.write("\n" + rule)
                        added = True
            if added:
                self._log("  HOSTS 封锁规则已添加")
                subprocess.run(["ipconfig", "/flushdns"], capture_output=True, check=False)
            else:
                self._log("  HOSTS 封锁规则已存在")
        except OSError as e:
            self._log(f"  HOSTS 写入失败: {e}")
            raise

    def _remove_hosts_blocks(self):
        if not os.path.exists(HOSTS_PATH):
            return
        try:
            with open(HOSTS_PATH, "r") as f:
                lines = f.readlines()
            filtered = [
                line for line in lines
                if line.strip() not in HOSTS_BLOCK_RULES
            ]
            if len(filtered) != len(lines):
                with open(HOSTS_PATH, "w") as f:
                    f.writelines(filtered)
                self._log("  HOSTS 封锁规则已移除")
                subprocess.run(["ipconfig", "/flushdns"], capture_output=True, check=False)
        except OSError as e:
            self._log(f"  HOSTS 写入失败: {e}")
            raise


class GHubStartWorker(GHubWorker):
    dll_ready = Signal(bool)

    def run(self):
        if self._stop_requested:
            return
        self._log("正在重新启动 G HUB...")
        self._kill_ghub_processes()
        sleep(2)
        if self._stop_requested:
            return
        try:
            subprocess.Popen([LGHUB_EXE], creationflags=subprocess.DETACHED_PROCESS)
        except OSError as e:
            self._log(f"G HUB 启动失败: {e}")
            self.result_ready.emit(False, f"G HUB 启动失败: {e}")
            return

        self._log("等待 DLL 就绪（以光标真实位移为准）...")
        ok = self._wait_for_dll()
        if ok:
            self._log("DLL 已可用")
            self.dll_ready.emit(True)
        else:
            self._log("等待超时，DLL 仍未就绪")
            self.dll_ready.emit(False)
        self.result_ready.emit(ok, "G HUB 启动成功" if ok else "DLL 未就绪")


class GHubEnableUpdatesWorker(GHubWorker):
    def run(self):
        self._log("正在恢复更新通道...")
        try:
            self._restore_hosts_or_clean()
        except OSError as e:
            self._log(f"恢复更新通道失败: {e}")
            self.result_ready.emit(False, f"恢复更新通道失败: {e}")
            return

        cfg.set_value("ghub_updates_blocked", False)
        self._log("更新通道已恢复")
        self.result_ready.emit(True, "更新通道已恢复")


class GHubDisableUpdatesWorker(GHubWorker):
    def run(self):
        self._log("正在封锁 G HUB 更新通道...")
        self._log("正在备份 HOSTS...")
        try:
            self._backup_hosts()
            self._add_hosts_blocks()
        except OSError as e:
            self._log(f"封锁更新失败: {e}")
            self.result_ready.emit(False, f"封锁更新失败: {e}")
            return

        cfg.set_value("ghub_updates_blocked", True)
        self._log("更新封锁完成：仅拦截更新域名，G HUB 与驱动状态保持不变")
        self.result_ready.emit(True, "更新已封锁（仅 HOSTS 拦截）")


class GHubManager(QWidget):
    def _logitech_instruction(self) -> str:
        return self.tr(
            "使用流程：\n"
            "1. 检测 DLL — 按光标真实位移确认罗技驱动 DLL 是否可用\n"
            "2. 启动 G HUB — DLL 不可用时重启 G HUB，不修改服务、驱动与 depots\n"
            "3. 封锁更新 — 仅向 HOSTS 添加更新域名拦截，G HUB 保持运行\n\n"
            "注意：缺少虚拟 HID 子设备时 move 调用仍会成功但光标不动，"
            "以「检测 DLL」结果为准。"
        )

    def _razer_instruction(self) -> str:
        return self.tr(
            "使用流程：\n"
            "1. 检测 DLL — 确认当前雷蛇驱动 DLL 是否能正常控制鼠标\n\n"
            "注意：雷蛇驱动无需额外启动或封锁更新，仅需验证 DLL 可用性。"
        )

    def __init__(self):
        super().__init__()
        self.setWindowTitle(self.tr("驱动 DLL 管理器"))
        self.setMinimumSize(480, 420)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self._worker = None
        self._close_pending = False
        self._driver_type = "logitech"
        self._init_ui()
        self._apply_theme_style()
        qconfig.themeChanged.connect(self._apply_theme_style)
        self._refresh_block_status()

    def _init_ui(self):
        layout = QVBoxLayout()

        driver_layout = QHBoxLayout()
        self.logitech_radio = QRadioButton(self.tr("罗技"))
        self.razer_radio = QRadioButton(self.tr("雷蛇"))
        self.logitech_radio.setChecked(True)
        self.driver_group = QButtonGroup(self)
        self.driver_group.addButton(self.logitech_radio)
        self.driver_group.addButton(self.razer_radio)
        self.logitech_radio.toggled.connect(self._on_driver_type_changed)
        driver_layout.addWidget(self.logitech_radio)
        driver_layout.addWidget(self.razer_radio)
        driver_layout.addStretch()
        layout.addLayout(driver_layout)

        self.instruction_label = QLabel(self._logitech_instruction())
        self.instruction_label.setWordWrap(True)
        layout.addWidget(self.instruction_label)

        self.dll_status_label = QLabel(self.tr("DLL 状态：❓ 未检测"))
        self.dll_status_label.setStyleSheet(get_status_label_style())
        layout.addWidget(self.dll_status_label)

        self.block_status_label = QLabel(self.tr("更新封锁：⋯ 读取中"))
        self.block_status_label.setStyleSheet(get_status_label_style())
        layout.addWidget(self.block_status_label)

        btn_layout = QHBoxLayout()
        self.check_btn = QPushButton(self.tr("检测 DLL"))
        self.check_btn.clicked.connect(self._on_check_dll)
        btn_layout.addWidget(self.check_btn)

        self.start_btn = QPushButton(self.tr("启动 G HUB"))
        self.start_btn.clicked.connect(self._on_start_ghub)
        btn_layout.addWidget(self.start_btn)

        self.disable_btn = QPushButton(self.tr("封锁更新"))
        self.disable_btn.clicked.connect(self._on_disable_updates)
        btn_layout.addWidget(self.disable_btn)

        self.enable_btn = QPushButton(self.tr("恢复更新"))
        self.enable_btn.clicked.connect(self._on_enable_updates)
        btn_layout.addWidget(self.enable_btn)

        layout.addLayout(btn_layout)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(220)
        self.log_text.append("=== 驱动 DLL 管理器 ===")
        layout.addWidget(self.log_text)

        self.setLayout(layout)
        center_window(self)

    def _set_dll_status(self, ok: bool, detail: str = ""):
        icon = "✔" if ok else "✘"
        if detail:
            text = self.tr("DLL 状态：{0} {1}").format(icon, detail)
        elif ok:
            text = self.tr("DLL 状态：{0} 可用").format(icon)
        else:
            text = self.tr("DLL 状态：✘ 不可用")
        self.dll_status_label.setText(text)

    def _refresh_block_status(self):
        blocked = cfg.get_value("ghub_updates_blocked", False)
        icon = "🔒" if blocked else "🔓"
        label = self.tr("已封锁") if blocked else self.tr("未封锁")
        self.block_status_label.setText(self.tr("更新封锁：{0} {1}").format(icon, label))

    def _on_driver_type_changed(self):
        if self.logitech_radio.isChecked():
            self._driver_type = "logitech"
            self.instruction_label.setText(self._logitech_instruction())
            self.block_status_label.setVisible(True)
            self.start_btn.setVisible(True)
            self.disable_btn.setVisible(True)
            self.enable_btn.setVisible(True)
            self._refresh_block_status()
        else:
            self._driver_type = "razer"
            self.instruction_label.setText(self._razer_instruction())
            self.block_status_label.setVisible(False)
            self.start_btn.setVisible(False)
            self.disable_btn.setVisible(False)
            self.enable_btn.setVisible(False)
        self.dll_status_label.setText(self.tr("DLL 状态：❓ 未检测"))

    def _apply_theme_style(self):
        apply_tool_window_theme(self, "GHubManager")
        self.dll_status_label.setStyleSheet(get_status_label_style())
        self.block_status_label.setStyleSheet(get_status_label_style())

    def _set_buttons_enabled(self, enabled: bool):
        for btn in (self.check_btn, self.start_btn, self.disable_btn, self.enable_btn):
            btn.setEnabled(enabled)
        self.logitech_radio.setEnabled(enabled)
        self.razer_radio.setEnabled(enabled)

    def _run_worker(self, worker: QThread):
        if self._worker and self._worker.isRunning():
            self.log_text.append("已有操作进行中，请等待完成")
            return
        self._set_buttons_enabled(False)
        self._worker = worker
        worker.log_line.connect(self._on_log_line)
        worker.finished.connect(self._on_worker_finished)
        worker.start()

    def _on_log_line(self, msg: str):
        self.log_text.append(msg)

    def _on_worker_finished(self):
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        self._set_buttons_enabled(True)
        if self._close_pending:
            self._close_pending = False
            self.close()

    def _on_check_dll(self):
        if self._driver_type == "logitech":
            dll_path = cfg.get_value("logitech_dll_path", "")
            driver_name = "罗技"
        else:
            dll_path = cfg.get_value("razer_dll_path", "")
            driver_name = "雷蛇"

        if not dll_path:
            self._set_dll_status(False, self.tr("路径未配置"))
            self.log_text.append(f"{driver_name} DLL 路径未配置，请在设置中指定 DLL 路径")
            return
        if not os.path.exists(dll_path):
            self._set_dll_status(False, self.tr("文件不存在"))
            self.log_text.append(f"DLL 文件不存在: {dll_path}")
            return

        self.log_text.append(f"正在检测{driver_name} DLL...")
        worker = _DllCheckWorker(dll_path, check_ghub_block=(self._driver_type == "logitech"))
        worker.dll_detected.connect(self._set_dll_status)
        self._run_worker(worker)

    def _on_start_ghub(self):
        if not os.path.exists(LGHUB_EXE):
            QMessageBox.warning(
                self,
                self.tr("G HUB 未安装"),
                self.tr("未找到 G HUB: {0}\n请先安装 Logitech G HUB").format(LGHUB_EXE),
            )
            return
        self.log_text.append("正在启动 G HUB...")
        worker = GHubStartWorker()
        worker.dll_ready.connect(lambda ok: self._set_dll_status(ok, self.tr("就绪") if ok else self.tr("不可用")))
        self._run_worker(worker)

    def _on_disable_updates(self):
        reply = QMessageBox.question(
            self,
            self.tr("确认封锁更新"),
            self.tr(
                "即将执行以下操作：\n"
                "  - 向 HOSTS 添加更新域名封锁规则\n\n"
                "不会终止 G HUB 进程，也不会修改服务、驱动文件或 depots 目录。\n\n"
                "确认继续？"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.log_text.append("正在封锁更新...")
        worker = GHubDisableUpdatesWorker()
        worker.finished.connect(lambda: self._refresh_block_status())
        self._run_worker(worker)

    def _on_enable_updates(self):
        reply = QMessageBox.question(
            self,
            self.tr("确认恢复更新"),
            self.tr(
                "即将执行以下操作：\n"
                "  - 移除 HOSTS 中的更新域名封锁规则\n\n"
                "恢复后 G HUB 可自动更新到最新版本，可能因版本变更导致罗技 DLL 失效。\n确认继续？"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.log_text.append("正在恢复更新通道...")
        worker = GHubEnableUpdatesWorker()
        worker.finished.connect(lambda: self._refresh_block_status())
        self._run_worker(worker)

    def closeEvent(self, event):
        worker = self._worker
        if worker is None or not worker.isRunning():
            event.accept()
            return
        worker.request_stop()
        self._close_pending = True
        self.hide()
        event.ignore()


class _DllCheckWorker(GHubWorker):
    dll_detected = Signal(bool, str)

    def __init__(self, dll_path: str, check_ghub_block: bool = False, parent=None):
        super().__init__(parent)
        self._dll_path = dll_path
        self._check_ghub_block = check_ghub_block

    def run(self):
        if not self._dll_path or not os.path.exists(self._dll_path):
            self.log_line.emit("DLL 文件不存在")
            self.dll_detected.emit(False, self.tr("文件不存在"))
            self.result_ready.emit(False, "DLL 未找到")
            return

        if self._check_ghub_block:
            blocked = cfg.get_value("ghub_updates_blocked", False)
            if blocked:
                self.log_line.emit("检测到 G HUB 更新处于封锁状态")

        self.log_line.emit(f"正在检测 DLL: {self._dll_path}")
        dll = None
        try:
            dll = ctypes.CDLL(self._dll_path)
            device_open = dll.device_open
            device_open.restype = ctypes.c_bool
            if not device_open():
                self.log_line.emit("  device_open() 返回 False，DLL 不可用")
                self.dll_detected.emit(False, self.tr("device_open 失败"))
                self.result_ready.emit(False, "device_open 失败")
                return

            move = dll.move
            move.argtypes = [ctypes.c_byte, ctypes.c_byte]
            move.restype = ctypes.c_bool

            if _probe_mouse_move(dll):
                self.log_line.emit("  光标位移验证通过，DLL 正常工作")
                self.dll_detected.emit(True, self.tr("可用"))
                self.result_ready.emit(True, "DLL 正常工作")
            else:
                self.log_line.emit("  光标未移动：虚拟 HID 子设备缺失，移动请求被驱动吞掉")
                self.dll_detected.emit(False, self.tr("鼠标移动未生效"))
                self.result_ready.emit(False, "鼠标移动未生效")
        except Exception as e:
            self.log_line.emit(f"  DLL 检测异常: {e}")
            self.dll_detected.emit(False, self.tr("检测异常"))
            self.result_ready.emit(False, f"DLL 检测失败: {e}")
        finally:
            if dll is not None:
                try:
                    dll.device_close()
                except Exception as e:
                    log.warning(f"DLL 关闭异常: {e}")
