import unittest
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


if __name__ == "__main__":
    unittest.main()
