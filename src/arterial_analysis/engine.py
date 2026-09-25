from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import sqrt
from typing import Any


ARTERIAL_TYPES = ("유형 I", "유형 II", "유형 III")
FUNCTIONAL_CLASSES = ("고규격", "중간규격", "저규격")
ROAD_CATEGORIES = ("외부 기존도로", "사업시행으로 변경되는 기존도로", "사업지 내부도로")

_RUNNING_TIME = {
    ("유형 I", "대"): (108, 80, 71, 66, 63, 61, 60, 59, 58, 58),
    ("유형 I", "소"): (86, 66, 59, 56, 54, 53, 52, 51, 50, 50),
    ("유형 II", "대"): (143, 100, 85, 77, 73, 70, 68, 66, 65, 65),
    ("유형 II", "소"): (102, 75, 67, 63, 60, 58, 57, 56, 55, 54),
    ("유형 III", "대"): (178, 119, 99, 88, 83, 79, 75, 74, 72, 72),
    ("유형 III", "소"): (119, 85, 74, 69, 65, 63, 62, 61, 60, 58),
}

_LOS_LIMITS = {
    "유형 I": ((67, "A"), (51, "B"), (37, "C"), (28, "D"), (21, "E"), (10, "F"), (6, "FF")),
    "유형 II": ((60, "A"), (46, "B"), (33, "C"), (25, "D"), (18, "E"), (10, "F"), (6, "FF")),
    "유형 III": ((49, "A"), (39, "B"), (29, "C"), (20, "D"), (12, "E"), (8, "F"), (5, "FF")),
}


@dataclass(slots=True)
class AnalysisSettings:
    analysis_period_h: float = 0.25
    base_saturation_flow: float = 2200.0
    saturation_adjustment: float = 1.0
    initial_queue: float = 0.0
    coordinated: bool = False
    pf_override: float | None = None
    crossing_signals: int = 0
    fcw_override: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AnalysisSettings":
        raw = data or {}
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: raw[key] for key in allowed if key in raw})


@dataclass(slots=True)
class SegmentInput:
    uid: str
    comparison_id: str
    scenario: str
    year: int
    road_category: str = ROAD_CATEGORIES[0]
    road_name: str = ""
    start_name: str = ""
    start_number: str = ""
    direction: str = "→"
    end_name: str = ""
    end_number: str = ""
    length_km: float = 1.0
    report_length_km: float | None = None
    cycle_s: float = 120.0
    green_s: float = 50.0
    main_volume: float = 500.0
    report_volume: float | None = None
    phf: float = 1.0
    lanes: int = 2
    functional_class: str = "저규격"
    road_condition_override: str = "보통"
    arterial_type_override: str = "자동"
    bus_stops: int = 0
    access_points: int = 0
    intersection_los: str = ""
    approach_los: str = ""
    speed_limit_kmh: float | None = None
    manual_speed_kmh: float | None = None
    speed_adjustment_history: list[dict[str, Any]] = field(default_factory=list)
    saturation_adjustment: float | None = None
    initial_queue: float | None = None
    pf_override: float | None = None
    fcw_override: float | None = None
    analysis_period_h: float | None = None
    base_saturation_flow: float | None = None
    coordinated: bool | None = None
    crossing_signals: int | None = None
    blank_fields: list[str] = field(default_factory=list)
    volume_source_cell: str = ""
    volume_source_path: str = ""
    volume_source_sheet: str = ""
    volume_link_status: str = ""
    volume_last_value: float | None = None
    volume_link_error: str = ""
    phf_source_cell: str = ""
    phf_source_path: str = ""
    phf_source_sheet: str = ""
    phf_link_status: str = ""
    phf_last_value: float | None = None
    phf_link_error: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SegmentInput":
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: data[key] for key in allowed if key in data})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AnalysisResult:
    segment: SegmentInput
    road_condition: str
    arterial_type: str
    roadside_friction: str
    running_sec_per_km: float
    running_time_s: float
    design_flow: float
    saturation_flow: float
    capacity: float
    vc_ratio: float
    qs_ratio: float
    degree_of_saturation: float
    uniform_delay_s: float
    incremental_delay_s: float
    initial_queue_delay_s: float
    pf: float
    fcw: float
    control_delay_s: float
    total_time_s: float
    calculated_speed_kmh: float
    speed_kmh: float
    los: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["segment"] = self.segment.to_dict()
        return data


def road_condition(functional_class: str, lanes: int) -> str:
    """편람 표 12-3과 예제: 본선 편도 차로수로 도로여건을 1차 판정한다.

    중·저규격의 4차로 이상 '양호' 판정은 접근부 직진차로 2개 이상이라는
    추가 조건을 사용자가 확인해야 한다.
    """
    if functional_class == "고규격":
        return "양호" if lanes >= 3 else "보통"
    return "양호" if lanes >= 4 else "보통"


def arterial_type(functional_class: str, condition: str) -> str:
    """편람 표 12-4의 도로기능 등급·도로여건 조합."""
    if functional_class == "고규격":
        return "유형 I"
    if functional_class == "중간규격":
        return "유형 I" if condition == "양호" else "유형 II"
    return "유형 II" if condition == "양호" else "유형 III"


def roadside_friction(arterial: str, bus_per_km: float, access_per_km: float) -> str:
    access_limit = {"유형 I": 2, "유형 II": 3, "유형 III": 4}[arterial]
    return "대" if bus_per_km > 2 or access_per_km > access_limit else "소"


def running_sec_per_km(arterial: str, friction: str, length_km: float) -> float:
    boundaries = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
    index = next((i for i, upper in enumerate(boundaries) if length_km <= upper), 9)
    return float(_RUNNING_TIME[(arterial, friction)][index])


def los_for_speed(arterial: str, speed: float) -> str:
    for threshold, grade in _LOS_LIMITS[arterial]:
        if speed >= threshold:
            return grade
    return "FFF"


def crossing_factor(coordinated: bool, crossing_signals: int) -> float:
    count = max(0, int(crossing_signals))
    if coordinated:
        return (1.0, 1.1, 1.2)[min(count, 2)]
    return (1.0, 1.0, 1.1)[min(count, 2)]


def _initial_queue_delay(qb: float, capacity: float, flow: float, x: float, period_h: float) -> float:
    if qb <= 0 or capacity <= 0:
        return 0.0
    clearance = (1.0 - x) * capacity * period_h
    if capacity > flow and qb < clearance:
        return 1800.0 * qb * qb / (capacity * period_h * (capacity - flow))
    if clearance > 0 and qb >= clearance:
        return max(0.0, 3600.0 * qb / capacity - 1800.0 * period_h * (1.0 - x))
    return 3600.0 * qb / capacity


def analyze_segment(segment: SegmentInput, settings: AnalysisSettings | None = None) -> AnalysisResult:
    settings = settings or AnalysisSettings()
    warnings: list[str] = []
    if segment.length_km <= 0:
        raise ValueError("구간길이는 0보다 커야 합니다.")
    if segment.cycle_s <= 0:
        raise ValueError("신호주기는 0보다 커야 합니다.")
    if not 0 < segment.green_s <= segment.cycle_s:
        raise ValueError("녹색시간은 0보다 크고 신호주기 이하여야 합니다.")
    if not 0 < segment.phf <= 1:
        raise ValueError("PHF는 0 초과 1 이하여야 합니다.")
    if segment.lanes < 1:
        raise ValueError("본선 차로수(편도)는 1 이상이어야 합니다.")
    if segment.main_volume < 0 or (segment.report_volume is not None and segment.report_volume < 0):
        raise ValueError("교통량은 음수가 될 수 없습니다.")

    automatic_condition = road_condition(segment.functional_class, segment.lanes)
    condition = segment.road_condition_override if segment.road_condition_override in ("양호", "보통") else automatic_condition
    if condition != automatic_condition:
        warnings.append(f"자동 도로여건 {automatic_condition} 대신 {condition} 수동값을 적용했습니다.")
    if segment.road_condition_override == "자동" and segment.functional_class in ("중간규격", "저규격") and condition == "양호":
        warnings.append("도로여건 '양호' 자동판정은 접근부 직진차로 2개 이상 조건을 별도로 확인해야 합니다.")
    automatic_type = arterial_type(segment.functional_class, condition)
    selected_type = segment.arterial_type_override if segment.arterial_type_override in ARTERIAL_TYPES else automatic_type
    if selected_type != automatic_type:
        warnings.append(f"자동 판정 {automatic_type} 대신 {selected_type} 수동값을 적용했습니다.")

    bus_per_km = segment.bus_stops / segment.length_km
    access_per_km = segment.access_points / segment.length_km
    friction = roadside_friction(selected_type, bus_per_km, access_per_km)
    unit_time = running_sec_per_km(selected_type, friction, segment.length_km)
    running_time = unit_time * segment.length_km

    g_ratio = segment.green_s / segment.cycle_s
    design_flow = segment.main_volume / segment.phf
    sat_adjustment = segment.saturation_adjustment if segment.saturation_adjustment is not None else settings.saturation_adjustment
    base_saturation = segment.base_saturation_flow if segment.base_saturation_flow is not None else settings.base_saturation_flow
    saturation = base_saturation * max(0.01, sat_adjustment) * segment.lanes
    capacity = saturation * g_ratio
    vc = design_flow / capacity
    qs = design_flow / saturation
    # 2013 편람 8장 정의에 따라 X=V/c를 적용한다. 12장 예제의 q/s 표기는 별도 안내한다.
    x = vc

    denominator = max(1e-9, 1.0 - min(1.0, x) * g_ratio)
    d1 = 0.5 * segment.cycle_s * (1.0 - g_ratio) ** 2 / denominator
    period_value = segment.analysis_period_h if segment.analysis_period_h is not None else settings.analysis_period_h
    period = max(1e-6, period_value)
    radicand = (x - 1.0) ** 2 + 4.0 * x / max(1e-9, capacity * period)
    d2 = 900.0 * period * ((x - 1.0) + sqrt(max(0.0, radicand)))
    qb = segment.initial_queue if segment.initial_queue is not None else settings.initial_queue
    d3 = _initial_queue_delay(max(0.0, qb), capacity, design_flow, x, period)

    pf_value = segment.pf_override if segment.pf_override is not None else settings.pf_override
    coordinated = segment.coordinated if segment.coordinated is not None else settings.coordinated
    if pf_value is None:
        pf_value = 1.0
        if coordinated:
            warnings.append("연동신호이지만 PF 자료가 없어 기본값 1.0을 적용했습니다.")
    fcw_value = segment.fcw_override if segment.fcw_override is not None else settings.fcw_override
    if fcw_value is None:
        crossing_signals = segment.crossing_signals if segment.crossing_signals is not None else settings.crossing_signals
        fcw_value = crossing_factor(coordinated, crossing_signals)

    delay = d1 * pf_value * fcw_value + d2 + d3
    total_time = running_time + delay
    calculated_speed = 3600.0 * segment.length_km / max(1e-9, total_time)
    speed = segment.manual_speed_kmh if segment.manual_speed_kmh is not None else calculated_speed
    los = los_for_speed(selected_type, speed)
    if vc > 1.0:
        warnings.append("V/c가 1.0을 초과하여 과포화 상태입니다.")
    # 화면·보고서의 V/c가 소수 둘째자리에서 1.10으로 표시되는 경계도 포함한다.
    if vc >= 1.095:
        warnings.append("V/c 1.1 이상에서는 편람 지체모형의 적용 신뢰도가 낮아 현장자료 또는 추가 분석이 필요합니다.")
    if segment.report_volume is not None and segment.report_volume != segment.main_volume:
        warnings.append("보고서 교통량은 계산에 사용한 주이동류 교통량과 다릅니다.")
    if segment.manual_speed_kmh is not None:
        warnings.append(f"편람 원계산 {calculated_speed:.1f}km/h 대신 수동조정 {speed:.1f}km/h를 적용했습니다.")

    return AnalysisResult(
        segment=segment,
        road_condition=condition,
        arterial_type=selected_type,
        roadside_friction=friction,
        running_sec_per_km=unit_time,
        running_time_s=running_time,
        design_flow=design_flow,
        saturation_flow=saturation,
        capacity=capacity,
        vc_ratio=vc,
        qs_ratio=qs,
        degree_of_saturation=x,
        uniform_delay_s=d1,
        incremental_delay_s=d2,
        initial_queue_delay_s=d3,
        pf=pf_value,
        fcw=fcw_value,
        control_delay_s=delay,
        total_time_s=total_time,
        calculated_speed_kmh=calculated_speed,
        speed_kmh=speed,
        los=los,
        warnings=warnings,
    )
