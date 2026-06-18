import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import tasks.daily.get_prize as get_prize_module


class TestGetPassPrize(unittest.TestCase):
    def test_find_pass_claim_all_click_coordinate_uses_scaled_ocr_bbox(self):
        screenshot = np.zeros((1440, 2560, 3), dtype=np.uint8)
        ocr_result = SimpleNamespace(
            txts=("Claim", "All"),
            boxes=np.array(
                [
                    [[120.0, 4.0], [304.0, 4.0], [304.0, 52.0], [120.0, 52.0]],
                    [[314.0, 6.0], [394.0, 6.0], [394.0, 46.0], [314.0, 46.0]],
                ]
            ),
        )

        with patch.object(get_prize_module.ocr, "run", return_value=ocr_result):
            coordinate = get_prize_module.find_pass_claim_all_click_coordinate(screenshot)

        claim_bbox = get_prize_module.get_pass_claim_all_bbox(screenshot.shape)
        expected_bbox = (
            claim_bbox[0] + 60,
            claim_bbox[1] + 2,
            claim_bbox[0] + 197,
            claim_bbox[1] + 26,
        )
        self.assertEqual(coordinate, get_prize_module.get_bbox_center(expected_bbox))

    def test_find_pass_claim_all_click_coordinate_returns_none_without_ocr(self):
        screenshot = np.zeros((1440, 2560, 3), dtype=np.uint8)
        ocr_result = SimpleNamespace(txts=None, boxes=None)

        with patch.object(get_prize_module.ocr, "run", return_value=ocr_result):
            coordinate = get_prize_module.find_pass_claim_all_click_coordinate(screenshot)

        self.assertIsNone(coordinate)

    def test_get_pass_prize_claims_daily_weekly_and_battle_pass_rewards(self):
        actions = []

        class AutoStub:
            def take_screenshot(self):
                actions.append("screenshot")
                return object()

            def click_element(self, target, *args, **kwargs):
                actions.append(f"click:{target}")
                return True

        def claim_visible_side_effect():
            actions.append("claim_visible")

        def open_battle_pass_side_effect():
            actions.append("open_battle_pass")
            return True

        def claim_battle_pass_side_effect():
            actions.append("claim_battle_pass")
            return True

        with (
            patch.object(get_prize_module, "auto", AutoStub()),
            patch.object(get_prize_module, "open_pass_mission_page", return_value=True),
            patch.object(get_prize_module, "claim_visible_pass_coins", side_effect=claim_visible_side_effect),
            patch.object(get_prize_module, "open_battle_pass_page", side_effect=open_battle_pass_side_effect),
            patch.object(get_prize_module, "claim_pass_level_rewards", side_effect=claim_battle_pass_side_effect),
            patch.object(get_prize_module, "sleep", lambda *_: None),
        ):
            result = get_prize_module.get_pass_prize()

        self.assertIsInstance(result, float)
        self.assertEqual(
            actions,
            [
                "claim_visible",
                "screenshot",
                "click:pass/weekly_assets.png",
                "claim_visible",
                "open_battle_pass",
                "claim_battle_pass",
            ],
        )


if __name__ == "__main__":
    unittest.main()
