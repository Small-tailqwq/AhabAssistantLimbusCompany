import unittest
from typing import Any, cast
from unittest.mock import patch

import tasks.mirror.mirror as mirror_module
from app.observe_ego_gift_selection import parse_observe_ego_gift_value
from module.config.config_typing import TeamSetting


class _ObserveGiftAuto:
    def __init__(self):
        self.model = None
        self.mouse_action_calls = []
        self.mouse_click_calls = []
        self.click_calls = []

    def find_element(self, target, *_, **__):
        if target == "mirror/road_to_mir/observe_ego_gift/observe_burn_assets.png":
            return (100, 200)
        if target == "mirror/road_to_mir/observe_ego_gift/Level_III.png":
            return (300, 400)
        return False

    def mouse_action_with_pos(self, coordinates, *_, **__):
        self.mouse_action_calls.append(coordinates)
        return True

    def mouse_click(self, x, y, *_, **__):
        self.mouse_click_calls.append((x, y))
        return True

    def mouse_drag(self, *_, **__):
        return True

    def find_language_text(self, zh_text, en_text, bbox=None, **__):
        if zh_text == "选择" and en_text == "select" and bbox == (10, 20, 110, 120):
            return True
        if zh_text == "拒绝" and en_text == "reject":
            return False
        return False

    def click_element(self, target, *_, **__):
        self.click_calls.append(target)
        return target == "mirror/shop/leave_shop_confirm_assets.png"


class TestObserveEgoGiftSupport(unittest.TestCase):
    def test_parse_legacy_observe_ego_gift_value(self):
        selection = parse_observe_ego_gift_value("burn_gift_3_9.png")

        self.assertIsNotNone(selection)
        self.assertEqual(selection.system, "burn")
        self.assertEqual(selection.level, 3)
        self.assertEqual(selection.row, 2)
        self.assertEqual(selection.col, 1)

    def test_team_setting_normalizes_legacy_observe_ego_gift_selection(self):
        team_setting = TeamSetting(observe_ego_gift_selected=["burn_gift_3_9.png", "general_gift_1_1.png", "bad"])

        self.assertEqual(team_setting.observe_ego_gift_selected, ["burn_3_2_1", "general_1_1_1"])

    def test_select_observe_ego_gift_supports_legacy_selection_and_safe_clicks(self):
        auto = _ObserveGiftAuto()
        mirror = cast(Any, mirror_module.Mirror.__new__(mirror_module.Mirror))
        mirror.observe_ego_gift_selected = ["burn_gift_3_9.png"]

        cfg_stub = type("CfgStub", (), {"set_win_size": 1440, "mouse_action_interval": 0})()

        def fake_get_bbox(asset):
            if asset.endswith("gift_box_bbox.png"):
                return (0, 0, 1000, 1000)
            return (10, 20, 110, 120)

        with (
            patch.object(mirror_module, "auto", auto),
            patch.object(mirror_module, "cfg", cfg_stub),
            patch.object(mirror_module.ImageUtils, "load_image", side_effect=lambda asset: asset),
            patch.object(mirror_module.ImageUtils, "get_bbox", side_effect=fake_get_bbox),
            patch.object(mirror_module, "sleep", return_value=None),
        ):
            mirror.select_observe_ego_gift()

        self.assertEqual(
            auto.mouse_action_calls,
            [
                (210.0, 200),
                (100.0, 200),
                (300.0, 640.0),
                (60.0, 70.0),
            ],
        )
        self.assertEqual(auto.mouse_click_calls, [])


if __name__ == "__main__":
    unittest.main()
