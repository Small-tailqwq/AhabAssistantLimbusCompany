import unittest
from typing import Any, cast
from unittest.mock import patch

import tasks.mirror.mirror as mirror_module


class _DriveScreenAuto:
    def __init__(self):
        self.model = None
        self.iteration = 0
        self.clicked = []

    def take_screenshot(self):
        self.iteration += 1
        return object()

    def mouse_to_blank(self):
        return None

    def find_text_element(self, *_args, **_kwargs):
        return True

    def find_element(self, target, *_, threshold=0.8, **__):
        if target == "home/mirror_dungeons_assets.png":
            return self.iteration == 1 and threshold <= 0.68
        if target == "home/inferno_bus_assets.png":
            return self.iteration == 1
        if target == "mirror/road_to_mir/select_team_stars_assets.png":
            return self.iteration >= 2
        return False

    def click_element(self, target, *_, threshold=0.8, **__):
        if target == "home/mirror_dungeons_assets.png":
            if self.find_element(target, threshold=threshold):
                self.clicked.append(target)
                return True
            return False
        if target == "home/window_assets.png":
            self.clicked.append(target)
            return True
        return False


class _StopAfterCommence(Exception):
    pass


class _EventPriorityAuto:
    def __init__(self):
        self.model = None
        self.clicked = []

    def take_screenshot(self):
        return object()

    def find_element(self, target, *_, **__):
        return {
            "battle/turn_assets.png": False,
            "mirror/road_in_mir/legend_assets.png": False,
            "event/select_to_gain_ego.png": False,
            "event/choices_assets.png": False,
            "event/perform_the_check_feature_assets.png": True,
            "event/continue_assets.png": False,
            "event/proceed_assets.png": False,
            "event/commence_assets.png": True,
            "event/commence_battle_assets.png": False,
        }.get(target, False)

    def click_element(self, target, *_, **__):
        self.clicked.append(target)
        if target == "event/commence_assets.png":
            raise _StopAfterCommence
        return False


class _EventProgressTextAuto:
    def __init__(self):
        self.model = None
        self.clicked = []

    def take_screenshot(self):
        return object()

    def find_element(self, target, *_, **__):
        return {
            "battle/turn_assets.png": False,
            "mirror/road_in_mir/legend_assets.png": False,
            "event/unknown_event.png": False,
            "event/select_to_gain_ego.png": False,
            "event/choices_assets.png": False,
            "event/perform_the_check_feature_assets.png": True,
            "event/continue_assets.png": False,
            "event/proceed_assets.png": False,
            "event/commence_assets.png": False,
            "event/commence_battle_assets.png": False,
        }.get(target, False)

    def click_element(self, target, *_, **__):
        self.clicked.append(("image", target))
        return False

    def find_language_text(self, zh_text, en_text, my_crop=None, **__):
        if my_crop and zh_text == ["继续", "开始", "开始战斗"] and en_text == ["continue", "proceed", "commence"]:
            return [my_crop[0] + 1, my_crop[1] + 1]
        return False

    def mouse_click(self, x, y, *_, **__):
        self.clicked.append(("ocr", x, y))
        raise _StopAfterCommence


class _MirrorShopExitAuto:
    def __init__(self, legend_visible):
        self.legend_visible = legend_visible

    def take_screenshot(self):
        return object()

    def find_element(self, target, *_, **__):
        if target == "mirror/road_in_mir/legend_assets.png":
            return self.legend_visible
        return False


class _StarlightSelectionAuto:
    def __init__(self):
        self.iteration = 0
        self.model = None
        self.mouse_action_calls = []
        self.mouse_click_calls = []

    def find_element(self, target, *_, **__):
        if target == "mirror/road_to_mir/dreaming_star/coins_assets.png":
            return (2000, 400)
        if target == "mirror/road_to_mir/bleed_gift_assets.png":
            return self.iteration >= 2
        if target == "mirror/road_to_mir/dreaming_star/select_star_confirm_assets.png":
            return False
        return False

    def click_element(self, target, *_, **__):
        if target == "mirror/road_to_mir/dreaming_star/dreaming_star_enter_assets.png":
            return self.iteration == 1
        return False

    def mouse_action_with_pos(self, coordinates, *_, **__):
        self.mouse_action_calls.append(coordinates)
        return True

    def mouse_click(self, x, y, *_, **__):
        self.mouse_click_calls.append((x, y))
        return True

    def mouse_to_blank(self, *_, **__):
        return None

    def take_screenshot(self):
        self.iteration += 1
        return object()


class _ShopStub:
    def __init__(self, result):
        self.result = result
        self.called_with_floor = None

    def in_shop(self, floor):
        self.called_with_floor = floor
        return self.result


class _MirrorMapStub:
    def __init__(self):
        self.cache_calls = 0

    def cache_post_shop_boss_route(self):
        self.cache_calls += 1


class TestMirrorNavigation(unittest.TestCase):
    def test_road_to_mir_clicks_low_confidence_mirror_dungeons_before_window_fallback(self):
        auto = _DriveScreenAuto()
        mirror = mirror_module.Mirror.__new__(mirror_module.Mirror)

        with (
            patch.object(mirror_module, "auto", auto),
            patch.object(mirror_module, "retry", return_value=True),
            patch.object(mirror_module.ImageUtils, "load_image", return_value=object()),
            patch.object(mirror_module.ImageUtils, "get_bbox", return_value=(0, 0, 10, 10)),
            patch.object(mirror_module, "sleep", return_value=None),
        ):
            mirror.road_to_mir()

        self.assertIn("home/mirror_dungeons_assets.png", auto.clicked)
        self.assertNotIn("home/window_assets.png", auto.clicked)

    def test_event_handling_prioritizes_commence_over_repeating_decision_selection(self):
        auto = _EventPriorityAuto()
        mirror = mirror_module.Mirror.__new__(mirror_module.Mirror)

        with (
            patch.object(mirror_module, "auto", auto),
            patch.object(mirror_module, "retry", return_value=True),
            patch.object(mirror_module, "sleep", return_value=None),
            patch.object(mirror_module.event_handling, "decision_event_handling", side_effect=AssertionError),
            patch.object(mirror, "wake_event_after_progress", return_value=True),self.assertRaises(_StopAfterCommence)
        ):
            mirror.event_handling()

        self.assertIn("event/commence_assets.png", auto.clicked)

    def test_event_handling_uses_progress_text_fallback_before_repeating_decision_selection(self):
        auto = _EventProgressTextAuto()
        mirror = mirror_module.Mirror.__new__(mirror_module.Mirror)

        with (
            patch.object(mirror_module, "auto", auto),
            patch.object(mirror_module, "retry", return_value=True),
            patch.object(mirror_module, "sleep", return_value=None),
            patch.object(mirror_module.ImageUtils, "load_image", return_value=object()),
            patch.object(mirror_module.ImageUtils, "get_bbox", return_value=(10, 20, 110, 120)),
            patch.object(mirror_module.event_handling, "decision_event_handling", side_effect=AssertionError),
            patch.object(mirror, "wake_event_after_progress", return_value=True),self.assertRaises(_StopAfterCommence)
        ):
            mirror.event_handling()

        self.assertIn(("ocr", 60, 70), auto.clicked)

    def test_in_shop_writes_post_shop_cache_when_shop_exits_successfully(self):
        mirror = cast(Any, mirror_module.Mirror.__new__(mirror_module.Mirror))
        shop_stub = _ShopStub(result=True)
        map_stub = _MirrorMapStub()
        mirror.floor = 5
        mirror.shop = shop_stub
        mirror.mirror_map = map_stub

        with patch.object(mirror_module, "auto", _MirrorShopExitAuto(legend_visible=False)):
            mirror.in_shop()

        self.assertEqual(shop_stub.called_with_floor, 5)
        self.assertEqual(map_stub.cache_calls, 1)

    def test_in_shop_skips_post_shop_cache_when_shop_exit_failed(self):
        mirror = cast(Any, mirror_module.Mirror.__new__(mirror_module.Mirror))
        shop_stub = _ShopStub(result=False)
        map_stub = _MirrorMapStub()
        mirror.floor = 4
        mirror.shop = shop_stub
        mirror.mirror_map = map_stub

        with patch.object(mirror_module, "auto", _MirrorShopExitAuto(legend_visible=True)):
            mirror.in_shop()

        self.assertEqual(shop_stub.called_with_floor, 4)
        self.assertEqual(map_stub.cache_calls, 0)

    def test_enter_mir_with_star_uses_mouse_action_for_starlight_clicks(self):
        auto = _StarlightSelectionAuto()
        mirror = cast(Any, mirror_module.Mirror.__new__(mirror_module.Mirror))
        mirror.use_starlight = True
        mirror.opening_bonus = [1, 1, 1, 1, 0, 0, 0, 0, 0, 0]
        mirror.opening_bonus_order = [0] * 10

        cfg_stub = type("CfgStub", (), {"set_win_size": 1440, "mouse_action_interval": 0})()

        with (
            patch.object(mirror_module, "auto", auto),
            patch.object(mirror_module, "cfg", cfg_stub),
            patch.object(mirror_module, "sleep", return_value=None),
        ):
            mirror.enter_mir_with_star()

        self.assertEqual(
            auto.mouse_action_calls,
            [
                (200.0, 700.0),
                (600.0, 700.0),
                (1000.0, 700.0),
                (1400.0, 700.0),
            ],
        )
        self.assertEqual(auto.mouse_click_calls, [])


if __name__ == "__main__":
    unittest.main()
