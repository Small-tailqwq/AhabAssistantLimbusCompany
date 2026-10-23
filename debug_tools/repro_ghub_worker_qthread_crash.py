"""离线验证 G HUB 检测线程的结果、设备清理和窗口关闭顺序。

使用可赋 ctypes 签名的假 DLL/光标 API，不加载驱动、不移动鼠标、不修改 HOSTS。
用法：uv run python debug_tools/repro_ghub_worker_qthread_crash.py [check|close-running]
"""

import argparse
import ctypes
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import tasks.tools.ghub_manager as ghub  # noqa: E402


class FakeCall:
    def __init__(self, callback):
        self.callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.callback(*args)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", default="check", choices=("check", "close-running"))
    args = parser.parse_args()
    dummy_path = str(Path(__file__).resolve())
    events = []
    cursor = [100, 100]

    def cursor_pos(pointer):
        pointer._obj.x, pointer._obj.y = cursor
        return True

    def move(dx, dy):
        events.append("move")
        cursor[0] += dx
        cursor[1] += dy
        return True

    def close_device():
        # 结果信号到达 UI 后仍有清理工作，必须保留线程直到原生 finished。
        time.sleep(0.2)
        events.append("device_closed")

    def fake_dll(path):
        assert path == dummy_path
        events.append("dll_loaded")
        return SimpleNamespace(
            device_open=FakeCall(lambda: events.append("device_opened") or True),
            device_close=FakeCall(close_device),
            move=FakeCall(move),
        )

    fake_ctypes = SimpleNamespace(
        CDLL=fake_dll, c_bool=ctypes.c_bool, c_byte=ctypes.c_byte, byref=ctypes.byref,
        windll=SimpleNamespace(user32=SimpleNamespace(
            GetCursorPos=FakeCall(cursor_pos), GetSystemMetrics=FakeCall(lambda _index: 1920),
        )),
    )
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    original_get_value = ghub.cfg.get_value

    def get_value(key, default=None):
        if key in {"logitech_dll_path", "razer_dll_path"}:
            return dummy_path
        if key == "ghub_updates_blocked":
            return False
        return original_get_value(key, default)

    with patch.object(ghub, "ctypes", fake_ctypes), patch.object(ghub.cfg, "get_value", side_effect=get_value):
        window = ghub.GHubManager()
        window.show()
        window._on_check_dll()
        worker = window._worker
        assert isinstance(worker, ghub._DllCheckWorker)
        results = []
        worker.result_ready.connect(lambda ok, message: results.append((ok, message)))
        worker.finished.connect(lambda: events.append("thread_finished"))
        worker.finished.connect(lambda: QTimer.singleShot(20, app.quit))
        if args.mode == "close-running":
            def close_running():
                assert worker.isRunning()
                window.close()
                assert window._close_pending and window._worker is worker
                assert not window.isVisible()
                events.append("close_requested")
            QTimer.singleShot(5, close_running)
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(lambda: app.exit(1))
        timeout.start(3000)
        rc = app.exec()
        if "thread_finished" not in events and worker.isRunning():
            worker.request_stop()
            worker.wait(1000)
        assert rc == 0, "线程或窗口关闭超时"
        assert results and results[-1][0] is True, results
        expected = ["dll_loaded", "device_opened", "move"]
        if args.mode == "close-running":
            expected.append("close_requested")
        expected += ["device_closed", "thread_finished"]
        assert events == expected, events
        if args.mode == "close-running":
            assert worker._stop_requested
        else:
            assert window._worker is None
    print(f"SURVIVED: {args.mode}; fake DLL path, result, device cleanup and native finish verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
