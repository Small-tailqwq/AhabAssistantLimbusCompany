import unittest
from pathlib import Path

from ruamel.yaml import YAML

from app.theme_pack_setting_interface import (
    CN_OCR_ALTERNATIVES,
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
        cls.asset_dir = Path("assets/app/theme_packs")

    def test_hard_mode_inherits_base_and_adds_hard_exclusive_packs(self):
        self.assertEqual(
            Theme_pack_list.build_setting_key(None, False, "en"),
            ["theme_pack_list"],
        )
        self.assertEqual(
            Theme_pack_list.build_setting_key(None, True, "en"),
            ["theme_pack_list", "theme_pack_list_hard"],
        )
        self.assertEqual(
            Theme_pack_list.build_setting_key(None, True, "zh_cn"),
            ["theme_pack_list_cn", "theme_pack_list_hard_cn"],
        )

    def test_existing_base_and_hard_catalog_classification_is_preserved(self):
        expected_base = {
            "forgot",
            "gambl",
            "nagel",
            "faith",
            "unconf",
            "workshop",
            "tearful",
            "lake",
            "dregs",
            "certain",
            "chick",
            "s.e.a",
            "miracle",
            "bullet",
            "cleaved",
            "penetra",
            "pierced",
            "crushers",
            "repression",
            "addict",
            "seduct",
            "dolen",
            "devoured",
            "cravi",
            "degraded",
            "subserv",
            "nsignif",
            "judgment",
            "outcast",
            "crushed",
            "automated",
            "spring",
            "unloving",
            "flowers",
            "abyss",
            "bones",
            "time",
            "warp",
            "violet",
            "dicers",
            "repressed",
            "treadwheel",
            "flood",
            "vain",
            "check",
            "sweep",
            "Hatred",
            "Wander",
            "dusk",
            "thread",
            "compassion",
            "mnestic",
            "unknown",
        }
        expected_hard_increment = {
            "Theb",
            "b·e",
            "line",
            "seismic",
            "external",
            "thunder",
            "sanguine",
            "dizzying",
            "pang",
            "sigh",
            "supply",
            "four",
            "opening",
            "procession",
            "unchanging",
            "unchang",
            "evil",
            "heartb",
            "unbound",
            "tangling",
            "inert",
            "excessive",
            "sunk",
            "pride",
            "pitiful",
            "haze",
            "season",
            "corpses",
            "might",
            "deluge",
            "poised",
            "ending",
            "witnessing",
            "Text",
            "Blade",
            "Unsever",
        }

        self.assertSetEqual(
            set(map(str, self.default["theme_pack_list"])), expected_base
        )
        self.assertSetEqual(
            set(map(str, self.default["theme_pack_list_hard"])),
            expected_hard_increment,
        )

    def test_catalog_does_not_have_weight_migration(self):
        self.assertFalse(hasattr(Theme_pack_list, "_migrate_theme_pack_catalog"))

    def test_renamed_translations_keep_old_and_new_keys(self):
        """零协 2026-07-18 改名的两个主题包，新旧译名都要能命中且权重一致。"""
        base = self.default["theme_pack_list_cn"]
        for old_name, new_name in (("无作为", "未曾面对"), ("无慈悲", "无法去爱")):
            self.assertIn(new_name, base)
            self.assertEqual(base[new_name], base[old_name])
            self.assertEqual(CN_OCR_ALTERNATIVES[new_name], old_name)

    def test_ocr_alternatives_are_hidden_but_configured(self):
        """OCR 备用名称在 yaml 中有独立权重，但不在设置页展示。"""
        cn_keys = {
            *map(str, self.default["theme_pack_list_cn"]),
            *map(str, self.default["theme_pack_list_hard_cn"]),
        }
        for alternative, main_name in CN_OCR_ALTERNATIVES.items():
            self.assertIn(alternative, cn_keys)
            self.assertIn(main_name, cn_keys)
            self.assertNotIn(alternative, THEME_PACK_CN_IMAGE_MAP)
            self.assertNotIn(alternative, THEME_PACK_CN_HARD_IMAGE_MAP)

    def test_current_llc_names_resolve_to_the_expected_weight_key(self):
        """当前零协译名经排序后命中的 key，必须是设计上对应的那一个。"""
        weights = _specific_theme_keywords_first(
            {
                **{str(key): 0 for key in self.default["theme_pack_list_cn"]},
                **{str(key): 0 for key in self.default["theme_pack_list_hard_cn"]},
            }
        )
        expected = {
            "被遗忘者们": "遗忘",
            "因情感困惑者": "情感困惑",
            "未曾面对": "未曾面对",
            "无法去爱": "无法去爱",
            "切磋琢春": "琢春",
            "善意的巡礼": "巡礼",
            "经验记忆": "经验",
            # 原版与复刻共用一个短 key，OCR 容错率更高。
            "LCB定期体检": "体检",
            "LCB定期体检 复刻": "体检",
            "深夜清扫": "清扫",
            "深夜清扫 复刻": "清扫",
            "肉斩骨断": "骨断",
            "肉斩骨断 复刻": "骨断",
            "时间杀人时间": "时间杀人",
            "时间杀人时间 复刻": "时间杀人",
            "WARP快车谋杀案": "谋杀",
            "WARP快车谋杀案 复刻": "谋杀",
            "20区的奇迹": "区的奇",
            "20区的奇迹 复刻": "区的奇",
            # 压抑的暴怒属于基础列表，解放的暴怒是 HARD 独有。
            "压抑的暴怒": "压抑的",
            "解放的暴怒": "解放的",
            "空转的怠惰": "空转",
            "于情感沉溺者": "沉溺者",
            "1号线": "号线",
            "4号线 - 第3区段": "号线",
        }
        for name, key in expected.items():
            self.assertEqual(self._match(name, weights), key, name)

    def test_english_names_resolve_to_the_expected_weight_key(self):
        """卡包名取自游戏 EN_MirrorDungeonTheme-1.json，短 key 不能抢走同名系列的另一个卡包。"""
        weights = _specific_theme_keywords_first(
            {
                **{str(key): 0 for key in self.default["theme_pack_list"]},
                **{str(key): 0 for key in self.default["theme_pack_list_hard"]},
            }
        )
        expected = {
            # 复刻包与原版共用一个短 key。
            "Miracle in District 20": "miracle",
            "Miracle in District 20 BokGak": "miracle",
            "Timekilling Time": "time",
            "Timekilling Time BokGak": "time",
            "Murder on the WARP Express": "warp",
            "Murder on the WARP Express BokGak": "warp",
            "Yield My Flesh to Claim Their Bones": "bones",
            "Yield My Flesh to Claim Their Bones BokGak": "bones",
            # 基础列表与 HARD 增量列表里的同名系列，各自归位。
            "Nagel and Hammer": "nagel",
            "Thunder and Lightning": "thunder",
            "To be Crushed": "crushed",
            "Crushers & Breakers": "crushers",
            "Repressed Wrath": "repressed",
            "Unbound Wrath": "unbound",
            "Treadwheel Sloth": "treadwheel",
            "Inert Sloth": "inert",
            "Devoured Gluttony": "devoured",
            "Excessive Gluttony": "excessive",
            "Degraded Gloom": "degraded",
            "Sunk Gloom": "sunk",
            "Mnestic Experience": "mnestic",
            "Crushing External Force": "external",
        }
        for name, key in expected.items():
            self.assertEqual(self._match(name, weights), key, name)

    @staticmethod
    def _match(text, weights):
        """复刻 Automation.find_str_in_text 的忽略空格子串匹配。"""
        haystack = str(text).replace(" ", "").lower()
        for key in weights:
            if str(key).replace(" ", "").lower() in haystack:
                return str(key)
        return None

    def test_specific_ocr_keyword_precedes_common_substring(self):
        ordered = _specific_theme_keywords_first({"unchang": 1, "unchanging": 2})
        self.assertEqual(next(iter(ordered)), "unchanging")

    def test_original_and_bokgak_share_one_weight_and_bokgak_cover(self):
        """复刻包与原版共用一个 key 和一份权重，并只展示复刻封面。"""
        base = self.default["theme_pack_list"]
        hard = self.default["theme_pack_list_hard"]
        expected_covers = {
            "check": "LCB Regular Checkup BokGak.png",
            "sweep": "Nocturnal Sweeping BokGak.png",
            "time": "Timekilling Time BokGak.png",
            "warp": "Marder on.the WARP Express BokGak.png",
            "bones": "Vield My Flesh to Claim Their Bones BokGak.png",
            "miracle": "Miracle in District 20 BokGak.png",
        }
        for key, cover in expected_covers.items():
            self.assertIn(key, base)
            self.assertNotIn(key, hard)
            self.assertEqual(THEME_PACK_IMAGE_MAP[key], cover)

        obsolete_originals = (
            "LCB Reguar Checkup.png",
            "Nocturnal Sweeping.png",
            "Timekilling Time.png",
            "Murder on the WARP Express.png",
            "Yield My Flesh to Claim Their Bones.png",
            "Miracle in District 20.png",
        )
        for cover in obsolete_originals:
            self.assertFalse((self.asset_dir / cover).exists(), cover)

    def test_line_packs_use_one_shared_key_and_cover(self):
        self.assertEqual(self.default["theme_pack_list_hard"]["line"], -5)
        self.assertEqual(self.default["theme_pack_list_hard_cn"]["号线"], -5)
        self.assertEqual(THEME_PACK_HARD_IMAGE_MAP["line"], "Line 1.png")
        self.assertEqual(THEME_PACK_CN_HARD_IMAGE_MAP["号线"], "Line 1.png")
        self.assertEqual(
            sorted(path.name for path in self.asset_dir.glob("Line*.png")),
            ["Line 1.png"],
        )

    def test_miracle_rerun_no_longer_has_a_separate_hard_weight(self):
        """20 区奇迹原版与复刻已合并为基础列表的单一权重。"""
        self.assertNotIn("20", self.default["theme_pack_list_hard"])
        self.assertNotIn("20 bokgak", self.default["theme_pack_list_hard"])
        self.assertNotIn("奇迹复刻", self.default["theme_pack_list_hard_cn"])
        self.assertEqual(self.default["theme_pack_list"]["miracle"], 0)
        self.assertEqual(self.default["theme_pack_list_cn"]["区的奇"], 0)

    def test_unknown_fallback_uses_generated_cover_and_low_default_weight(self):
        self.assertEqual(self.default["theme_pack_list"]["unknown"], -5)
        self.assertEqual(self.default["theme_pack_list_cn"]["未知"], -5)
        self.assertEqual(THEME_PACK_IMAGE_MAP["unknown"], "Unknown.png")
        self.assertEqual(THEME_PACK_CN_IMAGE_MAP["未知"], "Unknown.png")
        self.assertEqual(_unknown_theme_weight({"未知": -4}, {}), -4)
        self.assertEqual(_unknown_theme_weight({}, {"unknown": -3}), -3)
        self.assertEqual(_unknown_theme_weight({}, {}), -5)

    def test_every_configured_cover_exists(self):
        self.assertSetEqual(
            set(map(str, self.default["theme_pack_list"])),
            set(THEME_PACK_IMAGE_MAP),
        )
        self.assertSetEqual(
            set(map(str, self.default["theme_pack_list_hard"])),
            set(THEME_PACK_HARD_IMAGE_MAP),
        )
        # OCR 备用名称在设置页不展示，因此不进中文封面映射表。
        self.assertSetEqual(
            set(map(str, self.default["theme_pack_list_cn"])) - set(CN_OCR_ALTERNATIVES),
            set(THEME_PACK_CN_IMAGE_MAP),
        )
        self.assertSetEqual(
            set(map(str, self.default["theme_pack_list_hard_cn"]))
            - set(CN_OCR_ALTERNATIVES),
            set(THEME_PACK_CN_HARD_IMAGE_MAP),
        )
        image_names = {
            *THEME_PACK_IMAGE_MAP.values(),
            *THEME_PACK_HARD_IMAGE_MAP.values(),
        }
        missing = sorted(
            image_name
            for image_name in image_names
            if not (self.asset_dir / image_name).is_file()
        )
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
