import json
import os
import time

from module.automation import TextMatchResult, auto
from module.config import cfg, theme_list
from module.logger import log
from utils.path_manager import path_manager

COLLECTED_PACKS_PATH = os.path.join("assets", "model", "collected_packs.json")
SCREENSHOT_DIR = os.path.join("assets", "model", "map")


def load_collected_packs():
    if not os.path.exists(COLLECTED_PACKS_PATH):
        return {}
    try:
        with open(COLLECTED_PACKS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"读取已收集卡包记录失败: {e}")
        return {}


def save_collected_packs(data):
    os.makedirs(os.path.dirname(COLLECTED_PACKS_PATH), exist_ok=True)
    with open(COLLECTED_PACKS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_collected_packs(floor):
    data = load_collected_packs()
    return data.get(str(floor), [])


def add_collected_pack(floor, pack_name):
    data = load_collected_packs()
    key = str(floor)
    if key not in data:
        data[key] = []
    if pack_name not in data[key]:
        data[key].append(pack_name)
        save_collected_packs(data)
        log.info(f"[资源收集] 第{floor + 1}层卡包 '{pack_name}' 已记录，共收集 {len(data[key])} 个")


def save_map_screenshot(floor, pack_name):
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    auto.take_screenshot(gray=False)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"f{floor + 1}_{pack_name}_{timestamp}.png"
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    auto.screenshot.save(filepath)
    auto.take_screenshot(gray=True)
    log.info(f"[资源收集] 地图截图已保存: {filepath}")
    return filepath


def _identify_all_packs(hard_switch, team_num, use_custom_theme_pack_weight):
    scale = cfg.set_win_size / 1080
    if path_manager.current_language == "zh_cn":
        theme_pack_list_zh = theme_list.get_effective_theme_pack_list(
            hard_switch, "zh_cn", team_num, use_custom_theme_pack_weight
        )
        theme_pack_list_en = {}
    elif path_manager.current_language == "en":
        theme_pack_list_zh = {}
        theme_pack_list_en = theme_list.get_effective_theme_pack_list(
            hard_switch, "en", team_num, use_custom_theme_pack_weight
        )
    else:
        theme_pack_list_zh = theme_list.get_effective_theme_pack_list(
            hard_switch, "zh_cn", team_num, use_custom_theme_pack_weight
        )
        theme_pack_list_en = theme_list.get_effective_theme_pack_list(
            hard_switch, "en", team_num, use_custom_theme_pack_weight
        )

    all_theme_pack = auto.find_element(
        "mirror/theme_pack/theme_pack_features.png",
        find_type="image_with_multiple_targets",
        take_screenshot=True,
    )
    if not all_theme_pack:
        return []

    packs = []
    for pack in all_theme_pack:
        top_left = (
            max(pack[0] - 210 * scale, 0),
            max(pack[1] - 60 * scale, 0),
        )
        bottom_right = (
            min(pack[0] + 60 * scale, cfg.set_win_size * 16 / 9),
            min(pack[1] + 390 * scale, cfg.set_win_size),
        )
        crop = (top_left[0], top_left[1], bottom_right[0], bottom_right[1])
        result = auto.find_language_text(theme_pack_list_zh, theme_pack_list_en, crop)
        if isinstance(result, TextMatchResult):
            packs.append({"name": result.text, "position": pack, "weight": result.value})
        else:
            packs.append({"name": "unknown", "position": pack, "weight": -5})

    return packs


def select_theme_pack_for_collection(
    floor, hard_switch, team_num, use_custom_theme_pack_weight, max_refresh=3
):
    collected = get_collected_packs(floor)
    log.info(f"[资源收集] 第{floor + 1}层已收集 {len(collected)} 个卡包: {collected}")

    auto.model = "clam"
    refresh_times = max_refresh

    while True:
        if auto.take_screenshot() is None:
            continue

        if auto.find_element("mirror/road_in_mir/legend_assets.png", take_screenshot=True):
            return None

        packs = _identify_all_packs(hard_switch, team_num, use_custom_theme_pack_weight)
        if not packs:
            log.warning("[资源收集] 未识别到任何卡包")
            return None

        uncollected = [p for p in packs if p["name"] not in collected]
        log.debug(
            f"[资源收集] 当前可见卡包: {[p['name'] for p in packs]}, "
            f"未收集: {[p['name'] for p in uncollected]}"
        )

        if uncollected:
            pack = uncollected[0]
            auto.mouse_drag_down(pack["position"][0], pack["position"][1])
            log.info(f"[资源收集] 选择未收集卡包: {pack['name']}")
            time.sleep(3)
            return pack["name"]

        if refresh_times > 0 and auto.click_element("mirror/theme_pack/refresh_assets.png"):
            refresh_times -= 1
            auto.mouse_to_blank()
            time.sleep(1)
            log.debug(f"[资源收集] 刷新卡包，剩余刷新次数: {refresh_times}")
            continue

        log.info(f"[资源收集] 第{floor + 1}层所有可见卡包均已收集且刷新已耗尽，进入正常流程")
        pack = packs[0]
        auto.mouse_drag_down(pack["position"][0], pack["position"][1])
        log.debug(f"[资源收集] 选择卡包进入正常流程: {pack['name']}")
        time.sleep(3)
        return None
