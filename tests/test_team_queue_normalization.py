import tempfile
import unittest
from unittest.mock import patch

from ruamel.yaml import YAML

import app.base_tools as base_tools
import app.farming_interface as farming_interface
import app.page_card as page_card
import tasks.base.script_task_scheme as script_task_scheme
import utils.utils as utils_module
from module.config.config import Config
from module.config.config_typing import ConfigModel, TeamSetting


class TestTeamQueueNormalization(unittest.TestCase):
    def make_config(self, team_numbers, **overrides):
        cfg = Config.__new__(Config)
        cfg.config = ConfigModel(
            teams={str(team_num): TeamSetting() for team_num in team_numbers},
            **overrides,
        )
        cfg.save = lambda *args, **kwargs: None
        return cfg

    def test_config_model_defaults_empty_active_queue(self):
        self.assertEqual(ConfigModel().teams_active_queue, [])

    def test_migrate_legacy_order_to_active_queue(self):
        cfg = self.make_config(
            [1, 2, 3, 4, 5],
            teams_order=[0, 2, 0, 3, 1],
            teams_be_select=[False, True, False, True, True],
        )

        self.assertEqual(cfg.migrate_legacy_team_queue(), [5, 2, 4])

    def test_migrate_from_selected_teams_when_order_missing(self):
        cfg = self.make_config(
            [1, 2, 3, 4],
            teams_order=[0, 0, 0, 0],
            teams_be_select=[False, True, False, True],
        )

        self.assertEqual(cfg.migrate_legacy_team_queue(), [2, 4])

    def test_migrate_partial_duplicate_order_appends_remaining_selected_teams(self):
        cfg = self.make_config(
            [1, 2, 3, 4, 5],
            teams_order=[2, 2, 0, 0, 1],
            teams_be_select=[True, True, False, True, True],
        )

        self.assertEqual(cfg.migrate_legacy_team_queue(), [5, 1, 2, 4])

    def test_migrate_legacy_order_repairs_missing_one_and_mismatched_count(self):
        cfg = self.make_config(
            [1, 2, 3],
            teams_order=[2, 3, 4, 0],
            teams_be_select=[True, True, True, False],
            teams_be_select_num=4,
        )

        self.assertEqual(cfg.migrate_legacy_team_queue(), [1, 2, 3])

    def test_normalize_filters_invalid_queue_members_and_projects_legacy_fields(self):
        cfg = self.make_config(
            [1, 2, 3, 4, 5],
            teams_active_queue=[5, 2, 2, 9, 4, 0, -1],
            teams_be_select=[True, False, True, False, False],
            teams_order=[1, 2, 3, 4, 5],
        )

        cfg.normalize_and_sync_team_state()

        self.assertEqual(cfg.config.teams_active_queue, [5, 2, 4])
        self.assertEqual(cfg.config.teams_be_select, [False, True, False, True, True])
        self.assertEqual(cfg.config.teams_order, [0, 2, 0, 3, 1])
        self.assertEqual(cfg.config.teams_be_select_num, 3)

    def test_normalize_ignores_bool_values_in_active_queue(self):
        cfg = self.make_config([1, 2, 3, 4, 5])
        cfg.config.teams_active_queue = [True, 5, False, 2]

        cfg.normalize_and_sync_team_state()

        self.assertEqual(cfg.config.teams_active_queue, [5, 2])
        self.assertEqual(cfg.config.teams_be_select, [False, True, False, False, True])
        self.assertEqual(cfg.config.teams_order, [0, 2, 0, 0, 1])
        self.assertEqual(cfg.config.teams_be_select_num, 2)

    def test_explicit_empty_queue_stays_empty_without_reviving_legacy_state(self):
        cfg = self.make_config(
            [1, 2, 3, 4],
            teams_active_queue=[],
            teams_be_select=[False, True, False, True],
            teams_order=[0, 1, 0, 2],
            teams_be_select_num=2,
        )

        cfg.normalize_and_sync_team_state()

        self.assertEqual(cfg.config.teams_active_queue, [])
        self.assertEqual(cfg.config.teams_be_select, [False, False, False, False])
        self.assertEqual(cfg.config.teams_order, [0, 0, 0, 0])
        self.assertEqual(cfg.config.teams_be_select_num, 0)

    def test_normalize_and_sync_team_state_can_skip_persist(self):
        cfg = self.make_config(
            [1, 2, 3, 4],
            teams_active_queue=[4, 2, 2, 9],
        )
        save_calls = []
        cfg.save = lambda *args, **kwargs: save_calls.append((args, kwargs))

        cfg.normalize_and_sync_team_state(persist=False)

        self.assertEqual(cfg.config.teams_active_queue, [4, 2])
        self.assertEqual(cfg.config.teams_be_select, [False, True, False, True])
        self.assertEqual(cfg.config.teams_order, [0, 2, 0, 1])
        self.assertEqual(cfg.config.teams_be_select_num, 2)
        self.assertEqual(save_calls, [])

    def test_normalize_repairs_drifted_team_number_fields(self):
        cfg = self.make_config([1, 2, 3])
        cfg.config.teams["1"].team_number = 9
        cfg.config.teams["2"].team_number = 1
        cfg.config.teams["3"].team_number = 1

        cfg.normalize_and_sync_team_state(persist=False)

        self.assertEqual(cfg.config.teams["1"].team_number, 1)
        self.assertEqual(cfg.config.teams["2"].team_number, 2)
        self.assertEqual(cfg.config.teams["3"].team_number, 3)

    def test_just_load_config_normalizes_team_state_in_memory(self):
        yaml = YAML()
        cases = [
            (
                {
                    "teams": {str(team_num): {} for team_num in [1, 2, 3, 4, 5]},
                    "teams_active_queue": [5, 2, 2, 9, True],
                    "teams_be_select": [True, False, False, False, False],
                    "teams_order": [1, 0, 0, 0, 0],
                },
                [5, 2],
                [False, True, False, False, True],
                [0, 2, 0, 0, 1],
                2,
            ),
            (
                {
                    "teams": {str(team_num): {} for team_num in [1, 2, 3, 4]},
                    "teams_be_select": [False, True, False, True],
                    "teams_order": [0, 0, 0, 0],
                },
                [2, 4],
                [False, True, False, True],
                [0, 1, 0, 2],
                2,
            ),
            (
                {
                    "teams": {
                        "1": {"team_number": 1},
                        "2": {"team_number": 1},
                        "3": {"team_number": 1},
                    },
                    "teams_be_select": [True, True, True, False],
                    "teams_be_select_num": 4,
                    "teams_order": [2, 3, 4, 0],
                },
                [1, 2, 3],
                [True, True, True],
                [1, 2, 3],
                3,
            ),
        ]

        for payload, expected_queue, expected_selected, expected_order, expected_count in cases:
            with self.subTest(payload=payload):
                cfg = Config.__new__(Config)
                cfg.yaml = YAML()
                cfg.config = ConfigModel()
                cfg._schedule_save = lambda *args, **kwargs: None

                with tempfile.TemporaryDirectory() as temp_dir:
                    config_path = f"{temp_dir}\\config.yaml"
                    with open(config_path, "w", encoding="utf-8") as file:
                        yaml.dump(payload, file)

                    cfg.just_load_config(config_path)

                self.assertEqual(cfg.config.teams_active_queue, expected_queue)
                self.assertEqual(cfg.config.teams_be_select, expected_selected)
                self.assertEqual(cfg.config.teams_order, expected_order)
                self.assertEqual(cfg.config.teams_be_select_num, expected_count)
                self.assertEqual(
                    [cfg.config.teams[str(team_num)].team_number for team_num in expected_queue],
                    expected_queue,
                )

    def test_reindex_team_queue_updates_team_numbers(self):
        cfg = self.make_config(
            [1, 2, 3, 4, 5, 6],
            teams_active_queue=[2, 6, 4],
        )

        cfg.reindex_team_queue({1: 1, 2: 2, 4: 3, 5: 4, 6: 5})

        self.assertEqual(cfg.config.teams_active_queue, [2, 5, 3])

    def test_rotate_team_queue_moves_front_team_to_back(self):
        cfg = self.make_config(
            [1, 2, 3, 4, 5],
            teams_active_queue=[2, 5, 3],
        )

        cfg.rotate_team_queue()

        self.assertEqual(cfg.config.teams_active_queue, [5, 3, 2])

    def test_set_team_enabled_and_remove_team_keep_legacy_projection_in_sync(self):
        cfg = self.make_config(
            [1, 2, 3, 4],
            teams_active_queue=[2, 4],
        )

        cfg.set_team_enabled(3, True)
        cfg.set_team_enabled(4, False)
        cfg.remove_team_from_queue(2)

        self.assertEqual(cfg.config.teams_active_queue, [3])
        self.assertEqual(cfg.config.teams_be_select, [False, False, True, False])
        self.assertEqual(cfg.config.teams_order, [0, 0, 1, 0])
        self.assertEqual(cfg.config.teams_be_select_num, 1)

    def test_base_checkbox_team_toggle_uses_queue_helper_and_emits_refresh(self):
        checkbox = base_tools.BaseCheckBox.__new__(base_tools.BaseCheckBox)
        checkbox.config_name = "the_team_3"
        checkbox.temporary = False
        checkbox.check_box = type("CheckBoxStub", (), {"right_clicked": False})()

        class CfgStub:
            def __init__(self):
                self.set_team_enabled_calls = []
                self.set_value_calls = []

            def get_value(self, key):
                if key == "the_team_3":
                    return None
                if key == "teams_be_select_num":
                    return 1
                if key == "teams_be_select":
                    return [True, False, False, False]
                if key == "teams_order":
                    return [1, 0, 0, 0]
                raise AssertionError(f"unexpected get_value({key!r})")

            def set_team_enabled(self, team_num, checked):
                self.set_team_enabled_calls.append((team_num, checked))

            def set_value(self, key, value):
                self.set_value_calls.append((key, value))

        class EmitStub:
            def __init__(self):
                self.calls = 0

            def emit(self):
                self.calls += 1

        cfg_stub = CfgStub()
        emit_stub = EmitStub()
        mediator_stub = type(
            "MediatorStub",
            (),
            {"refresh_teams_order": emit_stub},
        )()

        with patch.object(base_tools, "cfg", cfg_stub), patch.object(base_tools, "mediator", mediator_stub):
            checkbox.on_toggle(True)

        self.assertEqual(cfg_stub.set_team_enabled_calls, [(3, True)])
        self.assertEqual(emit_stub.calls, 1)
        self.assertEqual(cfg_stub.set_value_calls, [])

    def test_page_mirror_get_setting_normalizes_before_rebuild(self):
        page = page_card.PageMirror.__new__(page_card.PageMirror)
        calls = []

        class UpdateStub:
            def setUpdatesEnabled(self, enabled):
                calls.append(("updates", enabled))

        class LayoutStub:
            def count(self):
                return 2

            def insertWidget(self, index, widget):
                calls.append(("insert", index, widget.team_number))

        class MirrorTeamStub:
            def __init__(self, team_number, *args):
                self.team_number = team_number
                calls.append(("build", team_number))

        class ButtonGroupStub:
            def clear(self):
                calls.append(("clear",))

        class CfgStub:
            def __init__(self):
                self.config = type("ConfigStub", (), {"teams": {"1": object()}})()

            def normalize_and_sync_team_state(self, persist=True):
                calls.append(("normalize", persist))

        page.page_general = UpdateStub()
        page.vbox_general = LayoutStub()
        page.findChild = lambda cls, name: calls.append(("find", name)) or (object() if name == "team_1" else None)
        page.remove_team_card = lambda name: calls.append(("remove", name))
        page.refresh = lambda: calls.append(("refresh",))

        with (
            patch.object(page_card, "cfg", CfgStub()),
            patch.object(page_card, "team_toggle_button_group", ButtonGroupStub()),
            patch.object(page_card, "MirrorTeamCombination", MirrorTeamStub),
        ):
            page.get_setting()

        self.assertLess(calls.index(("normalize", False)), calls.index(("find", "team_1")))
        self.assertIn(("remove", "team_1"), calls)
        self.assertIn(("insert", 1, 1), calls)
        self.assertEqual(calls[-1], ("refresh",))

    def test_page_mirror_new_team_normalizes_without_legacy_appends(self):
        page = page_card.PageMirror.__new__(page_card.PageMirror)
        calls = []

        class AppendForbiddenList(list):
            def append(self, value):
                raise AssertionError(f"legacy append should not be used: {value!r}")

        class UpdateStub:
            def setUpdatesEnabled(self, enabled):
                calls.append(("updates", enabled))

        class LayoutStub:
            def count(self):
                return 2

            def insertWidget(self, index, widget):
                calls.append(("insert", index, widget.team_number))

        class MirrorTeamStub:
            def __init__(self, team_number, *args):
                self.team_number = team_number
                calls.append(("build", team_number))

            def retranslateUi(self):
                calls.append(("retranslate", self.team_number))

        class ThemeListStub:
            def create_team_weight_config(self, number):
                calls.append(("create_weight", number))

        class CfgStub:
            def __init__(self):
                self.config = type(
                    "ConfigStub",
                    (),
                    {
                        "teams": {},
                        "teams_be_select": AppendForbiddenList(),
                        "teams_order": AppendForbiddenList(),
                    },
                )()

            def normalize_and_sync_team_state(self):
                calls.append(("normalize", tuple(self.config.teams)))

            def save(self):
                calls.append(("save",))

        team_setting_sentinel = object()
        page.page_general = UpdateStub()
        page.vbox_general = LayoutStub()

        with (
            patch.object(page_card, "cfg", CfgStub()),
            patch.object(page_card, "team_toggle_button_group", []),
            patch.object(page_card, "MirrorTeamCombination", MirrorTeamStub),
            patch.object(page_card, "theme_list", ThemeListStub()),
            patch.object(page_card, "TeamSetting", lambda: team_setting_sentinel),
        ):
            page.new_team()
            cfg_stub = page_card.cfg

        self.assertIs(cfg_stub.config.teams["1"], team_setting_sentinel)
        self.assertIn(("create_weight", 1), calls)
        self.assertIn(("save",), calls)
        self.assertIn(("normalize", ("1",)), calls)

    def test_page_mirror_refresh_team_setting_card_compacts_and_reindexes_queue(self):
        page = page_card.PageMirror.__new__(page_card.PageMirror)
        calls = []

        team1 = TeamSetting(team_number=1)
        team2 = TeamSetting(team_number=2)
        team4 = TeamSetting(team_number=1)
        team5 = TeamSetting(team_number=1)
        team6 = TeamSetting(team_number=1)

        class CfgStub:
            def __init__(self):
                self.config = type(
                    "ConfigStub",
                    (),
                    {
                        "teams": {
                            "1": team1,
                            "2": team2,
                            "4": team4,
                            "5": team5,
                            "6": team6,
                        }
                    },
                )()

            def reindex_team_queue(self, mapping):
                calls.append(("reindex", mapping))

            def save(self):
                calls.append(("save",))

        class ThemeListStub:
            def set_team_weight_config_from_team(self, new_number, old_number):
                if not isinstance(new_number, int) or not isinstance(old_number, int):
                    raise AssertionError(f"theme remap expects ints, got {new_number!r}, {old_number!r}")
                calls.append(("weight_copy", new_number, old_number))

            def delete_team_weight_config(self, number):
                if not isinstance(number, int):
                    raise AssertionError(f"theme delete expects int, got {number!r}")
                calls.append(("weight_delete", number))

        cfg_stub = CfgStub()
        page.get_setting = lambda: calls.append(("get_setting", tuple(cfg_stub.config.teams.items())))

        with patch.object(page_card, "cfg", cfg_stub), patch.object(page_card, "theme_list", ThemeListStub()):
            page.refresh_team_setting_card()

        self.assertEqual(
            cfg_stub.config.teams,
            {
                "1": team1,
                "2": team2,
                "3": team4,
                "4": team5,
                "5": team6,
            },
        )
        self.assertEqual(cfg_stub.config.teams["3"].team_number, 3)
        self.assertEqual(cfg_stub.config.teams["4"].team_number, 4)
        self.assertEqual(cfg_stub.config.teams["5"].team_number, 5)
        self.assertIn(("reindex", {1: 1, 2: 2, 4: 3, 5: 4, 6: 5}), calls)
        self.assertIn(("weight_copy", 3, 4), calls)
        self.assertIn(("weight_copy", 4, 5), calls)
        self.assertIn(("weight_copy", 5, 6), calls)
        self.assertEqual(calls[-1][0], "get_setting")

    def test_page_mirror_delete_team_removes_queue_and_rebuilds_without_retranslate(self):
        page = page_card.PageMirror.__new__(page_card.PageMirror)
        calls = []

        class TeamStub:
            team_number = 4

            def findChild(self, cls, name):
                calls.append(("team_find_child", name))
                return None

        class CfgStub:
            def __init__(self):
                self.config = type("ConfigStub", (), {"teams": {"2": object(), "4": object(), "5": object()}})()

            def remove_team_from_queue(self, number):
                calls.append(("remove_queue", number))

            def save(self):
                calls.append(("save",))

        class ThemeListStub:
            def delete_team_weight_config(self, number):
                calls.append(("delete_weight", number))

        cfg_stub = CfgStub()
        page.findChild = lambda cls, name: TeamStub() if name == "team_4" else None
        page.remove_team_card = lambda name: calls.append(("remove_card", name))
        page.refresh_team_setting_card = lambda: calls.append(("refresh_team_setting_card", tuple(sorted(cfg_stub.config.teams))))
        page.retranslateUi = lambda: calls.append(("retranslate",))

        with patch.object(page_card, "cfg", cfg_stub), patch.object(page_card, "theme_list", ThemeListStub()):
            page.delete_team("team_4")

        self.assertNotIn("4", cfg_stub.config.teams)
        self.assertIn(("remove_queue", 4), calls)
        self.assertIn(("delete_weight", 4), calls)
        self.assertIn(("remove_card", "team_4"), calls)
        self.assertIn(("refresh_team_setting_card", ("2", "5")), calls)
        self.assertNotIn(("retranslate",), calls)
        self.assertNotIn(("save",), calls)

    def test_farming_interface_check_setting_normalizes_and_flushes_mirror_team_state(self):
        calls = []

        class ParentLevel2Stub:
            def findChild(self, cls):
                return None

        class ParentLevel1Stub:
            def __init__(self):
                self._parent = ParentLevel2Stub()

            def parent(self):
                return self._parent

        class TeamSettingStub:
            fixed_team_use = False
            fixed_team_use_select = 0
            sinners_be_select = 1

        class SignalStub:
            def __init__(self, name):
                self.name = name

            def emit(self, *args):
                calls.append((self.name, args))

        class CfgStub:
            mirror = True
            auto_hard_mirror = False
            hard_mirror = False
            daily_task = False
            get_reward = False
            buy_enkephalin = False
            teams_be_select = [True]

            def __init__(self):
                self.teams_be_select_num = 999
                self.config = type("ConfigStub", (), {"teams": {"1": TeamSettingStub()}})()

            def normalize_and_sync_team_state(self):
                calls.append(("normalize",))
                self.teams_be_select_num = 1

            def flush(self):
                calls.append(("flush",))

            def get_value(self, key):
                if key == "teams_be_select":
                    return [True]
                raise AssertionError(f"unexpected get_value({key!r})")

            def set_value(self, key, value):
                raise AssertionError(f"legacy self-heal should not call set_value({key!r}, {value!r})")

        def legacy_check_teams_order(*args, **kwargs):
            raise AssertionError("legacy check_teams_order should not be used")

        page = farming_interface.FarmingInterfaceLeft.__new__(farming_interface.FarmingInterfaceLeft)
        page.parent = lambda: ParentLevel1Stub()
        page.tr = lambda text: text

        mediator_stub = type(
            "MediatorStub",
            (),
            {
                "save_warning": SignalStub("save_warning"),
                "warning": SignalStub("warning"),
                "tasks_warning": SignalStub("tasks_warning"),
            },
        )()

        with (
            patch.object(farming_interface, "cfg", CfgStub()),
            patch.object(farming_interface, "mediator", mediator_stub),
            patch.object(utils_module, "check_teams_order", legacy_check_teams_order),
        ):
            self.assertIsNone(page.check_setting())

        self.assertEqual(calls[:2], [("normalize",), ("flush",)])
        self.assertNotIn(("warning", ("没有启用任何队伍，请选择一个队伍进行镜牢任务",)), calls)

    def test_farming_interface_check_setting_handles_missing_one_legacy_order_via_normalize(self):
        calls = []

        class ParentLevel2Stub:
            def findChild(self, cls):
                return None

        class ParentLevel1Stub:
            def __init__(self):
                self._parent = ParentLevel2Stub()

            def parent(self):
                return self._parent

        class TeamSettingStub:
            fixed_team_use = False
            fixed_team_use_select = 0
            sinners_be_select = 1

        class SignalStub:
            def __init__(self, name):
                self.name = name

            def emit(self, *args):
                calls.append((self.name, args))

        class CfgStub:
            mirror = True
            auto_hard_mirror = False
            hard_mirror = False
            daily_task = False
            get_reward = False
            buy_enkephalin = False
            teams_be_select = [True, True, True, False]

            def __init__(self):
                self.teams_be_select_num = 4
                self.teams_active_queue = []
                self.teams_order = [2, 3, 4, 0]
                self.config = type(
                    "ConfigStub",
                    (),
                    {
                        "teams": {
                            "1": TeamSettingStub(),
                            "2": TeamSettingStub(),
                            "3": TeamSettingStub(),
                        }
                    },
                )()

            def normalize_and_sync_team_state(self):
                calls.append(("normalize", tuple(self.teams_order), self.teams_be_select_num))
                self.teams_be_select_num = 3
                self.teams_be_select = [True, True, True]

            def flush(self):
                calls.append(("flush",))

            def get_value(self, key):
                if key == "teams_be_select":
                    return self.teams_be_select
                raise AssertionError(f"unexpected get_value({key!r})")

            def set_value(self, key, value):
                raise AssertionError(f"legacy self-heal should not call set_value({key!r}, {value!r})")

        def legacy_check_teams_order(*args, **kwargs):
            raise AssertionError("legacy check_teams_order should not be used")

        page = farming_interface.FarmingInterfaceLeft.__new__(farming_interface.FarmingInterfaceLeft)
        page.parent = lambda: ParentLevel1Stub()
        page.tr = lambda text: text

        mediator_stub = type(
            "MediatorStub",
            (),
            {
                "save_warning": SignalStub("save_warning"),
                "warning": SignalStub("warning"),
                "tasks_warning": SignalStub("tasks_warning"),
            },
        )()

        with (
            patch.object(farming_interface, "cfg", CfgStub()),
            patch.object(farming_interface, "mediator", mediator_stub),
            patch.object(utils_module, "check_teams_order", legacy_check_teams_order),
        ):
            self.assertIsNone(page.check_setting())

        self.assertEqual(calls[:2], [("normalize", (2, 3, 4, 0), 4), ("flush",)])
        self.assertNotIn(("warning", ("没有启用任何队伍，请选择一个队伍进行镜牢任务",)), calls)

    def test_mirror_task_uses_front_queue_team_instead_of_legacy_order(self):
        calls = []

        class TeamSettingStub:
            def __init__(self, fixed_team_use=False, fixed_team_use_select=0):
                self.fixed_team_use = fixed_team_use
                self.fixed_team_use_select = fixed_team_use_select

        class SignalStub:
            def emit(self, *args):
                calls.append(("emit", args))

        class AutoStub:
            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

        class CfgStub:
            def __init__(self):
                self.set_mirror_count = 1
                self.infinite_dungeons = False
                self.save_rewards = False
                self.hard_mirror = False
                self.auto_hard_mirror = False
                self.re_claim_rewards = False
                self.teams_active_queue = [3, 1]
                self.teams_order = [1, 2, 3]
                self.config = type(
                    "ConfigStub",
                    (),
                    {
                        "teams": {
                            "1": TeamSettingStub(),
                            "2": TeamSettingStub(),
                            "3": TeamSettingStub(),
                        }
                    },
                )()

            def get_value(self, key):
                if key == "teams_be_select":
                    return [True, False, True]
                raise AssertionError(f"unexpected get_value({key!r})")

            def normalize_and_sync_team_state(self, persist=True):
                calls.append(("normalize", persist, tuple(self.teams_active_queue)))

            def rotate_team_queue(self):
                calls.append(("rotate",))
                self.teams_active_queue = self.teams_active_queue[1:] + self.teams_active_queue[:1]

        cfg_stub = CfgStub()
        mediator_stub = type(
            "MediatorStub",
            (),
            {
                "mirror_signal": SignalStub(),
                "mirror_bar_kill_signal": SignalStub(),
            },
        )()

        def fake_onetime(team_setting, team_num):
            calls.append(("onetime", team_num, team_setting))
            return True

        with (
            patch.object(script_task_scheme, "cfg", cfg_stub),
            patch.object(script_task_scheme, "mediator", mediator_stub),
            patch.object(script_task_scheme, "auto", AutoStub()),
            patch.object(script_task_scheme, "onetime_mir_process", fake_onetime),
            patch.object(script_task_scheme, "to_get_reward", lambda: calls.append(("reward",))),
        ):
            script_task_scheme.Mirror_task()

        self.assertIn(("normalize", False, (3, 1)), calls)
        self.assertIn(("onetime", 3, cfg_stub.config.teams["3"]), calls)

    def test_mirror_task_uses_normalized_queue_before_usefulness_check(self):
        calls = []

        class TeamSettingStub:
            def __init__(self, fixed_team_use=False, fixed_team_use_select=0):
                self.fixed_team_use = fixed_team_use
                self.fixed_team_use_select = fixed_team_use_select

        class SignalStub:
            def emit(self, *args):
                calls.append(("emit", args))

        class AutoStub:
            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

        class CfgStub:
            def __init__(self):
                self.set_mirror_count = 1
                self.infinite_dungeons = False
                self.save_rewards = False
                self.hard_mirror = False
                self.auto_hard_mirror = False
                self.re_claim_rewards = False
                self.teams_active_queue = [99]
                self.config = type(
                    "ConfigStub",
                    (),
                    {
                        "teams": {
                            "1": TeamSettingStub(),
                            "2": TeamSettingStub(),
                        }
                    },
                )()

            def get_value(self, key):
                if key == "teams_be_select":
                    calls.append(("get_selected", tuple(self.teams_active_queue)))
                    return [False, True]
                raise AssertionError(f"unexpected get_value({key!r})")

            def normalize_and_sync_team_state(self, persist=True):
                calls.append(("normalize", persist, tuple(self.teams_active_queue)))
                self.teams_active_queue = [2]

            def rotate_team_queue(self):
                calls.append(("rotate", tuple(self.teams_active_queue)))
                self.teams_active_queue = self.teams_active_queue[1:] + self.teams_active_queue[:1]

        cfg_stub = CfgStub()
        mediator_stub = type(
            "MediatorStub",
            (),
            {
                "mirror_signal": SignalStub(),
                "mirror_bar_kill_signal": SignalStub(),
            },
        )()

        def fake_onetime(team_setting, team_num):
            calls.append(("onetime", team_num, team_setting))
            return True

        with (
            patch.object(script_task_scheme, "cfg", cfg_stub),
            patch.object(script_task_scheme, "mediator", mediator_stub),
            patch.object(script_task_scheme, "auto", AutoStub()),
            patch.object(script_task_scheme, "onetime_mir_process", fake_onetime),
            patch.object(script_task_scheme, "to_get_reward", lambda: calls.append(("reward",))),
        ):
            script_task_scheme.Mirror_task()

        self.assertIn(("normalize", False, (99,)), calls)
        self.assertIn(("get_selected", (2,)), calls)
        self.assertIn(("onetime", 2, cfg_stub.config.teams["2"]), calls)
        self.assertLess(calls.index(("normalize", False, (99,))), calls.index(("get_selected", (2,))))

    def test_mirror_task_rotates_queue_when_fixed_team_use_skips_current_difficulty(self):
        calls = []

        class TeamSettingStub:
            def __init__(self, fixed_team_use=False, fixed_team_use_select=0):
                self.fixed_team_use = fixed_team_use
                self.fixed_team_use_select = fixed_team_use_select

        class SignalStub:
            def emit(self, *args):
                calls.append(("emit", args))

        class AutoStub:
            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

        class CfgStub:
            def __init__(self):
                self.set_mirror_count = 1
                self.infinite_dungeons = False
                self.save_rewards = False
                self.hard_mirror = False
                self.auto_hard_mirror = False
                self.re_claim_rewards = False
                self.teams_active_queue = [2, 1]
                self.teams_order = [2, 1]
                self.rotate_calls = 0
                self.config = type(
                    "ConfigStub",
                    (),
                    {
                        "teams": {
                            "1": TeamSettingStub(),
                            "2": TeamSettingStub(fixed_team_use=True, fixed_team_use_select=0),
                        }
                    },
                )()

            def get_value(self, key):
                if key == "teams_be_select":
                    return [True, True]
                raise AssertionError(f"unexpected get_value({key!r})")

            def normalize_and_sync_team_state(self, persist=True):
                calls.append(("normalize", persist, tuple(self.teams_active_queue)))

            def rotate_team_queue(self):
                self.rotate_calls += 1
                calls.append(("rotate", self.rotate_calls))
                self.teams_active_queue = self.teams_active_queue[1:] + self.teams_active_queue[:1]

        cfg_stub = CfgStub()
        mediator_stub = type(
            "MediatorStub",
            (),
            {
                "mirror_signal": SignalStub(),
                "mirror_bar_kill_signal": SignalStub(),
            },
        )()

        def fake_onetime(team_setting, team_num):
            calls.append(("onetime", team_num, team_setting))
            self.assertEqual(team_num, 1)
            return True

        with (
            patch.object(script_task_scheme, "cfg", cfg_stub),
            patch.object(script_task_scheme, "mediator", mediator_stub),
            patch.object(script_task_scheme, "auto", AutoStub()),
            patch.object(script_task_scheme, "onetime_mir_process", fake_onetime),
            patch.object(script_task_scheme, "to_get_reward", lambda: calls.append(("reward",))),
        ):
            script_task_scheme.Mirror_task()

        self.assertIn(("rotate", 1), calls)
        self.assertIn(("onetime", 1, cfg_stub.config.teams["1"]), calls)
        self.assertLess(calls.index(("rotate", 1)), calls.index(("onetime", 1, cfg_stub.config.teams["1"])))

    def test_mirror_task_rotates_queue_after_successful_run(self):
        calls = []

        class TeamSettingStub:
            def __init__(self, fixed_team_use=False, fixed_team_use_select=0):
                self.fixed_team_use = fixed_team_use
                self.fixed_team_use_select = fixed_team_use_select

        class SignalStub:
            def emit(self, *args):
                calls.append(("emit", args))

        class AutoStub:
            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

        class CfgStub:
            def __init__(self):
                self.set_mirror_count = 1
                self.infinite_dungeons = False
                self.save_rewards = False
                self.hard_mirror = False
                self.auto_hard_mirror = False
                self.re_claim_rewards = False
                self.teams_active_queue = [2, 1]
                self.teams_order = [2, 1]
                self.rotate_calls = 0
                self.config = type(
                    "ConfigStub",
                    (),
                    {
                        "teams": {
                            "1": TeamSettingStub(),
                            "2": TeamSettingStub(),
                        }
                    },
                )()

            def get_value(self, key):
                if key == "teams_be_select":
                    return [True, True]
                raise AssertionError(f"unexpected get_value({key!r})")

            def normalize_and_sync_team_state(self, persist=True):
                calls.append(("normalize", persist, tuple(self.teams_active_queue)))

            def rotate_team_queue(self):
                self.rotate_calls += 1
                calls.append(("rotate", self.rotate_calls, tuple(self.teams_active_queue)))
                self.teams_active_queue = self.teams_active_queue[1:] + self.teams_active_queue[:1]

        cfg_stub = CfgStub()
        mediator_stub = type(
            "MediatorStub",
            (),
            {
                "mirror_signal": SignalStub(),
                "mirror_bar_kill_signal": SignalStub(),
            },
        )()

        def fake_onetime(team_setting, team_num):
            calls.append(("onetime", team_num, team_setting))
            return True

        with (
            patch.object(script_task_scheme, "cfg", cfg_stub),
            patch.object(script_task_scheme, "mediator", mediator_stub),
            patch.object(script_task_scheme, "auto", AutoStub()),
            patch.object(script_task_scheme, "onetime_mir_process", fake_onetime),
            patch.object(script_task_scheme, "to_get_reward", lambda: calls.append(("reward",))),
        ):
            script_task_scheme.Mirror_task()

        self.assertIn(("onetime", 2, cfg_stub.config.teams["2"]), calls)
        self.assertEqual(cfg_stub.rotate_calls, 1)
        self.assertIn(("rotate", 1, (2, 1)), calls)


if __name__ == "__main__":
    unittest.main()
