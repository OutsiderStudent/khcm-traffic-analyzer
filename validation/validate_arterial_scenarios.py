"""국내 도시·교외간선도로의 대표 조건에 대한 공학적 방향성 회귀검증."""
from __future__ import annotations

from dataclasses import replace

from arterial_analysis.engine import SegmentInput, analyze_segment, arterial_type, crossing_factor, los_for_speed, road_condition


LOS_RANK = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5, "FF": 6, "FFF": 7}


def segment(name: str, **values) -> SegmentInput:
    base = dict(
        uid=name,
        comparison_id=name,
        scenario="현황",
        year=2026,
        road_name=name,
        start_name="기점",
        end_name="종점",
        length_km=1.0,
        report_length_km=1.0,
        cycle_s=160.0,
        green_s=60.0,
        main_volume=500.0,
        report_volume=500.0,
        phf=0.95,
        lanes=2,
        functional_class="중간규격",
    )
    base.update(values)
    return SegmentInput(**base)


ENVIRONMENTS = {
    "교외 고규격": segment("교외 고규격", length_km=1.8, cycle_s=140, green_s=75, lanes=3, functional_class="고규격", bus_stops=0, access_points=1),
    "도시 중간규격": segment("도시 중간규격", length_km=0.8, cycle_s=160, green_s=60, lanes=3, functional_class="중간규격", bus_stops=1, access_points=2),
    "도심 저규격": segment("도심 저규격", length_km=0.4, cycle_s=140, green_s=45, lanes=2, functional_class="저규격", bus_stops=1, access_points=2, crossing_signals=2, phf=0.92),
}

# 기존 '도시 및 교외간선도로_08~09.xlsx' 현황 탭 8개 방향 입력과 표시 결과.
EXCEL_CASES = [
    (2500, 4, 8, 8, 160, 59, 986, 1.0, 2, 16, 40.19, "B"),
    (1200, 3, 7, 8, 160, 59, 1505, 1.0, 2, 9, 31.45, "C"),
    (1000, 2, 3, 4, 160, 67, 1288, 1.0, 2, 11, 37.27, "C"),
    (1000, 2, 5, 4, 160, 32, 584, 1.0, 2, 18, 24.85, "D"),
    (1000, 4, 6, 6, 160, 57, 996, 1.0, 2, 12, 35.08, "C"),
    (1600, 4, 6, 6, 160, 37, 637, 1.0, 2, 19, 32.15, "C"),
    (1900, 4, 3, 2, 160, 94, 704, 1.0, 3, 10, 53.63, "A"),
    (2500, 5, 2, 2, 160, 27, 667, 1.0, 3, 15, 35.88, "C"),
]


def flow_at_vc(base: SegmentInput, target_vc: float) -> SegmentInput:
    capacity = analyze_segment(base).capacity
    volume = round(target_vc * capacity * base.phf)
    return replace(base, main_volume=volume, report_volume=volume)


def main() -> None:
    # 지침 경계·판정표 회귀검증
    assert road_condition("고규격",2)=="보통" and road_condition("고규격",3)=="양호"
    assert road_condition("중간규격",3)=="보통" and road_condition("중간규격",4)=="양호"
    assert arterial_type("고규격","보통")=="유형 I"
    assert arterial_type("중간규격","보통")=="유형 II" and arterial_type("저규격","보통")=="유형 III"
    assert crossing_factor(False,2)==1.1 and crossing_factor(True,2)==1.2
    for arterial, boundaries in {
        "유형 I": ((67,"A"),(51,"B"),(37,"C"),(28,"D"),(21,"E"),(10,"F"),(6,"FF"),(5.99,"FFF")),
        "유형 II": ((60,"A"),(46,"B"),(33,"C"),(25,"D"),(18,"E"),(10,"F"),(6,"FF"),(5.99,"FFF")),
        "유형 III": ((49,"A"),(39,"B"),(29,"C"),(20,"D"),(12,"E"),(8,"F"),(5,"FF"),(4.99,"FFF")),
    }.items():
        for speed, expected in boundaries: assert los_for_speed(arterial,speed)==expected

    print("환경\t목표V/c\t실제V/c\t평균통행속도\tLOS\t지체(초)\t경고")
    for name, base in ENVIRONMENTS.items():
        prior_speed = float("inf")
        prior_rank = -1
        for target in (0.30, 0.60, 0.85, 1.00, 1.10, 1.30):
            result = analyze_segment(flow_at_vc(base, target))
            assert result.speed_kmh <= prior_speed + 1e-9, f"{name}: 교통량 증가 시 속도 역전"
            assert LOS_RANK[result.los] >= prior_rank, f"{name}: 교통량 증가 시 LOS 역전"
            assert result.control_delay_s >= 0 and result.total_time_s > result.running_time_s
            if result.vc_ratio >= 1.095:
                assert any("적용 신뢰도" in warning for warning in result.warnings)
            prior_speed, prior_rank = result.speed_kmh, LOS_RANK[result.los]
            print(f"{name}\t{target:.2f}\t{result.vc_ratio:.2f}\t{result.speed_kmh:.1f}\t{result.los}\t{result.control_delay_s:.1f}\t{' / '.join(result.warnings)}")

    urban = flow_at_vc(ENVIRONMENTS["도시 중간규격"], 0.95)
    improved = replace(urban, lanes=4, green_s=75, road_condition_override="양호")
    before, after = analyze_segment(urban), analyze_segment(improved)
    assert after.capacity > before.capacity and after.speed_kmh > before.speed_kmh and LOS_RANK[after.los] <= LOS_RANK[before.los]
    print(f"개선대책\t차로·녹색시간 개선\t{before.speed_kmh:.1f}→{after.speed_kmh:.1f}\t{before.los}→{after.los}\tV/c {before.vc_ratio:.2f}→{after.vc_ratio:.2f}")

    clean = segment("마찰 비교", length_km=0.7, lanes=3, functional_class="중간규격", bus_stops=0, access_points=0)
    friction = replace(clean, bus_stops=2, access_points=4)
    clean_result, friction_result = analyze_segment(clean), analyze_segment(friction)
    assert friction_result.running_time_s > clean_result.running_time_s and friction_result.speed_kmh < clean_result.speed_kmh
    print(f"노변마찰\t정류장·진출입 증가\t{clean_result.speed_kmh:.1f}→{friction_result.speed_kmh:.1f}\t{clean_result.los}→{friction_result.los}")

    sensitivity = flow_at_vc(ENVIRONMENTS["도시 중간규격"],0.85)
    normal = analyze_segment(sensitivity)
    low_phf = analyze_segment(replace(sensitivity,phf=0.80))
    queued = analyze_segment(replace(sensitivity,initial_queue=20))
    good_coordination = analyze_segment(replace(sensitivity,pf_override=0.75,coordinated=True))
    poor_coordination = analyze_segment(replace(sensitivity,pf_override=1.30,coordinated=True))
    crossings = analyze_segment(replace(sensitivity,crossing_signals=2))
    assert low_phf.vc_ratio>normal.vc_ratio and low_phf.speed_kmh<normal.speed_kmh
    assert queued.control_delay_s>normal.control_delay_s and queued.speed_kmh<normal.speed_kmh
    assert good_coordination.speed_kmh>normal.speed_kmh>poor_coordination.speed_kmh
    assert crossings.control_delay_s>normal.control_delay_s and crossings.speed_kmh<normal.speed_kmh
    print(f"민감도 PHF\t0.95→0.80\t속도 {normal.speed_kmh:.1f}→{low_phf.speed_kmh:.1f}\tV/c {normal.vc_ratio:.2f}→{low_phf.vc_ratio:.2f}")
    print(f"민감도 초기대기\t0→20대\t속도 {normal.speed_kmh:.1f}→{queued.speed_kmh:.1f}\t지체 {normal.control_delay_s:.1f}→{queued.control_delay_s:.1f}")
    print(f"민감도 PF\t0.75/1.00/1.30\t속도 {good_coordination.speed_kmh:.1f}/{normal.speed_kmh:.1f}/{poor_coordination.speed_kmh:.1f}")
    print(f"민감도 횡단신호\t0→2개 비연동\t속도 {normal.speed_kmh:.1f}→{crossings.speed_kmh:.1f}\tfcw {normal.fcw:.1f}→{crossings.fcw:.1f}")

    print("기존 액셀 대조\t액셀속도/LOS\t지침식 재계산 속도/LOS\t차이")
    for index, (length_m, bus, access, crossings, cycle, green, volume, phf, lanes, queue, excel_speed, excel_los) in enumerate(EXCEL_CASES, 1):
        case = segment(
            f"액셀-{index}", length_km=length_m / 1000, bus_stops=bus, access_points=access,
            crossing_signals=crossings, cycle_s=cycle, green_s=green, main_volume=volume,
            report_volume=volume, phf=phf, lanes=lanes, functional_class="중간규격", initial_queue=queue,
        )
        result = analyze_segment(case)
        print(f"{index}\t{excel_speed:.2f}/{excel_los}\t{result.speed_kmh:.2f}/{result.los}\t{result.speed_kmh-excel_speed:+.2f}km/h")


if __name__ == "__main__":
    main()
