import unittest

from arterial_analysis.engine import (
    SegmentInput,
    analyze_segment,
    arterial_type,
    los_for_speed,
    road_condition,
    running_sec_per_km,
)


def sample(**changes):
    data = dict(
        uid="1",
        comparison_id="A",
        scenario="현황",
        year=2026,
        road_name="테스트로",
        start_name="A",
        end_name="B",
        length_km=1.0,
        cycle_s=160,
        green_s=59,
        main_volume=986,
        report_volume=986,
        phf=1.0,
        lanes=2,
        functional_class="저규격",
        bus_stops=4,
        access_points=8,
    )
    data.update(changes)
    return SegmentInput(**data)


class ArterialEngineTest(unittest.TestCase):
    def test_table_12_3_and_12_4_auto_type(self):
        self.assertEqual(road_condition("고규격", 3), "양호")
        self.assertEqual(road_condition("중간규격", 2), "보통")
        self.assertEqual(road_condition("중간규격", 3), "보통")
        self.assertEqual(road_condition("중간규격", 4), "양호")
        self.assertEqual(arterial_type("고규격", "보통"), "유형 I")
        self.assertEqual(arterial_type("중간규격", "보통"), "유형 II")
        self.assertEqual(arterial_type("저규격", "보통"), "유형 III")

    def test_road_condition_can_be_overridden_with_audit_warning(self):
        result = analyze_segment(sample(functional_class="중간규격", lanes=3, road_condition_override="양호"))
        self.assertEqual(result.road_condition, "양호")
        self.assertEqual(result.arterial_type, "유형 I")
        self.assertTrue(any("수동값" in warning for warning in result.warnings))

    def test_high_oversaturation_has_model_limit_warning(self):
        result = analyze_segment(sample(main_volume=6000, report_volume=6000))
        self.assertGreaterEqual(result.vc_ratio, 1.1)
        self.assertTrue(any("적용 신뢰도" in warning for warning in result.warnings))

    def test_table_12_5_has_no_interpolation(self):
        self.assertEqual(running_sec_per_km("유형 III", "대", 0.9), 72)
        self.assertEqual(running_sec_per_km("유형 III", "대", 1.0), 72)
        self.assertEqual(running_sec_per_km("유형 I", "소", 0.15), 66)

    def test_main_and_report_volume_are_separate(self):
        a = analyze_segment(sample(report_volume=1800))
        b = analyze_segment(sample(report_volume=986))
        self.assertAlmostEqual(a.speed_kmh, b.speed_kmh)
        self.assertTrue(any("보고서 교통량" in warning for warning in a.warnings))

    def test_all_default_settings_affect_calculation(self):
        base = analyze_segment(sample())
        changed = analyze_segment(
            sample(initial_queue=20, fcw_override=1.2, pf_override=1.1, saturation_adjustment=0.9)
        )
        self.assertGreater(changed.control_delay_s, base.control_delay_s)
        self.assertLess(changed.capacity, base.capacity)
        self.assertLess(changed.speed_kmh, base.speed_kmh)

    def test_segment_specific_settings_override_project_defaults(self):
        base = analyze_segment(sample())
        changed = analyze_segment(sample(analysis_period_h=1.0, base_saturation_flow=1800, coordinated=True, crossing_signals=2))
        self.assertNotEqual(changed.capacity, base.capacity)
        self.assertNotEqual(changed.control_delay_s, base.control_delay_s)

    def test_los_boundaries(self):
        self.assertEqual(los_for_speed("유형 III", 49), "A")
        self.assertEqual(los_for_speed("유형 III", 39), "B")
        self.assertEqual(los_for_speed("유형 III", 4.9), "FFF")

    def test_invalid_green_is_rejected(self):
        with self.assertRaises(ValueError):
            analyze_segment(sample(green_s=161))

    def test_manual_speed_keeps_original_calculation(self):
        result=analyze_segment(sample(manual_speed_kmh=31.2))
        self.assertEqual(result.speed_kmh,31.2); self.assertNotEqual(result.calculated_speed_kmh,31.2)
        self.assertEqual(result.los,los_for_speed(result.arterial_type,31.2))


if __name__ == "__main__":
    unittest.main()
