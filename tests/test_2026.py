import copy
import math
import unittest
from arterial_analysis.engine_2026 import analyze_corridor, official_example, Corridor2026, END_TYPES
from arterial_analysis.project import ArterialProject


class Chapter12Test(unittest.TestCase):
    def test_scope_confirmation_is_not_assumed_for_old_files(self):
        raw=official_example().to_dict()
        for field in ("urban_road_confirmed","signal_control_confirmed","boundaries_confirmed"):
            raw.pop(field)
        with self.assertRaises(ValueError):analyze_corridor(Corridor2026.from_dict(raw))

    def test_capacity_uses_minimum_intersection_and_retains_ties(self):
        c=official_example()
        for s in c.subsegments:s.capacity_vph=1600 if s.end_type==END_TYPES[0] else 1
        c.subsegments[0].capacity_vph=1800
        r=analyze_corridor(c)
        self.assertEqual(r.capacity_vph,1600);self.assertEqual(len(r.bottlenecks),3)
        c.subsegments[0].capacity_vph=None
        self.assertIsNone(analyze_corridor(c).capacity_vph)
        self.assertEqual(analyze_corridor(c).los,r.los)

    def test_speed_samples_are_harmonic_not_arithmetic(self):
        c=official_example(1);c.method="speeds";c.travel_speeds_kmh=[20,40]
        self.assertAlmostEqual(analyze_corridor(c).speed_kmh,26.6666666667)
        self.assertEqual(analyze_corridor(c).sample_count,2)

    def test_string_numeric_length_uses_validated_number(self):
        c=official_example();c.subsegments[0].length_m="500"
        self.assertAlmostEqual(analyze_corridor(c).total_time_s,394.8)

    def test_default_subsegment_has_no_invented_inputs(self):
        from arterial_analysis.engine_2026 import Subsegment2026
        s=Subsegment2026()
        self.assertEqual((s.length_m,s.speed_limit_kmh,s.through_lanes),(0,0,0))
        self.assertIsNone(s.delay_s)

    def test_survey_faster_than_limit_is_reviewed_not_replaced(self):
        c=official_example(1);c.travel_times_s=[100]
        r=analyze_corridor(c)
        self.assertAlmostEqual(r.speed_kmh,79.2)
        self.assertTrue(any("짧습니다" in w for w in r.warnings))

    def test_official_examples(self):
        for number,speed,los,total in ((1,20.0,"D",395.2),(2,20.1,"D",394.8),(3,26.3,"C",300.8)):
            with self.subTest(number=number):
                result=analyze_corridor(official_example(number))
                self.assertEqual(round(result.speed_kmh,1),speed)
                self.assertEqual(result.los,los)
                self.assertAlmostEqual(result.total_time_s,total)
        self.assertEqual([round(x,1) for x in analyze_corridor(official_example()).thresholds.values()],[33.3,26.2,20.3,16.6,13.1])

    def test_grade_boundaries_and_no_rounding(self):
        c=official_example(1)
        for grade,limit in analyze_corridor(c).thresholds.items():
            c.travel_times_s=[7920/limit]
            self.assertEqual(analyze_corridor(c).los,grade)
            c.travel_times_s=[7920/(limit-0.0001)]
            self.assertNotEqual(analyze_corridor(c).los,grade)

    def test_missing_delay_not_assumed_zero(self):
        c=official_example();c.subsegments[0].delay_s=None
        with self.assertRaises(ValueError):analyze_corridor(c)

    def test_change_point_delay_not_counted(self):
        c=official_example();before=analyze_corridor(c)
        c.subsegments[1].delay_s=1000
        self.assertEqual(analyze_corridor(c),before)

    def test_scope_and_bad_values(self):
        mutations=[lambda c:setattr(c,"lanes",1),lambda c:setattr(c.subsegments[0],"through_lanes",1),
            lambda c:setattr(c.subsegments[0],"speed_limit_kmh",0),lambda c:setattr(c.subsegments[0],"delay_s",-1),
            lambda c:setattr(c.subsegments[0],"length_m",float("nan")),
            lambda c:setattr(c,"subsegments",c.subsegments[:2])]
        for mutation in mutations:
            c=official_example();mutation(c)
            with self.assertRaises(ValueError):analyze_corridor(c)

    def test_survey_uses_mean_time_not_mean_speed(self):
        c=official_example(1);c.travel_times_s=[200,600]
        self.assertAlmostEqual(analyze_corridor(c).speed_kmh,7920/400)

    def test_project_round_trip_and_legacy_default(self):
        p=ArterialProject();p.add_starter_rows();before=p.analyze_all()
        p.analysis_edition="2026";p.corridors_2026=[official_example().to_dict()]
        restored=ArterialProject.from_dict(p.to_dict())
        self.assertEqual(restored.analysis_edition,"2026")
        self.assertEqual(restored.analyze_all()[0].los,"D")
        self.assertAlmostEqual(restored.analyze_all()[0].speed_kmh,20.06079027355623)
        restored.analysis_edition="2013"
        self.assertEqual(restored.analyze_all(),before)
        self.assertEqual(analyze_corridor(Corridor2026.from_dict(restored.corridors_2026[0])).los,"D")
        self.assertEqual(ArterialProject.from_dict({"version":3}).analysis_edition,"2013")


if __name__=="__main__":unittest.main()
