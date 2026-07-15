import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_hdr",
    Path(__file__).parent.parent / "debug_tools" / "check_hdr.py",
)
check_hdr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_hdr)


class TestColorSpaceName(unittest.TestCase):
    def test_sdr_color_space(self):
        self.assertEqual(check_hdr.color_space_name(0), "RGB_FULL_G22_NONE_P709")

    def test_hdr_color_space(self):
        self.assertEqual(check_hdr.color_space_name(16), "RGB_FULL_G2084_NONE_P2020")

    def test_unknown_color_space(self):
        result = check_hdr.color_space_name(999)
        self.assertIn("UNKNOWN", result)
        self.assertIn("999", result)


class TestFormatMonitorInfo(unittest.TestCase):
    def test_format_hdr_monitor(self):
        info = check_hdr.MonitorInfo(
            device_name=r"\\.\DISPLAY1",
            friendly_name="Dell U2720Q",
            is_primary=True,
            desktop_rect=(0, 0, 3840, 2160),
            attached_to_desktop=True,
            hdr_enabled=True,
            hdr_supported=True,
            bits_per_color=10,
            color_space=16,
            color_space_name="RGB_FULL_G2084_NONE_P2020",
            max_luminance=350.0,
            min_luminance=0.1,
            max_full_frame_luminance=350.0,
        )
        result = check_hdr.format_monitor_info(info, 1)
        self.assertIn("HDR 已开启: 是", result)
        self.assertIn("Dell U2720Q", result)
        self.assertIn("主显示器: 是", result)
        self.assertIn("10", result)

    def test_format_sdr_monitor(self):
        info = check_hdr.MonitorInfo(
            device_name=r"\\.\DISPLAY1",
            hdr_enabled=False,
            hdr_supported=True,
            color_space=0,
            color_space_name="RGB_FULL_G22_NONE_P709",
        )
        result = check_hdr.format_monitor_info(info, 1)
        self.assertIn("HDR 已开启: 否", result)

    def test_format_unsupported_monitor(self):
        info = check_hdr.MonitorInfo(
            device_name=r"\\.\DISPLAY1",
            hdr_supported=False,
        )
        result = check_hdr.format_monitor_info(info, 1)
        self.assertIn("不支持 HDR 检测", result)


if __name__ == "__main__":
    unittest.main()
