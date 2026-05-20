import os
import platform
import socket
import sys
import threading

# 在导入任何模块之前设置工作目录，确保相对路径（如 ./assets/、./config.yaml）正确解析
if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))
else:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

_is_mac = platform.system() == "Darwin"

if getattr(sys, "frozen", False) and _is_mac:
    _macos_dir = os.path.dirname(sys.executable)
    _contents_dir = os.path.dirname(_macos_dir)
    _frameworks_dir = os.path.join(_contents_dir, "Frameworks")
    _resources_dir = os.path.join(_contents_dir, "Resources")
    for _pkg in ("rapidocr", "certifi"):
        _src = os.path.join(_resources_dir, _pkg)
        _dst = os.path.join(_frameworks_dir, _pkg)
        if os.path.isdir(_src) and os.path.isdir(_frameworks_dir):
            _need_sync = False
            try:
                _need_sync = not any(
                    os.path.isfile(os.path.join(_dst, f))
                    for f in os.listdir(_dst)
                )
            except OSError:
                _need_sync = True
            if _need_sync:
                try:
                    import shutil
                    if os.path.isdir(_dst):
                        shutil.rmtree(_dst, ignore_errors=True)
                        try:
                            os.rmdir(_dst)
                        except OSError:
                            pass
                    shutil.copytree(_src, _dst, symlinks=False)
                except Exception:
                    pass

if _is_mac:
    # macOS: 修复 qframelesswindow 标准窗口按钮为 None 时的崩溃
    # 使用 _MacFramelessWindowBase__nsWindow 绕过 Python 名称改写
    _NSWIN = "_MacFramelessWindowBase__nsWindow"
    try:
        import Cocoa as _Cocoa
        import qframelesswindow.mac as _qfw_mac
        def _patched_set_visible(self, isVisible):
            self._isSystemButtonVisible = isVisible
            _nswin = object.__getattribute__(self, _NSWIN)
            _nswin.setShowsToolbarButton_(isVisible)
            isHidden = not isVisible
            for _btn_type in (_Cocoa.NSWindowCloseButton, _Cocoa.NSWindowZoomButton,
                              _Cocoa.NSWindowMiniaturizeButton):
                _btn = _nswin.standardWindowButton_(_btn_type)
                if _btn is not None:
                    _btn.setHidden_(isHidden)
            if isVisible:
                self._updateSystemButtonRect()
        _qfw_mac.MacFramelessWindowBase.setSystemTitleBarButtonVisible = _patched_set_visible
    except ImportError:
        pass
else:
    # 解决 Windows DPI 缩放问题
    from ctypes import c_void_p, windll

    try:
        # 1. 尝试 Win10 1703+ 的最强方案 (Per Monitor V2)
        # -4 对应 DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        windll.user32.SetProcessDpiAwarenessContext(c_void_p(-4))
    except (AttributeError, OSError):
        try:
            # 2. 尝试 Win8.1+ 的方案 (Per Monitor)
            # 2 对应 PROCESS_PER_MONITOR_DPI_AWARE
            windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            try:
                # 3. 最后的兜底方案 (Win7/Vista)
                windll.user32.SetProcessDPIAware()
            except Exception:
                pass

from app.language_manager import LanguageManager
from app.my_app import MainWindow, _mac_rounded_icon
from module.config import cfg

# 获取管理员权限 (Windows only)
if not _is_mac:
    import pyuac

    if not pyuac.isUserAdmin():
        try:
            pyuac.runAsAdmin(False)
            sys.exit(0)
        except Exception:
            sys.exit(1)

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication

QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
QApplication.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)


# 创建一个辅助类用于在主线程处理信号
class ArgumentSignaler(QObject):
    arguments_received = Signal(list)


def start_socket_server(port, signaler):
    """后台线程：监听新实例发来的参数"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", port))
        s.listen(5)
        while True:
            conn, addr = s.accept()
            with conn:
                data = conn.recv(1024).decode("utf-8")
                if data:
                    # 收到参数后通过信号发送给主线程处理
                    signaler.arguments_received.emit(data.split("|"))


def send_args_to_existing_instance(port, args):
    """尝试将参数发送给已存在的实例"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)  # 设置 1 秒超时
            s.connect(("127.0.0.1", port))
            s.sendall("|".join(args).encode("utf-8"))
        return True
    except ConnectionRefusedError:
        return False
    except Exception:
        return False


if __name__ == "__main__":
    # 定义一个唯一的端口号（建议选择 1024-65535 之间的随机数）
    APP_PORT = 62333

    # 1. 尝试发送参数给已有实例
    if send_args_to_existing_instance(APP_PORT, sys.argv[1:]):
        sys.exit(0)

    # 2. 如果发送失败，说明是第一个实例，开始初始化
    if cfg.zoom_scale != 0:
        os.environ["QT_SCALE_FACTOR"] = str(cfg.zoom_scale / 100)

    lang_manager = LanguageManager()
    lang = lang_manager.init_language()

    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)
    app.setWindowIcon(_mac_rounded_icon("./assets/logo/canary.png"))

    # 创建主窗口
    ui = MainWindow(sys.argv)

    # 3. 设置参数监听信号
    signaler = ArgumentSignaler()

    def handle_args(args):
        # 处理新参数的逻辑
        args.insert(0, "aalc")
        ui.command_start(args)
        ui.showNormal()
        ui.activateWindow()
        ui.raise_()
        # 如果需要，可以在这里调用 ui.open_file(args[0]) 等

    signaler.arguments_received.connect(handle_args)

    # 4. 在后台启动 Socket 服务器（非阻塞主线程）
    # 注意：这里需要捕获 bind 异常，防止极短时间内双击导致的竞争
    try:
        threading.Thread(target=start_socket_server, args=(APP_PORT, signaler), daemon=True).start()
    except OSError:
        # 如果走到这说明刚才的 bind 突然成功了但又瞬间失败，通常直接退出即可
        sys.exit(1)

    QTimer.singleShot(50, lambda: lang_manager.set_language(lang))

    sys.exit(app.exec())
