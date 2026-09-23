import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from arterial_analysis.excel_links import (
    format_external_formula,
    list_sheets,
    parse_external_formula,
    read_saved_cells,
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


if __name__ == "__main__":
    unittest.main()
