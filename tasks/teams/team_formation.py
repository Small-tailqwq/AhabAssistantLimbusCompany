import re
from time import sleep

import cv2
import numpy as np

from module.automation import auto
from module.config import cfg
from module.decorator.decorator import begin_and_finish_time_log
from module.logger import log
from module.ocr import ocr

LAST_BATTLE_TEAM_PAGE = None


def get_team_name_candidates(num):
    if cfg.language_in_game == "en":
        return [f"TEAMS #{num}", f"TEAMS#{num}", f"TFAMS#{num}"]
    return [f"编队#{num}", f"编队 # {num}", f"编队 {num}"]


def get_team_text_crop(position, scale):
    return (0, 0, int(position[0] + 130 * scale), int(position[1] + 600 * scale))


def extract_team_number(text):
    if not text:
        return None
    matches = re.findall(r"\d+", text)
    if not matches:
        return None
    return int(matches[-1])


def get_rgb_screenshot_array():
    screenshot = np.array(auto.screenshot)
    if screenshot.size == 0:
        return None
    if screenshot.ndim == 2:
        return cv2.cvtColor(screenshot, cv2.COLOR_GRAY2RGB)
    if screenshot.ndim == 3 and screenshot.shape[2] == 1:
        return np.repeat(screenshot, 3, axis=2)
    if screenshot.ndim == 3 and screenshot.shape[2] > 3:
        return screenshot[:, :, :3]
    return screenshot


def find_team_text_position(num, crop_bbox):
    screenshot = get_rgb_screenshot_array()
    if screenshot is None:
        return None
    x1, y1, x2, y2 = crop_bbox
    crop = screenshot[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    result = ocr.run(crop)
    if not result.txts or result.boxes is None:
        return None
    boxes = result.boxes.tolist() if hasattr(result.boxes, "tolist") else result.boxes
    for text, box in zip(result.txts, boxes):
        if extract_team_number(text) != num:
            continue
        center_x = int((box[0][0] + box[2][0]) / 2 + x1)
        center_y = int((box[0][1] + box[2][1]) / 2 + y1)
        return center_x, center_y
    return None


def get_selected_team_number(position, scale):
    screenshot = get_rgb_screenshot_array()
    if screenshot is None:
        return None
    selected_team_bbox = (
        max(0, int(position[0] - 150 * scale)),
        max(0, int(position[1] + 30 * scale)),
        int(position[0] + 150 * scale),
        int(position[1] + 620 * scale),
    )
    selected_team_area = screenshot[
        selected_team_bbox[1] : selected_team_bbox[3],
        selected_team_bbox[0] : selected_team_bbox[2],
    ]
    if selected_team_area.size == 0:
        return None
    hsv = cv2.cvtColor(selected_team_area, cv2.COLOR_RGB2HSV)
    highlight_mask = cv2.inRange(
        hsv,
        np.array([15, 180, 180], dtype=np.uint8),
        np.array([35, 255, 255], dtype=np.uint8),
    )
    contours, _ = cv2.findContours(highlight_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        aspect_ratio = w / max(h, 1)
        if area < 8000 * scale * scale or aspect_ratio < 2.5:
            continue
        candidates.append((area, x, y, w, h))
    if not candidates:
        return None
    _, x, y, w, h = max(candidates, key=lambda item: item[0])
    row_crop = selected_team_area[
        y + int(8 * scale) : y + h - int(8 * scale),
        x + int(20 * scale) : x + w - int(20 * scale),
    ]
    if row_crop.size == 0:
        return None
    result = ocr.run(row_crop)
    recognized_text = "".join(result.txts) if result.txts else ""
    return extract_team_number(recognized_text)


def click_team_in_current_view(num, position, scale):
    position_bbox = get_team_text_crop(position, scale)
    if target_position := find_team_text_position(num, position_bbox):
        auto.mouse_click(target_position[0], target_position[1])
        return True
    return False


def click_team_by_order(team_range, team_order, first_position, scale):
    y_offset = 0
    if team_range > 2:
        y_offset = 100 * scale
    auto.mouse_click(
        first_position[0],
        first_position[1] + y_offset + 75 * team_order * scale,
    )
    return True


def reset_battle_team_dropdown(position, scale):
    my_position = [position[0], position[1] + 150 * scale]
    for _ in range(3):
        auto.mouse_drag(my_position[0], my_position[1], dy=1333 * scale, drag_time=0.3)
    sleep(0.75)


def scroll_battle_team_dropdown(first_position, page_delta, scale):
    if page_delta == 0:
        return
    drag_distance = -385 * scale if page_delta > 0 else 385 * scale
    for _ in range(abs(page_delta)):
        auto.mouse_drag(
            first_position[0],
            first_position[1] + 375 * scale,
            dy=drag_distance,
            drag_time=1.5,
        )
        sleep(0.8)


# 清队
def clean_team():
    while True:
        # 自动截图
        if auto.take_screenshot() is None:
            continue
        if auto.click_element("teams/clear_selection_confirm_assets.png"):
            break
        if auto.click_element("teams/clear_selection_assets.png"):
            sleep(0.5)
            auto.take_screenshot()
            if auto.find_element("teams/clear_selection_confirm_assets.png") is None:
                break


@begin_and_finish_time_log(task_name="罪人编队")
# 编队
def team_formation(sinner_team):
    scale = cfg.set_win_size / 1440

    clean_team()
    while auto.take_screenshot() is None:
        continue
    if reset_team := auto.find_element("teams/identify_assets.png"):
        first_sinner = [reset_team[0] - 1800 * scale, reset_team[1] + 130 * scale]
    else:
        log.error("无法找到罪人编队的起始位置")
        return
    sleep(0.5)

    for i in range(1, 13):
        if i in sinner_team:
            sinner = sinner_team.index(i)
        else:
            return
        if sinner <= 5:
            auto.mouse_click(first_sinner[0] + 270 * sinner * scale, first_sinner[1])
        else:
            auto.mouse_click(
                first_sinner[0] + 270 * (sinner - 6) * scale,
                first_sinner[1] + 500 * scale,
            )
        sleep(cfg.mouse_action_interval)


@begin_and_finish_time_log(task_name="寻找队伍")
# 找队
def select_battle_team(num):
    global LAST_BATTLE_TEAM_PAGE
    scale = cfg.set_win_size / 1440
    find = False
    while auto.take_screenshot() is None:
        continue
    if auto.find_element("home/first_prompt_assets.png", model="clam") and auto.find_element(
        "home/back_assets.png", model="normal"
    ):
        auto.click_element("home/back_assets.png")
    if position := auto.find_element("battle/teams_assets.png", take_screenshot=True):
        auto.mouse_click(1, 1)
        first_position = [position[0], position[1] + 70 * scale]
        if cfg.select_team_by_order:
            team_range = (num - 1) // 5
            team_order = (num - 1) % 5

            if LAST_BATTLE_TEAM_PAGE is not None and abs(team_range - LAST_BATTLE_TEAM_PAGE) <= 1:
                scroll_battle_team_dropdown(first_position, team_range - LAST_BATTLE_TEAM_PAGE, scale)
            else:
                reset_battle_team_dropdown(position, scale)
                scroll_battle_team_dropdown(first_position, team_range, scale)
            click_team_by_order(team_range, team_order, first_position, scale)
            LAST_BATTLE_TEAM_PAGE = team_range
            sleep(1)
            return True
        else:
            current_team_num = get_selected_team_number(position, scale)
            if current_team_num == num:
                LAST_BATTLE_TEAM_PAGE = (num - 1) // 5
                log.info(f"当前已是目标队伍 # {num}，跳过重选")
                return True
            if click_team_in_current_view(num, position, scale):
                LAST_BATTLE_TEAM_PAGE = None
                sleep(1)
                return True
            reset_battle_team_dropdown(position, scale)
            for i in range(10):
                while auto.take_screenshot() is None:
                    continue
                if get_selected_team_number(position, scale) == num:
                    find = True
                    break
                if click_team_in_current_view(num, position, scale):
                    find = True
                    break
                auto.mouse_drag(
                    first_position[0],
                    first_position[1] + 375 * scale,
                    dy=-385 * scale,
                    drag_time=1.5,
                )
                sleep(1)
                while auto.take_screenshot() is None:
                    continue
            if find:
                LAST_BATTLE_TEAM_PAGE = None
                msg = f"成功找到队伍 # {num}"
                log.info(msg)
                sleep(1)
                return True
            else:
                LAST_BATTLE_TEAM_PAGE = None
                msg = f"找不到队伍 # {num}"
                log.info(msg)
                return False
    LAST_BATTLE_TEAM_PAGE = None
    return False


def deal_with_spills():
    import cv2
    import numpy as np

    from module.ocr import ocr
    from utils.image_utils import ImageUtils

    scale = cfg.set_win_size / 1440
    sinner_nums_bbox = ImageUtils.get_bbox(ImageUtils.load_image("battle/normal_to_battle_assets.png"))
    sinner_nums_bbox = (
        sinner_nums_bbox[0],
        sinner_nums_bbox[1] - 115 * scale,
        sinner_nums_bbox[2],
        sinner_nums_bbox[3] - 115 * scale,
    )
    sc = ImageUtils.crop(np.array(auto.screenshot), sinner_nums_bbox)
    sc = cv2.bitwise_not(sc)
    mask = cv2.inRange(sc, 220, 255)
    mask = cv2.bitwise_not(mask)
    background = np.zeros((300, 300), dtype=np.uint8)
    h, w = mask.shape[:2]
    y_off = (300 - h) // 2
    x_off = (300 - w) // 2
    background[y_off : y_off + h, x_off : x_off + w] = mask
    try:
        result = ocr.run(background)
        ocr_result = [result.txts[i] for i in range(len(result.txts))]
        ocr_result = "".join(ocr_result)
        log.debug(f"对于配队人数OCR得到：{ocr_result}")
        if "/" in ocr_result:
            result = ocr_result.split("/")
            result = [i.strip() for i in result]
            import re

            now = int(re.sub(r"\D", "", result[-2]))
            max = int(re.sub(r"\D", "", result[-1]))
            if now > max:
                all_selected = auto.find_element("teams/selected.png", find_type="image_with_multiple_targets")
                kernel = np.ones((3, 3), np.uint8)
                for selected in all_selected:
                    try:
                        order_bbox = (
                            selected[0] - 40 * scale,
                            selected[1] - 120 * scale,
                            selected[0] + 40 * scale,
                            selected[1] - 30 * scale,
                        )
                        sc2 = ImageUtils.crop(np.array(auto.screenshot), order_bbox)
                        background2 = np.zeros((300, 300), dtype=np.uint8)
                        h, w = sc2.shape[:2]
                        y_off = (300 - h) // 2
                        x_off = (300 - w) // 2
                        background2[y_off : y_off + h, x_off : x_off + w] = sc2
                        result = ocr.run(background2)
                        ocr_result = [result.txts[i] for i in range(len(result.txts))]
                        ocr_result = "".join(ocr_result)
                        if ocr_result == "G":
                            ocr_result = "6"
                        if int(ocr_result) == 1:
                            # 再腐蚀 3 次
                            background2 = cv2.erode(background2, kernel, iterations=3)
                            # 再膨胀 2 次
                            background2 = cv2.dilate(background2, kernel, iterations=2)
                            result = ocr.run(background2)
                            ocr_result = [result.txts[i] for i in range(len(result.txts))]
                            ocr_result = "".join(ocr_result)
                        if int(ocr_result) > max:
                            auto.mouse_click(selected[0], selected[1])
                    except Exception:
                        continue
    except Exception:
        pass


@begin_and_finish_time_log(task_name="检查队伍剩余战斗力")
def check_team():
    # 至少还有5人可以战斗
    sinner_nums = [f"{a}/{b}" for b in range(5, 10) for a in range(5, b + 1)]
    if auto.find_element(sinner_nums, find_type="text"):
        return True
    else:
        return False
