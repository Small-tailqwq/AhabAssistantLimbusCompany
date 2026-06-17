import unittest
from unittest.mock import patch

import app.farming_interface as farming_interface


class _ButtonStub:
    def __init__(self, text=""):
        self._text = text
        self.visible = None

    def get_text(self):
        return self._text

    def set_text(self, text):
        self._text = text

    def setVisible(self, visible):
        self.visible = visible


class TestPauseResumeButton(unittest.TestCase):
    def test_farming_interface_pause_shortcut_emits_mediator_signal(self):
        calls = []
        page = farming_interface.FarmingInterface.__new__(farming_interface.FarmingInterface)
        mediator_stub = type(
            "MediatorStub",
            (),
            {"pause_resume": type("SignalStub", (), {"emit": lambda self: calls.append("emit")})()},
        )()

        with patch.object(farming_interface, "mediator", mediator_stub):
            page.my_pause_and_resume()

        self.assertEqual(calls, ["emit"])

    def test_pause_or_resume_tasks_resets_button_when_script_not_running(self):
        page = farming_interface.FarmingInterfaceLeft.__new__(farming_interface.FarmingInterfaceLeft)
        page.link_start_button = _ButtonStub("Link Start!")
        reset_calls = []
        page.reset_pause_resume_button = lambda: reset_calls.append("reset")

        with patch.object(farming_interface.auto, "set_pause", side_effect=AssertionError("should not pause")):
            page.pause_or_resume_tasks()

        self.assertEqual(reset_calls, ["reset"])

    def test_pause_or_resume_tasks_toggles_pause_and_syncs_button_while_running(self):
        calls = []
        page = farming_interface.FarmingInterfaceLeft.__new__(farming_interface.FarmingInterfaceLeft)
        page.link_start_button = _ButtonStub("S t o p !")
        page.sync_pause_resume_button = lambda: calls.append("sync")

        with patch.object(farming_interface.auto, "set_pause", side_effect=lambda: calls.append("pause")):
            page.pause_or_resume_tasks()

        self.assertEqual(calls, ["pause", "sync"])

    def test_sync_pause_resume_button_updates_text_and_visibility(self):
        page = farming_interface.FarmingInterfaceLeft.__new__(farming_interface.FarmingInterfaceLeft)
        page.link_start_button = _ButtonStub("S t o p !")
        page.pause_resume_button = _ButtonStub()
        page.tr = lambda text: text

        with patch.object(farming_interface.auto, "check_pause", return_value=True):
            page.sync_pause_resume_button()

        self.assertEqual(page.pause_resume_button.get_text(), "继续")
        self.assertTrue(page.pause_resume_button.visible)

    def test_reset_pause_resume_button_unpauses_and_hides_button(self):
        calls = []
        page = farming_interface.FarmingInterfaceLeft.__new__(farming_interface.FarmingInterfaceLeft)
        page.pause_resume_button = _ButtonStub()

        with (
            patch.object(farming_interface.auto, "check_pause", return_value=True),
            patch.object(farming_interface.auto, "set_pause", side_effect=lambda: calls.append("pause")),
        ):
            page.reset_pause_resume_button()

        self.assertEqual(calls, ["pause"])
        self.assertFalse(page.pause_resume_button.visible)

    def test_start_and_stop_tasks_stopping_only_requests_safe_stop(self):
        calls = []
        page = farming_interface.FarmingInterfaceLeft.__new__(farming_interface.FarmingInterfaceLeft)
        page.link_start_button = _ButtonStub("S t o p !")
        page.stop_script = lambda: calls.append("stop")
        page.sync_pause_resume_button = lambda: calls.append("sync")
        page.check_setting = lambda: calls.append("check")
        page._disable_setting = lambda parent: calls.append("disable")
        page.create_and_start_script = lambda: calls.append("start")

        page.start_and_stop_tasks()

        self.assertEqual(calls, ["stop"])


if __name__ == "__main__":
    unittest.main()
