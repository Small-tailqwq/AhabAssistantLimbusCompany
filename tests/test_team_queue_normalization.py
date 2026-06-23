import tempfile
import unittest
from unittest.mock import patch

from ruamel.yaml import YAML

import app.base_tools as base_tools
import app.farming_interface as farming_interface
import app.my_app as my_app_module
import app.page_card as page_card
import module.automation.automation as automation_module
import module.automation.input_handlers.input as input_module
import module.automation.input_handlers.logitech as logitech_module
import module.config.team_import_export as team_import_export
import module.config.theme_pack_import_export as theme_pack_import_export
import tasks.base.script_task_scheme as script_task_scheme
import utils.utils as utils_module
from module.config.config import Config
from module.config.config_typing import ConfigModel, TeamSetting
from module.my_error.my_error import userStopError
from utils.singletonmeta import SingletonMeta


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

    def test_normalize_does_not_override_runtime_team_selection(self):
        cfg = self.make_config([1, 2, 3])
        cfg.config.teams["1"].team_number = 9
        cfg.config.teams["2"].team_number = 1
        cfg.config.teams["3"].team_number = 1

        cfg.normalize_and_sync_team_state(persist=False)

        self.assertEqual(cfg.config.teams["1"].team_number, 9)
        self.assertEqual(cfg.config.teams["2"].team_number, 1)
        self.assertEqual(cfg.config.teams["3"].team_number, 1)

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

    def test_load_phase_preserves_selected_team_number_fields(self):
        yaml = YAML()
        payload = {
            "teams": {
                "1": {"team_number": 9},
                "2": {"team_number": 1},
                "3": {"team_number": 5},
            },
            "teams_active_queue": [1, 2, 3],
        }

        cfg = Config.__new__(Config)
        cfg.yaml = YAML()
        cfg.config = ConfigModel()
        cfg._schedule_save = lambda *args, **kwargs: None

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = f"{temp_dir}\\config.yaml"
            with open(config_path, "w", encoding="utf-8") as file:
                yaml.dump(payload, file)

            cfg.just_load_config(config_path)

        self.assertEqual(cfg.config.teams["1"].team_number, 9)
        self.assertEqual(cfg.config.teams["2"].team_number, 1)
        self.assertEqual(cfg.config.teams["3"].team_number, 5)

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

    def test_apply_team_settings_preserves_imported_team_number_for_target_slot(self):
        yaml = YAML()
        team_setting = TeamSetting(team_number=9, remark_name="Imported")

        class CfgStub:
            def __init__(self):
                self.config = type("ConfigStub", (), {"teams": {}})()
                self.save_calls = 0

            def save(self):
                self.save_calls += 1

        with tempfile.TemporaryDirectory() as temp_dir:
            theme_weight_path = f"{temp_dir}\\theme_pack_weight_team_7.yaml"

            class ThemeListStub:
                def build_team_weight_path(self, team_num):
                    self.last_team_num = team_num
                    return theme_weight_path

            cfg_stub = CfgStub()
            theme_pack_weight = {"theme_pack_list": {"forgot": 9}}

            with patch.object(team_import_export, "cfg", cfg_stub), patch.object(
                team_import_export,
                "theme_list",
                ThemeListStub(),
            ):
                team_import_export.apply_team_settings(7, team_setting, theme_pack_weight)

            self.assertIs(cfg_stub.config.teams["7"], team_setting)
            self.assertEqual(team_setting.team_number, 9)
            self.assertEqual(cfg_stub.config.teams["7"].team_number, 9)
            self.assertEqual(cfg_stub.save_calls, 1)

            with open(theme_weight_path, "r", encoding="utf-8") as file:
                self.assertEqual(yaml.load(file), theme_pack_weight)

    def test_import_theme_pack_weight_overwrites_existing_file(self):
        yaml = YAML()

        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = f"{temp_dir}\\theme_pack_weight_team_3.yaml"
            import_path = f"{temp_dir}\\import_theme_pack.yaml"

            with open(target_path, "w", encoding="utf-8") as file:
                yaml.dump(
                    {
                        "preferred_thresholds": 5,
                        "theme_pack_list": {"forgot": 1, "gambl": 2},
                    },
                    file,
                )

            imported_data = {"theme_pack_list": {"forgot": 9}}
            with open(import_path, "w", encoding="utf-8") as file:
                yaml.dump(imported_data, file)

            class ThemeListStub:
                def build_team_weight_path(self, team_num):
                    self.last_team_num = team_num
                    return target_path

            with patch.object(theme_pack_import_export, "theme_list", ThemeListStub()):
                self.assertTrue(theme_pack_import_export.import_theme_pack_weight(import_path, 3))

            with open(target_path, "r", encoding="utf-8") as file:
                self.assertEqual(yaml.load(file), imported_data)

    def test_logitech_input_pastes_text_with_ctrl_v(self):
        clipboard_calls = []
        key_calls = []
        focus_calls = []

        def fake_base_init(self):
            self.is_pause = False
            self.restore_time = None

        logitech_cfg = type(
            "CfgStub",
            (),
            {"logitech_dll_path": "", "logitech_bionic_trajectory": True, "set_win_size": 1080},
        )()

        SingletonMeta._instances.pop(logitech_module.LogitechInput, None)
        try:
            with (
                patch.object(logitech_module, "cfg", logitech_cfg),
                patch.object(logitech_module.WinAbstractInput, "__init__", fake_base_init),
            ):
                handler = logitech_module.LogitechInput()

            with (
                patch.object(
                    logitech_module,
                    "pyperclip",
                    type("PyperclipStub", (), {"copy": staticmethod(clipboard_calls.append)})(),
                    create=True,
                ),
                patch.object(logitech_module.LogitechInput, "_ensure_input_focus", lambda self: focus_calls.append("focus")),
                patch.object(logitech_module.LogitechInput, "key_down", lambda self, key: key_calls.append(("down", key))),
                patch.object(logitech_module.LogitechInput, "key_up", lambda self, key: key_calls.append(("up", key))),
                patch.object(logitech_module.HumanKinematics, "human_sleep", lambda *args, **kwargs: None),
            ):
                handler.input_text("TEAMCODE123")
        finally:
            SingletonMeta._instances.pop(logitech_module.LogitechInput, None)

        self.assertEqual(clipboard_calls, ["TEAMCODE123"])
        self.assertEqual(focus_calls, ["focus"])
        self.assertEqual(
            key_calls,
            [("down", "ctrl"), ("down", "v"), ("up", "v"), ("up", "ctrl")],
        )

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
        self.assertIn(("normalize", ("1",)), calls)
        self.assertNotIn(("save",), calls)

    def test_page_mirror_refresh_team_setting_card_compacts_slots_without_rewriting_selected_team_numbers(self):
        page = page_card.PageMirror.__new__(page_card.PageMirror)
        calls = []

        team1 = TeamSetting(team_number=8)
        team2 = TeamSetting(team_number=2)
        team4 = TeamSetting(team_number=7)
        team5 = TeamSetting(team_number=5)
        team6 = TeamSetting(team_number=9)

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
        self.assertEqual(cfg_stub.config.teams["1"].team_number, 8)
        self.assertEqual(cfg_stub.config.teams["2"].team_number, 2)
        self.assertEqual(cfg_stub.config.teams["3"].team_number, 7)
        self.assertEqual(cfg_stub.config.teams["4"].team_number, 5)
        self.assertEqual(cfg_stub.config.teams["5"].team_number, 9)
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

    def test_main_window_close_event_blocks_when_announcement_thread_still_running(self):
        my_app_module.QApplication.instance() or my_app_module.QApplication([])
        calls = []

        class EventStub:
            def __init__(self):
                self.ignored = False

            def ignore(self):
                self.ignored = True

        class AnnouncementThreadStub:
            def isRunning(self):
                return True

            def wait(self, timeout):
                calls.append(("announcement_wait", timeout))
                return False

        class WarningStub:
            def exec(self):
                calls.append(("warning",))

        window = my_app_module.MainWindow.__new__(my_app_module.MainWindow)
        window.x = lambda: 12
        window.y = lambda: 34
        window.isVisible = lambda: True
        window.showNormal = lambda: calls.append(("showNormal",))
        window.raise_ = lambda: calls.append(("raise",))
        window.activateWindow = lambda: calls.append(("activate",))
        window.window = lambda: window
        window.tr = lambda text: text
        window.farming_interface = type("FarmingStub", (), {"interface_left": type("IL", (), {"my_script": None})()})()
        window.tools_interface = type("ToolsStub", (), {"tools": {}})()
        window.announcement_thread = AnnouncementThreadStub()

        cfg_stub = type("CfgStub", (), {"set_value": lambda self, key, value: calls.append((key, value))})()
        event = EventStub()

        with (
            patch.object(my_app_module, "cfg", cfg_stub),
            patch.object(my_app_module, "MessageBoxWarning", lambda *args, **kwargs: WarningStub()),
            patch.object(my_app_module.FramelessWindow, "closeEvent", lambda self, e: calls.append(("super",))),
        ):
            my_app_module.MainWindow.closeEvent(window, event)

        self.assertIn(("announcement_wait", 5000), calls)
        self.assertIn(("warning",), calls)
        self.assertTrue(event.ignored)
        self.assertNotIn(("super",), calls)

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

    def test_automation_exposes_stop_lifecycle_contract(self):
        self.assertTrue(hasattr(automation_module.Automation, "request_stop"))
        self.assertTrue(hasattr(automation_module.Automation, "clear_stop_request"))
        self.assertTrue(hasattr(automation_module.Automation, "ensure_not_stopped"))

    def test_my_script_task_initializes_exception_and_stop_requests_auto(self):
        calls = []
        task = script_task_scheme.my_script_task()

        auto_stub = type("AutoStub", (), {"request_stop": lambda self, reason: calls.append(reason)})()

        with patch.object(script_task_scheme, "auto", auto_stub):
            task.stop("stop-now")

        self.assertIsNone(task.exception)
        self.assertEqual(calls, ["stop-now"])

    def test_my_script_task_run_clears_stop_state_and_disconnects_obs(self):
        calls = []
        task = script_task_scheme.my_script_task()
        task._run = lambda: calls.append(("run",))

        auto_stub = type("AutoStub", (), {"clear_stop_request": lambda self: calls.append(("clear_stop",))})()
        mediator_stub = type(
            "MediatorStub",
            (),
            {"script_finished": type("SignalStub", (), {"emit": lambda self: calls.append(("finished",))})()},
        )()

        with (
            patch.object(script_task_scheme, "auto", auto_stub),
            patch.object(script_task_scheme, "mediator", mediator_stub),
            patch.object(script_task_scheme, "disconnect_obs_capture", lambda: calls.append(("disconnect_obs",)), create=True),
        ):
            task.run()

        self.assertIn(("clear_stop",), calls)
        self.assertIn(("disconnect_obs",), calls)
        self.assertIn(("finished",), calls)

    def test_init_game_passes_stop_checker_into_screen_init_handle(self):
        calls = []

        class AutoStub:
            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

            def init_input(self):
                calls.append(("init_input",))

        class GameProcessStub:
            def start_game(self):
                calls.append(("start_game",))

        class ScreenStub:
            def init_handle(self, stop_checker=None):
                calls.append(("init_handle", callable(stop_checker)))
                return True

            def set_win(self):
                calls.append(("set_win",))

        cfg_stub = type("CfgStub", (), {"simulator": False, "set_windows": True})()

        with (
            patch.object(script_task_scheme, "auto", AutoStub()),
            patch.object(script_task_scheme, "cfg", cfg_stub),
            patch.object(script_task_scheme, "game_process", GameProcessStub()),
            patch.object(script_task_scheme, "screen", ScreenStub()),
        ):
            script_task_scheme.init_game()

        self.assertIn(("init_handle", True), calls)
        self.assertIn(("start_game",), calls)
        self.assertIn(("set_win",), calls)

    def test_script_task_initializes_image_paths_before_waiting_for_main_menu(self):
        calls = []

        class AutoStub:
            def clear_img_cache(self):
                calls.append(("clear_img_cache",))

            def click_element(self, target, *args, **kwargs):
                calls.append(("click_element", target, kwargs.get("take_screenshot")))
                return False

            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

        cfg_stub = type(
            "CfgStub",
            (),
            {
                "skip_enkephalin": False,
                "simulator": False,
                "set_win_size": 1080,
                "resonate_with_Ahab": False,
                "daily_task": False,
                "get_reward": False,
                "buy_enkephalin": False,
                "mirror": False,
                "set_reduce_miscontact": False,
                "lab_screenshot_obs": False,
            },
        )()
        path_manager_stub = type(
            "PathManagerStub",
            (),
            {"initialize_paths": lambda self: calls.append(("initialize_paths",)), "pic_path": []},
        )()

        def wait_for_main_menu(*, allow_restart=True):
            calls.append(("wait_main_menu", allow_restart))
            return "main_menu"

        with (
            patch.object(script_task_scheme, "cfg", cfg_stub),
            patch.object(script_task_scheme, "auto", AutoStub()),
            patch.object(script_task_scheme, "path_manager", path_manager_stub),
            patch.object(script_task_scheme, "_get_game_rendering_scale", return_value=None),
            patch.object(script_task_scheme, "init_game", lambda: calls.append(("init_game",))),
            patch.object(
                script_task_scheme,
                "wait_until_main_menu_after_launch",
                wait_for_main_menu,
                create=True,
            ),
            patch.object(script_task_scheme, "send_toast", lambda *args, **kwargs: calls.append(("send_toast",))),
            patch.object(script_task_scheme.platform, "system", return_value="Linux"),
        ):
            script_task_scheme.script_task()

        self.assertEqual(
            calls[:5],
            [
                ("init_game",),
                ("initialize_paths",),
                ("clear_img_cache",),
                ("click_element", "battle/turn_assets.png", True),
                ("wait_main_menu", True),
            ],
        )

    def test_script_task_falls_back_to_back_init_menu_when_startup_wait_detects_runtime_ui(self):
        calls = []

        class AutoStub:
            def clear_img_cache(self):
                calls.append(("clear_img_cache",))

            def click_element(self, *args, **kwargs):
                return False

            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

        cfg_stub = type(
            "CfgStub",
            (),
            {
                "skip_enkephalin": False,
                "simulator": False,
                "set_win_size": 1080,
                "resonate_with_Ahab": False,
                "daily_task": False,
                "get_reward": False,
                "buy_enkephalin": False,
                "mirror": False,
                "set_reduce_miscontact": False,
                "lab_screenshot_obs": False,
            },
        )()
        path_manager_stub = type(
            "PathManagerStub",
            (),
            {"initialize_paths": lambda self: calls.append(("initialize_paths",)), "pic_path": []},
        )()

        def wait_for_main_menu(*, allow_restart=True):
            calls.append(("wait_main_menu", allow_restart))
            return "runtime_ui"

        def back_to_main_menu(*, allow_restart=True):
            calls.append(("back_init_menu", allow_restart))
            return True

        with (
            patch.object(script_task_scheme, "cfg", cfg_stub),
            patch.object(script_task_scheme, "auto", AutoStub()),
            patch.object(script_task_scheme, "path_manager", path_manager_stub),
            patch.object(script_task_scheme, "_get_game_rendering_scale", return_value=None),
            patch.object(script_task_scheme, "init_game", lambda: calls.append(("init_game",))),
            patch.object(
                script_task_scheme,
                "wait_until_main_menu_after_launch",
                wait_for_main_menu,
                create=True,
            ),
            patch.object(script_task_scheme, "back_init_menu", back_to_main_menu),
            patch.object(script_task_scheme, "send_toast", lambda *args, **kwargs: calls.append(("send_toast",))),
            patch.object(script_task_scheme.platform, "system", return_value="Linux"),
        ):
            script_task_scheme.script_task()

        self.assertIn(("wait_main_menu", True), calls)
        self.assertIn(("back_init_menu", True), calls)
        self.assertLess(calls.index(("wait_main_menu", True)), calls.index(("back_init_menu", True)))

    def test_script_task_raises_when_runtime_ui_recovery_and_back_init_menu_fail(self):
        calls = []

        class AutoStub:
            def clear_img_cache(self):
                calls.append(("clear_img_cache",))

            def click_element(self, *args, **kwargs):
                return False

            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

        cfg_stub = type(
            "CfgStub",
            (),
            {
                "skip_enkephalin": False,
                "simulator": False,
                "set_win_size": 1080,
                "resonate_with_Ahab": False,
                "daily_task": False,
                "get_reward": False,
                "buy_enkephalin": False,
                "mirror": False,
                "set_reduce_miscontact": False,
                "lab_screenshot_obs": False,
            },
        )()
        path_manager_stub = type(
            "PathManagerStub",
            (),
            {"initialize_paths": lambda self: calls.append(("initialize_paths",)), "pic_path": []},
        )()

        def wait_for_main_menu(*, allow_restart=True):
            calls.append(("wait_main_menu", allow_restart))
            return "runtime_ui"

        def back_to_main_menu(*, allow_restart=True):
            calls.append(("back_init_menu", allow_restart))
            return False

        with (
            patch.object(script_task_scheme, "cfg", cfg_stub),
            patch.object(script_task_scheme, "auto", AutoStub()),
            patch.object(script_task_scheme, "path_manager", path_manager_stub),
            patch.object(script_task_scheme, "_get_game_rendering_scale", return_value=None),
            patch.object(script_task_scheme, "init_game", lambda: calls.append(("init_game",))),
            patch.object(
                script_task_scheme,
                "wait_until_main_menu_after_launch",
                wait_for_main_menu,
                create=True,
            ),
            patch.object(script_task_scheme, "back_init_menu", back_to_main_menu),
            patch.object(script_task_scheme, "send_toast", lambda *args, **kwargs: calls.append(("send_toast",))),
            patch.object(script_task_scheme.platform, "system", return_value="Linux"),
            self.assertRaises(script_task_scheme.cannotOperateGameError) as exc_info,
        ):
            script_task_scheme.script_task()

        self.assertEqual(str(exc_info.exception), "启动后未能进入主界面，请手动检查后重试")
        self.assertIn(("wait_main_menu", True), calls)
        self.assertIn(("back_init_menu", True), calls)

    def test_script_task_allows_startup_wait_to_restart_on_timeout(self):
        calls = []

        class AutoStub:
            def clear_img_cache(self):
                calls.append(("clear_img_cache",))

            def click_element(self, *args, **kwargs):
                return False

            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

        cfg_stub = type(
            "CfgStub",
            (),
            {
                "skip_enkephalin": False,
                "simulator": False,
                "set_win_size": 1080,
                "resonate_with_Ahab": False,
                "daily_task": False,
                "get_reward": False,
                "buy_enkephalin": False,
                "mirror": False,
                "set_reduce_miscontact": False,
                "lab_screenshot_obs": False,
            },
        )()
        path_manager_stub = type(
            "PathManagerStub",
            (),
            {"initialize_paths": lambda self: calls.append(("initialize_paths",)), "pic_path": []},
        )()

        def wait_for_main_menu(*, allow_restart=True):
            calls.append(("wait_main_menu", allow_restart))
            return "main_menu" if allow_restart else "timeout"

        with (
            patch.object(script_task_scheme, "cfg", cfg_stub),
            patch.object(script_task_scheme, "auto", AutoStub()),
            patch.object(script_task_scheme, "path_manager", path_manager_stub),
            patch.object(script_task_scheme, "_get_game_rendering_scale", return_value=None),
            patch.object(script_task_scheme, "init_game", lambda: calls.append(("init_game",))),
            patch.object(
                script_task_scheme,
                "wait_until_main_menu_after_launch",
                wait_for_main_menu,
                create=True,
            ),
            patch.object(
                script_task_scheme,
                "back_init_menu",
                side_effect=AssertionError("startup timeout recovery is handled inside wait_until_main_menu_after_launch()"),
            ),
            patch.object(script_task_scheme, "send_toast", lambda *args, **kwargs: calls.append(("send_toast",))),
            patch.object(script_task_scheme.platform, "system", return_value="Linux"),
        ):
            script_task_scheme.script_task()

        self.assertEqual(calls.count(("wait_main_menu", True)), 1)
        self.assertNotIn(("wait_main_menu", False), calls)

    def test_script_task_resumes_battle_before_waiting_for_main_menu(self):
        calls = []

        class AutoStub:
            def clear_img_cache(self):
                calls.append(("clear_img_cache",))

            def click_element(self, target, *args, **kwargs):
                calls.append(("click_element", target, kwargs.get("take_screenshot")))
                return target == "battle/turn_assets.png"

            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

        cfg_stub = type(
            "CfgStub",
            (),
            {
                "skip_enkephalin": False,
                "simulator": False,
                "set_win_size": 1080,
                "resonate_with_Ahab": False,
                "daily_task": False,
                "get_reward": False,
                "buy_enkephalin": False,
                "mirror": False,
                "set_reduce_miscontact": False,
                "lab_screenshot_obs": False,
            },
        )()
        path_manager_stub = type(
            "PathManagerStub",
            (),
            {"initialize_paths": lambda self: calls.append(("initialize_paths",)), "pic_path": []},
        )()
        battle_stub = type(
            "BattleStub",
            (),
            {"fight": lambda self=None: calls.append(("battle_fight",)) or "battle_resumed"},
        )()

        def wait_for_main_menu(*, allow_restart=True):
            calls.append(("wait_main_menu", allow_restart))
            raise AssertionError("battle recovery should skip main menu wait")

        with (
            patch.object(script_task_scheme, "cfg", cfg_stub),
            patch.object(script_task_scheme, "auto", AutoStub()),
            patch.object(script_task_scheme, "path_manager", path_manager_stub),
            patch.object(script_task_scheme, "battle", battle_stub),
            patch.object(script_task_scheme, "_get_game_rendering_scale", return_value=None),
            patch.object(script_task_scheme, "init_game", lambda: calls.append(("init_game",))),
            patch.object(
                script_task_scheme,
                "wait_until_main_menu_after_launch",
                wait_for_main_menu,
                create=True,
            ),
            patch.object(script_task_scheme, "send_toast", lambda *args, **kwargs: calls.append(("send_toast",))),
            patch.object(script_task_scheme.platform, "system", return_value="Linux"),
        ):
            script_task_scheme.script_task()

        self.assertIn(("click_element", "battle/turn_assets.png", True), calls)
        self.assertIn(("battle_fight",), calls)
        self.assertNotIn(("wait_main_menu", True), calls)
        self.assertLess(
            calls.index(("click_element", "battle/turn_assets.png", True)),
            calls.index(("battle_fight",)),
        )

    def test_script_task_validates_obs_capture_before_running(self):
        calls = []

        class AutoStub:
            def clear_img_cache(self):
                calls.append(("clear_img_cache",))

            def click_element(self, *args, **kwargs):
                calls.append(("click_element", args[0]))
                return False

            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

        class ObsStub:
            def validate_capture_ready(self):
                calls.append(("validate_capture_ready",))
                return False, "obs not ready"

        cfg_stub = type(
            "CfgStub",
            (),
            {
                "skip_enkephalin": False,
                "simulator": False,
                "set_win_size": 1080,
                "resonate_with_Ahab": False,
                "daily_task": False,
                "get_reward": False,
                "buy_enkephalin": False,
                "mirror": False,
                "set_reduce_miscontact": False,
                "lab_screenshot_obs": True,
            },
        )()
        mediator_stub = type(
            "MediatorStub",
            (),
            {"warning": type("SignalStub", (), {"emit": lambda self, msg: calls.append(("warning", msg))})()},
        )()
        path_manager_stub = type(
            "PathManagerStub",
            (),
            {"initialize_paths": lambda self: calls.append(("initialize_paths",)), "pic_path": []},
        )()

        with (
            patch.object(script_task_scheme, "cfg", cfg_stub),
            patch.object(script_task_scheme, "auto", AutoStub()),
            patch.object(script_task_scheme, "mediator", mediator_stub),
            patch.object(script_task_scheme, "path_manager", path_manager_stub),
            patch.object(script_task_scheme, "init_game", lambda: calls.append(("init_game",))),
            patch.object(
                script_task_scheme,
                "wait_until_main_menu_after_launch",
                lambda allow_restart=True: calls.append(("wait_main_menu", allow_restart)) or "main_menu",
                create=True,
            ),
            patch.object(script_task_scheme, "get_obs_capture", lambda: ObsStub(), create=True),
            self.assertRaises(script_task_scheme.cannotOperateGameError),
        ):
            script_task_scheme.script_task()

        self.assertIn(("validate_capture_ready",), calls)
        self.assertIn(("warning", "obs not ready"), calls)

    def test_script_task_obs_not_ready_fails_before_main_menu_wait(self):
        calls = []

        class AutoStub:
            def clear_img_cache(self):
                calls.append(("clear_img_cache",))

            def click_element(self, *args, **kwargs):
                calls.append(("click_element", args[0]))
                return False

            def ensure_not_stopped(self):
                calls.append(("ensure_not_stopped",))

        class ObsStub:
            def validate_capture_ready(self):
                calls.append(("validate_capture_ready",))
                return False, "obs not ready"

        cfg_stub = type(
            "CfgStub",
            (),
            {
                "skip_enkephalin": False,
                "simulator": False,
                "set_win_size": 1080,
                "resonate_with_Ahab": False,
                "daily_task": False,
                "get_reward": False,
                "buy_enkephalin": False,
                "mirror": False,
                "set_reduce_miscontact": False,
                "lab_screenshot_obs": True,
            },
        )()
        mediator_stub = type(
            "MediatorStub",
            (),
            {"warning": type("SignalStub", (), {"emit": lambda self, msg: calls.append(("warning", msg))})()},
        )()
        path_manager_stub = type(
            "PathManagerStub",
            (),
            {"initialize_paths": lambda self: calls.append(("initialize_paths",)), "pic_path": []},
        )()

        with (
            patch.object(script_task_scheme, "cfg", cfg_stub),
            patch.object(script_task_scheme, "auto", AutoStub()),
            patch.object(script_task_scheme, "mediator", mediator_stub),
            patch.object(script_task_scheme, "path_manager", path_manager_stub),
            patch.object(script_task_scheme, "init_game", lambda: calls.append(("init_game",))),
            patch.object(
                script_task_scheme,
                "wait_until_main_menu_after_launch",
                lambda allow_restart=True: calls.append(("wait_main_menu", allow_restart)) or "main_menu",
                create=True,
            ),
            patch.object(script_task_scheme, "get_obs_capture", lambda: ObsStub(), create=True),
            self.assertRaises(script_task_scheme.cannotOperateGameError),
        ):
            script_task_scheme.script_task()

        self.assertEqual(calls[:3], [("init_game",), ("validate_capture_ready",), ("warning", "obs not ready")])
        self.assertNotIn(("initialize_paths",), calls)
        self.assertNotIn(("wait_main_menu", True), calls)

    def test_automation_init_input_prefers_logitech_handler_when_enabled(self):
        class FakeBaseInput(automation_module.AbstractInput):
            def mouse_click(self, *args, **kwargs):
                return True

            def mouse_click_blank(self, *args, **kwargs):
                return True

            def mouse_drag(self, *args, **kwargs):
                return None

            def mouse_drag_down(self, *args, **kwargs):
                return None

            def mouse_drag_link(self, *args, **kwargs):
                return None

            def mouse_scroll(self, *args, **kwargs):
                return True

            def mouse_to_blank(self, *args, **kwargs):
                return None

            def key_press(self, *args, **kwargs):
                return None

            def input_text(self, *args, **kwargs):
                return None

        class FakeLogitechInput(FakeBaseInput):
            pass

        class FakeBackgroundInput(FakeBaseInput):
            pass

        cfg_stub = type(
            "CfgStub",
            (),
            {
                "simulator": False,
                "simulator_type": 0,
                "win_input_type": "background",
                "lab_mouse_logitech": True,
                "memory_protection": False,
            },
        )()

        automation = automation_module.Automation.__new__(automation_module.Automation)
        automation.input_handler = None

        with (
            patch.object(automation_module, "cfg", cfg_stub),
            patch.object(logitech_module, "LogitechInput", FakeLogitechInput),
            patch.object(input_module, "BackgroundInput", FakeBackgroundInput),
        ):
            automation_module.Automation.init_input(automation)

        self.assertIsInstance(automation.input_handler, FakeLogitechInput)

    def test_automation_click_element_accepts_and_forwards_log_result(self):
        automation = automation_module.Automation.__new__(automation_module.Automation)
        automation.model = "clam"
        captured = {}

        def fake_find_element(*args, **kwargs):
            captured["kwargs"] = kwargs
            return (10, 20)

        automation.find_element = fake_find_element

        result = automation_module.Automation.click_element(
            automation,
            "mirror/road_in_mir/enter_assets.png",
            click=False,
            log_result=False,
        )

        self.assertEqual(result, (10, 20))
        self.assertIn("log_result", captured["kwargs"])
        self.assertFalse(captured["kwargs"]["log_result"])

    def test_logitech_input_focus_waiting_respects_stop_checker(self):
        checks = []

        class SignalStub:
            def __init__(self, name):
                self.name = name
                self.events = []

            def emit(self, *args):
                self.events.append((self.name, args))

        mediator_stub = type(
            "MediatorStub",
            (),
            {
                "warning": SignalStub("warning"),
                "warning_clear": SignalStub("warning_clear"),
            },
        )()

        logitech_input = logitech_module.LogitechInput.__new__(logitech_module.LogitechInput)
        logitech_input._focus_waiting_notified = False

        def stop_checker():
            checks.append("checked")
            raise userStopError("stop")

        ready_state = {"count": 0}

        def fake_ready():
            ready_state["count"] += 1
            return ready_state["count"] >= 2

        logitech_input.stop_checker = stop_checker

        with (
            patch.object(logitech_module, "mediator", mediator_stub),
            patch.object(logitech_module.screen, "ensure_direct_input_ready", side_effect=fake_ready),
            patch.object(logitech_module.HumanKinematics, "human_sleep", lambda *args, **kwargs: None),
        ):
            with self.assertRaises(userStopError):
                logitech_input._ensure_input_focus()

        self.assertIn("checked", checks)


if __name__ == "__main__":
    unittest.main()
