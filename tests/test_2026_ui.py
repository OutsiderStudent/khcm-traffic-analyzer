import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QInputDialog
from PySide6.QtCore import QEvent
from arterial_analysis.app_fast import MainWindow
from arterial_analysis.engine_2026 import official_example
from arterial_analysis.project import ArterialProject

APP=QApplication.instance() or QApplication([])


class EditionUiTest(unittest.TestCase):
    def setUp(self):self.window=MainWindow()
    def tearDown(self):
        APP.clipboard().clear()
        self.window.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()

    def test_new_corridor_requires_scope_and_data(self):
        page=self.window.beta_page;page.add_corridor();page.add_row()
        self.assertFalse(page.urban.isChecked())
        self.assertEqual(page.table.cellWidget(0,1).value(),0)
        self.assertFalse(page.analyze())
        self.assertIn("확인",page.result.toPlainText())

    def test_only_inputs_for_selected_speed_method_are_shown(self):
        page = self.window.beta_page
        self.window.project.corridors_2026 = [official_example(2).to_dict()]
        page.load_project(self.window.project)
        for index, show_time, show_speed, show_delay in (
            (0, False, False, True),
            (1, True, False, False),
            (2, False, True, False),
            (0, False, False, True),
        ):
            page.method.setCurrentIndex(index)
            self.assertEqual(page.method_form.isRowVisible(page.times), show_time)
            self.assertEqual(page.method_form.isRowVisible(page.speeds), show_speed)
            self.assertEqual(not page.table.isColumnHidden(5), show_delay)
        self.assertEqual(page.table.cellWidget(0, 5).value(), 44.5)

    def test_wheel_keeps_numeric_cells_and_dialog_fields_unchanged(self):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        from PySide6.QtTest import QTest
        from arterial_analysis.app_fast import FastDetailDialog

        w = self.window
        page = w.beta_page
        w.project.corridors_2026 = [official_example(2).to_dict()]
        page.load_project(w.project)
        dialog = FastDetailDialog(w.project.segments[0], w.project, w)
        for field in (page.table.cellWidget(0, 1), dialog.base):
            original = field.value()
            field.setFocus()
            for target in (field, field.lineEdit()):
                event = QWheelEvent(QPointF(), QPointF(), QPoint(), QPoint(0, 120),
                                    Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False)
                APP.sendEvent(target, event)
                self.assertEqual(field.value(), original)
            QTest.keyClick(field, Qt.Key_Up)
            self.assertGreater(field.value(), original)

    def test_reorder_preserves_delay_and_capacity(self):
        w=self.window;w.project.corridors_2026=[official_example().to_dict()];w.beta_page.load_project(w.project)
        page=w.beta_page;page.table.cellWidget(0,6).setValue(1500);page.table.selectRow(0);page.move_row(1)
        c=page.current();self.assertEqual(c.subsegments[1].end_name,"교차로 B")
        self.assertEqual(c.subsegments[1].capacity_vph,1500)
        self.assertEqual(c.subsegments[1].delay_s,44.5)

    def test_speeds_and_source_survive_save_and_html_copy(self):
        w=self.window;w.project.corridors_2026=[official_example(1).to_dict()];page=w.beta_page;page.load_project(w.project)
        page.method.setCurrentIndex(2);page.speeds.setText("20, 40");page.source.setText("조사자료 <A>");page.commit()
        self.assertTrue(page.analyze());self.assertIn("26.7",page.result.toPlainText())
        page.copy_result();self.assertTrue(APP.clipboard().mimeData().hasHtml())
        restored=ArterialProject.from_dict(w.project.to_dict());page.load_project(restored)
        self.assertEqual(page.source.text(),"조사자료 <A>");self.assertEqual(page.speeds.text(),"20, 40")

    def test_mode_preserves_legacy_data_and_undo(self):
        w=self.window;before=[s.to_dict() for s in w.project.segments]
        w.project.analysis_edition="2026";w.sync_edition();w.mark_dirty()
        self.assertFalse(w.tabs.isTabVisible(0));self.assertTrue(w.tabs.isTabVisible(w.beta_index))
        w.beta_page.add_examples();self.assertEqual(len(w.project.corridors_2026),3)
        self.assertEqual(before,[s.to_dict() for s in w.project.segments])
        w.undo_project();self.assertEqual(len(w.project.corridors_2026),0)
        w.undo_project();self.assertEqual(w.project.analysis_edition,"2013");self.assertTrue(w.tabs.isTabVisible(0))

    def test_edit_invalidates_results_and_restores(self):
        w=self.window;w.project.analysis_edition="2026";w.project.corridors_2026=[official_example(2).to_dict()];w.sync_edition()
        page=w.beta_page;page.analyze();self.assertIn("20.1",page.result.toPlainText())
        page.table.cellWidget(0,5).setValue(100)
        self.assertIn("다시 분석",page.result.toPlainText())
        restored=ArterialProject.from_dict(w.project.to_dict());page.load_project(restored)
        self.assertEqual(page.table.cellWidget(0,5).value(),100)
        page.analyze();self.assertIn("2026 도로용량편람",page.result.toPlainText())

    def test_invalid_survey_is_saved_and_not_analyzed(self):
        w=self.window;w.project.corridors_2026=[official_example(1).to_dict()];w.beta_page.load_project(w.project)
        page=w.beta_page;page.times.setText("abc");page.commit();page.analyze()
        self.assertIn("분석할 수 없습니다",page.result.toPlainText())
        self.assertEqual(w.project.corridors_2026[0]["travel_times_s"],["abc"])

    def test_shortcuts_target_beta_corridors(self):
        w=self.window;w.project.analysis_edition="2026";w.sync_edition();w.add_tab_shortcut()
        self.assertEqual(len(w.project.corridors_2026),1)
        w.add_tab_shortcut();w.move_analysis_tab(-1)
        self.assertEqual(w.beta_page.selector.currentIndex(),0)

    def test_diagram_tracks_directed_rows_and_does_not_merge_same_names(self):
        w = self.window
        corridor = official_example(2)
        corridor.start_id = "A01"
        corridor.subsegments[0].end_id = "B01"
        corridor.subsegments[0].approach_id = "EB"
        corridor.subsegments[3].end_name = corridor.subsegments[0].end_name
        w.project.analysis_edition = "2026"
        w.project.corridors_2026 = [corridor.to_dict()]
        w.sync_edition()
        page = w.beta_page
        page.show_legacy_diagram()
        diagram = page.diagram_dialog.diagram
        self.assertEqual(len(diagram.nodes), 7)
        self.assertEqual(len(diagram.edges), 6)
        first = diagram.edges[0]["directions"][0]
        self.assertEqual(first["from"], ("신호교차로 ID", "A01"))
        self.assertEqual(first["to"], ("신호교차로 ID", "B01"))
        self.assertIn("44.5", first["segment"].metric_text)
        diagram.edgeSelected.emit({"3"})
        self.assertEqual(page.tabs.currentIndex(), 1)
        self.assertEqual(page.table.currentRow(), 3)
        self.assertEqual(diagram.highlight_uids, {"3"})
        page.commit()
        self.assertEqual(page.current().subsegments[0].approach_id, "EB")

    def test_copy_alternative_keeps_route_and_clears_analysis_inputs(self):
        w = self.window
        corridor = official_example(2)
        corridor.subsegments[0].end_id = "B01"
        corridor.subsegments[0].approach_id = "EB"
        corridor.subsegments[0].capacity_vph = 1500
        w.project.corridors_2026 = [corridor.to_dict()]
        page = w.beta_page
        page.load_project(w.project)
        with patch.object(QInputDialog, "getItem", return_value=("사업 시행시", True)), \
             patch.object(QInputDialog, "getInt", return_value=(2035, True)):
            page.copy_corridor()
        copy = page.current()
        self.assertEqual((copy.scenario, copy.year), ("사업 시행시", 2035))
        self.assertEqual(copy.subsegments[0].approach_id, "EB")
        self.assertEqual(copy.subsegments[0].end_id, "B01")
        self.assertIsNone(copy.subsegments[0].delay_s)
        self.assertIsNone(copy.subsegments[0].capacity_vph)
        self.assertEqual(w.project.corridors_2026[0]["subsegments"][0]["capacity_vph"], 1500)

    def test_manual_diagram_click_connect_insert_and_undo(self):
        from PySide6.QtCore import Qt, QRectF
        from PySide6.QtTest import QTest
        w=self.window;w.project.analysis_edition='2026';w.sync_edition()
        page=w.beta_page;page.add_corridor();page.show_legacy_diagram()
        for name in ('시청교차로','공원교차로','중간교차로'):
            with patch.object(QInputDialog,'getText',return_value=(name,True)):
                page.add_diagram_node()
        self.assertEqual(len(page.diagram_dialog.diagram.nodes),3)
        keys=[('신호교차로 ID',n['id']) for n in page.current().diagram_nodes]
        diagram=page.diagram_dialog.diagram
        APP.processEvents()
        area=QRectF(58,78,max(100,diagram.width()-116),max(100,diagram.height()-145))
        positions=diagram._positions(area)
        QTest.mouseClick(diagram,Qt.LeftButton,Qt.ControlModifier,positions[keys[0]].toPoint())
        self.assertEqual(page.connection_start,keys[0])
        with patch.object(QInputDialog,'getDouble',side_effect=[(500,True),(50,True)]):
            QTest.mouseClick(diagram,Qt.LeftButton,Qt.NoModifier,positions[keys[1]].toPoint())
        self.assertEqual(page.table.rowCount(),1)
        self.assertEqual(len(diagram.edges),1)
        page.diagram_node_clicked(keys[2],False)
        diagram.edgeSelected.emit({'0'})
        with patch.object(QInputDialog,'getDouble',side_effect=[(200,True),(300,True)]):
            page.insert_diagram_node()
        self.assertEqual([s.end_name for s in page.current().subsegments],['중간교차로','공원교차로'])
        self.assertEqual(len(diagram.edges),2)
        w.undo_project()
        self.assertEqual(page.table.rowCount(),1)
        self.assertEqual(len(page.current().diagram_nodes),1)
        page.name.setText('변경된 이름');page.commit()
        self.assertEqual(len(page.current().diagram_nodes),1)
