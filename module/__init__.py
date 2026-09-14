from pathlib import Path

from module.instance_context import get_instance_context

VERSION_PATH = "./assets/config/version.txt"
EXAMPLE_PATH = "./assets/config/config.example.yaml"
THEME_PACK_LIST_EXAMPLE_PATH = "./assets/config/theme_pack_list.example.yaml"

_instance_context = get_instance_context()
_runtime_root = _instance_context.profile_dir if _instance_context.is_child_session else Path(".")

CONFIG_PATH = str(_runtime_root / "config.yaml")
CONFIG_BACKUP_PATH = str(_runtime_root / "config_backup")
THEME_PACK_LIST_PATH = str(_runtime_root / "theme_pack_list.yaml")
THEME_PACK_WEIGHT_PATH = str(_runtime_root / "theme_pack_weight")
LOG_DIR = str(_runtime_root / "logs")
