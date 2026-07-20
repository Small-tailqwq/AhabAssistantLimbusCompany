import types
import unittest
from unittest import mock

from PIL import Image

from tasks.mirror.in_shop import Shop, _extract_money_from_ocr_texts, _retry_money_ocr_with_scaled_crop


class TestShopMoneyOcr(unittest.TestCase):
    def test_extract_money_accepts_plain_digits(self):
        self.assertEqual(_extract_money_from_ocr_texts(["285"]), 285)

    def test_extract_money_ignores_unrelated_text_and_uses_later_digits(self):
        self.assertEqual(_extract_money_from_ocr_texts(["Refres", "285"]), 285)

    def test_extract_money_normalizes_common_digit_confusions(self):
        self.assertEqual(_extract_money_from_ocr_texts(["G10 "]), 610)

    def test_extract_money_returns_none_for_non_numeric_text(self):
        self.assertIsNone(_extract_money_from_ocr_texts(["Refres"]))

    @mock.patch("tasks.mirror.in_shop.ocr.run")
    @mock.patch("tasks.mirror.in_shop.auto")
    def test_retry_money_ocr_with_scaled_crop_uses_enlarged_crop(self, auto_mock, ocr_run_mock):
        auto_mock.screenshot = Image.new("RGB", (20, 20), color="black")
        ocr_run_mock.return_value = types.SimpleNamespace(txts=["610"])

        result = _retry_money_ocr_with_scaled_crop((2, 2, 8, 8), scale=2)

        self.assertEqual(result, ["610"])
        enlarged_crop = ocr_run_mock.call_args.args[0]
        self.assertEqual(enlarged_crop.size, (12, 12))

    @mock.patch("tasks.mirror.in_shop.retry", return_value=True)
    @mock.patch("tasks.mirror.in_shop.sleep")
    @mock.patch("tasks.mirror.in_shop.auto")
    def test_keyword_refresh_does_not_succeed_without_confirm(self, auto_mock, _sleep_mock, retry_mock):
        shop = Shop.__new__(Shop)
        shop.system = "pierce"
        shop.skill_replacement = False
        shop.replacement = 0
        shop.replacement_skill = mock.Mock()

        auto_mock.click_element.side_effect = [True, True, False]

        self.assertFalse(shop._try_keyword_refresh())
        retry_mock.assert_not_called()
        shop.replacement_skill.assert_not_called()

    @mock.patch("tasks.mirror.in_shop.auto")
    def test_keyword_refresh_returns_none_when_entry_button_not_found(self, auto_mock):
        shop = Shop.__new__(Shop)
        shop.system = "pierce"
        shop.skill_replacement = False
        shop.replacement = 0

        auto_mock.click_element.return_value = False

        self.assertIsNone(shop._try_keyword_refresh())

    @mock.patch("tasks.mirror.in_shop.retry", return_value=True)
    @mock.patch("tasks.mirror.in_shop.sleep")
    @mock.patch("tasks.mirror.in_shop.auto")
    def test_keyword_refresh_returns_false_when_dialog_does_not_close(self, auto_mock, _sleep_mock, retry_mock):
        shop = Shop.__new__(Shop)
        shop.system = "pierce"
        shop.skill_replacement = False
        shop.replacement = 0
        shop.replacement_skill = mock.Mock()

        auto_mock.click_element.side_effect = [True, True, True]
        auto_mock.take_screenshot.return_value = object()
        auto_mock.find_element.side_effect = [object()] * 20

        self.assertFalse(shop._try_keyword_refresh())
        retry_mock.assert_not_called()
        shop.replacement_skill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
