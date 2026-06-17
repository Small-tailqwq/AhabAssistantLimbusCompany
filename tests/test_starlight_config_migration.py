import tempfile
import unittest
from pathlib import Path

from ruamel.yaml import YAML

import module.config.team_import_export as team_import_export
from module.config.config import migrate_legacy_team_setting_data


class TestStarlightConfigMigration(unittest.TestCase):
    def test_migrate_new_starlight_shape_into_legacy_fields(self):
        migrated = migrate_legacy_team_setting_data({"opening_bonus": [1, 3, 0, 2, 0, 0, 0, 0, 0, 0]})

        self.assertTrue(migrated["choose_opening_bonus"])
        self.assertEqual(migrated["opening_bonus_select"], 3)
        self.assertEqual(migrated["opening_bonus"], [1, 1, 0, 1, 0, 0, 0, 0, 0, 0])
        self.assertEqual(migrated["opening_bonus_order"], [1, 2, 0, 3, 0, 0, 0, 0, 0, 0])
        self.assertEqual(migrated["opening_bonus_level"], [0, 2, 0, 1, 0, 0, 0, 0, 0, 0])

    def test_migrate_default_new_starlight_shape_preserves_non_custom_behavior(self):
        migrated = migrate_legacy_team_setting_data({"opening_bonus": [1, 1, 1, 1, 0, 0, 0, 0, 0, 0]})

        self.assertFalse(migrated["choose_opening_bonus"])
        self.assertEqual(migrated["opening_bonus_select"], 0)
        self.assertEqual(migrated["opening_bonus"], [0] * 10)
        self.assertEqual(migrated["opening_bonus_order"], [0] * 10)
        self.assertEqual(migrated["opening_bonus_level"], [0] * 10)

    def test_import_team_settings_accepts_new_starlight_shape(self):
        yaml = YAML()
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "team.yaml"
            with file_path.open("w", encoding="utf-8") as handle:
                yaml.dump({"opening_bonus": [1, 0, 2, 0, 0, 0, 0, 0, 0, 0]}, handle)

            team_setting, theme_pack_weight, missing_fields = team_import_export.import_team_settings(str(file_path), 1)

        self.assertIsNotNone(team_setting)
        self.assertIsNone(theme_pack_weight)
        self.assertEqual(missing_fields, [])
        self.assertTrue(team_setting.choose_opening_bonus)
        self.assertEqual(team_setting.opening_bonus, [1, 0, 1, 0, 0, 0, 0, 0, 0, 0])
        self.assertEqual(team_setting.opening_bonus_order, [1, 0, 2, 0, 0, 0, 0, 0, 0, 0])
        self.assertEqual(team_setting.opening_bonus_level, [0, 0, 1, 0, 0, 0, 0, 0, 0, 0])


if __name__ == "__main__":
    unittest.main()
