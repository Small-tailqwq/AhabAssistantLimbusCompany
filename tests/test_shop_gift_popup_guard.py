import unittest
from unittest import mock

from tasks.mirror import in_shop as in_shop_module

POPUP = "mirror/road_in_mir/ego_gift_get_confirm_assets.png"


class _FakeAuto:
    """按帧序列回答 find_element：帧里出现的模板返回坐标。"""

    def __init__(self, frames):
        self.frames = frames
        self.frame_index = -1
        self.screenshot = object()
        self.click_calls = []

    @property
    def frame(self):
        return self.frames[max(self.frame_index, 0)]

    def find_element(self, target, *_, take_screenshot=False, **__):
        # 复现 Automation.find_element：先截图再匹配
        if take_screenshot:
            self.take_screenshot()
        return self.frames[max(self.frame_index, 0)].get(target)

    def ensure_not_stopped(self):
        return None

    def take_screenshot(self, *_, **__):
        if self.frame_index + 1 < len(self.frames):
            self.frame_index += 1
        return self.screenshot

    def mouse_click(self, x, y, *_, **__):
        self.click_calls.append((x, y))
        return True


class TestGiftPopupDismiss(unittest.TestCase):
    def test_popup_is_clicked_until_gone(self):
        # 每次 find_element 会先截图再匹配，因此帧序列要按「观察 → 观察 → 消失」排布
        auto = _FakeAuto(
            [
                {POPUP: (900, 500)},
                {POPUP: (900, 500)},
                {},
                {},
            ]
        )
        with (
            mock.patch.object(in_shop_module, "auto", auto),
            mock.patch.object(in_shop_module, "sleep", return_value=None),
        ):
            result = in_shop_module._dismiss_gift_get_popup(timeout_seconds=1.5, poll_interval=0.3)

        self.assertTrue(result)
        self.assertEqual(auto.click_calls, [(900, 500), (900, 500)])

    def test_popup_persisting_returns_false(self):
        auto = _FakeAuto([{POPUP: (900, 500)}])
        with (
            mock.patch.object(in_shop_module, "auto", auto),
            mock.patch.object(in_shop_module, "sleep", return_value=None),
        ):
            result = in_shop_module._dismiss_gift_get_popup(timeout_seconds=0.6, poll_interval=0.3)

        self.assertFalse(result)

    def test_no_popup_returns_true_without_clicking(self):
        auto = _FakeAuto([{}])
        with (
            mock.patch.object(in_shop_module, "auto", auto),
            mock.patch.object(in_shop_module, "sleep", return_value=None),
        ):
            result = in_shop_module._dismiss_gift_get_popup()

        self.assertTrue(result)
        self.assertEqual(auto.click_calls, [])


class TestGetCostGuardedByPopup(unittest.TestCase):
    def test_get_cost_skips_ocr_while_popup_persists(self):
        auto = _FakeAuto([{POPUP: (900, 500)}])
        shop = in_shop_module.Shop.__new__(in_shop_module.Shop)
        with (
            mock.patch.object(in_shop_module, "auto", auto),
            mock.patch.object(in_shop_module, "sleep", return_value=None),
            mock.patch.object(in_shop_module, "_debug_save_on_failure") as save_mock,
            mock.patch.object(in_shop_module, "ocr") as ocr_mock,
        ):
            money = shop._get_cost()

        self.assertEqual(money, -1)
        ocr_mock.run.assert_not_called()
        save_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
