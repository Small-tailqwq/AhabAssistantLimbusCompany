import unittest
from types import SimpleNamespace
from unittest import mock

import tasks.base.retry as retry_module


class _RetryAuto:
    def __init__(self):
        self.screenshot_count = 0
        self.click_count = 0

    def get_restore_time(self):
        return None

    def take_screenshot(self):
        self.screenshot_count += 1
        return object()

    def find_element(self, *_args, **_kwargs):
        return False

    def click_element(self, *_args, **_kwargs):
        self.click_count += 1
        return False


class TestRetryRefresh(unittest.TestCase):
    def test_retry_refreshes_screenshot_and_checks_every_call(self):
        auto = _RetryAuto()
        screen = SimpleNamespace(handle=SimpleNamespace(hwnd=123))

        with (
            mock.patch.object(retry_module, "auto", auto),
            mock.patch.object(retry_module, "screen", screen),
            mock.patch.object(retry_module, "check_times", return_value=False),
            mock.patch.object(retry_module.time, "time", return_value=1000.0),
        ):
            retry_module.retry()
            retry_module.retry()

        # 每次调用都截图一次
        self.assertEqual(auto.screenshot_count, 2)
        # 每次调用都执行全部弹窗检查：retry.png + only_option_assets.png 各点击一次
        self.assertEqual(auto.click_count, 4)


if __name__ == "__main__":
    unittest.main()
