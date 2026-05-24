import unittest

from tasks.mirror.in_shop import _filter_enhance_gift_scan_points


class TestShopEnhanceRegionFilter(unittest.TestCase):
    def test_filter_removes_out_of_region_points_on_1080p(self):
        points = [
            (1066, 570),
            (1204, 569),
            (1617, 704),
            (1825, 580),
            (1849, 141),
            (533, 765),
        ]

        filtered = _filter_enhance_gift_scan_points(points, (1920, 1080))

        self.assertEqual(filtered, [(1066, 570), (1204, 569), (1617, 704)])

    def test_filter_is_resolution_relative_on_2k(self):
        points = [
            (1500, 700),
            (1420, 761),
            (2433, 772),
            (2465, 188),
        ]

        filtered = _filter_enhance_gift_scan_points(points, (2560, 1440))

        self.assertEqual(filtered, [(1500, 700), (1420, 761)])

    def test_filter_keeps_points_when_size_is_missing(self):
        points = [(100, 100), (200, 200)]

        filtered = _filter_enhance_gift_scan_points(points, None)

        self.assertEqual(filtered, points)


if __name__ == "__main__":
    unittest.main()
