import re
from time import sleep

import cv2
import numpy as np

from module.automation import auto
from module.config import cfg
from module.decorator.decorator import begin_and_finish_time_log
from module.logger import log
from module.ocr import ocr
from tasks.base.retry import retry
from utils.image_utils import ImageUtils

PASS_TASKS_RIGHT_COLUMN_BBOX = (1180, 300, 1500, 1260)
PASS_ROW_ACTION_PADDING = (150, 18, 25, 18)
PASS_CLAIM_ORANGE_THRESHOLD = 0.12


def to_gray_image(image):
    if image is None or image.size == 0:
        return None
    if image.ndim == 2:
        return image
    if image.ndim == 3 and image.shape[2] == 1:
        return image[:, :, 0]
    if image.ndim == 3 and image.shape[2] > 3:
        image = image[:, :, :3]
    return cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)


def to_rgb_image(image):
    if image is None or image.size == 0:
        return None
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    if image.ndim == 3 and image.shape[2] == 1:
        return np.repeat(image, 3, axis=2)
    if image.ndim == 3 and image.shape[2] > 3:
        return image[:, :, :3]
    return image


def get_screenshot_scale(screenshot_shape):
    return screenshot_shape[0] / 1440


def get_scaled_bbox(bbox, screenshot_shape):
    scale = get_screenshot_scale(screenshot_shape)
    x1, y1, x2, y2 = bbox
    return (
        int(x1 * scale),
        int(y1 * scale),
        int(x2 * scale),
        int(y2 * scale),
    )


def get_pass_tasks_right_column_bbox(screenshot_shape):
    return get_scaled_bbox(PASS_TASKS_RIGHT_COLUMN_BBOX, screenshot_shape)


def build_pass_action_bbox(ratio_bbox, screenshot_shape):
    scale = get_screenshot_scale(screenshot_shape)
    left_pad, top_pad, right_pad, bottom_pad = PASS_ROW_ACTION_PADDING
    x1, y1, x2, y2 = ratio_bbox
    return (
        max(0, int(x1 - left_pad * scale)),
        max(0, int(y1 - top_pad * scale)),
        min(screenshot_shape[1], int(x2 + right_pad * scale)),
        min(screenshot_shape[0], int(y2 + bottom_pad * scale)),
    )


def get_bbox_center(bbox):
    return (int((bbox[0] + bbox[2]) / 2), int((bbox[1] + bbox[3]) / 2))


def orange_pixel_ratio(image):
    rgb_image = to_rgb_image(image)
    if rgb_image is None or rgb_image.size == 0:
        return 0.0
    hsv = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2HSV)
    orange_mask = (
        (hsv[:, :, 0] > 5)
        & (hsv[:, :, 0] < 35)
        & (hsv[:, :, 1] > 80)
        & (hsv[:, :, 2] > 120)
    )
    return float(np.mean(orange_mask))


def extract_pass_progress_entries(screenshot):
    x1, y1, x2, y2 = get_pass_tasks_right_column_bbox(screenshot.shape)
    progress_crop = screenshot[y1:y2, x1:x2]
    if progress_crop.size == 0:
        return []
    ratio_pattern = re.compile(r"(\d+)\s*/\s*(\d+)")
    for candidate in (to_rgb_image(progress_crop), to_gray_image(progress_crop)):
        if candidate is None:
            continue
        result = ocr.run(candidate)
        if not result.txts or result.boxes is None:
            continue
        boxes = result.boxes.tolist() if hasattr(result.boxes, "tolist") else result.boxes
        rows = []
        for text, box in zip(result.txts, boxes):
            if match := ratio_pattern.search(text):
                xs = [point[0] for point in box]
                ys = [point[1] for point in box]
                rows.append(
                    {
                        "bbox": (
                            int(min(xs) + x1),
                            int(min(ys) + y1),
                            int(max(xs) + x1),
                            int(max(ys) + y1),
                        ),
                        "progress_ratio": (int(match.group(1)), int(match.group(2))),
                    }
                )
        if rows:
            return sorted(rows, key=lambda item: item["bbox"][1])
    return []


def analyze_pass_reward_rows(screenshot, threshold=0.8):
    rows = []
    for entry in extract_pass_progress_entries(screenshot):
        ratio_bbox = entry["bbox"]
        progress_ratio = entry["progress_ratio"]
        action_bbox = build_pass_action_bbox(ratio_bbox, screenshot.shape)
        action_crop = screenshot[action_bbox[1] : action_bbox[3], action_bbox[0] : action_bbox[2]]
        orange_ratio = orange_pixel_ratio(action_crop)
        rows.append(
            {
                "coordinate": get_bbox_center(ratio_bbox),
                "progress_ratio": progress_ratio,
                "claim_bbox": action_bbox,
                "click_coordinate": get_bbox_center(action_bbox),
                "orange_ratio": orange_ratio,
                "claimable": bool(
                    progress_ratio
                    and progress_ratio[1] > 0
                    and progress_ratio[0] == progress_ratio[1]
                    and orange_ratio >= PASS_CLAIM_ORANGE_THRESHOLD
                ),
            }
        )
    return rows


def claim_visible_pass_coins():
    claimed = False
    for _ in range(2):
        if auto.take_screenshot(gray=False) is None:
            continue
        screenshot = np.array(auto.screenshot)
        rows = analyze_pass_reward_rows(screenshot)
        claimable_rows = [row for row in rows if row["claimable"]]
        if not claimable_rows:
            break
        for target_row in claimable_rows:
            current, total = target_row["progress_ratio"]
            log.debug(
                f"通行证任务进度识别：坐标{target_row['click_coordinate']} -> "
                f"{current}/{total}, orange={target_row['orange_ratio']:.3f}"
            )
            auto.mouse_click(*target_row["click_coordinate"])
            sleep(0.2)
            retry()
            claimed = True
            sleep(0.5)
    return claimed


def open_pass_mission_page():
    loop_count = 15
    auto.model = "clam"
    season_bbox = ImageUtils.get_bbox(ImageUtils.load_image("home/season_assets.png"))
    while True:
        if auto.take_screenshot() is None:
            continue
        if auto.click_element("pass/pass_missions_assets.png"):
            sleep(0.8)
            return True
        if loop_count >= 10:
            if auto.click_element("home/season_assets.png"):
                sleep(0.8)
                continue
        elif auto.find_text_element("season", season_bbox):
            auto.mouse_click(
                (season_bbox[0] + season_bbox[2]) / 2,
                (season_bbox[1] + season_bbox[3]) / 2,
            )
            sleep(0.8)
            continue
        auto.mouse_to_blank()
        loop_count -= 1
        if loop_count < 10:
            auto.model = "normal"
        if loop_count < 5:
            auto.model = "aggressive"
        if loop_count < 0:
            log.error("无法打开通行证任务界面")
            return False


@begin_and_finish_time_log(task_name="收取日常/周常", calculate_time=False)
def get_pass_prize():
    if not open_pass_mission_page():
        log.error("无法收取日常/周常")
        return
    claim_visible_pass_coins()
    auto.take_screenshot()
    auto.click_element("pass/weekly_assets.png")
    sleep(0.8)
    claim_visible_pass_coins()


@begin_and_finish_time_log(task_name="收取邮箱", calculate_time=False)
def get_mail_prize():
    loop_count = 15
    auto.model = "clam"
    while True:
        # 自动截图
        if auto.take_screenshot() is None:
            continue
        if auto.click_element("mail/get_mail_prize_confirm.png"):
            auto.click_element("mail/close_assets.png")
            break
        if auto.click_element("mail/claim_all_assets.png"):
            auto.click_element("mail/close_assets.png")
            break
        mail_clicked = auto.click_element("home/mail_assets.png")
        if not mail_clicked and cfg.language_in_game == "zh_cn":
            mail_clicked = auto.click_element("home/mail_cn_assets.png", model="normal")
        if mail_clicked:
            continue
        auto.mouse_to_blank()
        loop_count -= 1
        if loop_count < 20:
            auto.model = "normal"
        if loop_count < 10:
            auto.model = "aggressive"
        if loop_count < 0:
            log.error("无法收取邮箱")
            break
