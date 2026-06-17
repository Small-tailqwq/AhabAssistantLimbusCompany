from time import sleep

from module.automation import auto
from module.config import cfg
from module.decorator.decorator import begin_and_finish_time_log
from module.logger import log
from module.my_error.my_error import backMainWinError, userStopError
from tasks.base.back_init_menu import back_init_menu
from tasks.base.retry import retry
from tasks.battle import battle
from tasks.event import event_handling
from tasks.mirror.reward_card import get_reward_card


class MainStory:
    LOOP_COUNT = 250

    def __init__(self, choice_event_handling=True):
        self.choice_event_handling = choice_event_handling

    @begin_and_finish_time_log(task_name="主线关卡")
    def run(self):
        main_loop_count = self.LOOP_COUNT
        back_menu_count = 0

        try:
            while True:
                auto.ensure_not_stopped()
                if auto.take_screenshot() is None:
                    continue
                retry()

                if main_loop_count >= 50:
                    auto.model = "clam"

                # 剧情跳过（复用 back_init_menu 已有逻辑）
                if auto.click_element("scenes/story_skip_confirm_assets.png"):
                    continue
                if auto.click_element("scenes/story_skip_assets.png"):
                    continue
                if auto.click_element("scenes/story_meun_assets.png"):
                    continue

                # 地图寻路：主线没有 legend，用巴士检测代替
                if auto.find_element("mirror/mybus_default_distance.png") and not auto.find_element(
                    "mirror/road_in_mir/enter_assets.png"
                ):
                    self._navigate_main_story()
                    continue

                # 进入节点确认
                if auto.click_element("mirror/road_in_mir/enter_assets.png"):
                    continue

                # 进入战斗准备（点击"开始作战"按钮）
                if auto.click_element("battle/normal_to_battle_assets.png"):
                    continue
                if auto.click_element("battle/chaim_to_battle_assets.png"):
                    continue

                # 战斗中
                if (
                    auto.find_element("battle/turn_assets.png")
                    or auto.find_element("battle/in_mirror_assets.png")
                    or auto.find_element("battle/more_information_assets.png")
                ):
                    battle.fight(choice_event_handling=self.choice_event_handling)
                    continue

                # 事件处理：与非主线路径一致
                if (
                    self.choice_event_handling
                    and auto.find_element("event/choices_assets.png")
                    and auto.find_element("event/select_first_option_assets.png")
                ):
                    auto.click_element("event/select_first_option_assets.png")
                    continue
                if self.choice_event_handling and auto.find_element("event/perform_the_check_feature_assets.png"):
                    event_handling.decision_event_handling()
                    continue
                if self.choice_event_handling:
                    if auto.click_element("event/continue_assets.png"):
                        continue
                    if auto.click_element("event/proceed_assets.png"):
                        continue
                    if auto.click_element("event/commence_assets.png"):
                        continue
                    if auto.click_element("event/skip_assets.png", times=6):
                        continue

                # 奖励卡选择
                if auto.find_element("mirror/road_in_mir/select_encounter_reward_card_assets.png"):
                    get_reward_card()
                    continue

                # EGO 饰品获取
                if auto.click_element("mirror/road_in_mir/ego_gift_get_confirm_assets.png"):
                    continue

                # 等待加载
                if auto.find_element("base/waiting_assets.png") or auto.find_element("base/waiting_2_assets.png"):
                    continue

                # 战斗结算确认
                if auto.click_element("battle/battle_finish_confirm_assets.png"):
                    continue

                # 后退按钮
                if auto.click_element("home/back_assets.png"):
                    continue

                # 回到主界面（驱动盘/窗口），视为完成
                if auto.click_element("home/drive_assets.png") or auto.find_element("home/window_assets.png"):
                    log.info("主线关卡已完成")
                    break

                # 防卡死
                auto.mouse_click_blank()
                retry()
                main_loop_count -= 1
                if main_loop_count < 75:
                    auto.model = "normal"
                if main_loop_count < 15:
                    auto.model = "aggressive"
                if main_loop_count < 0:
                    if back_menu_count > 5:
                        raise backMainWinError("主线关卡道中出错，请手动操作重试")
                    log.error("主线关卡识别失败次数达到最大值，正在返回主界面")
                    back_init_menu()
                    back_menu_count += 1
                    main_loop_count = self.LOOP_COUNT

        except userStopError:
            log.info("用户主动终止主线关卡")
            return

        return True

    def _navigate_main_story(self):
        """主线地图寻路：以固定间距向右点击节点，依靠 enter_assets 反馈确认。

        根据截图分析，mini 镜牢节点呈网格排列：
        - 水平列间距 ~800px（1440 高度基准）
        - 上下两行间距 ~380px
        优先点击最右侧节点，从右向左扫描。
        """
        scale = cfg.set_win_size / 1440
        bus_position = None
        for _ in range(3):
            if bus_position := auto.find_element(
                "mirror/mybus_default_distance.png",
                take_screenshot=True,
            ):
                break
            if retry() is False:
                return False

        if bus_position is None:
            return self._scan_for_node_fallback(scale)

        base_x, base_y = bus_position
        # 水平列间距 800px，垂直行间距 380px（1440 基准）
        # 从最右侧开始扫描（优先最右），逐列向左
        x_offsets = [800, 1600]
        y_offsets = [0, 380]

        pairs = [(dx, dy) for dy in y_offsets for dx in x_offsets]
        pairs.sort(key=lambda p: p[0], reverse=True)

        for dx, dy in pairs:
            target_x = base_x + dx * scale
            target_y = base_y + dy * scale
            if not (0 < target_x < cfg.set_win_size * 16 / 9 and 0 < target_y < cfg.set_win_size):
                continue
            auto.mouse_click(target_x, target_y)
            sleep(1.0)
            if auto.click_element("mirror/road_in_mir/enter_assets.png", take_screenshot=True):
                log.debug(f"主线寻路点击成功: dx={dx}, dy={dy}")
                return True

        log.debug("固定间距扫描未找到节点，尝试全屏扫描")
        return self._scan_for_node_fallback(scale)

    def _scan_for_node_fallback(self, scale):
        """巴士不可见时的兜底扫描：在屏幕右侧中上部按网格点击。"""
        screen_w = cfg.set_win_size * 16 / 9
        screen_h = cfg.set_win_size
        center_y = screen_h * 0.45
        y_offsets = [-150, -50, 50, 150, 250]
        x_positions = [screen_w * 0.3, screen_w * 0.45, screen_w * 0.6, screen_w * 0.75, screen_w * 0.85]

        for x in x_positions:
            for dy in y_offsets:
                target_x = x
                target_y = center_y + dy * scale
                if not (0 < target_y < screen_h):
                    continue
                auto.mouse_click(target_x, target_y)
                sleep(1.0)
                if auto.click_element("mirror/road_in_mir/enter_assets.png", take_screenshot=True):
                    log.debug(f"主线兜底扫描点击成功: x={target_x:.0f}, y={target_y:.0f}")
                    return True
        return False
