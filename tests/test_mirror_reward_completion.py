import unittest
from unittest.mock import patch

import numpy as np

import tasks.base.script_task_scheme as script_task_scheme
import tasks.mirror.mirror as mirror_module


class RewardAutoStub:
    def __init__(self, *, completion_confirmed=True, submit_confirmation=True, open_claim_dialog=False):
        self.model = "clam"
        self.screenshot = np.zeros((720, 1280), dtype=np.uint8)
        self.claim_clicks = 0
        self.confirm_clicks = 0
        self.reward_loops = 0
        self.completion_confirmed = completion_confirmed
        self.submit_confirmation = submit_confirmation
        self.open_claim_dialog = open_claim_dialog

    def take_screenshot(self):
        return object()

    def find_element(self, target, *_, **__):
        if target == "mirror/claim_reward/battle_statistics_assets.png":
            return True
        if target == "mirror/claim_reward/complete_mirror_100%_assets.png":
            return self.completion_confirmed
        if target == "home/drive_assets.png":
            self.reward_loops += 1
            return self.open_claim_dialog and self.reward_loops > 1
        return False

    def find_text_element(self, *_, **__):
        return False

    def click_element(self, target, *_, **__):
        if target == "mirror/claim_reward/claim_rewards_assets.png":
            self.claim_clicks += 1
            return self.claim_clicks <= (2 if self.open_claim_dialog else 1)
        if target == "mirror/claim_reward/claim_rewards_confirm_assets.png":
            self.confirm_clicks += 1
            return self.submit_confirmation and self.confirm_clicks == 1
        return False

    def mouse_to_blank(self, *_, **__):
        return None

    def mouse_click_blank(self, *_, **__):
        return None


class TestMirrorRewardCompletion(unittest.TestCase):
    def _make_mirror(self):
        mirror = mirror_module.Mirror.__new__(mirror_module.Mirror)
        mirror.bequest_from_the_previous_game = False
        mirror.hard_switch = False
        mirror.pass_coins = None
        mirror.LOOP_COUNT = 1
        mirror.floor_times = [-9999.0] * 5
        mirror.floor = 1
        mirror.team_order = 1
        mirror.team_number = 1
        mirror.battle_total_time = 0
        mirror.event_times = 0
        mirror.event_total_time = 0
        mirror.shop_total_time = 0
        mirror.find_road_total_time = 0
        mirror.system = "test"
        return mirror

    def _cfg_stub(self):
        return type(
            "CfgStub",
            (),
            {
                "floor_3_exit": False,
                "save_rewards": False,
                "no_weekly_bonuses": False,
                "hard_mirror_single_bonuses": False,
                "set_win_size": 720,
                "config": type("ConfigStub", (), {"teams": {}})(),
            },
        )()

    def test_completed_mirror_is_counted_when_reward_page_recovery_times_out(self):
        auto_stub = RewardAutoStub()
        mirror = self._make_mirror()

        with (
            patch.object(mirror_module, "auto", auto_stub),
            patch.object(mirror_module, "cfg", self._cfg_stub()),
            patch.object(mirror_module, "retry", lambda: None),
            patch.object(mirror_module, "sleep", lambda *_: None),
        ):
            result = mirror.run()

        self.assertTrue(result)
        self.assertGreater(auto_stub.reward_loops, 20)

    def test_pass_coin_log_does_not_reuse_previous_claim_value(self):
        auto_stub = RewardAutoStub(submit_confirmation=False, open_claim_dialog=True)
        mirror = self._make_mirror()
        mirror.pass_coins = 45
        empty_ocr = type("OcrResultStub", (), {"txts": []})()

        with (
            patch.object(mirror_module, "auto", auto_stub),
            patch.object(mirror_module, "cfg", self._cfg_stub()),
            patch.object(mirror_module, "retry", lambda: None),
            patch.object(mirror_module, "sleep", lambda *_: None),
            patch.object(mirror_module.ImageUtils, "load_image", return_value=object()),
            patch.object(mirror_module.ImageUtils, "get_bbox", return_value=(0, 0, 10, 10)),
            patch.object(mirror_module.ocr, "run", return_value=empty_ocr),
        ):
            result = mirror.run()

        self.assertTrue(result)
        self.assertIsNone(mirror.pass_coins)

    def test_unsubmitted_reward_still_raises_when_recovery_times_out(self):
        auto_stub = RewardAutoStub(submit_confirmation=False)
        mirror = self._make_mirror()

        with (
            patch.object(mirror_module, "auto", auto_stub),
            patch.object(mirror_module, "cfg", self._cfg_stub()),
            patch.object(mirror_module, "retry", lambda: None),
            patch.object(mirror_module, "sleep", lambda *_: None),
            patch.object(mirror_module.ImageUtils, "load_image", return_value=object()),
            patch.object(mirror_module.ImageUtils, "get_bbox", return_value=(0, 0, 10, 10)),
            self.assertRaisesRegex(mirror_module.cannotOperateGameError, "镜牢奖励领取出错"),
        ):
            mirror.run()

    def test_mirror_task_stops_batch_after_failed_run(self):
        calls = []

        class SignalStub:
            def emit(self, *args):
                calls.append(("emit", args))

        team_setting = type("TeamSettingStub", (), {"fixed_team_use": False})()

        class CfgStub:
            set_mirror_count = 1
            infinite_dungeons = False
            save_rewards = False
            hard_mirror = False
            auto_hard_mirror = False
            re_claim_rewards = False
            teams_active_queue = [1]
            config = type("ConfigStub", (), {"teams": {"1": team_setting}})()

            @staticmethod
            def get_value(key):
                return [True]

            @staticmethod
            def normalize_and_sync_team_state(persist=True):
                calls.append(("normalize", persist))

        mediator_stub = type(
            "MediatorStub",
            (),
            {
                "mirror_signal": SignalStub(),
                "mirror_bar_kill_signal": SignalStub(),
            },
        )()
        auto_stub = type("AutoStub", (), {"ensure_not_stopped": lambda self: None})()

        with (
            patch.object(script_task_scheme, "cfg", CfgStub()),
            patch.object(script_task_scheme, "mediator", mediator_stub),
            patch.object(script_task_scheme, "auto", auto_stub),
            patch.object(
                script_task_scheme,
                "onetime_mir_process",
                side_effect=lambda *_: calls.append(("onetime",)) or False,
            ),
        ):
            script_task_scheme.Mirror_task()

        self.assertEqual(calls.count(("onetime",)), 1)


if __name__ == "__main__":
    unittest.main()
