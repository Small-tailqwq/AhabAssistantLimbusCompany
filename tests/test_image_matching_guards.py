import unittest

import numpy as np

from module.automation.input_handlers.simulator.mumu_control import EmulatorPortraitError, MumuControl
from utils.image_utils import ImageUtils


class TestImageMatchingGuards(unittest.TestCase):
    def test_match_template_returns_no_match_when_bbox_crop_is_smaller_than_template(self):
        screenshot = np.zeros((1280, 720), dtype=np.uint8)
        template = np.zeros((100, 100), dtype=np.uint8)

        center, match_value = ImageUtils.match_template(
            screenshot,
            template,
            (700, 1250, 720, 1280),
        )

        self.assertIsNone(center)
        self.assertEqual(match_value, 0.0)

    def test_match_template_returns_no_match_when_screenshot_is_smaller_than_template(self):
        screenshot = np.zeros((20, 20), dtype=np.uint8)
        template = np.zeros((30, 30), dtype=np.uint8)

        center, match_value = ImageUtils.match_template(
            screenshot,
            template,
            None,
        )

        self.assertIsNone(center)
        self.assertEqual(match_value, 0.0)

    def test_mumu_screenshot_refreshes_portrait_resolution_before_capture(self):
        control = MumuControl.__new__(MumuControl)
        control.connect_id = 1
        control.width = 720
        control.height = 1280
        refreshes = []

        def refresh_resolution():
            refreshes.append((control.width, control.height))

        control.get_resolution = refresh_resolution

        with self.assertRaises(EmulatorPortraitError):
            control.screenshot()

        self.assertEqual(refreshes, [(720, 1280)])


if __name__ == "__main__":
    unittest.main()
