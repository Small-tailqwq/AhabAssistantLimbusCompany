import unittest

from PySide6.QtWidgets import QApplication

from app.page_card import PageDailyTask, build_continuous_combat_preview


class TestDailyTaskPreview(unittest.TestCase):
    def test_formats_exp_and_thread_continuous_combat_batches(self):
        self.assertEqual(
            build_continuous_combat_preview(exp_times=10, thread_times=3, max_times=3),
            "当前经验本连战：\n10=3->3->3->1\n当前纽本连战：\n3=3",
        )

    def test_omits_zero_count_dungeons(self):
        self.assertEqual(
            build_continuous_combat_preview(exp_times=0, thread_times=5, max_times=2),
            "当前纽本连战：\n5=2->2->1",
        )

    def test_daily_task_page_can_initialize_when_continuous_combat_is_disabled(self):
        app = QApplication.instance() or QApplication([])
        page = PageDailyTask()

        self.assertFalse(page.continuous_combat_preview.isVisible())
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
