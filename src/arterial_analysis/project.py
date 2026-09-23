from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from .engine import AnalysisResult, AnalysisSettings, ROAD_CATEGORIES, SegmentInput, analyze_segment


SCENARIOS = ("현황", "사업 미시행시", "사업 시행시", "개선대책 이행시")


@dataclass
class ArterialProject:
    name: str = "도시·교외간선도로 분석"
    current_year: int = 2026
    future_years: list[int] = field(default_factory=lambda: [2033, 2037])
    settings: AnalysisSettings = field(default_factory=AnalysisSettings)
    segments: list[SegmentInput] = field(default_factory=list)
    source_note: str = "도로용량편람(2013) 제12장 및 제8장"
    analysis_tabs: list[dict[str, Any]] = field(default_factory=list)
    change_log: list[dict[str, Any]] = field(default_factory=list)

    def add_log(self, entry: dict[str, Any]) -> None:
        """프로젝트 감사 이력은 최근 1,000건만 유지한다."""
        self.change_log.append(dict(entry))
        if len(self.change_log) > 1000:
            del self.change_log[:-1000]

    @property
    def years(self) -> list[int]:
        return [self.current_year, *sorted(set(y for y in self.future_years if y != self.current_year))]

    def valid_years_for(self, scenario: str) -> list[int]:
        return [self.current_year] if scenario == "현황" else sorted(set(self.future_years))

    def add_starter_rows(self) -> None:
        if self.segments:
            return
        if not self.analysis_tabs:
            self.analysis_tabs = [{"scenario": "현황", "year": self.current_year}]
        for direction, start, end, volume in (("→", "기점교차로", "종점교차로", 500), ("←", "기점교차로", "종점교차로", 450)):
            self.segments.append(
                SegmentInput(
                    uid=uuid4().hex,
                    comparison_id="구간-01",
                    scenario="현황",
                    year=self.current_year,
                    road_category=ROAD_CATEGORIES[0],
                    road_name="가로명",
                    start_name=start,
                    end_name=end,
                    direction=direction,
                    main_volume=volume,
                    report_volume=volume,
                )
            )

    def rows(self, scenario: str, year: int) -> list[SegmentInput]:
        return [s for s in self.segments if s.scenario == scenario and s.year == year]

    def replace_rows(self, scenario: str, year: int, rows: list[SegmentInput]) -> None:
        self.segments = [s for s in self.segments if not (s.scenario == scenario and s.year == year)] + rows

    def copy_rows(self, source_scenario: str, source_year: int, target_scenario: str, target_year: int) -> int:
        source = self.rows(source_scenario, source_year)
        copied: list[SegmentInput] = []
        for row in source:
            data = row.to_dict()
            data.update(uid=uuid4().hex, scenario=target_scenario, year=target_year,
                        manual_speed_kmh=None, speed_adjustment_history=[],
                        report_length_km=None, report_volume=None,
                        intersection_los="", approach_los="")
            if data.get("volume_source_cell"):
                data["volume_link_status"] = "unconfirmed"
            else:
                data["main_volume"] = 0.0
                blanks = list(data.get("blank_fields", []))
                if "main_volume" not in blanks:
                    blanks.append("main_volume")
                data["blank_fields"] = blanks
            if data.get("phf_source_cell"):
                data["phf_link_status"] = "unconfirmed"
            copied.append(SegmentInput.from_dict(data))
        self.replace_rows(target_scenario, target_year, copied)
        return len(copied)

    def ensure_tab(self, scenario: str, year: int) -> None:
        if not any(str(item.get("scenario")) == scenario and int(item.get("year", 0)) == int(year) for item in self.analysis_tabs):
            self.analysis_tabs.append({"scenario": scenario, "year": int(year)})
        if scenario == "현황":
            self.current_year = int(year)
        elif int(year) not in self.future_years:
            self.future_years.append(int(year))
            self.future_years.sort()

    def tab_keys(self) -> list[tuple[str, int]]:
        keys = {(str(item["scenario"]), int(item["year"])) for item in self.analysis_tabs}
        keys.update((segment.scenario, segment.year) for segment in self.segments)
        keys.add(("현황", self.current_year))
        order = {"현황": 0, "사업 미시행시": 1, "사업 시행시": 2, "개선대책 이행시": 3}
        return sorted(keys, key=lambda key: (order.get(key[0], 9), key[1]))

    def tab_info(self, scenario: str, year: int) -> dict[str, Any]:
        for item in self.analysis_tabs:
            if str(item.get("scenario")) == scenario and int(item.get("year", 0)) == int(year):
                return item
        item = {"scenario": scenario, "year": int(year)}
        self.analysis_tabs.append(item)
        return item

    def analyze_all(self) -> list[AnalysisResult]:
        active = set(self.tab_keys())
        return [
            analyze_segment(row, self.settings)
            for row in self.segments
            if (row.scenario, row.year) in active and self.is_complete(row)
        ]

    @staticmethod
    def is_complete(row: SegmentInput) -> bool:
        # 저장된 수치가 후속 코드나 구버전 프로젝트에서 직접 바뀐 경우에는
        # 예전 blank_fields 표식을 그대로 결측으로 취급하지 않는다.
        if "main_volume" in row.blank_fields and row.main_volume == 0:
            return False
        return row.length_km > 0 and row.lanes >= 1 and row.cycle_s > 0 and 0 < row.green_s <= row.cycle_s and 0 < row.phf <= 1 and row.main_volume >= 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "arterial-analysis-project",
            "version": 3,
            "name": self.name,
            "current_year": self.current_year,
            "future_years": self.future_years,
            "settings": asdict(self.settings),
            "segments": [s.to_dict() for s in self.segments],
            "source_note": self.source_note,
            "analysis_tabs": self.analysis_tabs,
            "change_log": self.change_log,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArterialProject":
        project = cls(
            name=str(data.get("name", "도시·교외간선도로 분석")),
            current_year=int(data.get("current_year", 2026)),
            future_years=[int(y) for y in data.get("future_years", [2033, 2037])],
            settings=AnalysisSettings.from_dict(data.get("settings")),
            source_note=str(data.get("source_note", "도로용량편람(2013) 제12장 및 제8장")),
            analysis_tabs=list(data.get("analysis_tabs", [])),
            change_log=list(data.get("change_log", []))[-1000:],
        )
        project.segments = [SegmentInput.from_dict(row) for row in data.get("segments", [])]
        return project

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "ArterialProject":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
