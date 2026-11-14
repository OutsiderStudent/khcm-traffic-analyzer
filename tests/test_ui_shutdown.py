"""Queued widget work must not outlive its Qt receiver."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import unittest
from unittest.mock import patch
from PySide6.QtCore import QEvent
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import QApplication
from arterial_analysis.app_fast import InputPage, CompactCellComboBox
from arterial_analysis.app_v2 import FrozenColumnsView
from arterial_analysis.project import ArterialProject

APP = QApplication.instance() or QApplication([])


class ShutdownTest(unittest.TestCase):
    def delete_before_callbacks(self, widget):
        errors = []
        with patch.object(sys, 'excepthook', side_effect=lambda *args: errors.append(args)):
            widget.deleteLater()
            APP.sendPostedEvents(None, QEvent.DeferredDelete)
            APP.processEvents()
        self.assertEqual(errors, [], str([str(e[1]) for e in errors]))

    def test_frozen_anchor_cancelled_when_view_deleted(self):
        view = FrozenColumnsView(2)
        model = QStandardItemModel(2, 3, view)
        view.setModel(model)
        view.scrollTo(model.index(0, 0))
        self.delete_before_callbacks(view)

    def test_responsive_update_cancelled_when_page_deleted(self):
        page = InputPage(ArterialProject())
        self.delete_before_callbacks(page)

    def test_combo_fit_cancelled_when_editor_deleted(self):
        combo = CompactCellComboBox()
        combo.setEditable(True)
        combo.show()
        self.delete_before_callbacks(combo)

    def test_pending_layout_still_runs_for_live_view(self):
        view = FrozenColumnsView(2)
        model = QStandardItemModel(2, 3, view)
        view.setModel(model)
        view.scrollTo(model.index(0, 0))
        view.horizontalHeader().setOffset(20)
        APP.processEvents()
        self.assertEqual(view.horizontalHeader().offset(), 0)
        self.delete_before_callbacks(view)
