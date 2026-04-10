from time import sleep
import numpy as np

from module.automation import auto
from module.config import cfg
from module.decorator.decorator import begin_and_finish_time_log
from module.logger import log
from utils.image_utils import ImageUtils


def find_color_image_element(target, threshold=0.9):
    use_1440_base = ImageUtils.should_use_low_res_match_optimization()
    template = ImageUtils.load_image(target, resize=not use_1440_base, gray=False)
    if template is None:
        return None
    bbox = ImageUtils.get_bbox(template)
    template_crop = ImageUtils.crop(template, bbox)
    if auto.take_screenshot(gray=False) is None:
        return None
    screenshot = np.array(auto.screenshot)
    scale_to_1440 = 1.0
    if use_1440_base:
        screenshot, scale_to_1440 = ImageUtils.normalize_screenshot_for_1440_matching(screenshot)
    center, match_val = ImageUtils.match_template(screenshot, template_crop, bbox, "clam")
    if use_1440_base and center:
        center = ImageUtils.restore_coordinates_from_1440_matching(center, scale_to_1440)
        log.debug(f"{target} 1440基准彩色匹配：相似度{match_val:.2f}, 目标位置：{center}")
    else:
        log.debug(f"{target} 彩色匹配：相似度{match_val:.2f}, 目标位置：{center}")
    if isinstance(match_val, (int, float)) and match_val >= threshold:
        return center
    return None


def handle_disabled_module_exchange(cancel, close_when_disabled=True):
    log.debug("脑啡肽模块兑换按钮当前为灰态，本轮不执行兑换")
    if cancel and close_when_disabled:
        if auto.take_screenshot() is None:
            return False
        auto.click_element("enkephalin/enkephalin_cancel_assets.png")
    return False


def get_the_timing(return_time=False):
    if module_position := auto.find_element("enkephalin/lunacy_assets.png", take_screenshot=True):
        my_scale = cfg.set_win_size / 1440
        bbox = (
            module_position[0] - 200 * my_scale,
            module_position[1] + 150 * my_scale,
            module_position[0] + 600 * my_scale,
            module_position[1] + 220 * my_scale,
        )
        ocr_result = auto.find_text_element(None, my_crop=bbox, only_text=True)
        s = ""
        if ocr_result is not None:
            try:
                for ocr in ocr_result:
                    s += str(ocr)
                if ":" in s:
                    parts = s.split(":")
                    minute = int(parts[0][-2:])
                    seconds = int(parts[1][:2])
                    if return_time:
                        return minute * 60 + seconds
                    if minute >= 5 and seconds >= 20:
                        log.debug(f"生成下一点体力的时间为{minute}分{seconds}秒，符合葛朗台模式操作")
                        return True
            except Exception:
                return False
        return False


def get_current_enkephalin():
    import cv2
    import numpy as np

    from module.ocr import ocr
    from utils.image_utils import ImageUtils

    enkephalin_bbox = ImageUtils.get_bbox(ImageUtils.load_image("enkephalin/enkephalin_now_bbox.png"))
    for _ in range(5):
        try:
            while auto.take_screenshot() is None:
                continue
            sc = ImageUtils.crop(np.array(auto.screenshot), enkephalin_bbox)
            _, binary_image = cv2.threshold(sc, 110, 255, cv2.THRESH_BINARY)
            result = ocr.run(binary_image)
            ocr_result = [result.txts[i] for i in range(len(result.txts))]
            ocr_result = "".join(ocr_result)
            ocr_result = ocr_result.lower()
            if "/" in ocr_result:
                ocr_result = ocr_result.split("/")
                current_enkephalin = int(ocr_result[0])
                return current_enkephalin
        except Exception:
            continue
    try:
        sc = ImageUtils.crop(np.array(auto.screenshot), enkephalin_bbox)
        _, binary_image = cv2.threshold(sc, 150, 255, cv2.THRESH_BINARY)
        result = ocr.run(binary_image)
        ocr_result = [result.txts[i] for i in range(len(result.txts))]
        ocr_result = "".join(ocr_result)
        current_enkephalin = int(ocr_result[0])
        return current_enkephalin
    except Exception:
        pass
    return None


@begin_and_finish_time_log(task_name="体力换饼", calculate_time=False)
def make_enkephalin_module(cancel=True, skip=True, close_when_disabled=True):
    """体力换饼的模块
    Args:
        cancel (bool): 是否点击取消按钮 (即关闭换体界面)
        skip (bool): 是否遵循设置跳过换体 (优先于cfg.skip_enkephalin)
    """
    if skip and cfg.skip_enkephalin:
        return
    import time

    start_time = time.time()
    last_log_time = None
    first_popup_warning = True

    while True:
        now_time = time.time()
        if 60 > now_time - start_time > 20 and int(now_time - start_time) % 10 == 0:
            if last_log_time is None or now_time - last_log_time > 5:
                msg = f"已尝试狂气换体超过{int(now_time - start_time)}秒，如果非电脑硬件配置不足，请确认是否执行了正确的语言配置"
                log.warning(msg)
                last_log_time = now_time
        if now_time - start_time > 60:
            from app import mediator

            if first_popup_warning and (last_log_time is None or now_time - last_log_time > 5):
                # only do it once
                first_popup_warning = False
                log.warning("已尝试狂气换体超过1分钟，脚本将停止运行，请先检查语言配置，或检查电脑配置是否支持")
                mediator.link_start.emit()
                message = "脚本卡死在狂气换体，请检查语言配置，或检查电脑配置是否支持"
                mediator.warning.emit(message)
        # 自动截图
        if auto.take_screenshot() is None:
            continue
        auto.mouse_to_blank()
        if auto.find_element("base/update_close_assets.png", model="clam") and auto.find_element(
            "home/drive_assets.png", model="normal"
        ):
            auto.click_element("base/update_close_assets.png")
            from tasks.base.back_init_menu import back_init_menu

            back_init_menu()
            start_time = time.time()
            continue
        if auto.find_element("base/renew_confirm_assets.png", model="clam") and auto.find_element(
            "home/drive_assets.png", model="normal"
        ):
            auto.click_element("base/renew_confirm_assets.png")
            from tasks.base.back_init_menu import back_init_menu

            back_init_menu()
            start_time = time.time()
            continue
        if auto.find_element("enkephalin/use_lunacy_assets.png") is None:
            if auto.click_element("home/enkephalin_box_assets.png", threshold=0.75):
                sleep(0.5)
            continue
        if all_in_position := find_color_image_element("enkephalin/all_in_assets.png"):
            auto.mouse_click(*all_in_position)
            sleep(0.2)
            if auto.take_screenshot() is None:
                continue
            auto.click_element("enkephalin/enkephalin_confirm_assets.png")
            if cancel:
                auto.click_element("enkephalin/enkephalin_cancel_assets.png")
            return True
        if find_color_image_element("enkephalin/all_in_disabled_assets.png"):
            return handle_disabled_module_exchange(cancel, close_when_disabled=close_when_disabled)
        if auto.take_screenshot() is None:
            continue
        log.debug("未识别到脑啡肽模块兑换按钮状态，等待界面稳定后重试")
        sleep(0.5)


@begin_and_finish_time_log(task_name="狂气换体", calculate_time=False)
def lunacy_to_enkephalin(times=0):
    make_enkephalin_module(cancel=False, skip=False, close_when_disabled=False)
    auto.click_element("enkephalin/use_lunacy_assets.png")
    sleep(0.5)
    Grandet = False
    while times > 0:
        auto.mouse_to_blank(move_back=False)
        # 自动截图
        if auto.take_screenshot() is None:
            continue
        if times > 0 and auto.find_element("enkephalin/lunacy_spend_26_assets.png"):
            # 葛朗台模式
            if cfg.Dr_Grandet_mode:
                while get_the_timing() is False:
                    if Grandet:
                        break
                    sleep(2)
                Grandet = True
            auto.click_element("enkephalin/enkephalin_confirm_assets.png")
            sleep(1)
            continue
        if times >= 2 and auto.find_element("enkephalin/lunacy_spend_52_assets.png"):
            if cfg.Dr_Grandet_mode:
                while get_the_timing() is False:
                    if Grandet:
                        break
                    sleep(2)
                    Grandet = True
            auto.click_element("enkephalin/enkephalin_confirm_assets.png")
            sleep(1)
            continue
        if times >= 3 and auto.find_element("enkephalin/lunacy_spend_78_assets.png"):
            if cfg.Dr_Grandet_mode:
                while get_the_timing() is False:
                    if Grandet:
                        break
                    sleep(2)
                    Grandet = True
            auto.click_element("enkephalin/enkephalin_confirm_assets.png")
            sleep(1)
            continue
        break
    current_enkephalin = get_current_enkephalin()
    auto.click_element("enkephalin/enkephalin_cancel_assets.png")
    if current_enkephalin is not None and current_enkephalin >= 20:
        make_enkephalin_module(skip=False)
    else:
        log.debug(f"狂气换体结束后当前体力为{current_enkephalin}，不足20，跳过补做脑啡肽模块")
