import copy
import unittest
from pathlib import Path

from ruamel.yaml import YAML

from app.theme_pack_setting_interface import (
    THEME_PACK_CN_HARD_IMAGE_MAP,
    THEME_PACK_CN_IMAGE_MAP,
    THEME_PACK_HARD_IMAGE_MAP,
    THEME_PACK_IMAGE_MAP,
)
from module.config.config import Theme_pack_list
from tasks.mirror.select_theme_pack import (
    _specific_theme_keywords_first,
    _unknown_theme_weight,
)


class ThemePackCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.default = YAML().load(Path("assets/config/theme_pack_list.example.yaml"))

    def test_legacy_weights_move_to_current_catalog(self):
        legacy = copy.deepcopy(self.default)
        legacy["theme_pack_list"]["sweep"] = 7
        legacy["theme_pack_list_hard"]["line"] = 3
        legacy["theme_pack_list_cn"]["清扫"] = 7
        legacy["theme_pack_list_hard_cn"]["号线"] = 3

        Theme_pack_list._migrate_theme_pack_catalog(legacy, self.default)

        self.assertNotIn("sweep", legacy["theme_pack_list"])
        self.assertEqual(legacy["theme_pack_list_hard"]["sweep"], 7)
        self.assertNotIn("line", legacy["theme_pack_list_hard"])
        self.assertNotIn("清扫", legacy["theme_pack_list_cn"])
        self.assertEqual(legacy["theme_pack_list_hard_cn"]["深夜清扫"], 7)
        self.assertNotIn("号线", legacy["theme_pack_list_hard_cn"])

    def test_existing_new_key_weight_wins_over_legacy_weight(self):
        legacy = copy.deepcopy(self.default)
        legacy["theme_pack_list"]["sweep"] = 7
        legacy["theme_pack_list_hard"]["sweep"] = 9

        Theme_pack_list._migrate_theme_pack_catalog(legacy, self.default)

        self.assertEqual(legacy["theme_pack_list_hard"]["sweep"], 9)

    def test_specific_ocr_keyword_precedes_common_substring(self):
        ordered = _specific_theme_keywords_first({"清扫": 1, "深夜清扫复刻": 2})
        self.assertEqual(next(iter(ordered)), "深夜清扫复刻")

    def test_original_and_bokgak_share_one_weight_and_bokgak_cover(self):
        self.assertEqual(THEME_PACK_IMAGE_MAP["check"], "LCB Regular Checkup BokGak.png")
        self.assertEqual(THEME_PACK_HARD_IMAGE_MAP["sweep"], "Nocturnal Sweeping BokGak.png")

    def test_miracle_bokgak_is_active_hard_pack(self):
        legacy = copy.deepcopy(self.default)
        legacy["theme_pack_list_hard"][20] = 6
        legacy["theme_pack_list_hard_cn"]["奇迹复刻"] = 6

        Theme_pack_list._migrate_theme_pack_catalog(legacy, self.default)

        self.assertEqual(legacy["theme_pack_list_hard"][20], 6)
        self.assertEqual(legacy["theme_pack_list_hard_cn"]["奇迹复刻"], 6)
        self.assertEqual(self.default["theme_pack_list_hard"][20], 0)
        self.assertEqual(self.default["theme_pack_list_hard_cn"]["奇迹复刻"], 0)
        self.assertEqual(
            THEME_PACK_HARD_IMAGE_MAP["20"], "Miracle in District 20 BokGak.png"
        )
        self.assertEqual(
            THEME_PACK_CN_HARD_IMAGE_MAP["奇迹复刻"], "Miracle in District 20 BokGak.png"
        )

    def test_unknown_fallback_uses_generated_cover_and_low_default_weight(self):
        self.assertEqual(self.default["theme_pack_list"]["unknown"], -5)
        self.assertEqual(self.default["theme_pack_list_cn"]["未知"], -5)
        self.assertEqual(THEME_PACK_IMAGE_MAP["unknown"], "Unknown.png")
        self.assertEqual(THEME_PACK_CN_IMAGE_MAP["未知"], "Unknown.png")
        self.assertEqual(_unknown_theme_weight({"未知": -4}, {}), -4)
        self.assertEqual(_unknown_theme_weight({}, {"unknown": -3}), -3)
        self.assertEqual(_unknown_theme_weight({}, {}), -5)


if __name__ == "__main__":
    unittest.main()
