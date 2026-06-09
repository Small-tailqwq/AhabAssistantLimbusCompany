"""Tutorial Skip Tool — 直接修改 Limbus Company 存档以跳过/恢复新手提示"""

import base64
import glob
import json
import os
import re
import tempfile
import urllib.parse
from xml.dom import minidom

try:
    from Crypto.Cipher import AES
except ImportError:
    AES = None
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import qconfig

from tasks.tools.ui_style import apply_tool_window_theme, center_window, get_status_label_style

# ── Platform paths ──────────────────────────────────────────

WINDOWS_SAVE_DIR = os.path.expandvars(
    r"%USERPROFILE%\AppData\LocalLow\ProjectMoon\LimbusCompany"
)

WINDOWS_REG_KEY = r"Software\ProjectMoon\LimbusCompany"

ANDROID_SAVE_DIR = "/sdcard/Android/data/com.ProjectMoon.LimbusCompany/files"
ANDROID_PREFS_PATH = (
    "/data/data/com.ProjectMoon.LimbusCompany/shared_prefs/"
    "com.ProjectMoon.LimbusCompany.v2.playerprefs.xml"
)

# ── Registry helpers (Windows) ──────────────────────────────


def _reg_query_all():
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_REG_KEY, 0, winreg.KEY_READ) as key:
            result = {}
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    result[name] = value
                    i += 1
                except OSError:
                    break
            return result
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _load_key_iv_windows():
    entries = _reg_query_all()
    pref_name = None
    for name in entries:
        if "LocalSave.LocalGameOptionData" in name:
            pref_name = name
            break
    if not pref_name:
        return None
    raw_data = entries[pref_name]
    json_str = raw_data.rstrip(b"\x00").decode("utf-8")
    opt = json.loads(json_str)
    return base64.b64decode(opt["key"]), base64.b64decode(opt["iv"]), opt


# ── ADB helpers (Android) ───────────────────────────────────


def _android_device():
    from adbutils import adb

    try:
        devices = adb.device_list()
        if not devices:
            return None
        target = None
        for d in devices:
            if "7555" in d.serial:
                target = d
                break
        return target or devices[0]
    except Exception:
        return None


def _get_adb_device_auto():
    """复用 AALC 的模拟器连接信息获取 ADB 设备"""
    from module.config import cfg as aalc_cfg

    if not aalc_cfg.simulator:
        return None
    try:
        if aalc_cfg.simulator_type == 0:
            from module.automation.input_handlers.simulator.mumu_control import MumuControl

            conn = MumuControl.connection_device
            if conn is None:
                return None
            port = conn.get_mumu_adb_port()
            from adbutils import adb
            return adb.device(port)
        else:
            from module.automation.input_handlers.simulator.simulator_control import SimulatorControl

            conn = SimulatorControl.connection_device
            if conn is None or conn.simulator_device is None:
                return None
            return conn.simulator_device
    except Exception:
        return None


def _load_key_iv_android(device):
    try:
        out = device.shell(f"cat '{ANDROID_PREFS_PATH}'")
        if not out:
            return None
        xml = minidom.parseString(out)
        for s in xml.getElementsByTagName("string"):
            name = s.getAttribute("name")
            if "LocalSave.LocalGameOptionData" in name:
                decoded = urllib.parse.unquote(s.firstChild.nodeValue)
                opt = json.loads(decoded)
                return base64.b64decode(opt["key"]), base64.b64decode(opt["iv"]), opt
        return None
    except Exception:
        return None


# ── AES ─────────────────────────────────────────────────────


def _check_crypto():
    if AES is None:
        raise ImportError("pycryptodome 未安装，无法加密/解密存档")


def _decrypt_save(text, key, iv):
    _check_crypto()
    raw = base64.b64decode(text)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    plaintext = cipher.decrypt(raw)
    pad = plaintext[-1]
    return json.loads(plaintext[:-pad])


def _encrypt_save(obj, key, iv):
    _check_crypto()
    plaintext = json.dumps(obj, separators=(",", ":")).encode()
    pad = 16 - (len(plaintext) % 16)
    plaintext += bytes([pad] * pad)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return base64.b64encode(cipher.encrypt(plaintext)).decode()


# ── Patching logic ─────────────────────────────────────────


def _patch_data(data, disable=True):
    string_dic = data.setdefault("_stringDic", {"keys": [], "values": []})
    keys = string_dic["keys"]
    values = string_dic["values"]
    existing = set(keys)
    patches = {}

    for k, v in zip(keys, values):
        try:
            obj = json.loads(v)
        except json.JSONDecodeError:
            continue

        patched = False

        if k == "LocalSave.UserLocalTutorialSaveModel":
            if "tutorialDic" in obj:
                obj["tutorialDic"]["keys"] = list(range(1, 24))
                obj["tutorialDic"]["values"] = [disable] * 23
                patched = True

        if k == "UserLocalFormationDataModel":
            for fld in [
                "_isParticipation7TutorialOccured",
                "_isStoryDungeon4Opened",
                "_isRailwayDungeonLine2LastNodeEnterFirst",
            ]:
                if fld in obj and obj[fld] != disable:
                    obj[fld] = disable
                    patched = True

        if k == "UserLocalMirrorDungeonRedDotModel":
            if obj.get("_isParticipation7TutorialOccured") != disable:
                obj["_isParticipation7TutorialOccured"] = disable
                patched = True

        if k == "UserLocalCheckBoxSaveModel":
            for cb in obj.get("_checkBoxDataList", []):
                if cb.get("isChecked") != disable:
                    cb["isChecked"] = disable
                    patched = True

        if k == "UserLocalDialogResultSaveModel":
            for dlg in obj.get("_dataList", []):
                for fld in ["isDoNotShowAgain", "isConfirmed"]:
                    if dlg.get(fld) != disable:
                        dlg[fld] = disable
                        patched = True

        if k == "UserLocalNoticeRedDotModel" and disable:
            existing_ids = set(obj.get("idList", []))
            all_notices = set(range(200001, 200700))
            new_ids = sorted(all_notices | existing_ids)
            if set(obj.get("idList", [])) != set(new_ids):
                obj["idList"] = new_ids
                patched = True

        if patched:
            patches[k] = json.dumps(obj, separators=(",", ":"))

    for i, k in enumerate(keys):
        if k in patches:
            values[i] = patches[k]

    MISSING_MODELS = {}
    if disable:
        MISSING_MODELS = {
            "UserLocalFormationDataModel": {
                "_formerNormalBattleTotalCount": 0,
                "_formerStoryDungeonBattleTotalCount": 0,
                "_isParticipation7TutorialOccured": True,
                "_isStoryDungeon4Opened": True,
                "_isRailwayDungeonLine2LastNodeEnterFirst": True,
            },
            "UserLocalMirrorDungeonRedDotModel": {
                "idList": [],
                "_isMirrorDungeonOpenedRedDotExist": False,
                "_isParticipation7TutorialOccured": True,
                "_lastDifficulty": 0,
                "_participation": {
                    "_recentPersonalityParticipatedOrder": [],
                    "_recentAllAliveCharacterParticipatedOrder": [],
                    "_dungeonStartDate": "2026-01-01T00:00:00.000Z",
                },
            },
            "UserLocalNoticeRedDotModel": {
                "idList": list(range(200001, 200700)),
                "isChanged": False,
            },
            "UserLocalDialogResultSaveModel": {
                "idList": [],
                "_dataList": [],
                "isChanged": False,
            },
        }

    added = 0
    for name, default_obj in MISSING_MODELS.items():
        if name not in existing:
            keys.append(name)
            values.append(json.dumps(default_obj, separators=(",", ":")))
            added += 1

    return len(patches), added


# ── Registry patching (Windows) ─────────────────────────────


def _patch_registry_windows(opt):
    import winreg

    changed = False
    for fld in ["_isLangSaved", "_showImportanceLevelUI", "_pushNotification"]:
        if not opt.get(fld):
            opt[fld] = True
            changed = True
    if not changed:
        return False
    entries = _reg_query_all()
    pref_name = None
    for name in entries:
        if "LocalSave.LocalGameOptionData" in name:
            pref_name = name
            break
    if not pref_name:
        return False
    try:
        new_hex = json.dumps(opt, separators=(",", ":")).encode("utf-8").hex() + "00"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_REG_KEY, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, pref_name, 0, winreg.REG_BINARY, bytes.fromhex(new_hex))
        return True
    except Exception:
        return False


# ── PlayerPrefs patching (Android) ──────────────────────────


def _patch_prefs_android(device, opt):
    changed = False
    for fld in ["_isLangSaved", "_showImportanceLevelUI", "_pushNotification"]:
        if not opt.get(fld):
            opt[fld] = True
            changed = True
    if not changed:
        return False
    try:
        out = device.shell(f"cat '{ANDROID_PREFS_PATH}'")
        new_val = urllib.parse.quote(json.dumps(opt, separators=(",", ":")))
        out = device.shell(f"cat '{ANDROID_PREFS_PATH}'")
        new_val = urllib.parse.quote(json.dumps(opt, separators=(",", ":")))
        xml_new = re.sub(
            r'(<string name="LocalSave\.LocalGameOptionData[^>]*>).*?(</string>)',
            lambda m: m.group(1) + new_val + m.group(2),
            out,
            flags=re.DOTALL,
        )
        local_tmp = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".xml", delete=False, mode="w", encoding="utf-8") as f:
                f.write(xml_new)
                local_tmp = f.name
            device.sync.push(local_tmp, ANDROID_PREFS_PATH)
        finally:
            if local_tmp and os.path.exists(local_tmp):
                os.unlink(local_tmp)
        return True
    except Exception:
        return False


# ── Public API ──────────────────────────────────────────────


class TutorialSkipResult:
    def __init__(
        self,
        success=False,
        platform="",
        total_slots=0,
        total_patched=0,
        total_added=0,
        registry_patched=False,
        errors=None,
    ):
        self.success = success
        self.platform = platform
        self.total_slots = total_slots
        self.total_patched = total_patched
        self.total_added = total_added
        self.registry_patched = registry_patched
        self.errors = errors or []


class _StopRequested(Exception):
    pass


def patch_windows(disable=True, log_func=None, stop_check=None):
    errors = []

    _log(log_func, "[Windows] 正在扫描注册表获取加密密钥...")
    result = _load_key_iv_windows()
    if not result:
        return TutorialSkipResult(
            success=False,
            errors=["无法从注册表读取加密密钥，请确认游戏已至少运行过一次"],
        )

    key, iv, opt = result
    _log(log_func, f"[Windows] 密钥加载成功 ({len(key)} bytes)")

    slots = glob.glob(os.path.join(WINDOWS_SAVE_DIR, "save_slot_*.json"))
    slots = [s for s in slots if not s.endswith(".bak")]

    if not slots:
        return TutorialSkipResult(
            success=False,
            errors=[f"未在 {WINDOWS_SAVE_DIR} 找到存档文件"],
        )

    _log(log_func, f"[Windows] 找到 {len(slots)} 个存档槽")

    total_patched = 0
    total_added = 0

    for sp in slots:
        if stop_check and stop_check():
            raise _StopRequested()
        try:
            _log(log_func, f"[Windows] 正在处理 {os.path.basename(sp)}...")
            with open(sp, encoding="utf-8-sig") as f:
                raw = f.read().strip()
            data = _decrypt_save(raw, key, iv)
            n, added = _patch_data(data, disable=disable)
            encrypted = _encrypt_save(data, key, iv)
            local_tmp = None
            try:
                with tempfile.NamedTemporaryFile(
                    suffix=".json", delete=False, mode="w", encoding="utf-8",
                    dir=os.path.dirname(sp),
                ) as f:
                    f.write(encrypted)
                    local_tmp = f.name
                os.replace(local_tmp, sp)
            finally:
                if local_tmp and os.path.exists(local_tmp):
                    os.unlink(local_tmp)
            total_patched += n
            total_added += added
            _log(log_func, f"[Windows]   ├ {os.path.basename(sp)}: 修改 {n} 个数据模型，补充 {added} 个模型")
        except _StopRequested:
            raise
        except Exception as e:
            errors.append(f"{os.path.basename(sp)}: {e}")
            _log(log_func, f"[Windows]   └ {os.path.basename(sp)}: 失败 - {e}")

    reg_patched = _patch_registry_windows(opt)
    if reg_patched:
        _log(log_func, "[Windows] 注册表同步完成")
    else:
        _log(log_func, "[Windows] 注册表无需修改")

    if errors:
        _log(log_func, f"[Windows] 完成，存在 {len(errors)} 个错误")
    else:
        _log(log_func, "[Windows] 全部完成")

    return TutorialSkipResult(
        success=not errors,
        platform="Windows",
        total_slots=len(slots),
        total_patched=total_patched,
        total_added=total_added,
        registry_patched=reg_patched,
        errors=errors,
    )


def patch_android(disable=True, log_func=None, stop_check=None):
    errors = []

    device = _android_device()
    if not device:
        return TutorialSkipResult(
            success=False,
            errors=["未检测到已连接的 Android 设备/模拟器，请确认 ADB 已连接"],
        )

    _log(log_func, f"[Android] 设备已连接: {device.serial}")
    _log(log_func, "[Android] 正在读取加密密钥...")

    result = _load_key_iv_android(device)
    if not result:
        return TutorialSkipResult(
            success=False,
            errors=["无法从 Android 读取加密密钥，请确认模拟器已启动且 LimbusCompany 已运行过"],
        )

    key, iv, opt = result
    _log(log_func, f"[Android] 密钥加载成功 ({len(key)} bytes)")

    out = device.shell(f"ls {ANDROID_SAVE_DIR}/save_slot_*.json 2>/dev/null")
    files = [
        f.strip()
        for f in out.strip().splitlines()
        if f.strip() and not f.strip().endswith(".bak")
    ]

    if not files:
        return TutorialSkipResult(
            success=False,
            errors=["未在 Android 设备找到存档文件"],
        )

    _log(log_func, f"[Android] 找到 {len(files)} 个存档槽")

    total_patched = 0
    total_added = 0

    for fp in files:
        if stop_check and stop_check():
            raise _StopRequested()
        try:
            _log(log_func, f"[Android] 正在处理 {os.path.basename(fp)}...")
            out = device.shell(f"cat '{fp}'")
            raw = out.strip()
            if raw.startswith("\ufeff"):
                raw = raw[1:]
            data = _decrypt_save(raw, key, iv)
            n, added = _patch_data(data, disable=disable)
            encrypted = _encrypt_save(data, key, iv)
            local_tmp = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8") as f:
                    f.write(encrypted)
                    local_tmp = f.name
                device.sync.push(local_tmp, fp)
            finally:
                if local_tmp and os.path.exists(local_tmp):
                    os.unlink(local_tmp)
            device.shell(f"chmod 660 '{fp}'")
            total_patched += n
            total_added += added
            _log(log_func, f"[Android]   ├ {os.path.basename(fp)}: 修改 {n} 个数据模型，补充 {added} 个模型")
        except _StopRequested:
            raise
        except Exception as e:
            errors.append(f"{os.path.basename(fp)}: {e}")
            _log(log_func, f"[Android]   └ {os.path.basename(fp)}: 失败 - {e}")

    prefs_ok = _patch_prefs_android(device, opt)
    if prefs_ok:
        _log(log_func, "[Android] PlayerPrefs 同步完成")
    else:
        _log(log_func, "[Android] PlayerPrefs 无需修改")

    if errors:
        _log(log_func, f"[Android] 完成，存在 {len(errors)} 个错误")
    else:
        _log(log_func, "[Android] 全部完成")

    return TutorialSkipResult(
        success=not errors,
        platform="Android",
        total_slots=len(files),
        total_patched=total_patched,
        total_added=total_added,
        registry_patched=False,
        errors=errors,
    )


def patch_auto(disable=True, log_func=None, stop_check=None):
    """自动检测平台：优先模拟器/ADB，回退到 Windows"""
    from module.config import cfg as aalc_cfg

    if aalc_cfg.simulator:
        _log(log_func, "[自动] 检测到模拟器已启用，尝试通过 ADB 连接...")
        device = _get_adb_device_auto()
        if device is not None:
            _log(log_func, f"[自动] ADB 设备已获取: {device.serial}")
            result = _load_key_iv_android(device)
            if result is not None:
                _log(log_func, "[自动] 采用 Android 平台")
                return patch_android(disable=disable, log_func=log_func, stop_check=stop_check)
            _log(log_func, "[自动] Android 密钥读取失败，回退到 Windows")
        else:
            _log(log_func, "[自动] 无法获取 ADB 设备，回退到 Windows")
    else:
        _log(log_func, "[自动] 模拟器未启用，使用 Windows 平台")

    return patch_windows(disable=disable, log_func=log_func, stop_check=stop_check)


def _log(log_func, msg):
    if log_func:
        log_func(msg)


# ── Qt Worker ──────────────────────────────────────────────


class TutorialSkipWorker(QThread):
    log_message = Signal(str)
    operation_finished = Signal(object)

    def __init__(self, disable: bool, platform: str, parent=None):
        super().__init__(parent)
        self.disable = disable
        self.platform = platform

    def run(self):
        def emit_log(msg):
            self.log_message.emit(msg)

        def stop_check():
            return self.isInterruptionRequested()

        try:
            if self.platform == "auto":
                result = patch_auto(disable=self.disable, log_func=emit_log, stop_check=stop_check)
            elif self.platform == "windows":
                result = patch_windows(disable=self.disable, log_func=emit_log, stop_check=stop_check)
            elif self.platform == "android":
                result = patch_android(disable=self.disable, log_func=emit_log, stop_check=stop_check)
            else:
                result = TutorialSkipResult(success=False, errors=[f"未知平台: {self.platform}"])
        except _StopRequested:
            result = TutorialSkipResult(success=False, errors=["用户中断操作"])

        self.operation_finished.emit(result)


# ── Qt Window ──────────────────────────────────────────────


class TutorialSkipWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.worker = None
        self.setup_ui()
        qconfig.themeChanged.connect(self._apply_theme_style)

    def setup_ui(self):
        self.setWindowTitle("跳过新手提示")
        self.setWindowIcon(QIcon("./assets/logo/canary.ico"))
        self.resize(600, 480)
        self.setMinimumSize(480, 360)

        layout = QVBoxLayout()

        # ── 操作选项 ──
        action_group = QGroupBox("操作选项")
        action_layout = QHBoxLayout()
        self.disable_radio = QRadioButton("关闭新手提示")
        self.disable_radio.setChecked(True)
        self.restore_radio = QRadioButton("恢复新手提示")
        action_layout.addWidget(self.disable_radio)
        action_layout.addWidget(self.restore_radio)
        action_layout.addStretch()
        action_group.setLayout(action_layout)
        layout.addWidget(action_group)

        # ── 目标平台 ──
        platform_group = QGroupBox("目标平台")
        platform_layout = QHBoxLayout()
        self.auto_radio = QRadioButton("自动检测")
        self.auto_radio.setChecked(True)
        self.win_radio = QRadioButton("Windows")
        self.android_radio = QRadioButton("Android")
        platform_layout.addWidget(self.auto_radio)
        platform_layout.addWidget(self.win_radio)
        platform_layout.addWidget(self.android_radio)
        platform_layout.addStretch()
        platform_group.setLayout(platform_layout)
        layout.addWidget(platform_group)

        # ── 执行按钮 ──
        self.start_button = QPushButton("开始执行")
        self.start_button.clicked.connect(self.toggle_patch)
        layout.addWidget(self.start_button)

        # ── 状态标签 ──
        self.status_label = QLabel("状态：就绪")
        self._apply_theme_style()
        layout.addWidget(self.status_label)

        # ── 日志输出 ──
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(150)
        self.log_text.append("=== 新手提示处理工具 ===")
        self.log_text.append("选择操作和平台后点击「开始执行」")
        layout.addWidget(self.log_text)

        self.setLayout(layout)
        center_window(self)

    def _apply_theme_style(self):
        apply_tool_window_theme(self, "TutorialSkipWindow")
        self.status_label.setStyleSheet(get_status_label_style())

    def toggle_patch(self):
        if self.worker and self.worker.isRunning():
            return

        disable = self.disable_radio.isChecked()

        if self.auto_radio.isChecked():
            platform = "auto"
        elif self.win_radio.isChecked():
            platform = "windows"
        else:
            platform = "android"

        action = "关闭" if disable else "恢复"
        self.log_text.append("")
        self.log_text.append(f"▶ 开始{action}新手提示（平台: {platform}）")

        self.worker = TutorialSkipWorker(disable, platform)
        self.worker.log_message.connect(self._on_log)
        self.worker.operation_finished.connect(self._on_finished)
        self.worker.start()

        self.start_button.setEnabled(False)
        self.status_label.setText("状态：处理中...")

    def _on_log(self, msg):
        self.log_text.append(msg)

    def _on_finished(self, result):
        self.start_button.setEnabled(True)

        if result.success:
            action = "关闭" if self.worker.disable else "恢复"
            parts = [f"[{result.platform}] 已处理 {result.total_slots} 个存档槽"]
            if result.total_patched:
                parts.append(f"修改 {result.total_patched} 个数据模型")
            if result.total_added:
                parts.append(f"补充 {result.total_added} 个数据模型")
            if result.registry_patched:
                parts.append("注册表同步完成")
            self.log_text.append("")
            self.log_text.append(f"✓ {action}完成：{'，'.join(parts)}")
            self.status_label.setText("状态：完成")
        else:
            self.status_label.setText("状态：失败")
            self.log_text.append("")
            self.log_text.append(f"✗ 操作失败：{'；'.join(result.errors)}")
            self.log_text.append("请检查游戏是否已运行、模拟器是否已连接")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(5000)
        event.accept()
