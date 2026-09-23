import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from arterial_analysis.excel_links import (
    format_external_formula,
    list_sheets,
    parse_external_formula,
    normalize_expression,
    read_saved_cells,
    read_saved_expressions,
)


class ExcelLinksTest(unittest.TestCase):
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
