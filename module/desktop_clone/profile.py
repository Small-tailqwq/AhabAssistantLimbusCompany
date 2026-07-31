"""Create an isolated, non-persistent runtime profile for the child AALC."""

from __future__ import annotations

import copy
import os
import shutil
from pathlib import Path

from ruamel.yaml import YAML

from module.config import cfg, theme_list
from module.logger import log


def child_profile_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("无法取得 LOCALAPPDATA，不能创建桌面分身配置")
    return Path(local_app_data) / "AALC" / "desktop-clone"


def _atomic_yaml_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    yaml = YAML()
    with temporary.open("w", encoding="utf-8") as file:
        yaml.dump(data, file)
    temporary.replace(path)


def prepare_child_profile(refresh_config: bool = True) -> Path:
    """准备分身 profile。

    refresh_config=True 时用主配置重新生成分身 config.yaml（root 显式同步路径）；
    refresh_config=False 时保留分身内已有配置，仅在快照不存在时首次生成，
    避免重开分身把用户在分身 UI 里做的修改静默清掉。
    """
    profile = child_profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    log.info(
        "准备桌面分身 profile（refresh_config=%s）：%s",
        refresh_config,
        profile.resolve(),
    )

    config_path = profile / "config.yaml"
    if refresh_config or not config_path.is_file():
        runtime_config = copy.deepcopy(cfg.config.model_dump())
        runtime_config["after_completion_actions"] = [
            action
            for action in runtime_config.get("after_completion_actions", [])
            if action != "exit_aalc"
        ]
        # The snapshot already represents the user's resolved settings for this run.
        # Prevent Config.just_load_config() from clearing one-time completion actions.
        runtime_config["keep_after_completion"] = True
        runtime_config.update(
            {
                # Child Session 只运行桌面端前台自动化，不能递归创建分身。
                "desktop_clone_enabled": False,
                "simulator": False,
                "background_click": False,
                "win_input_type": "foreground",
                "lab_mouse_logitech": False,
                "lab_mouse_razer": False,
                "lab_screenshot_obs": False,
                "obs_password": "",
                "mirrorchyan_cdk": "",
                "minimize_to_tray": False,
                # Root 进程统一负责常驻入口和更新。
                "autostart": False,
                "autodaily": False,
                "autodaily2": False,
                "autodaily3": False,
                "autodaily4": False,
            }
        )
        _atomic_yaml_write(config_path, runtime_config)
    else:
        log.info(
            "保留分身内已有配置：%s；从主进程启动任务时会重新同步主配置",
            config_path,
        )
    _atomic_yaml_write(profile / "theme_pack_list.yaml", copy.deepcopy(theme_list.config))

    source_weights = Path(theme_list.theme_pack_weight_path)
    destination_weights = profile / "theme_pack_weight"
    if source_weights.is_dir():
        shutil.copytree(source_weights, destination_weights, dirs_exist_ok=True)
    else:
        log.warning(
            "主题权重目录不存在，分身将使用空权重：%s",
            source_weights,
        )
        destination_weights.mkdir(parents=True, exist_ok=True)

    (profile / "logs").mkdir(parents=True, exist_ok=True)
    (profile / "config_backup").mkdir(parents=True, exist_ok=True)
    return profile.resolve()


def apply_child_runtime_overrides() -> None:
    """Reapply non-persistent invariants after the child reloads its snapshot."""
    overrides = {
        "desktop_clone_enabled": False,
        "simulator": False,
        "background_click": False,
        "win_input_type": "foreground",
        "lab_mouse_logitech": False,
        "lab_mouse_razer": False,
        "lab_screenshot_obs": False,
        "obs_password": "",
        "mirrorchyan_cdk": "",
        "minimize_to_tray": False,
        "autostart": False,
        "autodaily": False,
        "autodaily2": False,
        "autodaily3": False,
        "autodaily4": False,
    }
    for key, value in overrides.items():
        cfg.unsaved_set_value(key, value)
