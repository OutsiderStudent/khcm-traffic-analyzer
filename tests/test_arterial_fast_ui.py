import os
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QItemSelectionModel, QRect, QRectF, QSize, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QAbstractItemView, QApplication, QDialog, QFrame, QLineEdit, QPushButton, QStyleOptionViewItem, QTabBar, QTabWidget, QToolButton

from arterial_analysis.app_fast import APP_VERSION, FAST_STYLE, MainWindow, NetworkDiagramDialog, NetworkDiagramWidget, OptionalColorHeader, UserGuideDialog, build_network_graph, enable_native_file_dialogs
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
        self.assertEqual(APP_VERSION,"1.8.0")
        self.assertEqual(self.table.rowCount(),2)
        self.assertEqual(self.table.item(0,7).text(),"")
        self.assertEqual(self.table.item(0,12).text(),"")
        self.assertEqual(self.table.item(0,13).text(),"1.00")
        self.assertEqual(self.table.item(0,9).text(),"유형III")

    def test_windows_native_file_dialogs_are_enabled(self):
        QApplication.setAttribute(Qt.AA_DontUseNativeDialogs, True)
        enable_native_file_dialogs()
        self.assertFalse(QApplication.testAttribute(Qt.AA_DontUseNativeDialogs))

    def test_cell_combo_keeps_most_of_narrow_cell_for_text(self):
        old_style=APP.styleSheet();APP.setStyleSheet(FAST_STYLE)
        try:
            delegate=self.table.itemDelegateForColumn(1)
            index=self.table.model().index(0,1)
            option=QStyleOptionViewItem();option.rect=QRect(0,0,88,38)
            editor=delegate.createEditor(self.table,option,index)
            delegate.updateEditorGeometry(editor,option,index)
            self.assertEqual(editor.objectName(),"cellComboEditor")
            self.assertGreaterEqual(editor.lineEdit().width(),58)
            editor.deleteLater()
        finally:APP.setStyleSheet(old_style)

    def test_button_motion_has_tactile_press_and_release(self):
        controller=MotionController(APP,reduced_motion=False);button=QPushButton("확인")
        controller.press_button(button);QTest.qWait(controller.PRESS_MS+20)
        self.assertGreater(float(button.property("khcmPressProgress")),0.9)
        self.assertIsNone(button.graphicsEffect())
        controller.release_button(button);QTest.qWait(controller.RELEASE_MS+30)
        self.assertAlmostEqual(float(button.property("khcmPressProgress")),0.0,places=2)

    def test_compact_detail_button_keeps_text_height(self):
        button=self.table.cellWidget(0,16)
        self.assertGreaterEqual(button.height(),button.fontMetrics().height()+4)

    def test_comparison_review_buttons_keep_full_text_height(self):
        self.fill_row(0);self.fill_row(1);self.page.save_current();project=self.window.project
        for scenario in ("사업 미시행시","사업 시행시"):
            project.ensure_tab(scenario,2033);project.copy_rows("현황",2026,scenario,2033)
            for segment in project.rows(scenario,2033):segment.main_volume=600;segment.blank_fields=[field for field in segment.blank_fields if field!="main_volume"]
        page=self.window.workflow.results_page;page.refresh(project,project.analyze_all());index=next(i for i in range(page.tabs.count()) if "미시행-시행" in page.tabs.tabText(i));page.tabs.setCurrentIndex(index);self.window.show();APP.processEvents()
        buttons=page.table.findChildren(QPushButton,"reviewButton");self.assertTrue(buttons)
        for button in buttons:self.assertGreaterEqual(button.height(),button.fontMetrics().height()+8);self.assertGreaterEqual(button.minimumHeight(),button.fontMetrics().height()+10)

    def test_history_toggle_is_hidden_while_drawer_is_open(self):
        self.window.show();APP.processEvents();self.window.history_dock.show();APP.processEvents()
        self.assertFalse(self.window.history_toggle.isVisible())
        trash=self.window.findChild(QToolButton,"historyTrashButton");self.assertIsNotNone(trash);self.assertFalse(trash.icon().isNull())
        collapse=self.window.findChild(QToolButton,"historyCollapseButton");self.assertIsNotNone(collapse);self.assertFalse(collapse.icon().isNull());self.assertEqual(collapse.text(),"")
        self.window.history_dock.hide();APP.processEvents()
        self.assertTrue(self.window.history_toggle.isVisible())

    def test_reduce_motion_finishes_immediately(self):
        controller=MotionController(APP,reduced_motion=True);button=QPushButton("확인")
        controller.press_button(button);QTest.qWait(5)
        self.assertAlmostEqual(float(button.property("khcmPressProgress")),0.0,places=2)
        controller.release_button(button);QTest.qWait(5)
        self.assertAlmostEqual(float(button.property("khcmPressProgress")),0.0,places=2)

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

    def test_frozen_columns_do_not_follow_current_cell_horizontally(self):
        self.window.show();self.page.toggle_optional();self.table.setCurrentCell(0,20);self.table.scrollToItem(self.table.item(0,20));APP.processEvents()
        self.assertGreater(self.table.horizontalScrollBar().value(),0);self.assertEqual(self.table.frozen.horizontalScrollBar().value(),0);self.assertEqual(self.table.frozen.columnViewportPosition(0),0);self.assertEqual(self.table.frozen.columnViewportPosition(1),self.table.frozen.columnWidth(0))
        self.assertEqual(self.table.frozen.horizontalHeader().offset(),0)

    def test_frozen_columns_keep_row_alignment_during_vertical_scroll(self):
        self.window.show();self.table.setRowCount(12);self.table._update_frozen_geometry();APP.processEvents()
        self.table.verticalScrollBar().setValue(self.table.verticalScrollBar().maximum());APP.processEvents()
        self.assertEqual(self.table.verticalScrollMode(),QAbstractItemView.ScrollPerPixel)
        self.assertEqual(self.table.verticalScrollBar().value(),self.table.frozen.verticalScrollBar().value())
        for row in range(self.table.rowCount()):
            self.assertEqual(self.table.rowViewportPosition(row),self.table.frozen.rowViewportPosition(row))

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

    def test_same_arrival_shares_cycle_and_phf_link_metadata(self):
        first,second=self.window.project.rows("현황",2026)[:2];first.end_number="9";first.end_name="도착";second.start_number="9";second.start_name="도착";first.cycle_s=90;first.phf=.93;first.phf_source_cell="H12";first.phf_link_status="ok"
        self.page.load_key(("현황",2026));self.page.sync_arrival_values(first,10);self.page.sync_arrival_values(first,13)
        self.assertEqual(second.cycle_s,90);self.assertEqual(second.phf,.93);self.assertEqual(second.phf_source_cell,"H12");self.assertEqual(self.table.item(1,13).text(),"0.93")

    def test_equal_shortcut_requests_excel_link_for_volume(self):
        self.table.linkRequested.disconnect();spy=QSignalSpy(self.table.linkRequested);self.table.setCurrentCell(0,12)
        QTest.keyClick(self.table,Qt.Key_Equal)
        self.assertEqual(spy.count(),1);self.assertEqual(spy.at(0),[0])

    def test_excel_selection_is_not_polled_until_enter(self):
        self.page._link_window={"hwnd":123};self.page._enter_was_down=False;self.page._escape_was_down=False
        with patch("arterial_analysis.app_fast.ctypes.windll.user32.IsWindow",return_value=True),patch("arterial_analysis.app_fast.ctypes.windll.user32.GetAsyncKeyState",return_value=0),patch("arterial_analysis.app_fast.active_selection") as selected:
            self.page.poll_link()
        selected.assert_not_called()

    def test_unsaved_excel_waits_for_save_without_modal_loop(self):
        self.page._link_table=self.table;self.page._link_row=0;self.page._link_col=12;self.page._link_window={"hwnd":123};self.page._enter_was_down=True;self.page._escape_was_down=False;self.page._link_timer=Mock()
        with patch("arterial_analysis.app_fast.ctypes.windll.user32.IsWindow",return_value=True),patch("arterial_analysis.app_fast.ctypes.windll.user32.GetAsyncKeyState",return_value=0),patch("arterial_analysis.app_fast.active_selection",return_value=(__file__,"Sheet1","B12",False)),patch("arterial_analysis.app_fast.read_saved_cell") as reader:
            self.page.poll_link()
        reader.assert_not_called();segment=self.window.project.rows("현황",2026)[0]
        self.assertNotEqual(segment.main_volume,1234);self.assertIn("저장",self.page.formula.placeholderText())

    def test_manually_closed_excel_window_ends_link_mode(self):
        timer=Mock();self.page._link_timer=timer;self.page._link_window={"hwnd":123};self.page._link_table=self.table;self.page._link_row=0;self.page._link_col=12
        with patch("arterial_analysis.app_fast.ctypes.windll.user32.IsWindow",return_value=False),patch("arterial_analysis.app_fast.close_link_window"):
            self.page.poll_link()
        timer.stop.assert_called_once();timer.deleteLater.assert_called_once()
        self.assertIsNone(self.page._link_timer);self.assertIsNone(self.page._link_window);self.assertIsNone(self.page._link_table)
        self.assertIn("다시 연결",self.page.formula.placeholderText())

    def test_f5_reads_same_workbook_once_for_multiple_links(self):
        info=self.window.project.tab_info("현황",2026);info.update(source_path=__file__,source_sheet="Sheet1")
        first,second=self.window.project.rows("현황",2026)[:2];first.volume_source_cell="B12";second.volume_source_cell="B13";self.page.load_key(("현황",2026))
        values={"B12":(1200,"B12",""),"B13":(1300,"B13","")}
        with patch("arterial_analysis.app_fast.read_saved_cells",return_value=values) as reader:self.page.refresh_links()
        reader.assert_called_once();first,second=self.window.project.rows("현황",2026)[:2];self.assertEqual(first.main_volume,1200);self.assertEqual(second.main_volume,1300)

    def test_ctrl_h_changes_selected_link_source_and_keeps_cell_address(self):
        segment=self.window.project.rows("현황",2026)[0];segment.volume_source_cell="C20";info=self.window.project.tab_info("현황",2026);info.update(source_path=str(Path(__file__).resolve()),source_sheet="현황2026");self.page.load_key(("현황",2026));self.table.setCurrentCell(0,12)
        replacement=str(__file__)
        with patch("arterial_analysis.app_fast.ReplaceExcelLinksDialog") as dialog_type,patch("arterial_analysis.app_fast.read_saved_cells",return_value={"C20":(1500,"C20","")}):
            dialog=dialog_type.return_value;dialog.exec.return_value=QDialog.Accepted;dialog.values.return_value=(replacement,"미시행2033")
            self.page.replace_excel_sources(self.table)
        segment=self.window.project.rows("현황",2026)[0]
        self.assertEqual(segment.volume_source_cell,"C20");self.assertEqual(segment.volume_source_path,str(Path(replacement).resolve()));self.assertEqual(segment.volume_source_sheet,"미시행2033")

    def test_excel_linked_volume_has_excel_icon(self):
        segment=self.window.project.rows("현황",2026)[0];segment.volume_source_cell="B12";segment.volume_link_status="ok"
        info=self.window.project.tab_info("현황",2026);info.update(source_path=str(Path(__file__).resolve()),source_sheet="현황2026")
        self.page.load_key(("현황",2026))
        self.assertFalse(self.table.item(0,12).icon().isNull())
        self.assertTrue(str(self.table.item(0,12).data(Qt.UserRole+5)).startswith("="))

    def test_copy_keeps_excel_formula_and_paste_requests_link(self):
        item=self.table.item(0,12);self.table.setCurrentCell(0,12);self.table.blockSignals(True);item.setData(Qt.UserRole+5,"='C:\\[traffic.xlsx]현황2026'!$B$12");self.table.blockSignals(False);self.table.selectionModel().select(self.table.model().index(0,12),QItemSelectionModel.Select);self.table._copy()
        self.assertIn("traffic.xlsx",QApplication.clipboard().text())
        spy=QSignalSpy(self.table.formulasPasted);self.table.setCurrentCell(1,12);self.table._paste()
        self.assertEqual(spy.count(),1);self.assertIn("traffic.xlsx",spy.at(0)[0][0][1])

    def test_formula_bar_assigns_link_and_refreshes_saved_value(self):
        self.table.setCurrentCell(0,12);self.page.cell_selected(self.table,0,12)
        formula=f"='{Path(__file__).resolve().parent}\\[{Path(__file__).name}]현황2026'!$B$12";self.page.formula.setText(formula)
        with patch("arterial_analysis.app_fast.read_saved_cells",return_value={"B12":(1700,"B12","")}):self.page.apply_formula_bar()
        segment=self.window.project.rows("현황",2026)[0]
        self.assertEqual(segment.main_volume,1700);self.assertEqual(segment.volume_source_cell,"B12")

    def test_direct_paste_over_link_replaces_formula_like_excel(self):
        segment=self.window.project.rows("현황",2026)[0];segment.volume_source_cell="B12";segment.volume_link_status="ok"
        info=self.window.project.tab_info("현황",2026);info.update(source_path=str(Path(__file__).resolve()),source_sheet="현황2026");self.page.load_key(("현황",2026));self.table.setCurrentCell(0,12)
        QApplication.clipboard().setText("1,800");self.table._paste();segment=self.window.project.rows("현황",2026)[0]
        self.assertEqual(segment.main_volume,1800);self.assertEqual(segment.volume_source_cell,"")

    def test_non_segment_input_columns_have_equal_width(self):
        self.page.toggle_optional()
        self.assertEqual(len({self.table.columnWidth(c) for c in range(7,21)}),1)

    def test_narrow_metric_headers_are_wrapped_without_long_lines(self):
        for header in self.page.HEADERS[7:]:
            self.assertLessEqual(max(map(len,header.splitlines())),6)
        self.assertGreaterEqual(self.table.horizontalHeader().height(),84)

    def test_analysis_tab_plus_is_centered_and_close_sits_by_label(self):
        self.window.project.ensure_tab("사업 미시행시",2033);self.page.refresh_tabs(("사업 미시행시",2033))
        scenario=1;plus=self.page.analysis_tabs.count()-1;add_rect=self.page.analysis_tabs._add_icon_rect(plus);text_rect,close_rect=self.page.analysis_tabs._content_rects(scenario)
        self.assertEqual(add_rect.size(),QSize(14,14));self.assertEqual(add_rect.center().x(),self.page.analysis_tabs.tabRect(plus).center().x()-1);self.assertEqual(add_rect.center().y(),self.page.analysis_tabs.tabRect(plus).center().y());self.assertEqual(self.page.analysis_tabs.tabRect(plus).width(),30);self.assertEqual(close_rect.size(),add_rect.size());self.assertEqual(close_rect.left()-text_rect.right()-1,self.page.analysis_tabs.LABEL_CLOSE_GAP);self.assertIsNone(self.page.analysis_tabs.tabButton(scenario,QTabBar.RightSide));self.assertIsNone(self.page.analysis_tabs.tabButton(plus,QTabBar.RightSide))
        self.assertIn("border:1px solid #D8E1EC",FAST_STYLE)

    def test_tab_levels_are_visually_connected_to_their_content(self):
        self.assertEqual(self.window.tabs.objectName(),"mainTabs");self.assertEqual(self.window.tabs.tabBar().objectName(),"mainTabBar")
        self.assertEqual(self.page.analysis_tabs.objectName(),"sheetTabs");self.assertIsNotNone(self.page.findChild(QFrame,"analysisSheet"))
        self.assertEqual(self.page.road_tabs.objectName(),"connectedTabs");self.assertEqual(self.page.road_tabs.tabBar().objectName(),"contentTabBar")
        self.assertEqual(self.window.workflow.results_page.tabs.objectName(),"sheetTabs");self.assertIsNotNone(self.window.workflow.results_page.findChild(QFrame,"tabSheetPanel"))
        self.assertEqual(self.window.workflow.detail_page.tabs.objectName(),"sheetTabs");self.assertIsNotNone(self.window.workflow.detail_page.findChild(QFrame,"tabSheetPanel"))
        self.assertIn("QTabBar#sheetTabs::tab:selected{background:#F1F4F8",FAST_STYLE)
        self.assertIn("QFrame#analysisSheet{background:#F1F4F8",FAST_STYLE)
        self.assertNotIn("border-radius:0 9px",FAST_STYLE)

    def test_intersection_names_are_wider_and_frozen_boundary_is_visible(self):
        self.assertEqual(self.table.columnWidth(3),118);self.assertEqual(self.table.columnWidth(6),118)
        self.assertIn("border-right:2px solid #AEB9C8",self.table.frozen.styleSheet())

    def test_excel_controls_use_green_visual_system(self):
        for button in (self.page.choose_source,self.page.open_source,self.page.apply_source,self.page.refresh_source):self.assertFalse(button.icon().isNull())
        self.assertEqual(self.page.choose_source.objectName(),"excelPrimaryButton");self.assertEqual(self.page.open_source.objectName(),"excelButton")
        self.assertIn("#107C41",FAST_STYLE);self.assertIn("#EAF5EE",FAST_STYLE)

    def test_optional_columns_use_four_subtle_visual_colors(self):
        body_colors=[self.table.item(0,column).background().color().name() for column in (17,18,19,20)]
        header_colors=[self.table.horizontalHeaderItem(column).background().color().name() for column in (17,18,19,20)]
        self.assertEqual(body_colors,["#dceeff","#ddf4e7","#fff0c7","#eee2ff"]);self.assertEqual(len(set(header_colors)),4);self.assertIsInstance(self.table.horizontalHeader(),OptionalColorHeader)

    def test_workflow_has_no_gray_gap_between_steps_and_page(self):
        self.assertEqual(self.window.workflow.layout().spacing(),0)

    def test_user_guide_has_core_workflow_pages(self):
        dialog=UserGuideDialog(self.window);tabs=dialog.findChild(QTabWidget)
        self.assertIsNotNone(tabs);self.assertEqual(tabs.objectName(),"connectedTabs");self.assertEqual(tabs.tabBar().objectName(),"contentTabBar");self.assertGreaterEqual(tabs.count(),5);self.assertIn("Excel 연결",[tabs.tabText(i) for i in range(tabs.count())]);dialog.deleteLater()

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
        pair12=next(edge for edge in edges if {edge["start"][1],edge["end"][1]}=={"1","2"})
        self.assertEqual({item["segment"].direction for item in pair12["directions"]},{"→","←"})

    def test_network_layout_removes_crossings_for_extended_road_graph(self):
        def segment(uid,start,end):
            return SegmentInput(uid=uid,comparison_id=uid,scenario="현황",year=2026,road_name=uid,start_number=start,start_name=f"{start}교차로",end_number=end,end_name=f"{end}교차로")
        segments=[segment(f"{start}-{end}",start,end) for start,end in (("1","2"),("2","3"),("3","4"),("2","5"),("5","6"),("3","6"))]
        widget=NetworkDiagramWidget();widget.set_segments(segments);positions=widget._positions(QRectF(0,0,900,650))
        self.assertEqual(widget._crossing_count(positions),0)
        self.assertGreater(widget.width(),700)

    def test_network_diagram_has_fit_zoom_and_reset_controls(self):
        dialog=NetworkDiagramDialog();dialog.resize(740,540);dialog.show();APP.processEvents()
        self.assertEqual(dialog.fit_button.text(),"한눈에 보기")
        dialog.diagram.set_zoom(1.5);self.assertEqual(dialog.zoom_label.text(),"150%")
        dialog.zoom_reset.click();self.assertAlmostEqual(dialog.diagram._zoom,1.0)
        dialog.fit_button.click();self.assertLessEqual(dialog.diagram._zoom,1.0);dialog.deleteLater()

    def test_comparison_hero_lists_only_changed_existing_los(self):
        self.fill_row(0);self.fill_row(1);self.page.save_current();project=self.window.project
        for scenario in ("사업 미시행시","사업 시행시"):
            project.ensure_tab(scenario,2033);project.copy_rows("현황",2026,scenario,2033)
            for segment in project.rows(scenario,2033):segment.blank_fields=[]
        before=project.rows("사업 미시행시",2033);after=project.rows("사업 시행시",2033)
        before[0].manual_speed_kmh=25;after[0].manual_speed_kmh=35
        before[1].manual_speed_kmh=45;after[1].manual_speed_kmh=47
        new=SegmentInput.from_dict(after[0].to_dict());new.uid="new";new.comparison_id="new";new.road_name="신규로";project.segments.append(new)
        page=self.window.workflow.results_page;page.refresh(project,project.analyze_all());index=next(i for i in range(page.tabs.count()) if "미시행-시행" in page.tabs.tabText(i));page.tabs.setCurrentIndex(index);APP.processEvents();text=page.hero.text()
        self.assertIn("외부도로",text);self.assertIn("비슬로(기점→종점)는 “D”→“C”",text);self.assertIn("그 외 구간의 서비스수준은 “B”로 동일하게 분석되었음",text);self.assertNotIn("신규로",text)

    def test_single_los_summary_does_not_repeat_same_grade(self):
        self.fill_row(0);self.fill_row(1);self.page.save_current();results=self.window.project.analyze_all()
        for result in results:result.segment.manual_speed_kmh=35
        results=self.window.project.analyze_all();text=self.window.workflow.results_page._scenario_hero_line("외부도로",results)
        self.assertIn("서비스수준은 “C”로 분석되었음",text);self.assertNotIn("“C”~“C”",text)

    def test_result_pair_rows_share_one_background_band(self):
        self.fill_row(0);self.fill_row(1);self.page.save_current();page=self.window.workflow.results_page;page.refresh(self.window.project,self.window.project.analyze_all());APP.processEvents()
        data_rows=[]
        for row in range(page.table.rowCount()):
            item=page.table.item(row,0)
            if item and item.data(Qt.UserRole):data_rows.append(row)
        self.assertGreaterEqual(len(data_rows),2)
        first,second=data_rows[:2]
        self.assertEqual([page.table.item(first,col).background().color().name() for col in range(page.table.columnCount())],[page.table.item(second,col).background().color().name() for col in range(page.table.columnCount())])

    def test_network_direction_metric_has_volume_speed_and_los(self):
        segment=self.window.project.rows("현황",2026)[0]
        segment.length_km=1.0;segment.lanes=2;segment.cycle_s=120;segment.green_s=50;segment.main_volume=1500;segment.phf=0.95
        text=NetworkDiagramWidget._metric_text(segment,self.window.project.settings)
        self.assertIn("1,500대/시",text);self.assertIn("km/h",text);self.assertIn("LOS ",text)

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

    def test_diagram_uses_equal_short_arrows_and_non_overlapping_labels(self):
        def segment(uid,start,end,road,direction,volume):
            return SegmentInput(uid=uid,comparison_id=road,scenario="현황",year=2026,road_name=road,start_number=start,start_name=f"{start}교차로",end_number=end,end_name=f"{end}교차로",direction=direction,main_volume=volume)
        segments=[]
        for start,end,road in (("1","2","가로A"),("1","3","가로B"),("2","3","가로C")):
            segments.extend((segment(road+"a",start,end,road,"→",900),segment(road+"b",start,end,road,"←",800)))
        widget=NetworkDiagramWidget();widget.resize(820,620);widget.set_segments(segments,settings=self.window.project.settings);widget.show();APP.processEvents()
        lengths=[round(((end.x()-start.x())**2+(end.y()-start.y())**2)**0.5,1) for start,end in widget._arrow_segments]
        self.assertEqual(lengths,[36.0]*6)
        for index,box in enumerate(widget._label_boxes):
            self.assertFalse(any(box.adjusted(-1,-1,1,1).intersects(other) for other in widget._label_boxes[index+1:]))

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

    def test_diagram_and_selection_are_scoped_to_current_analysis_tab(self):
        future=SegmentInput(uid="implementation-only",comparison_id="new-link",scenario="사업 시행시",year=2033,road_category="사업지 내부도로",road_name="연결로",start_number="1",start_name="1교차로",end_number="3",end_name="3교차로")
        self.window.project.ensure_tab("사업 시행시",2033);self.window.project.segments.append(future)
        self.page.load_key(("현황",2026));self.page.show_network_diagram();APP.processEvents()
        self.assertNotIn("연결로",{road for edge in self.page.diagram_dialog.diagram.edges for road in edge["roads"]})
        self.assertFalse(any(future.uid in edge["uids"] for edge in self.page.diagram_dialog.diagram.edges))
        self.page.load_key(("사업 시행시",2033));APP.processEvents()
        self.assertIn("연결로",{road for edge in self.page.diagram_dialog.diagram.edges for road in edge["roads"]})


if __name__ == "__main__":
    unittest.main()
