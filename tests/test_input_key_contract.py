import unittest

from module.automation.input_handlers import AbstractInput
from module.automation.input_handlers.input import WINDOWS_KEY_CODES, WinAbstractInput
from module.automation.input_handlers.keys import (
    UnsupportedKeyError,
    normalize_key,
    resolve_backend_key,
)
from module.automation.input_handlers.simulator.simulator_control import ANDROID_KEYEVENT_CODES


class DummyInput(AbstractInput):
    KEY_BACKEND = "dummy"
    KEY_CODES = {
        "enter": 13,
        "ctrl": 17,
        "esc": 27,
    }
    KEY_PRESS_DURATION = 0

    def __init__(self):
        super().__init__()
        self.events = []

    def _before_key_input(self, key: str) -> None:
        self.events.append(("before", key))

    def _key_down_impl(self, backend_key):
        self.events.append(("down", backend_key))

    def _key_up_impl(self, backend_key):
        self.events.append(("up", backend_key))


class InputKeyContractTest(unittest.TestCase):
    def test_normalize_key_aliases(self):
        self.assertEqual(normalize_key("return"), "enter")
        self.assertEqual(normalize_key("Control"), "ctrl")
        self.assertEqual(normalize_key("<ctrl>"), "ctrl")
        self.assertEqual(normalize_key("page down"), "pagedown")

    def test_resolve_backend_key_uses_canonical_aliases(self):
        backend_map = {"enter": 66}

        self.assertEqual(resolve_backend_key("return", backend_map, "android"), 66)

    def test_resolve_backend_key_reports_backend(self):
        with self.assertRaises(UnsupportedKeyError) as context:
            resolve_backend_key("enter", {}, "empty")

        self.assertIn("empty", str(context.exception))
        self.assertIn("enter", str(context.exception))

    def test_public_key_press_normalizes_resolves_and_delegates(self):
        input_handler = DummyInput()

        input_handler.key_press("return")

        self.assertEqual(
            input_handler.events,
            [
                ("before", "enter"),
                ("down", 13),
                ("up", 13),
            ],
        )

    def test_public_key_down_and_up_share_contract(self):
        input_handler = DummyInput()

        input_handler.key_down("control")
        input_handler.key_up("control")

        self.assertEqual(
            input_handler.events,
            [
                ("before", "ctrl"),
                ("down", 17),
                ("before", "ctrl"),
                ("up", 17),
            ],
        )

    def test_windows_lparam_marks_extended_keys(self):
        extended_flag = 1 << 24
        key_up_flags = (1 << 30) | (1 << 31)

        for key in ("delete", "pageup", "lwindows", "rwindows"):
            with self.subTest(key=key):
                key_down_lparam = WinAbstractInput._make_key_lparam(WINDOWS_KEY_CODES[key])
                key_up_lparam = WinAbstractInput._make_key_lparam(WINDOWS_KEY_CODES[key], key_up=True)

                self.assertTrue(key_down_lparam & extended_flag)
                self.assertTrue(key_up_lparam & extended_flag)
                self.assertEqual(key_up_lparam & key_up_flags, key_up_flags)

    def test_android_backend_maps_insert_key(self):
        self.assertEqual(resolve_backend_key("insert", ANDROID_KEYEVENT_CODES, "android_keyevent"), 124)


if __name__ == "__main__":
    unittest.main()
