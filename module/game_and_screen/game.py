import os
import webbrowser
from time import monotonic, sleep

import win32con
import win32gui
import win32process

from module.config import cfg
from module.game_and_screen.steam_cloud import handle_steam_cloud_sync_dialog
from module.instance_context import get_instance_context
from module.my_error.my_error import userStopError
from module.session_process import (
    iter_processes_by_name,
    process_belongs_to_session,
    process_sessions_by_name,
    terminate_processes,
)
from utils.singletonmeta import SingletonMeta

GAME_GRACEFUL_CLOSE_TIMEOUT_SECONDS = 30.0


class Game(metaclass=SingletonMeta):
    def __init__(self, logger):
        self.game_path = cfg.game_path
        self.game_url = "steam://rungameid/1973530"
        self.log = logger
        self.process_name = cfg.game_process_name
        self.game_path_exists = True
        self._launch_requested_at: float | None = None
        self._cloud_sync_confirmation_attempted = False

    def reload_runtime_config(self) -> None:
        self.game_path = cfg.game_path
        self.process_name = cfg.game_process_name
        self.game_path_exists = True
        self._launch_requested_at: float | None = None
        self._cloud_sync_confirmation_attempted = False

    def check_game_alive(self):
        for proc in iter_processes_by_name(self.process_name):
            try:
                proc_name = proc.name()
                mem = proc.memory_info()
                cpu = proc.cpu_times()

                # 幽灵进程判定：几乎无内存占用 + 0 CPU 时间 = 进程尸体
                if mem is not None and cpu is not None:
                    if mem.rss < 1024 * 1024 and cpu.user == 0.0 and cpu.system == 0.0:
                        self.log.warning(
                            f"检测到幽灵进程：{proc_name}(PID:{proc.pid}) "
                            f"内存{mem.rss / 1024:.0f}KB，CPU时间0，跳过"
                        )
                        continue

                self.log.debug(f"游戏已启动：{proc_name}，进程ID：{proc.pid}")
                return True
            except Exception:
                continue
        return False

    def start_game(self) -> bool:
        """发起一次启动请求，窗口就绪前不重复唤起 Steam。"""
        if self._launch_requested_at is not None:
            return True
        self._launch_requested_at = monotonic()
        self._cloud_sync_confirmation_attempted = False
        if self.check_game_alive():
            return True

        self.game_path_exists = os.path.exists(self.game_path)
        if not self.game_path_exists:
            from module.config.config import Config
            detected = Config._auto_detect_game_path()
            if detected:
                cfg.set_value("game_path", detected)
                self.game_path = detected
                self.game_path_exists = True
                self.log.info(f"自动检测并更新游戏路径: {detected}")
            else:
                self.log.error(f"游戏路径不存在：{self.game_path}，使用steam命令启动...")
                self.game_path_exists = False

        try:
            context = get_instance_context()
            if context.is_child_session:
                from module.automation import auto
                from module.game_and_screen.steam import launch_limbus_via_steam

                auto.ensure_not_stopped()
                launch_limbus_via_steam(context.current_session_id)
                self.log.info(
                    f"已通过 Child Session {context.current_session_id} 内的 Steam 启动游戏"
                )
                for _ in range(50):
                    auto.ensure_not_stopped()
                    sleep(0.1)
                foreign_games = [
                    (process_id, session_id)
                    for process_id, session_id in process_sessions_by_name(self.process_name)
                    if session_id != context.current_session_id
                ]
                if foreign_games:
                    locations = ", ".join(
                        f"PID {process_id}/Session {session_id}"
                        for process_id, session_id in foreign_games
                    )
                    from module.desktop_clone.messages import translate_message
                    from module.game_and_screen.steam import SteamSessionConflictError

                    raise SteamSessionConflictError(
                        translate_message(
                            "Steam 将《边狱公司》启动到了桌面分身之外，已拒绝继续自动化。"
                            "请退出 Steam 和游戏后重试（{0}）。",
                            locations,
                        )
                    )
                return True

            if self.game_path_exists:
                os.startfile(self.game_path)
                self.log.info(f"使用本地路径启动游戏：{self.game_path}")
            else:
                webbrowser.open(self.game_url)
                self.log.info("使用 Steam 命令启动游戏")
            return True
        except userStopError:
            self.finish_launch_attempt()
            raise
        except Exception:
            self.finish_launch_attempt()
            self.log.exception("启动游戏时发生错误")
            if get_instance_context().is_child_session:
                raise
        return False

    def handle_pending_launch(self) -> bool:
        if self._launch_requested_at is None or self._cloud_sync_confirmation_attempted:
            return False
        from module.automation import auto

        auto.ensure_not_stopped()

        def consume_confirmation():
            auto.ensure_not_stopped()
            self._cloud_sync_confirmation_attempted = True

        handled = handle_steam_cloud_sync_dialog(on_dialog_detected=consume_confirmation)
        if handled:
            self.log.warning("检测到 Steam 云同步失败，已自动点击“仍然进行游戏”继续无人值守启动")
        return handled

    def finish_launch_attempt(self) -> None:
        self._launch_requested_at = None
        self._cloud_sync_confirmation_attempted = False

    def close_game(self) -> bool:
        """先正常关闭当前 Session 游戏，超时后仅结束该 Session 的进程。"""
        from module.automation import auto
        from module.game_and_screen import screen

        self.finish_launch_attempt()
        auto.ensure_not_stopped()
        if not self.check_game_alive():
            return True
        try:
            hwnd = screen.handle.hwnd
            if hwnd and win32gui.IsWindow(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if process_belongs_to_session(pid):
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception as exc:
            self.log.warning(f"请求游戏正常退出失败：{exc}")
        deadline = monotonic() + GAME_GRACEFUL_CLOSE_TIMEOUT_SECONDS
        while self.check_game_alive() and monotonic() < deadline:
            auto.ensure_not_stopped()
            sleep(0.1)
        auto.ensure_not_stopped()
        if not self.check_game_alive():
            return True
        self.log.warning("等待游戏正常退出超时，强制结束当前 Session 的游戏进程")
        return terminate_processes(self.process_name, timeout=1.0)
