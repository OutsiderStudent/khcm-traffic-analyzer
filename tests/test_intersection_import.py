import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from arterial_analysis.intersection_import import match_intersection_los, read_intersection_los


class IntersectionImportTest(unittest.TestCase):
    def test_reads_scenario_groups_and_matches_name_before_point(self):
        book=Workbook();sheet=book.active;sheet.title="교차로"
        sheet["F5"]="교차로명";sheet["G5"]="지점";sheet["J5"]="현황2026";sheet["J6"]="교통량";sheet["K6"]="지체";sheet["L6"]="LOS";sheet["M5"]="미시행2035";sheet["M6"]="교통량";sheet["N6"]="지체";sheet["O6"]="LOS"
        sheet["F8"]="01.간경교차로";sheet["G8"]=1;sheet["L8"]="C";sheet["O8"]="B"
        sheet["F9"]="02.화원교차로";sheet["G9"]=2;sheet["L9"]="연결로";sheet["O9"]="D"
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"intersection.xlsx";book.save(path);groups=read_intersection_los(path)
        self.assertEqual([(group.scenario,group.year) for group in groups],[('현황',2026),('사업 미시행시',2035)])
        self.assertEqual(match_intersection_los(groups[0].records,"99","간경교차로").los,"C")
        self.assertIsNone(match_intersection_los(groups[0].records,"2","화원교차로"))
        self.assertEqual(match_intersection_los(groups[1].records,"2","화원교차로").los,"D")

    def test_ignores_comparison_los_columns(self):
        book=Workbook();sheet=book.active;sheet.title="교차로"
        sheet["C5"]="비교(② 사업미시행시(2035) - ① 현황(2026))";sheet["E6"]="LOS"
        sheet["F5"]="교차로명";sheet["G5"]="지점";sheet["M5"]="사업미시행시(2035)";sheet["O6"]="LOS"
        sheet["F8"]="간경교차로";sheet["G8"]=1;sheet["E8"]="B→C";sheet["O8"]="C"
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"intersection.xlsx";book.save(path);groups=read_intersection_los(path)
        self.assertEqual(len(groups),1);self.assertEqual(groups[0].scenario,"사업 미시행시");self.assertEqual(groups[0].records[0].los,"C")


if __name__ == "__main__":
    unittest.main()
