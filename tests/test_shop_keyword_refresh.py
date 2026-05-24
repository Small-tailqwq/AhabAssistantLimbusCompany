import unittest
from unittest import mock

from tasks.mirror.in_shop import _wait_for_keyword_refresh_confirm_to_clear


class TestShopKeywordRefresh(unittest.TestCase):
    @mock.patch("tasks.mirror.in_shop.sleep", return_value=None)
    @mock.patch("tasks.mirror.in_shop.auto")
    def test_wait_for_keyword_refresh_confirm_to_clear_returns_true_when_dialog_disappears(
        self,
        auto_mock,
        _sleep_mock,
    ):
        auto_mock.find_element.side_effect = [(1, 1), (1, 1), None]

        result = _wait_for_keyword_refresh_confirm_to_clear(timeout_seconds=0.75, poll_interval=0.25)

        self.assertTrue(result)
        self.assertEqual(auto_mock.find_element.call_count, 3)

    @mock.patch("tasks.mirror.in_shop.sleep", return_value=None)
    @mock.patch("tasks.mirror.in_shop.auto")
    def test_wait_for_keyword_refresh_confirm_to_clear_returns_false_when_dialog_still_visible(self, auto_mock, sleep_mock):
        auto_mock.find_element.side_effect = [(1, 1), (1, 1), (1, 1)]

        result = _wait_for_keyword_refresh_confirm_to_clear(timeout_seconds=0.75, poll_interval=0.25)

        self.assertFalse(result)
        self.assertEqual(auto_mock.find_element.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
