import unittest
from types import SimpleNamespace
from unittest import mock

from tasks.mirror.in_shop import Shop


def make_team_setting(**overrides):
    base = {
        "team_system": 0,
        "sinner_order": [],
        "shop_strategy": 0,
        "do_not_heal": False,
        "do_not_buy": False,
        "do_not_fuse": False,
        "do_not_sell": False,
        "do_not_enhance": False,
        "aggressive_save_systems": False,
        "only_aggressive_fuse": False,
        "do_not_system_fuse": False,
        "only_system_fuse": False,
        "after_level_IV": False,
        "after_level_IV_select": 0,
        "shopping_strategy": False,
        "shopping_strategy_select": 0,
        "second_system": False,
        "second_system_select": 0,
        "second_system_setting": 0,
        "second_system_action": [False, False, False, False],
        "skill_replacement": False,
        "skill_replacement_select": 0,
        "skill_replacement_mode": 0,
        "max_keyword_refresh": 3,
        "max_normal_refresh": 3,
        "reserve_upgrade_funds": 500,
        "ignore_shop": [False] * 5,
        "aggressive_also_enhance": False,
        "system_slash": False,
        "system_burn": False,
        "system_bleed": False,
        "system_rupture": False,
        "system_charge": False,
        "system_sinking": False,
        "system_tremor": False,
        "system_poise": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestShopBuyFlowHelpers(unittest.TestCase):
    def setUp(self):
        self.shop = Shop(make_team_setting())

    def test_should_try_refresh_allows_unknown_money(self):
        self.assertTrue(self.shop._should_try_refresh(-1, 300))

    def test_should_try_refresh_respects_reserved_upgrade_funds(self):
        self.shop.reserve_upgrade_funds = 500

        self.assertFalse(self.shop._should_try_refresh(799, 300))
        self.assertTrue(self.shop._should_try_refresh(800, 300))

    @mock.patch.object(Shop, "_finish_shop_refresh")
    @mock.patch("tasks.mirror.in_shop._wait_for_keyword_refresh_confirm_to_clear")
    @mock.patch("tasks.mirror.in_shop.sleep", return_value=None)
    @mock.patch("tasks.mirror.in_shop.auto")
    def test_try_keyword_refresh_retries_confirmation_before_succeeding(
        self,
        auto_mock,
        _sleep_mock,
        wait_mock,
        finish_refresh_mock,
    ):
        auto_mock.click_element.return_value = True
        wait_mock.side_effect = [False, True]

        result = self.shop._try_keyword_refresh()

        self.assertTrue(result)
        self.assertEqual(wait_mock.call_count, 2)
        self.assertEqual(auto_mock.click_element.call_count, 4)
        finish_refresh_mock.assert_called_once_with()

    @mock.patch.object(Shop, "_finish_shop_refresh")
    @mock.patch("tasks.mirror.in_shop.sleep", return_value=None)
    @mock.patch("tasks.mirror.in_shop.auto")
    def test_try_keyword_refresh_returns_false_when_keyword_click_never_lands(
        self,
        auto_mock,
        _sleep_mock,
        finish_refresh_mock,
    ):
        auto_mock.click_element.return_value = False

        result = self.shop._try_keyword_refresh()

        self.assertFalse(result)
        auto_mock.click_element.assert_called_once_with(
            f"mirror/shop/keyword/keyword_{self.shop.system}.png",
            take_screenshot=True,
        )
        finish_refresh_mock.assert_not_called()

    @mock.patch("tasks.mirror.in_shop.sleep", return_value=None)
    @mock.patch("tasks.mirror.in_shop.auto")
    def test_finalize_purchase_attempt_handles_confirm_dialog(self, auto_mock, _sleep_mock):
        auto_mock.click_element.return_value = True

        self.shop._finalize_purchase_attempt()

        auto_mock.take_screenshot.assert_called_once_with()
        auto_mock.click_element.assert_called_once_with("mirror/road_in_mir/ego_gift_get_confirm_assets.png")
        auto_mock.mouse_click_blank.assert_called_once_with(times=3)


if __name__ == "__main__":
    unittest.main()
