import atexit
import copy
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from time import localtime, strftime, time
from typing import Any, Optional

if sys.platform == "win32":
    try:
        import winreg
    except ImportError:
        winreg = None

from pydantic import BaseModel, ValidationError
from ruamel.yaml import YAML, YAMLError

from module.after_completion_types import (
    LEGACY_AFTER_COMPLETION_TO_CONFIG,
    POWER_ACTION_NONE,
    serialize_after_actions,
    serialize_power_action,
)
from module.logger import log
from utils.singletonmeta import SingletonMeta

from .config_typing import ConfigModel, TeamSetting


class Config(metaclass=SingletonMeta):
    def __init__(self, version_path, example_path, config_path, backup_path: str = "config_backup"):
        self.yaml = YAML()
        # 并发与延迟写控制
        self._lock = threading.RLock()
        self._save_timer = None
        self._save_interval = 1.0  # 秒：在此时间窗口内的多次修改合并为一次写盘
        self._pending_save = False
        # 后台写盘线程
        self._writer_event = threading.Event()
        self._writer_thread = threading.Thread(target=self._writer_loop, name="ConfigWriter", daemon=True)
        self._writer_thread.start()

        # 日志复现模式：暂停自动写盘
        self._save_suspended = False
        self._replay_source = None

        # 加载版本信息
        self.version = self._load_version(version_path)
        # 加载默认配置
        self.config = ConfigModel()
        # 获取用户的配置文件路径
        self.config_path = Path(config_path)
        # 保存含有注释的yaml文件的路径
        self.example_path = Path(example_path)

        self.backup_path = Path(backup_path)

        # 加载实际配置，此方法会根据实际配置覆盖默认配置
        self._load_config()
        log.debug(f"配置文件已加载，版本号：{self.version}, 配置版本: {self.get_value('config_version', '未知')}")
        # 进程退出前确保落盘
        atexit.register(self.flush)

    def set_save_suspended(self, suspended: bool, source: Optional[str] = None) -> None:
        with self._lock:
            self._save_suspended = suspended
            if suspended:
                self._replay_source = source
            else:
                self._replay_source = None

    def is_save_suspended(self) -> bool:
        return self._save_suspended

    @property
    def replay_source(self) -> Optional[str]:
        return self._replay_source

    def _old_version_cfg_upgrade(self, saved_version: int, loaded_config: dict) -> None:
        """旧版本配置升级处理

        本身不进行保存文件操作
        """
        log.info("检测到旧版本配置文件，正在进行升级...")

        # 镜牢历史数据格式转换
        if saved_version < 1768403022:
            team_num = len(self.get_value("teams_be_select", []))

            def _calculate_time_history(time_list: list[float], count: int) -> list[float]:
                """从每局都记录转换为只记录三种平均值"""
                if count == 0:
                    return [0.0, 0.0, 0.0]
                if len(time_list) == 3 and count != 3:
                    return time_list  # 已经是新格式，直接返回
                elif len(time_list) == 3 and count == 3:
                    # 判断是否是巧合
                    if time_list[0] == time_list[1] == time_list[2]:
                        return time_list
                total_avr = 0
                five_avr = 0
                ten_avr = 0
                for index in range(-1, -len(time_list) - 1, -1):
                    total_avr += time_list[index]
                    if index >= -5:
                        five_avr += time_list[index]
                    if index >= -10:
                        ten_avr += time_list[index]
                total_avr /= count
                five_avr /= min(5, count)
                ten_avr /= min(10, count)
                new_time_list = [total_avr, five_avr, ten_avr]

                return new_time_list

            try:
                if team_num > 0:
                    for i in range(1, team_num + 1):
                        history_key = f"team{i}_history"
                        history = loaded_config.get(history_key, {})
                        if not history:
                            continue
                        hard_time = history.get("total_mirror_time_hard", [])
                        hard_count = history.get("mirror_hard_count", 0)
                        normal_time = history.get("total_mirror_time_normal", [])
                        normal_count = history.get("mirror_normal_count", 0)

                        hard_time = _calculate_time_history(hard_time, hard_count)
                        normal_time = _calculate_time_history(normal_time, normal_count)
                        history["total_mirror_time_hard"] = hard_time
                        history["mirror_hard_count"] = hard_count
                        history["total_mirror_time_normal"] = normal_time
                        history["mirror_normal_count"] = normal_count
                        loaded_config[history_key] = history
            except Exception as e:
                log.error(f"镜牢历史数据格式转换失败，错误信息：{e}")

        # 旧配置类型转换
        if saved_version < 1771413380:
            if self.get_value("set_win_position", True) is True:
                loaded_config["set_win_position"] = "free"
        if saved_version < 1771965838:
            if self.get_value("background_click", True) is True:
                loaded_config["win_input_type"] = "background"
            else:
                loaded_config["win_input_type"] = "foreground"
        if saved_version < 1772205660:
            # 迁移旧版结束后动作配置，按字段独立迁移，避免覆盖用户已设置的新字段
            # 映射表统一由 module.after_completion_types 维护；config 层只负责迁移与落盘。
            legacy_value = int(self.get_value("after_completion", 0) or 0)
            legacy_actions, legacy_power = LEGACY_AFTER_COMPLETION_TO_CONFIG.get(legacy_value, ((), POWER_ACTION_NONE))
            migrated = False

            # 仅在 actions 字段缺失或类型错误时补写
            current_actions = self.get_value("after_completion_actions")
            if not isinstance(current_actions, list):
                # 配置文件保持字符串协议，不直接持久化内部 Enum。
                loaded_config["after_completion_actions"] = serialize_after_actions(legacy_actions)
                migrated = True

            # 仅在 power_action 字段缺失或类型错误时补写（与 actions 独立判断）
            current_power = self.get_value("after_completion_power_action")
            if not isinstance(current_power, str):
                loaded_config["after_completion_power_action"] = serialize_power_action(legacy_power)
                migrated = True

            if migrated:
                log.info(f"已将旧版结束后操作配置迁移为组合动作（legacy={legacy_value}）")
        if saved_version < 1775826004:
            teams: dict[str, dict] = {}
            for i in range(1, 21):
                settings: dict | None = loaded_config.get(f"team{i}_setting", None)
                if settings is None:
                    continue
                remark_name: str | None = loaded_config.get(f"team{i}_remark_name", None)
                history: dict = loaded_config.get(f"team{i}_history", {}) or {}

                settings.update(history)
                settings["remark_name"] = remark_name
                teams[f"{i}"] = settings
            loaded_config["teams"] = teams
        if saved_version < 1779444115:
            current_config_path = Path("config.yaml")
            suffixes = [".yaml.bak", ".yaml.backup", ".yaml.old"]
            for suffix in suffixes:
                file = current_config_path.with_suffix(suffix)
                if file.exists():
                    try:
                        file.unlink()
                    except Exception as e:
                        log.error(f"删除旧备份文件 {file} 失败: {e}")

        log.info("配置升级完成")

    def _load_version(self, version_path: str) -> str:
        """加载版本信息"""
        try:
            with open(version_path, "r", encoding="utf-8") as file:
                return file.read().strip()
        except FileNotFoundError:
            sys.exit("版本文件未找到")

    def _load_default_config(self, example_path: str | Path | None = None) -> dict:
        """加载默认配置信息"""
        if example_path is None:
            example_path = self.example_path
        else:
            self.example_path = Path(example_path)
        try:
            with open(example_path, "r", encoding="utf-8") as file:
                loaded = self.yaml.load(file)
                return loaded or {}
        except FileNotFoundError:
            log.error(f"默认配置文件 {example_path} 未找到，使用空配置")
            return {}
        except Exception:
            log.warning(f"默认配置文件 {example_path} 读取失败，使用空配置")
            return {}

    @staticmethod
    def _parse_backup_timestamp(filename: str) -> float:
        """从备份文件名解析时间戳，解析失败返回 0"""
        m = re.search(r"config_(\d{8})_(\d{6})\.yaml", filename)
        if m:
            try:
                return datetime.strptime(f"{m.group(1)}_{m.group(2)}", "%Y%m%d_%H%M%S").timestamp()
            except ValueError:
                return 0.0
        return 0.0

    def _get_backup_path(self) -> Path:
        """获取备份目录路径，兼容测试场景下未完整初始化的 Config 实例。"""
        backup_path = self.__dict__.get("backup_path")
        if isinstance(backup_path, str):
            backup_path = Path(backup_path)
        elif not isinstance(backup_path, Path):
            backup_path = Path("config_backup")
        self.__dict__["backup_path"] = backup_path
        return backup_path

    def _get_sorted_backups(self) -> list[Path]:
        """按文件名时间戳降序排列备份文件"""
        backup_path = self._get_backup_path()
        if not backup_path.exists():
            return []
        files = [f for f in backup_path.iterdir() if f.is_file() and f.suffix == ".yaml"]
        files.sort(key=lambda f: self._parse_backup_timestamp(f.name), reverse=True)
        return files

    @staticmethod
    def _scan_steam_libraries() -> list[Path]:
        paths: list[Path] = []
        if sys.platform != "win32" or winreg is None:
            return paths
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")
            steam_path = Path(winreg.QueryValueEx(key, "InstallPath")[0])
            winreg.CloseKey(key)
        except OSError:
            return paths
        vdf_path = steam_path / "steamapps" / "libraryfolders.vdf"
        if not vdf_path.exists():
            return paths
        try:
            text = vdf_path.read_text(encoding="utf-8")
            for m in re.finditer(r'"path"\s*"([^"]+)"', text):
                p = Path(m.group(1).replace("\\\\", "\\"))
                if p not in paths:
                    paths.append(p)
        except OSError:
            pass
        return paths

    @staticmethod
    def _auto_detect_game_path() -> str:
        lib_paths = Config._scan_steam_libraries()
        for lib in lib_paths:
            candidate = lib / "steamapps" / "common" / "Limbus Company" / "LimbusCompany.exe"
            if candidate.exists():
                log.info(f"自动检测到游戏路径: {candidate}")
                return str(candidate)
        log.info("未自动检测到游戏路径，请手动设置")
        return ""

    def _repair_config(self, config: dict) -> int:
        """检测并修复已知的配置损坏模式，返回修复计数"""
        repairs = 0

        teams = config.get("teams")
        if isinstance(teams, dict):
            for k, v in list(teams.items()):
                if v is None:
                    teams[k] = TeamSetting().model_dump()
                    log.warning(f"自动修复: 队伍 {k} 配置为空，已重置为默认值")
                    repairs += 1

        gp = config.get("game_path", "")
        if isinstance(gp, str) and "(x86" in gp and "(x86)" not in gp:
            config["game_path"] = gp.replace("(x86", "(x86)")
            log.warning("自动修复: game_path 括号缺失")
            repairs += 1

        for key, val in list(config.items()):
            if isinstance(val, str) and re.search(r'\.{3,}$', val):
                log.warning(f"配置项 {key} 可能被截断: {val[:50]}...")

        return repairs

    def _load_config(self, path: str | Path | None = None) -> None:
        """加载用户配置文件，如未找到则保存默认配置"""
        if isinstance(path, str):
            path = Path(path)
        path = path or self.config_path

        # 构建恢复链：[ (文件路径, 描述), ..., (None, "默认配置") ]
        load_targets: list[tuple[Path | None, str]] = [(path, "主配置文件")]
        backup_files = self._get_sorted_backups()
        load_targets.extend((bf, f"备份文件 {bf.name}") for bf in backup_files)
        load_targets.append((None, "默认配置"))

        for attempt_path, label in load_targets:
            try:
                if attempt_path is None:
                    loaded_config = ConfigModel().model_dump()
                    log.error("所有配置文件和备份均无法加载，已重置为默认配置")
                else:
                    if not attempt_path.exists():
                        continue
                    with open(attempt_path, "r", encoding="utf-8") as file:
                        loaded_config: dict = self.yaml.load(file)
                    if loaded_config is None:
                        continue

                # 自动修复已知损坏模式
                repairs = self._repair_config(loaded_config)

                if not isinstance(loaded_config.get("config_version", 0), int):
                    raise TypeError("配置文件版本号不是 int 类型")
                if loaded_config.get("config_version", 0) < self.config.config_version:
                    saved_version = loaded_config.get("config_version", 0)
                    loaded_config["config_version"] = self.config.config_version
                    self._old_version_cfg_upgrade(saved_version, loaded_config)

                teams = loaded_config.get("teams", {})
                if isinstance(teams, dict):
                    for team_key, settings in list(teams.items()):
                        if isinstance(settings, dict):
                            teams[team_key] = migrate_legacy_team_setting_data(settings)

                self.config = ConfigModel(**loaded_config)
                gp = Path(self.config.game_path)
                if not gp.exists() or not gp.is_file():
                    detected = self._auto_detect_game_path()
                    if detected:
                        self.config.game_path = detected
                self._reset_session_only_config()
                queue_in_loaded_config = loaded_config.get("teams_active_queue")
                if queue_in_loaded_config is None:
                    normalized_queue = self._normalize_team_queue(self.migrate_legacy_team_queue())
                else:
                    normalized_queue = self._normalize_team_queue(queue_in_loaded_config)
                self._sync_legacy_team_state(normalized_queue)

                if attempt_path != path and attempt_path is not None:
                    log.warning(f"配置从 {label} 恢复，已自动写回主配置文件")
                if repairs > 0:
                    log.warning(f"配置已自动修复 {repairs} 处损坏")

                self.backup_config()
                self._save_config()
                return

            except (ValidationError, ValueError, TypeError, YAMLError) as e:
                log.warning(f"{label} 数据非法: {e}")
                continue
            except Exception as e:
                log.warning(f"{label} 加载失败: {e}")
                continue

    def _atomic_yaml_write(self, path: Path, data) -> None:
        """原子 YAML 写入：临时文件 → replace，崩溃不截断"""
        tmp = path.with_suffix(".yaml.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                self.yaml.dump(data, f)
            tmp.replace(path)
        except BaseException:
            if tmp.exists():
                tmp.unlink()
            raise

    def _save_config(self) -> None:
        """保存到配置文件（立即写盘）"""
        # 拷贝快照后在锁外写盘，避免长时间持锁
        with self._lock:
            snapshot = self.config.model_dump()
        example_yaml = self._load_default_config()
        # 从快照更新到yaml对象，保持注释不变
        example_yaml.update(snapshot)

        self._atomic_yaml_write(self.config_path, example_yaml)

    def get_value(self, key: str, default: Any = None, *, config_obj: Optional[BaseModel] = None) -> Any:
        """获取配置项的值, 如果是可变对象，则返回其指针"""
        if config_obj is not None:
            try:
                value = getattr(config_obj, key, default)
            except Exception:
                value = default
        else:
            try:
                value = getattr(self.config, key, default)
            except Exception:
                value = default
        return value

    def get_team_numbers(self) -> list[int]:
        """获取所有已配置的队伍编号，返回排序后的列表"""
        teams = self.get_value("teams", {}) or {}
        team_numbers: list[int] = []
        for team_key in teams:
            try:
                team_num = int(team_key)
            except (TypeError, ValueError):
                continue
            if team_num > 0:
                team_numbers.append(team_num)
        return sorted(team_numbers)

    def _normalize_team_queue(self, queue: list[int]) -> list[int]:
        """去重并过滤无效队伍编号，返回干净的队列"""
        valid_team_numbers = set(self.get_team_numbers())
        normalized_queue: list[int] = []
        seen: set[int] = set()
        for team_num in queue or []:
            if type(team_num) is not int:
                continue
            if team_num not in valid_team_numbers or team_num in seen:
                continue
            normalized_queue.append(team_num)
            seen.add(team_num)
        return normalized_queue

    def migrate_legacy_team_queue(self) -> list[int]:
        """从旧的 teams_order/teams_be_select 迁移出队列顺序"""
        team_numbers = self.get_team_numbers()
        if not team_numbers:
            return []

        teams_order = self.get_value("teams_order", []) or []
        order_pairs: list[tuple[int, int]] = []
        used_orders: set[int] = set()
        for team_num in team_numbers:
            order_index = team_num - 1
            if order_index >= len(teams_order):
                continue
            order = teams_order[order_index]
            if not isinstance(order, int) or order <= 0 or order in used_orders:
                continue
            order_pairs.append((order, team_num))
            used_orders.add(order)

        teams_be_select = self.get_value("teams_be_select", []) or []
        migrated_queue = [team_num for _, team_num in sorted(order_pairs)]
        queued_team_numbers = set(migrated_queue)
        for team_num in team_numbers:
            select_index = team_num - 1
            if select_index >= len(teams_be_select):
                continue
            if teams_be_select[select_index] is not True or team_num in queued_team_numbers:
                continue
            migrated_queue.append(team_num)
        return migrated_queue

    def _sync_legacy_team_state(self, queue: list[int]) -> None:
        """将队列状态写回 teams_be_select / teams_order 等旧字段"""
        max_team_num = max(self.get_team_numbers(), default=0)
        teams_be_select = [False] * max_team_num
        teams_order = [0] * max_team_num
        for order, team_num in enumerate(queue, start=1):
            if team_num <= 0 or team_num > max_team_num:
                continue
            teams_be_select[team_num - 1] = True
            teams_order[team_num - 1] = order

        self.unsaved_set_value("teams_active_queue", queue)
        self.unsaved_set_value("teams_be_select", teams_be_select)
        self.unsaved_set_value("teams_order", teams_order)
        self.unsaved_set_value("teams_be_select_num", len(queue))

    def normalize_and_sync_team_state(self, persist: bool = True) -> None:
        """归一化队伍队列并同步到旧字段，persist=True 时写入磁盘"""
        queue = self.get_value("teams_active_queue")
        if queue is None:
            queue = self._normalize_team_queue(self.migrate_legacy_team_queue())
        else:
            queue = self._normalize_team_queue(queue)
        self._sync_legacy_team_state(queue)
        if persist:
            self.save()

    def reindex_team_queue(self, old_to_new: dict[int, int]) -> None:
        """根据 old_to_new 映射重新索引队列（队伍编号压缩后调用）"""
        queue = []
        for team_num in self.get_value("teams_active_queue", []) or []:
            new_team_num = old_to_new.get(team_num)
            if isinstance(new_team_num, int):
                queue.append(new_team_num)
        self._sync_legacy_team_state(self._normalize_team_queue(queue))
        self.save()

    def rotate_team_queue(self) -> None:
        """将队首队伍轮转到队尾"""
        queue = self._normalize_team_queue(self.get_value("teams_active_queue", []))
        if len(queue) > 1:
            queue = queue[1:] + queue[:1]
        self._sync_legacy_team_state(queue)
        self.save()

    def remove_team_from_queue(self, team_num: int) -> None:
        """从队列中移除指定队伍"""
        queue = [value for value in self.get_value("teams_active_queue", []) or [] if value != team_num]
        self._sync_legacy_team_state(self._normalize_team_queue(queue))
        self.save()

    def set_team_enabled(self, team_num: int, enabled: bool) -> None:
        """启用/禁用指定队伍（将其加入或移出队列）"""
        queue = self._normalize_team_queue(self.get_value("teams_active_queue", []))
        if enabled:
            if team_num not in queue:
                queue.append(team_num)
        else:
            queue = [value for value in queue if value != team_num]
        self._sync_legacy_team_state(self._normalize_team_queue(queue))
        self.save()

    def set_value(self, key: str, value: Any, *, config_obj: Optional[BaseModel | dict] = None) -> None:
        """设置配置项的值并延迟保存"""
        with self._lock:
            self.unsaved_set_value(key, value, config_obj=config_obj, stacklevel=3)

            # 安排一次延迟保存
            self._schedule_save()

    def _schedule_save(self) -> None:
        """在时间窗口内合并多次修改，只触发一次写盘。"""
        with self._lock:
            if self._save_suspended:
                return
            self._pending_save = True
            # 取消已有的定时器，重新计时
            if self._save_timer is not None:
                try:
                    self._save_timer.cancel()
                except Exception:
                    pass
            self._save_timer = threading.Timer(self._save_interval, self._flush_save)
            self._save_timer.daemon = True
            self._save_timer.start()

    def save(self, instant: bool = False) -> None:
        """公开方法：请求一次保存

        Args:
            instant (bool): 是否立即保存（跳过延迟机制, 但会阻塞线程）
        """
        if instant:
            self._save_config()
        else:
            self._schedule_save()

    def _flush_save(self) -> None:
        """定时器回调：触发一次后台写盘信号。"""
        with self._lock:
            if self._save_suspended or not self._pending_save:
                return
            self._pending_save = False
            self._save_timer = None
            self._writer_event.set()

    def flush(self) -> None:
        """立即将挂起的更改写入磁盘。"""
        with self._lock:
            if self._save_timer is not None:
                try:
                    self._save_timer.cancel()
                except Exception:
                    pass
                self._save_timer = None
            pending = self._pending_save
            self._pending_save = False
        if pending:
            self._save_config()

    def _writer_loop(self) -> None:
        """后台写盘线程：收到事件后把当前config写入文件"""
        while True:
            self._writer_event.wait()
            try:
                self._save_config()
            except Exception as e:
                log.error(f"配置保存失败，错误信息：{e}")

            # 等待下一次
            self._writer_event.clear()

    def _reset_session_only_config(self) -> None:
        """确保会话级配置项不跨生命周期生效。

        因 _save_config() 全量序列化 self.config，任何 cfg.set_value()
        都会把此前通过 cfg.unsaved_set_value() 设置的 "仅本次" 值一起写盘。
        此处启动加载时若 keep_after_completion 为 False，回退为默认值。
        """
        if not self.config.keep_after_completion:
            self.config.after_completion_actions = []
            self.config.after_completion_power_action = "none"

    def just_load_config(self, path: Optional[Path | str] = None) -> None:
        """仅加载配置文件，不保存"""
        default_path = self.__dict__.get("config_path", Path("config.yaml"))
        if isinstance(default_path, str):
            default_path = Path(default_path)
        path = Path(path) if isinstance(path, str) else (path or default_path)
        load_targets: list[Path | None] = [path, *self._get_sorted_backups(), None]
        for attempt in load_targets:
            try:
                if attempt is None:
                    log.error(f"just_load_config: 所有来源均加载失败，使用默认配置 (path={path})")
                    self.config = ConfigModel()
                    return
                if not attempt.exists():
                    continue
                with open(attempt, "r", encoding="utf-8") as file:
                    loaded_config = self.yaml.load(file)
                if not loaded_config:
                    continue
                repairs = self._repair_config(loaded_config)
                self.config = ConfigModel(**loaded_config)
                gp = Path(self.config.game_path)
                if not gp.exists() or not gp.is_file():
                    detected = self._auto_detect_game_path()
                    if detected:
                        self.config.game_path = detected
                self._reset_session_only_config()
                queue_in_loaded_config = loaded_config.get("teams_active_queue")
                if queue_in_loaded_config is None:
                    normalized_queue = self._normalize_team_queue(self.migrate_legacy_team_queue())
                else:
                    normalized_queue = self._normalize_team_queue(queue_in_loaded_config)
                self._sync_legacy_team_state(normalized_queue)
                if attempt != path:
                    log.warning(f"just_load_config: 从备份 {attempt.name} 恢复（原文件 {path} 不可读）")
                if repairs > 0:
                    log.warning(f"just_load_config: 自动修复 {repairs} 处配置损坏")
                return
            except Exception:
                continue

    def unsaved_set_value(
        self, key: str, value: Any, *, config_obj: Optional[BaseModel | dict] = None, stacklevel: int = 2
    ) -> None:
        """仅设置配置项的值 不保存"""
        if self.config is None:
            self.just_load_config()
        if isinstance(value, (list, dict, set)):
            value = copy.deepcopy(value)
        if isinstance(config_obj, BaseModel):
            setattr(config_obj, key, value)
        elif isinstance(config_obj, dict):
            config_obj[key] = value
        else:
            setattr(self.config, key, value)

        if config_obj:
            if isinstance(config_obj, dict):
                value_obj: BaseModel | None | Any = config_obj.get(key, None)
                if isinstance(value_obj, BaseModel):
                    cls = value_obj.__class__.__name__
                else:
                    cls = "None"
                log.debug(f"{cls}::{key} change to: {value}", stacklevel=stacklevel)
            else:
                log.debug(f"{config_obj.__class__.__name__}::{key} change to: {value}", stacklevel=stacklevel)
        else:
            log.debug(f"{key} change to: {value}", stacklevel=stacklevel)  # 增加设置修改的信息

    def backup_config(self) -> None:
        """备份当前配置到备份目录（每天最多一份，保留最近10份）"""
        backup_path = self._get_backup_path()
        if not backup_path.exists():
            backup_path.mkdir(parents=True, exist_ok=True)
        now = strftime("%Y%m%d_%H%M%S", localtime(time()))
        today_prefix = now[:8]
        files = sorted(backup_path.glob("config_*.yaml"), reverse=True)

        # 检查今天是否已有备份
        if files and files[0].stem.startswith(f"config_{today_prefix}"):
            return

        backup_file = backup_path / f"config_{now}.yaml"
        self._atomic_yaml_write(backup_file, self.config.model_dump())

        # 保留最近10份
        all_files = sorted(backup_path.glob("config_*.yaml"))
        while len(all_files) > 10:
            try:
                all_files[0].unlink()
                all_files.pop(0)
            except Exception as e:
                log.error(f"删除旧备份文件 {all_files[0]} 失败: {e}")
                break

    def unsaved_del_key(self, key: str, *, config_obj: Optional[BaseModel | dict] = None) -> None:
        """仅删除配置项 不保存"""
        if self.config is None:
            self.just_load_config()
        if isinstance(config_obj, BaseModel):
            delattr(config_obj, key)
        elif isinstance(config_obj, dict):
            if key in config_obj:
                del config_obj[key]
        else:
            delattr(self.config, key)

    def del_key(self, key: str, *, config_obj: Optional[BaseModel | dict] = None) -> None:
        """删除配置项并保存"""
        self.unsaved_del_key(key, config_obj=config_obj)
        self._schedule_save()

    def __getitem__(self, key: str):
        """通过键名访问配置项的值"""
        if not hasattr(self.config, key):
            raise KeyError(f"配置项 '{key}' 不存在")
        return self.get_value(key)

    def __setitem__(self, key: str, value: Any):
        """通过键名设置配置项的值

        **注意该方法不请求保存**"""
        self.unsaved_set_value(key, value)

    def __getattr__(self, name):
        """允许通过属性访问配置项的值"""
        if hasattr(self.config, name):
            return self.get_value(name)
        raise AttributeError(f"'{type(self).__name__}' 对象没有属性 ‘{name}'")


def migrate_legacy_team_setting_data(data: dict) -> dict:
    """Normalize legacy and newer starlight fields into a shared runtime shape."""
    migrated = dict(data)
    runtime_bonus = _normalize_runtime_opening_bonus(migrated)
    if runtime_bonus is None:
        return migrated

    migrated["opening_bonus"] = runtime_bonus
    migrated.update(project_starlight_bonus_legacy_fields(runtime_bonus, migrated.get("opening_bonus_order")))
    return migrated


DEFAULT_OPENING_BONUS = [1, 1, 1, 1, 0, 0, 0, 0, 0, 0]


def _normalize_starlight_int_list(values: Any, *, max_value: int) -> list[int] | None:
    if not isinstance(values, list):
        return None

    normalized: list[int] = []
    for value in values[:10]:
        try:
            normalized.append(max(0, min(max_value, int(value or 0))))
        except (TypeError, ValueError):
            normalized.append(0)

    if len(normalized) < 10:
        normalized.extend([0] * (10 - len(normalized)))
    return normalized


def _normalize_runtime_opening_bonus(data: dict) -> list[int] | None:
    raw_bonus = _normalize_starlight_int_list(data.get("opening_bonus"), max_value=3)
    legacy_levels = _normalize_starlight_int_list(data.get("opening_bonus_level"), max_value=2) or [0] * 10
    legacy_order = _normalize_starlight_int_list(data.get("opening_bonus_order"), max_value=10) or [0] * 10
    choose_opening_bonus = bool(data.get("choose_opening_bonus", False))

    if raw_bonus is None:
        if not choose_opening_bonus and not any(legacy_levels) and not any(legacy_order):
            return None
        raw_bonus = [0] * 10

    if any(value not in (0, 1) for value in raw_bonus):
        return raw_bonus

    if choose_opening_bonus or any(legacy_levels) or any(legacy_order):
        runtime_bonus = [0] * 10
        for index, selected in enumerate(raw_bonus):
            if selected > 0:
                runtime_bonus[index] = min(3, 1 + legacy_levels[index])
        return runtime_bonus

    if raw_bonus == [0] * 10 or raw_bonus == DEFAULT_OPENING_BONUS:
        return DEFAULT_OPENING_BONUS.copy()
    return raw_bonus


def project_starlight_bonus_legacy_fields(runtime_bonus: list[int], existing_order: Any = None) -> dict:
    normalized_bonus = _normalize_starlight_int_list(runtime_bonus, max_value=3) or DEFAULT_OPENING_BONUS.copy()
    selected_indices = [index for index, value in enumerate(normalized_bonus) if value > 0]

    if normalized_bonus == DEFAULT_OPENING_BONUS:
        return {
            "choose_opening_bonus": False,
            "opening_bonus_select": 0,
            "opening_bonus_order": [0] * 10,
            "opening_bonus_level": [0] * 10,
        }

    normalized_order = _normalize_starlight_int_list(existing_order, max_value=10) or [0] * 10
    ordered_pairs = [(normalized_order[index], index) for index in selected_indices if normalized_order[index] > 0]
    ordered_indices = [index for _, index in sorted(ordered_pairs)]
    ordered_indices.extend(index for index in selected_indices if index not in ordered_indices)

    opening_bonus_order = [0] * 10
    for order, index in enumerate(ordered_indices, start=1):
        opening_bonus_order[index] = order

    return {
        "choose_opening_bonus": True,
        "opening_bonus_select": len(selected_indices),
        "opening_bonus_order": opening_bonus_order,
        "opening_bonus_level": [max(value - 1, 0) if value > 0 else 0 for value in normalized_bonus],
    }


def sync_team_setting_starlight_fields(team_setting: TeamSetting) -> None:
    normalized_bonus = _normalize_starlight_int_list(team_setting.opening_bonus, max_value=3) or DEFAULT_OPENING_BONUS.copy()
    team_setting.opening_bonus = normalized_bonus
    for key, value in project_starlight_bonus_legacy_fields(normalized_bonus, team_setting.opening_bonus_order).items():
        setattr(team_setting, key, value)


class Theme_pack_list(metaclass=SingletonMeta):
    def __init__(self, example_path, theme_pack_list_path, theme_pack_weight_path):
        self.yaml = YAML()
        # 读取默认配置作为同步模板
        default_config = self._load_default_config(example_path)
        # 获取用户的配置文件路径
        self.theme_pack_list_path = theme_pack_list_path
        self.theme_pack_weight_path = Path(theme_pack_weight_path)
        # 先同步全局和队伍配置文件，再从全局配置文件加载 self.config
        self._sync_team_weight_configs(default_config)
        loaded_config = self.load_config(self.theme_pack_list_path)
        self.config = copy.deepcopy(loaded_config) if loaded_config else copy.deepcopy(default_config)

    def build_setting_key(self, hard_switch: bool, language: str | None) -> list[str]:
        """构建配置项键名列表。开启困难模式时同时返回普通和困难键。"""
        suffix = "_cn" if language == "zh_cn" else ""
        normal_key = f"theme_pack_list{suffix}"
        hard_key = f"theme_pack_list_hard{suffix}"
        if hard_switch:
            return [normal_key, hard_key]
        return [normal_key]

    def build_team_weight_path(self, team_num: int) -> str:
        """构建特定队伍的权重配置文件路径"""
        return str(Path(self.theme_pack_weight_path) / f"theme_pack_weight_team_{team_num}.yaml")

    def delete_team_weight_config(self, team_num: int) -> None:
        """删除指定队伍的自定义主题包权重配置文件。"""
        if team_num < 1:
            return

        path = Path(self.build_team_weight_path(team_num))
        if path.exists():
            path.unlink()

    def set_team_weight_config_from_team(self, target_team_num: int, source_team_num: int) -> None:
        """将 source 队伍的自定义主题包权重配置写入到 target 队伍。"""
        if target_team_num < 1 or source_team_num < 1:
            return
        if target_team_num == source_team_num:
            return

        source_path = Path(self.build_team_weight_path(source_team_num))
        target_path = Path(self.build_team_weight_path(target_team_num))

        if not source_path.exists():
            return

        with open(source_path, "r", encoding="utf-8") as file:
            source_config = self.yaml.load(file) or {}
        self.save_config(path=str(target_path), config_data=source_config)

    def create_team_weight_config(self, team_num: int) -> None:
        """创建指定队伍的自定义主题包权重配置文件（若不存在）。"""
        if team_num < 1:
            return

        target_path = Path(self.build_team_weight_path(team_num))
        if target_path.exists():
            return

        self.save_config(path=str(target_path), config_data=copy.deepcopy(self.config))

    def _sync_team_weight_configs(self, default_config: dict) -> None:
        """初始化时同步全局与已存在的队伍主题包权重配置。"""
        global_loaded_config = self.load_config(self.theme_pack_list_path)
        if global_loaded_config is None:
            self.save_config(path=self.theme_pack_list_path, config_data=default_config)
            global_loaded_config = copy.deepcopy(default_config)

        if global_loaded_config:
            merged_global_config = copy.deepcopy(default_config)
            self._update_config(merged_global_config, global_loaded_config)
            if merged_global_config != global_loaded_config:
                self.save_config(path=self.theme_pack_list_path, config_data=merged_global_config)

        if not self.theme_pack_weight_path.exists():
            return

        for team_weight_path in sorted(
            self.theme_pack_weight_path.glob("theme_pack_weight_team_*.yaml"), key=lambda item: item.name
        ):
            loaded_config = self.load_config(str(team_weight_path))
            if not loaded_config:
                continue

            merged_config = copy.deepcopy(default_config)
            self._update_config(merged_config, loaded_config)
            if merged_config != loaded_config:
                self.save_config(path=str(team_weight_path), config_data=merged_config)

    def get_effective_theme_pack_list(
        self, hard_switch: bool, language: str | None, team_num: int, use_custom_theme_pack_weight: bool
    ) -> tuple[dict]:
        """获取当前生效的主题包名单，考虑难度、语言、队伍和是否启用自定义权重等因素"""
        setting_keys = self.build_setting_key(hard_switch, language)
        theme_pack_list = {}
        for key in setting_keys:
            theme_pack_list.update(self.config.get(key, {}))
        if not use_custom_theme_pack_weight:
            log.debug("未启用自定义权重，返回默认主题包名单")
            return theme_pack_list

        custom_path = self.build_team_weight_path(team_num)
        loaded_data = self.load_config(custom_path)
        if loaded_data is None:
            log.debug(f"自定义文件不存在或读取失败，回退默认配置。path={custom_path}")
            return theme_pack_list

        effective_list = {}
        for key in setting_keys:
            effective_list.update(loaded_data.get(key, self.config.get(key, {})))
        log.debug(f"已加载自定义权重。path={custom_path}, keys={setting_keys}, count={len(effective_list)}")
        return effective_list

    def _load_version(self, version_path: str) -> str:
        """加载版本信息"""
        try:
            with open(version_path, "r", encoding="utf-8") as file:
                return file.read().strip()
        except FileNotFoundError:
            sys.exit("主题包名单文件未找到")

    def _load_default_config(self, example_path: str) -> dict:
        """加载默认配置信息"""
        try:
            with open(example_path, "r", encoding="utf-8") as file:
                loaded = self.yaml.load(file)
                return loaded or {}
        except FileNotFoundError:
            log.error(f"默认主题包配置文件 {example_path} 未找到")
            return {}
        except Exception as e:
            log.error(f"默认主题包配置文件 {example_path} 加载失败: {e}")
            return {}

    def load_config(self, path: str):
        """纯加载函数：从 path 读取并返回配置内容"""
        try:
            with open(path, "r", encoding="utf-8") as file:
                loaded = self.yaml.load(file)
                return loaded or {}
        except FileNotFoundError:
            return None
        except Exception as e:
            log.error(f"配置文件{path}加载错误: {e}")
            return None

    def _update_config(self, config: dict, new_config: dict) -> None:
        """更新配置信息"""
        if config == new_config:
            return
        for key, value in new_config.items():
            if isinstance(value, dict):
                if key not in config:
                    config[key] = {}
                for k, v in value.items():
                    config[key][k] = v
            else:
                config[key] = value
        log.debug("主题包名单已更新")

    def save_config(self, path, config_data):
        """保存配置到指定路径，config_data是要保存的配置内容，path是保存路径"""
        config_data = self.config if config_data is None else config_data
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".yaml.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as file:
                self.yaml.dump(config_data, file)
            tmp.replace(dest)
        except BaseException:
            if tmp.exists():
                tmp.unlink()
            raise

    def get_value(self, key, default=None):
        """获取配置项的值，如果是可变对象，则返回其拷贝"""
        value = self.config.get(key, default)
        # 如果是可变对象，则返回其拷贝
        if isinstance(value, (list, dict, set)):
            return copy.deepcopy(value)  # 使用深拷贝确保嵌套对象安全
        return value

    def set_value(self, key, value) -> None:
        """设置配置项的值并保存"""
        if isinstance(value, (list, dict, set)):
            self.config[key] = copy.deepcopy(value)
        else:
            self.config[key] = value
        self.save_config(path=self.theme_pack_list_path, config_data=self.config)

    def __getitem__(self, key: str):
        """通过键名访问配置项的值"""
        return self.get_value(key)

    def __setitem__(self, key: str, value: Any):
        """通过键名设置配置项的值"""
        self.set_value(key, value)

    def __getattr__(self, attr: str):
        """允许通过属性访问配置项的值"""
        if attr in self.config:
            value = self.config[attr]
            if isinstance(value, (list, dict, set)):
                return copy.deepcopy(value)
            return value
        raise AttributeError(f"'{type(self).__name__}' 对象没有属性 ‘{attr}'")
