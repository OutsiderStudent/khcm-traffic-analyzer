"""KHCM 2026, chapter 12, equations 12-1 through 12-3 (pp. 688–698).

One record is one directed corridor, not an individual intersection link.
Approach delays are supplied survey/chapter-8 results, never 2013 estimates.
"""
from dataclasses import dataclass, field, asdict
from math import isfinite
from statistics import fmean

END_TYPES = ("신호교차로", "신호횡단보도", "제한속도 변경지점")


@dataclass
class Subsegment2026:
    end_name: str = ""
    length_m: float = 0.0
    speed_limit_kmh: float = 0.0
    end_type: str = END_TYPES[0]
    through_lanes: int = 0
    delay_s: float | None = None
    capacity_vph: float | None = None
    end_id: str = ""
    approach_id: str = ""


@dataclass
class Corridor2026:
    name: str = "새 분석구간"
    scenario: str = "현황"
    year: int = 2026
    road_category: str = "외부도로"
    start_name: str = ""
    lanes: int = 0
    urban_road_confirmed: bool = False
    signal_control_confirmed: bool = False
    boundaries_confirmed: bool = False
    data_source: str = ""
    survey_date: str = ""
    method: str = "delay"
    travel_times_s: list[float] = field(default_factory=list)
    travel_speeds_kmh: list[float] = field(default_factory=list)
    subsegments: list[Subsegment2026] = field(default_factory=list)
    start_id: str = ""
    diagram_nodes: list[dict[str, str]] = field(default_factory=list)
    network_id: str = ""
    network_path: list[dict] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, raw):
        data = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        data["subsegments"] = [Subsegment2026(**s) for s in raw.get("subsegments", [])]
        return cls(**data)


@dataclass
class Result2026:
    length_m: float
    running_time_s: float
    total_time_s: float
    speed_kmh: float
    los: str
    thresholds: dict[str, float]
    intersections: int
    crossings: int
    capacity_vph: float | None = None
    bottlenecks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sample_count: int = 0


def _number(value, label, minimum=0.0, strict=False):
    try:
        parsed = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{label}: 숫자를 입력하세요.") from None
    if value is None or isinstance(value, bool) or not isfinite(parsed):
        raise ValueError(f"{label}: 유효한 값을 입력하세요.")
    if float(value) < minimum or (strict and float(value) == minimum):
        raise ValueError(f"{label}의 입력 범위를 확인하세요.")
    return float(value)


def analyze_corridor(c: Corridor2026) -> Result2026:
    confirmations=((c.urban_road_confirmed,"도시부 또는 도시부 진·출입 도로인지 확인하세요."),
                   (c.signal_control_confirmed,"평면교차로·횡단보도의 신호 운영 여부를 확인하세요."),
                   (c.boundaries_confirmed,"분석구간 경계와 직진 간선이동류를 확인하세요."))
    missing=[message for confirmed,message in confirmations if confirmed is not True]
    if missing:raise ValueError("\n".join(missing))
    if not c.start_name.strip():raise ValueError("시점 교차로명을 입력하세요.")
    if not c.subsegments:
        raise ValueError("소구간을 추가하세요.")
    if _number(c.lanes, "기본 차로수", 2) != int(c.lanes):
        raise ValueError("차로수는 정수로 입력하세요.")
    length = running = delay = 0.0
    intersections = crossings = 0
    capacities=[]
    warnings=[]
    sample_count=0
    for i, s in enumerate(c.subsegments, 1):
        if not s.end_name.strip():raise ValueError(f"{i}번 소구간 종점명을 입력하세요.")
        part_length = _number(s.length_m, f"{i}번 소구간 길이", strict=True)
        length += part_length
        speed = _number(s.speed_limit_kmh, f"{i}번 제한속도", strict=True)
        running += 3.6 * part_length / speed
        if s.end_type not in END_TYPES:
            raise ValueError(f"{i}번 소구간 종점 유형을 확인하세요.")
        if s.end_type == END_TYPES[0]:
            intersections += 1
            capacities.append((f"{i}. {s.end_name}", None if s.capacity_vph is None else _number(s.capacity_vph, f"{i}번 직진 용량", strict=True)))
            lanes = _number(s.through_lanes, f"{i}번 직진 가능 차로수", 2)
            if lanes != int(lanes):
                raise ValueError("차로수는 정수로 입력하세요.")
        elif s.end_type == END_TYPES[1]:
            crossings += 1
        if c.method == "delay" and s.end_type != END_TYPES[2]:
            delay += _number(s.delay_s, f"{i}번 직진이동류 평균접근지체")
    if length < 1500:
        raise ValueError("2026 기준은 분석구간 길이 1.5km 이상에 적용합니다.")
    if intersections + crossings < 3:
        raise ValueError("분석구간에 신호교차로·신호횡단보도가 합계 3개 이상 필요합니다. 시점 교차로는 제외합니다.")
    if length / (intersections + crossings) > 3000:
        raise ValueError("교통신호의 평균 간격이 3km를 초과합니다.")
    thresholds = {grade: 3.6 * length / (running + intersections * di + crossings * dc)
                  for grade, di, dc in zip("ABCDE", (15, 30, 50, 70, 100), (5, 10, 17, 23, 33))}
    if c.method == "survey":
        if not c.travel_times_s:
            raise ValueError("조사 차량별 구간통행시간을 입력하세요.")
        total = fmean(_number(t, "조사 통행시간", strict=True) for t in c.travel_times_s)
        sample_count=len(c.travel_times_s)
    elif c.method == "speeds":
        if not c.travel_speeds_kmh:raise ValueError("차량별 구간통행속도를 입력하세요.")
        total = fmean(3.6 * length / _number(v,"조사 통행속도",strict=True) for v in c.travel_speeds_kmh)
        sample_count=len(c.travel_speeds_kmh)
    elif c.method == "delay":
        total = running + delay
    else:
        raise ValueError("평균통행속도 산정 방법을 선택하세요.")
    if not all(isfinite(v) and v>0 for v in (length,running,total)):
        raise ValueError("입력값의 크기를 확인하세요. 계산 가능한 범위를 초과했습니다.")
    capacity=None; bottlenecks=[]
    if capacities and all(value is not None for _,value in capacities):
        capacity=min(value for _,value in capacities)
        bottlenecks=[name for name,value in capacities if value==capacity]
    else:
        warnings.append("용량 미산정: 모든 신호교차로의 직진 용량을 입력해야 합니다. 서비스수준 판정에는 영향을 주지 않습니다.")
    if total < running:
        warnings.append("조사 평균통행시간이 제한속도 기준 순행시간보다 짧습니다. 조사 구간·거리·단위를 확인하세요.")
    if not c.data_source.strip():warnings.append("조사자료 또는 접근지체 분석자료의 출처가 기록되지 않았습니다.")
    speed = 3.6 * length / total
    los = next((grade for grade, limit in thresholds.items() if speed >= limit), "F")
    return Result2026(length, running, total, speed, los, thresholds, intersections, crossings, capacity, bottlenecks, warnings, sample_count)


def official_example(number=2):
    """Official worked examples, pp. 699–707; editable review fixtures."""
    rows = [("교차로 B",500,50,END_TYPES[0],44.5),
            ("보호구역 시점",200,50,END_TYPES[2],None),
            ("횡단보도 1",300,30,END_TYPES[1],7.2),
            ("교차로 C",450,50,END_TYPES[0],45.3)]
    rows += ([("교차로 E",750,60,END_TYPES[0],40)] if number == 3 else
             [("교차로 D",400,50,END_TYPES[0],85),("교차로 E",350,50,END_TYPES[0],40)])
    return Corridor2026(name=f"편람 예제 {number}", start_name="교차로 A", lanes=2,
        urban_road_confirmed=True, signal_control_confirmed=True, boundaries_confirmed=True,
        data_source=f"2026 도로용량편람 제12장 예제 {number}",
        method="survey" if number == 1 else "delay",
        travel_times_s=[398,396,379,413,403,426,394,388,375,380] if number == 1 else [],
        subsegments=[Subsegment2026(n,l,s,t,2,d) for n,l,s,t,d in rows])
