import sys
import unittest
from types import ModuleType
from unittest import mock

from debug_tools import check_hdr
from module.game_and_screen import hdr


class TestColorSpaceName(unittest.TestCase):
    def test_sdr_color_space(self):
        self.assertEqual(hdr.color_space_name(0), "RGB_FULL_G22_NONE_P709")

    def test_hdr_color_space(self):
        self.assertEqual(hdr.color_space_name(12), "RGB_FULL_G2084_NONE_P2020")

    def test_unknown_color_space(self):
        result = hdr.color_space_name(999)
        self.assertIn("UNKNOWN", result)
        self.assertIn("999", result)


class TestFormatMonitorInfo(unittest.TestCase):
    def test_format_hdr_monitor(self):
        info = hdr.HdrDisplayInfo(
            monitor_handle=1,
            device_name=r"\\.\DISPLAY1",
            friendly_name="Dell U2720Q",
            is_primary=True,
            desktop_rect=(0, 0, 3840, 2160),
            attached_to_desktop=True,
            bits_per_color=10,
            color_space=12,
            max_luminance=350.0,
            min_luminance=0.1,
            max_full_frame_luminance=350.0,
        )
        result = check_hdr.format_monitor_info(info, 1)
        self.assertIn("HDR 已开启: 是", result)
        self.assertIn("Dell U2720Q", result)
        self.assertIn("主显示器: 是", result)
        self.assertIn("每通道位数: 10", result)

    def test_format_sdr_monitor(self):
        info = hdr.HdrDisplayInfo(
            monitor_handle=1,
            device_name=r"\\.\DISPLAY1",
            color_space=0,
        )
        result = check_hdr.format_monitor_info(info, 1)
        self.assertIn("HDR 已开启: 否", result)


class TestHdrDetectionModule(unittest.TestCase):
    def test_pq_bt2020_color_space_is_hdr(self):
        info = hdr.HdrDisplayInfo(
            monitor_handle=1,
            device_name=r"\\.\DISPLAY1",
            color_space=12,
        )

        self.assertTrue(info.hdr_enabled)
        self.assertEqual(
            hdr.color_space_name(info.color_space),
            "RGB_FULL_G2084_NONE_P2020",
        )

    def test_get_monitor_hdr_info_returns_only_matching_monitor(self):
        first = hdr.HdrDisplayInfo(monitor_handle=1, device_name=r"\\.\DISPLAY1")
        second = hdr.HdrDisplayInfo(monitor_handle=2, device_name=r"\\.\DISPLAY2")

        with mock.patch.object(
            hdr,
            "enumerate_hdr_displays",
            return_value=[first, second],
        ):
            result = hdr.get_monitor_hdr_info(2)

        self.assertIs(result, second)

    def test_get_monitor_hdr_info_returns_none_when_output_is_missing(self):
        with mock.patch.object(hdr, "enumerate_hdr_displays", return_value=[]):
            result = hdr.get_monitor_hdr_info(999)

        self.assertIsNone(result)

    def test_com_initialization_failure_returns_empty_without_uninitialize(self):
        with (
            mock.patch.object(
                hdr._ole32,
                "CoInitializeEx",
                return_value=-2147417850,
            ),
            mock.patch.object(hdr._ole32, "CoUninitialize") as uninitialize,
        ):
            result = hdr.enumerate_hdr_displays()

        self.assertEqual(result, [])
        uninitialize.assert_not_called()


class TestMonitorInfoEnrichment(unittest.TestCase):
    def test_reads_monitor_name_from_display_adapter(self):
        desc = hdr.DXGI_OUTPUT_DESC1()
        desc.DeviceName = r"\\.\DISPLAY1"
        desc.Monitor = 123

        fake_win32api = ModuleType("win32api")
        fake_win32api.GetMonitorInfo = mock.Mock(
            return_value={"Flags": 1, "Device": r"\\.\DISPLAY1"}
        )
        display_device = mock.Mock()
        display_device.DeviceString = "Generic PnP Monitor"
        fake_win32api.EnumDisplayDevices = mock.Mock(return_value=display_device)

        with mock.patch.dict(sys.modules, {"win32api": fake_win32api}):
            info = hdr._build_display_info(desc)

        self.assertEqual(info.friendly_name, "Generic PnP Monitor")
        fake_win32api.EnumDisplayDevices.assert_called_once_with(
            r"\\.\DISPLAY1", 0, 0
        )


if __name__ == "__main__":
    unittest.main()
