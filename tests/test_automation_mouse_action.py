import unittest
from unittest.mock import Mock

import module.automation.automation as automation_module


class TestAutomationMouseAction(unittest.TestCase):
    def test_multi_target_mouse_action_forwards_drag_parameters_by_name(self):
        automation = automation_module.Automation.__new__(automation_module.Automation)
        forwarded_call = Mock(return_value=True)
        automation.mouse_action_with_pos = forwarded_call

        result = automation_module.Automation.mouse_action_with_pos(
            automation,
            [(100, 200)],
            action="drag",
            times=2,
            drag_time=0.75,
            dx=30,
            dy=40,
            find_type="image_with_multiple_targets",
        )

        self.assertTrue(result)
        forwarded_call.assert_called_once_with(
            (100, 200),
            offset=True,
            action="drag",
            times=2,
            drag_time=0.75,
            dx=30,
            dy=40,
            find_type="image",
            interval=1,
        )


if __name__ == "__main__":
    unittest.main()
