import os
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QLineEdit, QPushButton

from arterial_analysis.app_fast import APP_VERSION, MainWindow, NetworkDiagramWidget, build_network_graph
from arterial_analysis.engine import SegmentInput
from arterial_analysis.motion import MotionController


APP = QApplication.instance() or QApplication([])


class FastArterialUiTest(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow()
        self.page = self.window.workflow.input
        self.table = self.page.external

    def tearDown(self):
        self.window.deleteLater()

    def fill_row(self, row, volume=1500):
        values = {1:"비슬로",2:"1",3:"기점",5:"2",6:"종점",7:"1,000",8:"2",10:"120",11:"50",12:f"{volume:,}",13:"0.95"}
        self.table.blockSignals(True)
        for column, value in values.items():
            self.table.item(row, column).setText(value)
        self.table.blockSignals(False)
        self.page.commit_row(self.table,row,13)

    def test_release_and_blank_start(self):
        self.assertEqual(APP_VERSION,"1.4.1")
        self.assertEqual(self.table.rowCount(),2)
        self.assertEqual(self.table.item(0,7).text(),"")
        self.assertEqual(self.table.item(0,12).text(),"")
        self.assertEqual(self.table.item(0,13).text(),"1.00")
        self.assertEqual(self.table.item(0,9).text(),"유형III")

    def test_button_motion_has_tactile_press_and_release(self):
        controller=MotionController(APP,reduced_motion=False);button=QPushButton("확인")
        controller.press_button(button);QTest.qWait(controller.PRESS_MS+20)
        self.assertIsInstance(button.graphicsEffect(),QGraphicsOpacityEffect)
        self.assertLess(button.graphicsEffect().opacity(),0.8)
        controller.release_button(button);QTest.qWait(controller.RELEASE_MS+30)
        self.assertAlmostEqual(button.graphicsEffect().opacity(),1.0,places=2)

    def test_reduce_motion_finishes_immediately(self):
        controller=MotionController(APP,reduced_motion=True);button=QPushButton("확인")
        controller.press_button(button);QTest.qWait(5)
        self.assertAlmostEqual(button.graphicsEffect().opacity(),controller.PRESS_OPACITY,places=2)
        controller.release_button(button);QTest.qWait(5)
        self.assertAlmostEqual(button.graphicsEffect().opacity(),1.0,places=2)

    def test_integer_format_and_live_result(self):
        self.fill_row(0)
        self.assertEqual(self.table.item(0,12).text(),"1,500")
        self.assertTrue(self.table.item(0,14).text())
        self.assertTrue(self.table.item(0,15).text())

    def test_report_overrides_are_hidden_and_optional(self):
        self.assertTrue(self.table.isColumnHidden(17))
        self.page.toggle_optional()
        self.assertFalse(self.table.isColumnHidden(17))

    def test_complete_rows_only_reach_results(self):
        self.fill_row(0)
        self.window.workflow.go(1)
        self.assertEqual(len(self.window.workflow.results),1)

    def test_direct_volume_is_blank_on_copied_scenario(self):
        self.fill_row(0); self.page.save_current()
        self.window.project.ensure_tab("사업 미시행시",2033)
        self.window.project.copy_rows("현황",2026,"사업 미시행시",2033)
        copied=self.window.project.rows("사업 미시행시",2033)
        self.assertEqual(copied[0].main_volume,0)
        self.assertIn("main_volume",copied[0].blank_fields)

    def test_zero_volume_can_be_complete(self):
        self.fill_row(0,0)
        self.assertNotIn("main_volume",self.window.project.rows("현황",2026)[0].blank_fields)
        self.assertEqual(len(self.window.project.analyze_all()),1)

    def test_horizontal_scroll_and_pair_merges(self):
        self.assertGreater(self.table.horizontalScrollBar().maximum(),0)
        for column in (0,1,2,3,5,6):
            self.assertEqual(self.table.rowSpan(0,column),2)
            self.assertEqual(self.table.frozen.rowSpan(0,column),2)
        for column in (4,7,8,9,10,11,12,13):
            self.assertEqual(self.table.rowSpan(0,column),1)

    def test_internal_road_visibility(self):
        self.assertFalse(self.page.road_tabs.isTabVisible(1))
        self.window.project.ensure_tab("사업 시행시",2033)
        self.page.refresh_tabs(("사업 시행시",2033))
        self.assertTrue(self.page.road_tabs.isTabVisible(1))

    def test_checkbox_pair_selection(self):
        self.table.item(0,0).setCheckState(Qt.Checked)
        self.assertEqual(self.page.selected_rows(),[0,1])

    def test_tab_commits_and_moves_through_editors(self):
        self.window.show(); self.table.setCurrentCell(0,1); self.table.editItem(self.table.item(0,1)); APP.processEvents()
        editor=APP.focusWidget(); QTest.keyClicks(editor,"Road"); QTest.keyClick(editor,Qt.Key_Tab); APP.processEvents()
        self.assertEqual(self.table.item(0,1).text(),"Road"); self.assertEqual(self.table.currentColumn(),2)
        editor=APP.focusWidget(); QTest.keyClicks(editor,"1"); QTest.keyClick(editor,Qt.Key_Tab); APP.processEvents()
        self.assertEqual(self.table.item(0,2).text(),"1"); self.assertEqual(self.table.currentColumn(),3)

    def test_keyboard_skips_merged_lower_cells_and_hidden_optional_columns(self):
        self.table.setCurrentCell(0,13)
        self.table._move_editable(1)
        self.assertEqual((self.table.currentRow(),self.table.currentColumn()),(1,4))
        self.table._move_editable(-1)
        self.assertEqual((self.table.currentRow(),self.table.currentColumn()),(0,13))

    def test_numeric_editor_shows_input_immediately(self):
        self.window.show();self.table.setCurrentCell(0,10);self.table.editItem(self.table.item(0,10));APP.processEvents()
        editor=APP.focusWidget();QTest.keyClicks(editor,"120");APP.processEvents()
        self.assertEqual(editor.text(),"120")

    def test_first_numeric_key_is_visible_when_it_starts_editing(self):
        self.window.show();self.table.setCurrentCell(0,10);APP.processEvents();QTest.keyClick(self.table,Qt.Key_1);APP.processEvents()
        editor=APP.focusWidget();self.assertIsInstance(editor,QLineEdit);self.assertEqual(editor.text(),"1")

    def test_numeric_ranges_and_green_not_over_cycle(self):
        self.table.item(0,8).setText("14");self.table.item(0,10).setText("100");self.table.item(0,11).setText("120");self.table.item(0,13).setText("1.25")
        self.page.commit_row(self.table,0,13)
        self.assertEqual(self.table.item(0,8).text(),"10")
        self.assertEqual(self.table.item(0,11).text(),"100")
        self.assertEqual(self.table.item(0,13).text(),"1.00")

    def test_equal_shortcut_requests_excel_link_for_volume(self):
        self.table.linkRequested.disconnect();spy=QSignalSpy(self.table.linkRequested);self.table.setCurrentCell(0,12)
        self.table._excel_link_shortcut.activated.emit()
        self.assertEqual(spy.count(),1);self.assertEqual(spy.at(0),[0])

    def test_excel_selection_is_captured_before_enter_moves_cell(self):
        self.page._enter_was_down=False;self.page._pending_selection=None
        selected=(r"C:\traffic.xlsx","현황2026","B12",True)
        with patch("arterial_analysis.app_fast.ctypes.windll.user32.GetAsyncKeyState",return_value=0),patch("arterial_analysis.app_fast.active_selection",return_value=selected):
            self.page.poll_link()
        self.assertEqual(self.page._pending_selection,selected)

    def test_unsaved_excel_uses_last_saved_disk_value_without_modal_loop(self):
        self.page._link_table=self.table;self.page._link_row=0;self.page._enter_was_down=True
        self.page._pending_selection=(__file__,"Sheet1","B12",False);self.page._link_timer=Mock()
        with patch("arterial_analysis.app_fast.ctypes.windll.user32.GetAsyncKeyState",return_value=0),patch("arterial_analysis.app_fast.read_saved_cell",return_value=(1234,"B12")):
            self.page.poll_link()
        segment=self.window.project.rows("현황",2026)[0]
        self.assertEqual(segment.main_volume,1234);self.assertEqual(segment.volume_link_status,"last_saved")

    def test_f5_reads_same_workbook_once_for_multiple_links(self):
        info=self.window.project.tab_info("현황",2026);info.update(source_path=__file__,source_sheet="Sheet1")
        first,second=self.window.project.rows("현황",2026)[:2];first.volume_source_cell="B12";second.volume_source_cell="B13";self.page.load_key(("현황",2026))
        values={"B12":(1200,"B12",""),"B13":(1300,"B13","")}
        with patch("arterial_analysis.app_fast.read_saved_cells",return_value=values) as reader:self.page.refresh_links()
        reader.assert_called_once();first,second=self.window.project.rows("현황",2026)[:2];self.assertEqual(first.main_volume,1200);self.assertEqual(second.main_volume,1300)

    def test_ctrl_h_changes_selected_link_source_and_keeps_cell_address(self):
        segment=self.window.project.rows("현황",2026)[0];segment.volume_source_cell="C20";self.page.load_key(("현황",2026));self.table.setCurrentCell(0,12)
        replacement=str(__file__)
        with patch("arterial_analysis.app_fast.QFileDialog.getOpenFileName",return_value=(replacement,"")),patch("arterial_analysis.app_fast.list_sheets",return_value=["미시행2033"]),patch("arterial_analysis.app_fast.QInputDialog.getItem",return_value=("미시행2033",True)):
            self.page.replace_excel_sources(self.table)
        segment=self.window.project.rows("현황",2026)[0]
        self.assertEqual(segment.volume_source_cell,"C20");self.assertEqual(segment.volume_source_path,str(Path(replacement).resolve()));self.assertEqual(segment.volume_source_sheet,"미시행2033")

    def test_excel_linked_volume_has_excel_icon(self):
        segment=self.window.project.rows("현황",2026)[0];segment.volume_source_cell="B12";segment.volume_link_status="ok"
        self.page.load_key(("현황",2026))
        self.assertFalse(self.table.item(0,12).icon().isNull())

    def test_non_segment_input_columns_have_equal_width(self):
        self.page.toggle_optional()
        self.assertEqual(len({self.table.columnWidth(c) for c in range(7,21)}),1)

    def test_narrow_metric_headers_are_wrapped_without_long_lines(self):
        for header in self.page.HEADERS[7:]:
            self.assertLessEqual(max(map(len,header.splitlines())),6)
        self.assertGreaterEqual(self.table.horizontalHeader().height(),76)

    def test_lane_count_is_center_aligned(self):
        self.table.item(0,8).setText("10");self.page.commit_row(self.table,0,8)
        self.assertEqual(self.table.item(0,8).textAlignment()&Qt.AlignHorizontal_Mask,Qt.AlignHCenter)

    def test_network_diagram_makes_triangle_and_deduplicates_directions(self):
        def segment(uid,start,end,road,direction="→"):
            return SegmentInput(uid=uid,comparison_id=uid,scenario="현황",year=2026,road_name=road,start_number=start,start_name=f"{start}교차로",end_number=end,end_name=f"{end}교차로",direction=direction)
        segments=[segment("12a","1","2","가로A"),segment("12b","1","2","가로A","←"),segment("13","1","3","가로B"),segment("23","2","3","가로C")]
        nodes,edges=build_network_graph(segments)
        self.assertEqual(len(nodes),3);self.assertEqual(len(edges),3)
        self.assertEqual({tuple(sorted((edge["start"][1],edge["end"][1]))) for edge in edges},{("1","2"),("1","3"),("2","3")})

    def test_network_diagram_opens_and_has_current_counts(self):
        rows=self.window.project.rows("현황",2026);rows[0].start_number="1";rows[0].start_name="1교차로";rows[0].end_number="2";rows[0].end_name="2교차로"
        self.page.load_key(("현황",2026));self.page.show_network_diagram();APP.processEvents()
        self.assertTrue(self.page.diagram_dialog.isVisible());self.assertIn("교차로 2개",self.page.diagram_dialog.diagram.title);self.assertIn("연결 구간 1개",self.page.diagram_dialog.diagram.title)

    def test_clicking_diagram_edge_emits_all_direction_uids(self):
        def segment(uid,direction):
            return SegmentInput(uid=uid,comparison_id="pair",scenario="현황",year=2026,road_name="가로A",start_number="1",start_name="1교차로",end_number="2",end_name="2교차로",direction=direction)
        widget=NetworkDiagramWidget();widget.resize(700,500);widget.set_segments([segment("forward","→"),segment("backward","←")]);widget.show();APP.processEvents()
        spy=QSignalSpy(widget.edgeSelected);edge,start,end,_=widget._hit_edges[0];QTest.mouseClick(widget,Qt.LeftButton,pos=((start+end)/2).toPoint());APP.processEvents()
        self.assertEqual(spy.count(),1);self.assertEqual(set(spy.at(0)[0]),{"forward","backward"});self.assertEqual(widget.highlight_uids,{"forward","backward"})

    def test_diagram_selection_selects_both_input_rows(self):
        rows=self.window.project.rows("현황",2026)[:2]
        for segment in rows:segment.road_name="가로A";segment.start_number="1";segment.start_name="1교차로";segment.end_number="2";segment.end_name="2교차로"
        self.page.load_key(("현황",2026));self.page.show_network_diagram();APP.processEvents();self.page.select_diagram_edge({segment.uid for segment in rows});APP.processEvents()
        self.assertEqual({index.row() for index in self.table.selectedIndexes()},{0,1});self.assertEqual(self.page.diagram_dialog.diagram.highlight_uids,{segment.uid for segment in rows})

    def test_input_cell_selection_highlights_diagram_edge(self):
        rows=self.window.project.rows("현황",2026)[:2]
        for segment in rows:segment.road_name="가로A";segment.start_number="1";segment.start_name="1교차로";segment.end_number="2";segment.end_name="2교차로"
        self.page.load_key(("현황",2026));self.page.show_network_diagram();self.table.setCurrentCell(0,7);APP.processEvents()
        self.assertIn(rows[0].uid,self.page.diagram_dialog.diagram.highlight_uids)


if __name__ == "__main__":
    unittest.main()
