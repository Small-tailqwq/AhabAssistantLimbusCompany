import datetime
import re
from pathlib import Path

from ruamel.yaml import YAML

from module.config import cfg, theme_list
from module.logger import log


def generate_theme_pack_export_filename(team_num: int) -> str:
    """生成主题包权重导出文件名

    Args:
        team_num: 队伍编号

    Returns:
        格式为 theme_pack_weight_team_{remark_name}_{date}.yaml 的文件名
        如果没有备注名则为 theme_pack_weight_team_{team_num}_{date}.yaml
    """
    team_setting = cfg.config.teams.get(str(team_num))
    remark_name = team_setting.remark_name if team_setting else None

    date_str = datetime.date.today().isoformat()

    if remark_name:
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', remark_name)
        return f"theme_pack_weight_team_{safe_name}_{date_str}.yaml"
    else:
        return f"theme_pack_weight_team_{team_num}_{date_str}.yaml"


def export_theme_pack_weight(team_num: int, file_path: str) -> bool:
    """导出主题包权重到 YAML 文件

    Args:
        team_num: 队伍编号
        file_path: 导出主题包权重的路径

    Returns:
        成功返回 True，失败返回 False
    """
    try:
        theme_pack_weight_path = theme_list.build_team_weight_path(team_num)

        if not Path(theme_pack_weight_path).exists():
            log.error(f"队伍 {team_num} 的主题包权重文件未找到")
            return False

        yaml = YAML()
        with open(theme_pack_weight_path, 'r', encoding='utf-8') as f:
            theme_pack_data = yaml.load(f)

        if not theme_pack_data:
            log.error(f"队伍 {team_num} 的主题包权重文件为空")
            return False

        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(theme_pack_data, f)

        log.info(f"已导出队伍 {team_num} 的主题包权重到 {file_path}")
        return True
    except Exception as e:
        log.error(f"导出主题包权重失败: {e}")
        return False


def import_theme_pack_weight(file_path: str, team_num: int) -> bool:
    """从 YAML 文件导入主题包权重

    Args:
        file_path: 要导入的 YAML 文件路径
        team_num: 队伍编号（用于上下文）

    Returns:
        成功返回 True，失败返回 False
    """
    try:
        yaml = YAML()

        # 加载导入数据
        with open(file_path, 'r', encoding='utf-8') as f:
            import_data = yaml.load(f)

        if not import_data:
            log.warning(f"队伍 {team_num} 的导入文件为空")
            return True

        theme_pack_weight_path = theme_list.build_team_weight_path(team_num)
        target_path = Path(theme_pack_weight_path)

        if not isinstance(import_data, dict):
            log.error(f"队伍 {team_num} 的导入数据不是字典")
            return False

        # 确保父目录存在
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # 保存回 theme_pack_weight_team_{team_num}.yaml
        with open(theme_pack_weight_path, 'w', encoding='utf-8') as f:
            yaml.dump(import_data, f)

        log.info(f"已从 {file_path} 导入队伍 {team_num} 的主题包权重")
        return True
    except Exception as e:
        log.error(f"导入主题包权重失败: {e}")
        return False
