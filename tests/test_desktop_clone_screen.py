import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from module.game_and_screen.screen import Screen


@patch("module.game_and_screen.screen.get_instance_context",
       return_value=SimpleNamespace(is_child_session=True))
class DesktopCloneScreenSizeTests(unittest.TestCase):
    def test_1080p_monitor_accepts_1080p_with_foreground_input(self, _context):
        screen = object.__new__(Screen)
        screen.handle = MagicMock()
        screen.handle.monitor_size.return_value = (1920, 1080)
        screen.handle.width.return_value = 1600
        screen.handle.height.return_value = 900
        stop = MagicMock()

        with (
            patch(
                "module.game_and_screen.screen.cfg",
                SimpleNamespace(
                    background_click=False,
                    win_input_type="foreground",
                    set_win_position="free",
                ),
            ),
            patch(
                "module.game_and_screen.screen.mediator",
                SimpleNamespace(link_start=SimpleNamespace(emit=stop)),
            ),
        ):
            screen.check_win_size(1080)

        stop.assert_not_called()
        self.assertEqual(
            screen.handle.monitor_size.call_args_list,
            [call(), call()],
        )

    def test_monitor_smaller_than_target_resolution_is_rejected(self, _context):
        screen = object.__new__(Screen)
        screen.handle = MagicMock()
        screen.handle.monitor_size.return_value = (1600, 900)
        stop = MagicMock()

        with (
            patch(
                "module.game_and_screen.screen.cfg",
                SimpleNamespace(
                    background_click=False,
                    win_input_type="foreground",
                ),
            ),
            patch(
                "module.game_and_screen.screen.mediator",
                SimpleNamespace(link_start=SimpleNamespace(emit=stop)),
            ),
            patch("module.game_and_screen.screen.sleep"),
        ):
            screen.check_win_size(1080)

        stop.assert_called_once_with()
        self.assertEqual(
            screen.handle.monitor_size.call_args_list,
            [call()],
        )


if __name__ == "__main__":
    unittest.main()
