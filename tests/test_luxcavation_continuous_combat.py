import unittest
from unittest import mock

from tasks.daily.luxcavation import (
    _filter_thread_level_targets,
    _get_continuous_combat_up_clicks,
    _get_exp_continuous_combat_box_position,
    _prepare_continuous_combat_count,
    _set_continuous_combat_count,
    thread_luxcavation,
)


class TestLuxcavationContinuousCombat(unittest.TestCase):
    def test_get_continuous_combat_up_clicks_uses_default_count_one(self):
        self.assertEqual(_get_continuous_combat_up_clicks(1), 0)
        self.assertEqual(_get_continuous_combat_up_clicks(3), 2)

    def test_get_continuous_combat_up_clicks_clamps_to_game_max(self):
        self.assertEqual(_get_continuous_combat_up_clicks(10), 9)
        self.assertEqual(_get_continuous_combat_up_clicks(99), 9)

    def test_filter_thread_level_targets_keeps_one_anchor_per_row(self):
        targets = [
            (809, 300),
            (810, 500),
            (811, 506),
            (808, 398),
            (320, 410),
        ]

        self.assertEqual(
            _filter_thread_level_targets(targets, scale=0.5),
            [(810, 500), (808, 398), (809, 300)],
        )

    def test_get_exp_continuous_combat_box_position_uses_selected_entry(self):
        self.assertEqual(_get_exp_continuous_combat_box_position((800, 600), scale=0.5), (950, 375))

    @mock.patch("tasks.daily.luxcavation.sleep", return_value=None)
    @mock.patch("tasks.daily.luxcavation.auto")
    def test_finds_button_once_then_clicks_multiple_times(self, auto_mock, _sleep_mock):
        auto_mock.take_screenshot.return_value = True
        auto_mock.click_element.side_effect = [(123, 456), (300, 400)]

        result = _set_continuous_combat_count(3, "经验本")

        self.assertTrue(result)
        self.assertEqual(auto_mock.take_screenshot.call_count, 2)
        self.assertEqual(
            auto_mock.click_element.call_args_list,
            [
                mock.call(
                    "luxcavation/continuous_combat_up_box_assets.png",
                    threshold=0.85,
                    click=False,
                    model="aggressive",
                ),
                mock.call(
                    "luxcavation/thread_continuous_combat_show_box_assets.png",
                    threshold=0.85,
                    click=False,
                    model="aggressive",
                ),
            ],
        )
        self.assertEqual(auto_mock.mouse_click.call_args_list, [mock.call(123, 456), mock.call(123, 456), mock.call(300, 400)])

    @mock.patch("tasks.daily.luxcavation.sleep", return_value=None)
    @mock.patch("tasks.daily.luxcavation.auto")
    def test_returns_false_when_button_not_found(self, auto_mock, _sleep_mock):
        auto_mock.take_screenshot.return_value = True
        auto_mock.click_element.return_value = False

        result = _set_continuous_combat_count(4, "纽本")

        self.assertFalse(result)
        auto_mock.mouse_click.assert_not_called()

    @mock.patch("tasks.daily.luxcavation.sleep", return_value=None)
    @mock.patch("tasks.daily.luxcavation.auto")
    def test_prepare_opens_shared_count_box_before_setting_count(self, auto_mock, _sleep_mock):
        auto_mock.take_screenshot.return_value = True
        auto_mock.click_element.side_effect = [(746, 182), (717, 217), (746, 182)]

        result = _prepare_continuous_combat_count(2, "纽本")

        self.assertTrue(result)
        self.assertEqual(
            auto_mock.click_element.call_args_list,
            [
                mock.call(
                    "luxcavation/thread_continuous_combat_show_box_assets.png",
                    threshold=0.85,
                    click=False,
                    model="aggressive",
                ),
                mock.call(
                    "luxcavation/continuous_combat_up_box_assets.png",
                    threshold=0.85,
                    click=False,
                    model="aggressive",
                ),
                mock.call(
                    "luxcavation/thread_continuous_combat_show_box_assets.png",
                    threshold=0.85,
                    click=False,
                    model="aggressive",
                ),
            ],
        )
        self.assertEqual(auto_mock.mouse_click.call_args_list, [mock.call(746, 182), mock.call(717, 217), mock.call(746, 182)])

    @mock.patch("tasks.daily.luxcavation.sleep", return_value=None)
    @mock.patch("tasks.daily.luxcavation.auto")
    def test_prepare_can_use_selected_exp_entry_as_count_box_anchor(self, auto_mock, _sleep_mock):
        auto_mock.take_screenshot.return_value = True
        auto_mock.click_element.return_value = (717, 217)

        result = _prepare_continuous_combat_count(2, "经验本", (950, 375))

        self.assertTrue(result)
        self.assertEqual(
            auto_mock.click_element.call_args_list,
            [
                mock.call(
                    "luxcavation/continuous_combat_up_box_assets.png",
                    threshold=0.85,
                    click=False,
                    model="aggressive",
                ),
            ],
        )
        self.assertEqual(auto_mock.mouse_click.call_args_list, [mock.call(950, 375), mock.call(717, 217), mock.call(950, 375)])

    @mock.patch("tasks.daily.luxcavation.sleep", return_value=None)
    @mock.patch("tasks.daily.luxcavation.auto")
    def test_skips_when_target_is_default(self, auto_mock, _sleep_mock):
        result = _set_continuous_combat_count(1, "经验本")

        self.assertTrue(result)
        auto_mock.take_screenshot.assert_not_called()
        auto_mock.click_element.assert_not_called()
        auto_mock.mouse_click.assert_not_called()

    @mock.patch("tasks.daily.luxcavation.sleep", return_value=None)
    @mock.patch("tasks.daily.luxcavation.auto")
    def test_thread_sets_continuous_count_before_entering_level_list(self, auto_mock, _sleep_mock):
        teams_seen = 0

        def find_element(target, *args, **kwargs):
            nonlocal teams_seen
            if target == "teams/identify_assets.png":
                teams_seen += 1
                return teams_seen > 1
            if target == "home/first_prompt_assets.png":
                return False
            if target == "luxcavation/thread_consume.png":
                return False
            return False

        def click_element(target, *args, **kwargs):
            if target == "luxcavation/thread_enter_assets.png":
                return (100, 200)
            if target == "luxcavation/thread_continuous_combat_show_box_assets.png":
                return (300, 400)
            if target == "luxcavation/continuous_combat_up_box_assets.png":
                return (500, 600)
            return False

        auto_mock.take_screenshot.return_value = True
        auto_mock.find_element.side_effect = find_element
        auto_mock.click_element.side_effect = click_element

        thread_luxcavation(combat_count=3)

        self.assertEqual(
            auto_mock.mouse_click.call_args_list,
            [
                mock.call(300, 400),
                mock.call(500, 600),
                mock.call(500, 600),
                mock.call(300, 400),
                mock.call(100, 200),
            ],
        )


if __name__ == "__main__":
    unittest.main()
