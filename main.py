import os
import socket
import sys
import threading

# 尽早清除 SSLKEYLOGFILE，避免 OpenSSL 在建立 HTTPS 连接时因跨 CRT 边界崩溃。
# 该变量通常由调试代理（如 Fiddler/Charles/Wireshark）设置，Python 内嵌的 OpenSSL
# 在 Windows 上不提供 OPENSSL_Applink 符号，一试写文件就会抛错退出。
# 此处仅清除当前进程的环境变量，不影响系统设置和其他进程。
_ORIG_SSLKEYLOGFILE = os.environ.pop("SSLKEYLOGFILE", None)

# 将当前工作目录设置为程序所在的目录，确保无论从哪里执行，其工作目录都正确设置为程序本身的位置，避免路径错误。
os.chdir(
    os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
)

from module.instance_context import get_instance_context

instance_context = get_instance_context()

def _install_child_startup_crash_capture(profile_dir, context) -> None:
    """Persist pre-logger failures of a Child Session instance.

    The child is started by Task Scheduler with a hidden window, so stderr goes
    nowhere. Anything that fails before ``Logger()`` — session mismatch, import
    error, privilege rejection — exits silently and the controller can only sit
    out its 120s connection timeout. Without this the failure is undiagnosable.
    """
    import datetime
    import traceback

    crash_file = profile_dir / "logs" / "child-startup-error.txt"

    def _hook(exc_type, exc_value, exc_traceback):
        try:
            crash_file.parent.mkdir(parents=True, exist_ok=True)
            with open(crash_file, "a", encoding="utf-8") as handle:
                handle.write(f"\n===== {datetime.datetime.now().isoformat()} =====\n")
                handle.write(f"argv: {sys.argv}\n")
                handle.write(
                    f"session: current={context.current_session_id} "
                    f"expected={context.expected_session_id}\n"
                )
                traceback.print_exception(exc_type, exc_value, exc_traceback, file=handle)
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = _hook

    def _thread_hook(args) -> None:
        _hook(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = _thread_hook


if instance_context.is_child_session:
    if instance_context.profile_dir is not None:
        _install_child_startup_crash_capture(instance_context.profile_dir, instance_context)
    else:
        # 启动器漏传 --desktop-clone-profile 时 validate() 会抛 ValueError；
        # 回退到默认 profile 路径，保证这次静默失败仍能落盘定位。
        from pathlib import Path

        local_app_data = os.environ.get("LOCALAPPDATA")
        fallback_profile = (
            Path(local_app_data) / "AALC" / "desktop-clone"
            if local_app_data
            else Path.cwd()
        )
        _install_child_startup_crash_capture(fallback_profile, instance_context)

instance_context.validate()

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

# 为 Windows 任务栏注册唯一 AppUserModelID，避免首次启动时任务栏使用 python.exe 默认图标。
# 此 API 自 Windows 7 起可用，SetProcessDpiAwarenessContext 成功即保障可用。
try:
    app_user_model_id = "AALC.ChildSession" if instance_context.is_child_session else "AALC.MainWindow"
    windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_user_model_id)
except Exception:
    pass

from module.logger import log
from module.logger.my_log import Logger

Logger()

from module.config import cfg

if instance_context.is_child_session:
    from module.desktop_clone.profile import apply_child_runtime_overrides

    apply_child_runtime_overrides()

from app.language_manager import LanguageManager
from app.my_app import MainWindow


# 获取管理员权限
import pyuac

if not pyuac.isUserAdmin():
    if instance_context.is_child_session:
        log.error("Child Session AALC 未以管理员权限启动，拒绝在错误权限上下文中重启")
        sys.exit(1)
    try:
        pyuac.runAsAdmin(False)
        sys.exit(0)
    except Exception:
        sys.exit(1)

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
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
    if _ORIG_SSLKEYLOGFILE is not None:
        log.warning(f"检测到冲突的环境变量 SSLKEYLOGFILE={_ORIG_SSLKEYLOGFILE}，"
                     f"已在进程内清除，避免 OpenSSL 崩溃")

    # 定义一个唯一的端口号（建议选择 1024-65535 之间的随机数）
    APP_PORT = 62333

    # Child Session 使用专用命名管道，不能参与 root 的固定端口单实例判断。
    if instance_context.is_root and send_args_to_existing_instance(APP_PORT, sys.argv[1:]):
        sys.exit(0)

    # 2. 如果发送失败，说明是第一个实例，开始初始化
    if cfg.zoom_scale != 0:
        os.environ["QT_SCALE_FACTOR"] = str(cfg.zoom_scale / 100)

    lang_manager = LanguageManager()
    lang = lang_manager.init_language()

    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)
    app.setWindowIcon(QIcon("./assets/logo/canary.ico"))

    # 创建主窗口
    ui = MainWindow(sys.argv)

    desktop_clone_client = None
    if instance_context.is_child_session:
        from module.desktop_clone.client import (
            DesktopCloneClient,
            register_desktop_clone_client,
        )
        from module.logger.my_log import ui_log_dispatcher

        desktop_clone_client = DesktopCloneClient(ui)
        register_desktop_clone_client(desktop_clone_client)
        desktop_clone_client.install_log_forwarding(ui_log_dispatcher)
        ui.attach_desktop_clone_client(desktop_clone_client)
        desktop_clone_client.start()

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
    if instance_context.is_root:
        try:
            threading.Thread(target=start_socket_server, args=(APP_PORT, signaler), daemon=True).start()
        except OSError:
            # 如果走到这说明刚才的 bind 突然成功了但又瞬间失败，通常直接退出即可
            sys.exit(1)

    QTimer.singleShot(50, lambda: lang_manager.set_language(lang))

    sys.exit(app.exec())
