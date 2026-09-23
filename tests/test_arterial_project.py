import tempfile
import unittest
from pathlib import Path

from arterial_analysis.project import ArterialProject
from arterial_analysis.reports import comparison_report, current_report


class ArterialProjectTest(unittest.TestCase):
    def test_phf_link_memo_and_change_log_survive_save_load(self):
        project=ArterialProject();project.add_starter_rows();segment=project.segments[0];segment.phf_source_cell="H12";segment.phf_link_status="ok";project.tab_info("현황",project.current_year)["memo"]="현장 조사값 확인";project.add_log({"kind":"change","field":"PHF","old":1.0,"new":0.95})
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"project.ara1";project.save(path);loaded=ArterialProject.load(path)
        self.assertEqual(loaded.segments[0].phf_source_cell,"H12");self.assertEqual(loaded.tab_info("현황",loaded.current_year)["memo"],"현장 조사값 확인");self.assertEqual(loaded.change_log[-1]["field"],"PHF")
    def test_save_load_and_scenario_copy(self):
        project = ArterialProject(current_year=2026, future_years=[2033, 2037])
        project.add_starter_rows()
        count = project.copy_rows("현황", 2026, "사업 미시행시", 2033)
        self.assertEqual(count, 2)
        self.assertEqual(len(project.rows("사업 미시행시", 2033)), 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "project.ara1"
            project.save(path)
            loaded = ArterialProject.load(path)
        self.assertEqual(loaded.future_years, [2033, 2037])
        self.assertEqual(len(loaded.segments), 4)

    def test_segment_specific_settings_survive_save_load(self):
        project = ArterialProject()
        project.add_starter_rows()
        project.segments[0].analysis_period_h = 0.5
        project.segments[0].base_saturation_flow = 2100
        project.segments[0].coordinated = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "detail.ara1"
            project.save(path)
            loaded = ArterialProject.load(path)
        self.assertEqual(loaded.segments[0].analysis_period_h, 0.5)
        self.assertEqual(loaded.segments[0].base_saturation_flow, 2100)
        self.assertTrue(loaded.segments[0].coordinated)

    def test_reports_use_report_volume(self):
        project = ArterialProject(current_year=2026, future_years=[2033])
        project.add_starter_rows()
        project.segments[0].report_volume = 1800
        spec = current_report(project, project.analyze_all())
        self.assertIn("1,800", [row[8] for row in spec.rows])

    def test_comparison_keeps_explanation_metrics_collapsed(self):
        project = ArterialProject(current_year=2026, future_years=[2033])
        project.add_starter_rows()
        project.copy_rows("현황", 2026, "사업 미시행시", 2033)
        project.copy_rows("현황", 2026, "사업 시행시", 2033)
        for row in project.segments:
            if row.year == 2033:
                row.main_volume = 500
                row.blank_fields = [field for field in row.blank_fields if field != "main_volume"]
        spec = comparison_report(project, project.analyze_all(), 2033, "사업 미시행시", "사업 시행시")
        self.assertNotIn("교통량 증감률", spec.headers)
        self.assertTrue(any("교통량 증감률" in detail and "V/c" in detail and "지체 변화" in detail for detail in spec.row_details))

    def test_comparison_deltas_hide_plus_and_render_zero_as_dash(self):
        project=ArterialProject(current_year=2026,future_years=[2033]);project.add_starter_rows()
        project.copy_rows("현황",2026,"사업 미시행시",2033);project.copy_rows("현황",2026,"사업 시행시",2033)
        before=project.rows("사업 미시행시",2033);after=project.rows("사업 시행시",2033)
        for row in before+after:row.blank_fields=[];row.main_volume=500;row.manual_speed_kmh=30
        after[0].main_volume=600;after[0].manual_speed_kmh=35
        spec=comparison_report(project,project.analyze_all(),2033,"사업 미시행시","사업 시행시")
        self.assertEqual(spec.rows[0][12],"100")
        self.assertEqual(spec.rows[0][13],"5.0")
        self.assertEqual(spec.rows[1][12],"-")
        self.assertEqual(spec.rows[1][13],"-")
        self.assertEqual(spec.rows[1][14],"-")

    def test_reports_group_external_before_internal_then_road_name(self):
        project=ArterialProject();project.add_starter_rows()
        external=project.segments[0];external.road_name="나로"
        internal=project.segments[1];internal.road_category="사업지 내부도로";internal.road_name="가로"
        spec=current_report(project,project.analyze_all())
        self.assertEqual(spec.row_categories,["외부 기존도로","사업지 내부도로"])

    def test_manual_speed_and_history_survive_save_load(self):
        project=ArterialProject(); project.add_starter_rows(); segment=project.segments[0]
        segment.manual_speed_kmh=33.3; segment.speed_adjustment_history=[{"changed_at":"2026-08-30T12:00:00+09:00","reason":"현장자료"}]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"manual.ara1"; project.save(path); loaded=ArterialProject.load(path)
        result=loaded.analyze_all()[0]
        self.assertEqual(result.speed_kmh,33.3); self.assertNotEqual(result.calculated_speed_kmh,result.speed_kmh); self.assertEqual(loaded.segments[0].speed_adjustment_history[0]["reason"],"현장자료")

    def test_manual_speed_is_highlighted_in_reports(self):
        project=ArterialProject(); project.add_starter_rows(); project.segments[0].manual_speed_kmh=30
        spec=current_report(project,project.analyze_all()); self.assertTrue(any(column==9 for _,column in spec.highlight_cells))


if __name__ == "__main__":
    unittest.main()
