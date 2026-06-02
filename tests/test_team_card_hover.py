import unittest
from unittest import mock

from PySide6.QtCore import QAbstractAnimation, QEvent, QRect, QSize
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QApplication

from app.base_combination import SinnerSelect


class TestTeamCardHover(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])

    def _create_card(self):
        card = SinnerSelect("YiSang", "Yi Sang")
        card.setGeometry(10, 20, 155, 239)
        card.show()
        self.app.processEvents()
        self.addCleanup(card.close)
        self.addCleanup(card.deleteLater)
        return card

    def test_resize_during_running_hover_animation_keeps_base_geometry(self):
        card = self._create_card()
        base_geom = QRect(card.geometry())
        card.raw_geom = QRect(base_geom)

        resize_event = QResizeEvent(QSize(170, 262), QSize(155, 239))

        with mock.patch.object(card.ani, "state", return_value=QAbstractAnimation.State.Running):
            card.resizeEvent(resize_event)

        self.assertEqual(card.raw_geom, base_geom)

    def test_leave_after_running_hover_resize_targets_original_geometry(self):
        card = self._create_card()
        base_geom = QRect(card.geometry())
        hovered_geom = QRect(3, 8, 170, 262)

        card.setMaximumSize(hovered_geom.width(), hovered_geom.height())
        card.setGeometry(hovered_geom)
        self.app.processEvents()

        card.raw_geom = QRect(base_geom)
        card._end_geom = QRect(hovered_geom)

        resize_event = QResizeEvent(QSize(170, 262), QSize(155, 239))
        with mock.patch.object(card.ani, "state", return_value=QAbstractAnimation.State.Running):
            card.resizeEvent(resize_event)

        card.leaveEvent(QEvent(QEvent.Type.Leave))

        self.assertEqual(card.ani.endValue(), base_geom)


if __name__ == "__main__":
    unittest.main()
