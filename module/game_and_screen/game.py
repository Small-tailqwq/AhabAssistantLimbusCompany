import os
import webbrowser
from time import sleep, time

from module.config import cfg
from module.instance_context import get_instance_context
from module.session_process import iter_processes_by_name, process_sessions_by_name
from utils.singletonmeta import SingletonMeta


class Game(metaclass=SingletonMeta):
    def __init__(self, logger):
        self.game_path = cfg.game_path
        self.game_url = "steam://rungameid/1973530"
        self.log = logger
        self.process_name = cfg.game_process_name
        self.game_path_exists = True
        self.last_check_time = None
        self.check_in_short_time = 0

    def reload_runtime_config(self) -> None:
        self.game_path = cfg.game_path
        self.process_name = cfg.game_process_name
        self.game_path_exists = True
        self.last_check_time = None
        self.check_in_short_time = 0

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
        """启动游戏"""
        if self.check_game_alive():
            if self.last_check_time is None or time() - self.last_check_time > 60:
                self.last_check_time = time()
                self.check_in_short_time = 0
            else:
                self.check_in_short_time += 1
            if self.check_in_short_time > 5:
                from tasks.base.retry import kill_game

                kill_game()
                self.check_in_short_time = 0
            else:
                return True

        if not os.path.exists(self.game_path):
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
                from module.game_and_screen.steam import launch_limbus_via_steam

                launch_limbus_via_steam(context.current_session_id)
                self.log.info(
                    f"已通过 Child Session {context.current_session_id} 内的 Steam 启动游戏"
                )
                sleep(5)
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

            # 调用系统打开该 URL（会触发 Steam 启动游戏）
            webbrowser.open(self.game_url)
            self.log.info("使用steam命令启动游戏")
            sleep(5)
            if not self.check_game_alive() and self.game_path_exists:
                os.startfile(self.game_path)
                self.log.info(f"游戏启动：{self.game_path}")
            return True
        except Exception:
            self.log.exception("启动游戏时发生错误")
            if get_instance_context().is_child_session:
                raise
        return False
