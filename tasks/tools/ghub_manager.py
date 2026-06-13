import ctypes
import os
import shutil
import subprocess
from time import sleep

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
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
LGHUB_UPDATER = os.path.join(_GHUB_DIR, "lghub_updater.exe")
LGHUB_UPDATER_DISABLED = LGHUB_UPDATER + ".disabled"
LGHUB_DEPOTS = os.path.join(os.environ["PROGRAMDATA"], "LGHUB", "depots")
LGHUB_DEPOTS_DISABLED = LGHUB_DEPOTS + ".disabled"
LGHUB_SERVICE = "LGHUBUpdaterService"
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
    finished = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)

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
            move = dll.move
            move.argtypes = [ctypes.c_byte, ctypes.c_byte]
            move.restype = ctypes.c_bool
            move(3, 0)
            sleep(0.05)
            return True
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
            self._log("  HOSTS 文件不存在，跳过")
            return
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

    def _rename_file(self, src: str, dst: str, label: str):
        try:
            shutil.move(src, dst)
            self._log(f"  {label}成功")
        except OSError as e:
            self._log(f"  {label}失败: {e}")
            log.warning(f"重命名失败 {src} -> {dst}: {e}")

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


class GHubStartWorker(GHubWorker):
    dll_ready = Signal(bool)

    def run(self):
        self._log("正在恢复 G HUB 更新通道...")
        if os.path.exists(LGHUB_UPDATER_DISABLED):
            self._rename_file(LGHUB_UPDATER_DISABLED, LGHUB_UPDATER, "updater")
        if os.path.exists(LGHUB_DEPOTS_DISABLED):
            self._rename_file(LGHUB_DEPOTS_DISABLED, LGHUB_DEPOTS, "depots")
        self._run_cmd(["sc.exe", "config", LGHUB_SERVICE, "start=", "auto"], "恢复服务")
        self._log("  LGHUBUpdaterService 已恢复")

        self._log("正在重新启动 G HUB...")
        self._kill_ghub_processes()
        sleep(2)
        subprocess.Popen([LGHUB_EXE], creationflags=subprocess.DETACHED_PROCESS)

        self._log("等待 DLL 就绪...")
        ok = self._wait_for_dll()
        if ok:
            self._log("DLL 已可用")
            self.dll_ready.emit(True)
        else:
            self._log("等待超时，DLL 仍未就绪")
            self.dll_ready.emit(False)
        self.finished.emit(True, "G HUB 启动成功" if ok else "启动超时")


class GHubEnableUpdatesWorker(GHubWorker):
    def run(self):
        self._log("正在恢复更新通道...")
        if os.path.exists(LGHUB_UPDATER_DISABLED):
            self._rename_file(LGHUB_UPDATER_DISABLED, LGHUB_UPDATER, "updater")
        if os.path.exists(LGHUB_DEPOTS_DISABLED):
            self._rename_file(LGHUB_DEPOTS_DISABLED, LGHUB_DEPOTS, "depots")
        self._run_cmd(["sc.exe", "config", LGHUB_SERVICE, "start=", "auto"], "恢复服务")

        self._restore_hosts_or_clean()

        cfg.set_value("ghub_updates_blocked", False)
        self._log("更新通道已全部恢复")
        self.finished.emit(True, "更新通道已恢复")


class GHubDisableUpdatesWorker(GHubWorker):
    def run(self):
        self._log("正在封锁 G HUB 更新...")
        self._kill_ghub_processes()
        self._log("  G HUB 进程已终止")

        self._run_cmd(["sc.exe", "stop", LGHUB_SERVICE], "停止服务")
        self._run_cmd(["sc.exe", "config", LGHUB_SERVICE, "start=", "disabled"], "禁用服务")
        self._log("  服务已禁用")
        sleep(1)

        if os.path.exists(LGHUB_UPDATER):
            try:
                shutil.move(LGHUB_UPDATER, LGHUB_UPDATER_DISABLED)
                self._log("  updater 已封锁")
            except OSError as e:
                self._log(f"  updater 封锁失败: {e}，中止操作")
                self.finished.emit(False, f"updater 封锁失败: {e}")
                return

        if os.path.exists(LGHUB_DEPOTS):
            shutil.rmtree(LGHUB_DEPOTS, ignore_errors=True)
            if os.path.exists(LGHUB_DEPOTS):
                self._rename_file(LGHUB_DEPOTS, LGHUB_DEPOTS_DISABLED, "depots")
            else:
                self._log("  depots 已清理")

        self._log("正在备份 HOSTS...")
        self._backup_hosts()
        self._add_hosts_blocks()
        self._log("  HOSTS 封锁规则已添加")

        cfg.set_value("ghub_updates_blocked", True)
        self._log("更新封锁完成")
        self.finished.emit(True, "更新已封锁，G HUB 版本将被锁定")


class GHubManager(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("G HUB 驱动管理器")
        self.setMinimumSize(480, 420)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self._worker = None
        self._init_ui()
        self._apply_theme_style()
        qconfig.themeChanged.connect(self._apply_theme_style)
        self._refresh_block_status()

    def _init_ui(self):
        layout = QVBoxLayout()

        self.instruction_label = QLabel(
            "使用流程：\n"
            "1. 检测 DLL — 确认当前罗技驱动 DLL 是否可用\n"
            "2. 启动 G HUB — 若 DLL 不可用则自动恢复更新通道并启动 G HUB\n"
            "3. 封锁更新 — DLL 就绪后建议锁定版本，防止自动升级导致不兼容\n\n"
            "注意：G HUB 启动后可能弹出更新提示，关闭即可，不影响 DLL 使用。"
        )
        self.instruction_label.setWordWrap(True)
        layout.addWidget(self.instruction_label)

        self.dll_status_label = QLabel("DLL 状态：❓ 未检测")
        self.dll_status_label.setStyleSheet(get_status_label_style())
        layout.addWidget(self.dll_status_label)

        self.block_status_label = QLabel("更新封锁：⋯ 读取中")
        self.block_status_label.setStyleSheet(get_status_label_style())
        layout.addWidget(self.block_status_label)

        btn_layout = QHBoxLayout()
        self.check_btn = QPushButton("检测 DLL")
        self.check_btn.clicked.connect(self._on_check_dll)
        btn_layout.addWidget(self.check_btn)

        self.start_btn = QPushButton("启动 G HUB")
        self.start_btn.clicked.connect(self._on_start_ghub)
        btn_layout.addWidget(self.start_btn)

        self.disable_btn = QPushButton("封锁更新")
        self.disable_btn.clicked.connect(self._on_disable_updates)
        btn_layout.addWidget(self.disable_btn)

        self.enable_btn = QPushButton("恢复更新")
        self.enable_btn.clicked.connect(self._on_enable_updates)
        btn_layout.addWidget(self.enable_btn)

        layout.addLayout(btn_layout)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(220)
        self.log_text.append("=== G HUB 驱动管理器 ===")
        layout.addWidget(self.log_text)

        self.setLayout(layout)
        center_window(self)

    def _set_dll_status(self, ok: bool, detail: str = ""):
        icon = "✔" if ok else "✘"
        text = f"DLL 状态：{icon} {detail}" if detail else f"DLL 状态：{icon} 可用" if ok else "DLL 状态：✘ 不可用"
        self.dll_status_label.setText(text)

    def _refresh_block_status(self):
        blocked = cfg.get_value("ghub_updates_blocked", False)
        icon = "🔒" if blocked else "🔓"
        label = "已封锁" if blocked else "未封锁"
        self.block_status_label.setText(f"更新封锁：{icon} {label}")

    def _apply_theme_style(self):
        apply_tool_window_theme(self, "GHubManager")
        self.dll_status_label.setStyleSheet(get_status_label_style())
        self.block_status_label.setStyleSheet(get_status_label_style())

    def _set_buttons_enabled(self, enabled: bool):
        for btn in (self.check_btn, self.start_btn, self.disable_btn, self.enable_btn):
            btn.setEnabled(enabled)

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
        self._set_buttons_enabled(True)
        self._worker = None

    def _on_check_dll(self):
        dll_path = cfg.get_value("logitech_dll_path", "")
        if not dll_path:
            self._set_dll_status(False, "路径未配置")
            self.log_text.append("DLL 路径未配置，请在设置中指定罗技驱动 DLL 路径")
            return
        if not os.path.exists(dll_path):
            self._set_dll_status(False, "文件不存在")
            self.log_text.append(f"DLL 文件不存在: {dll_path}")
            return

        self.log_text.append("正在检测 DLL...")
        worker = _GHubCheckWorker()
        worker.dll_detected.connect(self._set_dll_status)
        self._run_worker(worker)

    def _on_start_ghub(self):
        if not os.path.exists(LGHUB_EXE):
            QMessageBox.warning(self, "G HUB 未安装", f"未找到 G HUB: {LGHUB_EXE}\n请先安装 Logitech G HUB")
            return
        self.log_text.append("正在启动 G HUB...")
        worker = GHubStartWorker()
        worker.dll_ready.connect(lambda ok: self._set_dll_status(ok, "就绪" if ok else "不可用"))
        self._run_worker(worker)

    def _on_disable_updates(self):
        reply = QMessageBox.question(
            self,
            "确认封锁更新",
            "即将执行以下操作：\n"
            "  - 终止 G HUB 进程\n"
            "  - 禁用 LGHUBUpdaterService\n"
            "  - 改名 lghub_updater.exe 封锁\n"
            "  - 清理 depots 目录\n"
            "  - 添加 HOSTS 封锁规则\n\n"
            "确认继续？",
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
            "确认恢复更新",
            "即将执行以下操作：\n"
            "  - 恢复 lghub_updater.exe\n"
            "  - 恢复 depots 目录\n"
            "  - 启用 LGHUBUpdaterService\n"
            "  - 移除 HOSTS 封锁规则\n\n"
            "恢复后 G HUB 可自动更新到最新版本，可能因版本变更导致罗技 DLL 失效。\n确认继续？",
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
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            if not self._worker.wait(2000):
                self._worker.terminate()
                self._worker.wait(1000)
        event.accept()


class _GHubCheckWorker(GHubWorker):
    dll_detected = Signal(bool, str)

    def run(self):
        dll_path = cfg.get_value("logitech_dll_path", "")
        if not dll_path or not os.path.exists(dll_path):
            self.log_line.emit("DLL 文件不存在")
            self.dll_detected.emit(False, "文件不存在")
            self.finished.emit(False, "DLL 未找到")
            return

        blocked = cfg.get_value("ghub_updates_blocked", False)
        if blocked:
            self.log_line.emit("检测到 G HUB 更新处于封锁状态")

        self.log_line.emit(f"正在检测 DLL: {dll_path}")
        dll = None
        try:
            dll = ctypes.CDLL(dll_path)
            device_open = dll.device_open
            device_open.restype = ctypes.c_bool
            if not device_open():
                self.log_line.emit("  device_open() 返回 False，DLL 不可用")
                self.dll_detected.emit(False, "device_open 失败")
                self.finished.emit(False, "device_open 失败")
                return

            move = dll.move
            move.argtypes = [ctypes.c_byte, ctypes.c_byte]
            move.restype = ctypes.c_bool

            GetCursorPos = ctypes.windll.user32.GetCursorPos
            GetCursorPos.restype = ctypes.c_bool

            p1 = _POINT()
            GetCursorPos(ctypes.byref(p1))
            move(3, 0)
            sleep(0.05)
            p2 = _POINT()
            GetCursorPos(ctypes.byref(p2))

            if p2.x == p1.x + 3:
                self.log_line.emit("  move(3,0) 验证通过，DLL 正常工作")
                self.dll_detected.emit(True, "可用")
                self.finished.emit(True, "DLL 正常工作")
            else:
                self.log_line.emit("  move(3,0) 未生效，G HUB 驱动异常")
                self.dll_detected.emit(False, "鼠标移动未生效")
                self.finished.emit(False, "鼠标移动未生效")
        except Exception as e:
            self.log_line.emit(f"  DLL 检测异常: {e}")
            self.dll_detected.emit(False, "检测异常")
            self.finished.emit(False, f"DLL 检测失败: {e}")
        finally:
            if dll is not None:
                try:
                    dll.device_close()
                except Exception as e:
                    log.warning(f"DLL 关闭异常: {e}")
