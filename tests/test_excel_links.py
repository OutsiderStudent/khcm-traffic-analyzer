import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from pathlib import Path

from openpyxl import Workbook

from arterial_analysis.excel_links import (
    format_external_formula,
    list_sheets,
    parse_external_formula,
    normalize_expression,
    open_link_window,
    close_link_window,
    read_saved_cells,
    read_saved_expressions,
)


class ExcelLinksTest(unittest.TestCase):
    def test_link_window_disables_excel_enter_move_and_restores_it(self):
        path=str((Path(tempfile.gettempdir())/"traffic.xlsx").resolve())
        window=SimpleNamespace(Hwnd=321,Caption="traffic.xlsx",WindowState=0,Activate=Mock(),Close=Mock())
        workbook=SimpleNamespace(FullName=path,NewWindow=Mock(return_value=window),Windows=[window],Saved=True)
        excel=SimpleNamespace(MoveAfterReturn=True,Workbooks=[workbook],Visible=False)
        pythoncom=SimpleNamespace(CoInitialize=Mock(),CoUninitialize=Mock());client=SimpleNamespace(Dispatch=Mock(return_value=excel),GetActiveObject=Mock(return_value=excel))
        with patch("arterial_analysis.excel_links._excel_modules",return_value=(pythoncom,client)):
            token=open_link_window(path)
            self.assertFalse(excel.MoveAfterReturn);self.assertTrue(token["move_after_return"])
            close_link_window(token)
        self.assertTrue(excel.MoveAfterReturn);window.Close.assert_called_once()

    def test_excel_started_by_program_is_quit_after_capture(self):
        path=str((Path(tempfile.gettempdir())/"program-opened.xlsx").resolve())
        window=SimpleNamespace(Hwnd=654,Caption="program-opened.xlsx",WindowState=0,Activate=Mock())
        class Windows(list):
            def __call__(self,index):return self[index-1]
        workbook=SimpleNamespace(FullName=path,Windows=Windows([window]),Saved=True,Close=Mock())
        class Workbooks(list):
            def Open(self,*_args,**_kwargs):self.append(workbook);return workbook
        excel=SimpleNamespace(MoveAfterReturn=True,Workbooks=Workbooks(),Visible=False,Quit=Mock())
        pythoncom=SimpleNamespace(CoInitialize=Mock(),CoUninitialize=Mock());client=SimpleNamespace(Dispatch=Mock(return_value=excel),GetActiveObject=Mock(side_effect=[RuntimeError("not running"),excel]))
        with patch("arterial_analysis.excel_links._excel_modules",return_value=(pythoncom,client)):
            token=open_link_window(path);self.assertTrue(token["created_application"]);close_link_window(token)
        workbook.Close.assert_called_once_with(SaveChanges=False);excel.Quit.assert_called_once()

    def test_external_formula_round_trip(self):
        path = str((Path(tempfile.gettempdir()) / "교통량 자료.xlsx").resolve())
        formula = format_external_formula(path, "미시행 2033", "h17")
        self.assertEqual(parse_external_formula(formula), (path, "미시행 2033", "H17"))
        self.assertIn("$H$17", formula)

    def test_same_workbook_sheet_formula_uses_default_path(self):
        path = str((Path(tempfile.gettempdir()) / "traffic.xlsx").resolve())
        self.assertEqual(parse_external_formula("='시행 2036'!$C$9", path), (path, "시행 2036", "C9"))

    def test_xlsx_saved_values_are_read_without_starting_excel(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "traffic.xlsx"
            workbook = Workbook(); sheet = workbook.active; sheet.title = "현황2026"; sheet["B12"] = 1499.6; workbook.create_sheet("미시행2033"); workbook.save(path); workbook.close()
            self.assertEqual(list_sheets(str(path)), ["현황2026", "미시행2033"])
            values = read_saved_cells(str(path), "현황2026", ["$B$12"])
            self.assertEqual(values["B12"], (1500, "B12", ""))

    def test_address_expressions_ranges_hidden_rows_and_round_each_cell(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"traffic.xlsx";workbook=Workbook();sheet=workbook.active;sheet.title="현황";sheet["H12"]=100.4;sheet["H13"]=100.6;sheet["H14"]=999;sheet.row_dimensions[14].hidden=True;workbook.save(path);workbook.close()
            self.assertEqual(normalize_expression("=$h$12 + H13,H12:H14"),"H12,H13,H12:H14")
            result=read_saved_expressions(str(path),"현황",["H12,H13,H12:H14"],"volume")
            self.assertEqual(result["H12,H13,H12:H14"][0],201)

    def test_phf_requires_one_cell_and_rounds_to_two_decimals(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"traffic.xlsx";workbook=Workbook();sheet=workbook.active;sheet.title="현황";sheet["A1"]=0.945;sheet["A2"]=0.9;workbook.save(path);workbook.close()
            one=read_saved_expressions(str(path),"현황",["A1"],"phf");self.assertEqual(one["A1"][0],0.95)
            many=read_saved_expressions(str(path),"현황",["A1:A2"],"phf");self.assertTrue(many["A1:A2"][2])


if __name__ == "__main__":
    unittest.main()
