import unittest
from unittest.mock import patch

import tasks.daily.get_prize as get_prize_module


class TestGetMailPrize(unittest.TestCase):
    def test_get_mail_prize_returns_false_when_retry_fails(self):
        state = {"screenshots": 0}

        class AutoStub:
            model = "clam"

            def take_screenshot(self):
                state["screenshots"] += 1
                return object()

            def click_element(self, *args, **kwargs):
                raise AssertionError("retry 失败后不应继续点击邮箱控件")

        with (
            patch.object(get_prize_module, "auto", AutoStub()),
            patch.object(get_prize_module, "retry", return_value=False),
        ):
            result = get_prize_module.get_mail_prize()

        self.assertIsInstance(result, float)
        self.assertEqual(state["screenshots"], 1)

    def test_get_mail_prize_waits_for_followup_state_after_claim_all(self):
        actions = []

        class AutoStub:
            def __init__(self):
                self.model = "clam"
                self.confirm_clicks = 0
                self.claim_clicks = 0

            def take_screenshot(self):
                actions.append("screenshot")
                return object()

            def click_element(self, target, *args, **kwargs):
                actions.append(f"click:{target}")
                if target == "mail/get_mail_prize_confirm.png":
                    if self.claim_clicks > 0 and self.confirm_clicks == 0:
                        self.confirm_clicks += 1
                        return True
                    return False
                if target == "mail/claim_all_assets.png":
                    if self.claim_clicks == 0:
                        self.claim_clicks += 1
                        return True
                    return False
                if target == "mail/close_assets.png":
                    return True
                if target == "home/mail_assets.png":
                    return False
                raise AssertionError(f"unexpected click target: {target}")

            def find_element(self, target, *args, **kwargs):
                actions.append(f"find:{target}")
                if target == "mail/get_mail_prize_confirm.png":
                    return self.claim_clicks > 0 and self.confirm_clicks == 0
                if target == "mail/claim_all_assets.png":
                    return False
                raise AssertionError(f"unexpected find target: {target}")

            def mouse_to_blank(self):
                actions.append("blank")

        with (
            patch.object(get_prize_module, "auto", AutoStub()),
            patch.object(get_prize_module, "retry", side_effect=[None, None, None]),
            patch.object(get_prize_module, "sleep", lambda *_: None),
        ):
            result = get_prize_module.get_mail_prize()

        self.assertIsInstance(result, float)
        self.assertIn("find:mail/get_mail_prize_confirm.png", actions)
        self.assertEqual(actions.count("click:mail/close_assets.png"), 1)
        self.assertLess(actions.index("click:mail/claim_all_assets.png"), actions.index("click:mail/close_assets.png"))


if __name__ == "__main__":
    unittest.main()
