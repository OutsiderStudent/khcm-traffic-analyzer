from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QFontDatabase, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .engine import (
    ARTERIAL_TYPES,
    FUNCTIONAL_CLASSES,
    ROAD_CATEGORIES,
    AnalysisResult,
    SegmentInput,
)
from .project import ArterialProject, SCENARIOS
from .reports import export_xlsx, render_report_image, report_for


APP_NAME = "도시·교외간선도로 분석"
APP_VERSION = "1.0.1"
APP_AUTHOR = "made by NYH"
PROJECT_FILTER = "간선도로 분석 프로젝트 (*.ara1)"


def resource_path(relative: str) -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return str(base / relative)


def load_korean_font() -> None:
    font_path = resource_path("assets/NotoSansKR.ttf")
    if Path(font_path).exists():
        QFontDatabase.addApplicationFont(font_path)


def card(title: str, child: QWidget) -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 18, 22, 20)
    heading = QLabel(title)
    heading.setObjectName("cardTitle")
    layout.addWidget(heading)
    layout.addSpacing(6)
    layout.addWidget(child)
    return frame


class ProjectPage(QWidget):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 16)
        title = QLabel("프로젝트와 기본 분석조건을 설정해 주세요")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        intro = QLabel("일반적인 상황의 기본값이 들어 있으며, 변경한 조건은 모든 구간 계산에 실제로 적용됩니다.")
        intro.setObjectName("infoBar")
        intro.setWordWrap(True)
        root.addWidget(intro)

        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(13)
        self.name = QLineEdit()
        self.current_year = QSpinBox(); self.current_year.setRange(2000, 2200)
        self.future_years = QLineEdit(); self.future_years.setPlaceholderText("예: 2033, 2037")
        self.analysis_period = QDoubleSpinBox(); self.analysis_period.setRange(0.05, 4); self.analysis_period.setDecimals(2); self.analysis_period.setSuffix(" 시간")
        self.base_saturation = QDoubleSpinBox(); self.base_saturation.setRange(500, 4000); self.base_saturation.setDecimals(0); self.base_saturation.setSuffix(" pcphgpl")
        self.sat_adjustment = QDoubleSpinBox(); self.sat_adjustment.setRange(0.1, 2); self.sat_adjustment.setDecimals(3)
        self.initial_queue = QDoubleSpinBox(); self.initial_queue.setRange(0, 10000); self.initial_queue.setDecimals(0); self.initial_queue.setSuffix(" 대")
        self.coordinated = QCheckBox("연동신호 적용")
        self.crossing_signals = QSpinBox(); self.crossing_signals.setRange(0, 20); self.crossing_signals.setSuffix(" 개")
        self.pf = QDoubleSpinBox(); self.pf.setRange(0, 3); self.pf.setDecimals(3); self.pf.setSpecialValueText("자동/1.0")
        self.fcw = QDoubleSpinBox(); self.fcw.setRange(0, 3); self.fcw.setDecimals(3); self.fcw.setSpecialValueText("자동")
        form.addRow("프로젝트명", self.name)
        form.addRow("현황 연도", self.current_year)
        form.addRow("장래 분석연도", self.future_years)
        form.addRow("분석기간 T", self.analysis_period)
        form.addRow("기본 포화교통류율", self.base_saturation)
        form.addRow("통합 포화교통류율 보정계수", self.sat_adjustment)
        form.addRow("초기 대기차량 Qb", self.initial_queue)
        form.addRow("신호 연동", self.coordinated)
        form.addRow("구간 중간 횡단신호", self.crossing_signals)
        form.addRow("연동보정계수 PF 직접입력", self.pf)
        form.addRow("횡단신호보정계수 fcw 직접입력", self.fcw)
        root.addWidget(card("1. 프로젝트 기본설정", form_widget))

        scenario_text = QLabel(
            "현황: 조사시점 도로망  ·  사업 미시행시: 우리 사업을 제외한 장래 도로망(타 사업 반영 가능)\n"
            "사업 시행시: 우리 사업과 사업지 내부도로 반영  ·  개선대책 이행시: 시행안에 개선대책 추가"
        )
        scenario_text.setWordWrap(True)
        root.addWidget(card("분석 상황 구분", scenario_text))
        root.addStretch()
        nav = QHBoxLayout(); nav.addStretch()
        self.next_button = QPushButton("구간 입력으로")
        self.next_button.setObjectName("primaryButton")
        nav.addWidget(self.next_button)
        root.addLayout(nav)

    def load_project(self, project: ArterialProject) -> None:
        self.name.setText(project.name)
        self.current_year.setValue(project.current_year)
        self.future_years.setText(", ".join(map(str, project.future_years)))
        s = project.settings
        self.analysis_period.setValue(s.analysis_period_h)
        self.base_saturation.setValue(s.base_saturation_flow)
        self.sat_adjustment.setValue(s.saturation_adjustment)
        self.initial_queue.setValue(s.initial_queue)
        self.coordinated.setChecked(s.coordinated)
        self.crossing_signals.setValue(s.crossing_signals)
        self.pf.setValue(s.pf_override or 0)
        self.fcw.setValue(s.fcw_override or 0)

    def apply(self, project: ArterialProject) -> None:
        years: list[int] = []
        for token in self.future_years.text().replace(";", ",").split(","):
            if token.strip():
                years.append(int(token.strip()))
        if not years:
            raise ValueError("장래 분석연도를 한 개 이상 입력해 주세요.")
        project.name = self.name.text().strip() or APP_NAME
        project.current_year = self.current_year.value()
        project.future_years = sorted(set(years))
        s = project.settings
        s.analysis_period_h = self.analysis_period.value()
        s.base_saturation_flow = self.base_saturation.value()
        s.saturation_adjustment = self.sat_adjustment.value()
        s.initial_queue = self.initial_queue.value()
        s.coordinated = self.coordinated.isChecked()
        s.crossing_signals = self.crossing_signals.value()
        s.pf_override = self.pf.value() or None
        s.fcw_override = self.fcw.value() or None


class CopyDialog(QDialog):
    def __init__(self, project: ArterialProject, current_scenario: str, current_year: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("현재 표 복사")
        layout = QFormLayout(self)
        self.scenario = QComboBox(); self.scenario.addItems(SCENARIOS); self.scenario.setCurrentText(current_scenario)
        self.year = QComboBox()
        self.scenario.currentTextChanged.connect(lambda text: self._sync_years(project, text))
        self._sync_years(project, current_scenario)
        if str(current_year) in [self.year.itemText(i) for i in range(self.year.count())]:
            self.year.setCurrentText(str(current_year))
        layout.addRow("복사할 상황", self.scenario)
        layout.addRow("복사할 연도", self.year)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _sync_years(self, project: ArterialProject, scenario: str) -> None:
        self.year.clear(); self.year.addItems([str(y) for y in project.valid_years_for(scenario)])


class SegmentDetailDialog(QDialog):
    """구간마다 달라질 수 있는 상세 분석조건 입력."""

    def __init__(self, segment: SegmentInput, project: ArterialProject, parent=None) -> None:
        super().__init__(parent)
        self.segment = segment
        self.project = project
        self.setWindowTitle("구간별 상세 분석조건")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        heading = QLabel(f"{segment.road_name} · {segment.start_name} {segment.direction} {segment.end_name}")
        heading.setObjectName("cardTitle")
        layout.addWidget(heading)
        note = QLabel("아래 값은 선택한 방향 구간에만 적용됩니다.")
        note.setObjectName("infoBar")
        layout.addWidget(note)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(11)
        self.analysis_period = QDoubleSpinBox(); self.analysis_period.setRange(0.05, 4); self.analysis_period.setDecimals(2); self.analysis_period.setSuffix(" 시간")
        self.base_saturation = QDoubleSpinBox(); self.base_saturation.setRange(500, 4000); self.base_saturation.setDecimals(0); self.base_saturation.setSuffix(" pcphgpl")
        self.sat_adjustment = QDoubleSpinBox(); self.sat_adjustment.setRange(0.1, 2); self.sat_adjustment.setDecimals(3)
        self.initial_queue = QDoubleSpinBox(); self.initial_queue.setRange(0, 10000); self.initial_queue.setDecimals(0); self.initial_queue.setSuffix(" 대")
        self.coordinated = QCheckBox("연동신호")
        self.crossing_signals = QSpinBox(); self.crossing_signals.setRange(0, 20); self.crossing_signals.setSuffix(" 개")
        self.pf = QDoubleSpinBox(); self.pf.setRange(0, 3); self.pf.setDecimals(3); self.pf.setSpecialValueText("자동/1.0")
        self.fcw = QDoubleSpinBox(); self.fcw.setRange(0, 3); self.fcw.setDecimals(3); self.fcw.setSpecialValueText("자동")
        form.addRow("분석기간 T", self.analysis_period)
        form.addRow("기본 포화교통류율", self.base_saturation)
        form.addRow("통합 포화교통류율 보정계수", self.sat_adjustment)
        form.addRow("초기 대기차량 Qb", self.initial_queue)
        form.addRow("신호 연동", self.coordinated)
        form.addRow("구간 중간 횡단신호", self.crossing_signals)
        form.addRow("연동보정계수 PF 직접입력", self.pf)
        form.addRow("횡단신호보정계수 fcw 직접입력", self.fcw)
        layout.addWidget(form_widget)
        buttons = QDialogButtonBox(QDialogButtonBox.RestoreDefaults | QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.RestoreDefaults).setText("기본값")
        buttons.button(QDialogButtonBox.Ok).setText("적용")
        buttons.button(QDialogButtonBox.Cancel).setText("취소")
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self.set_defaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.load_segment()

    def load_segment(self) -> None:
        s, defaults = self.segment, self.project.settings
        self.analysis_period.setValue(s.analysis_period_h if s.analysis_period_h is not None else defaults.analysis_period_h)
        self.base_saturation.setValue(s.base_saturation_flow if s.base_saturation_flow is not None else defaults.base_saturation_flow)
        self.sat_adjustment.setValue(s.saturation_adjustment if s.saturation_adjustment is not None else defaults.saturation_adjustment)
        self.initial_queue.setValue(s.initial_queue if s.initial_queue is not None else defaults.initial_queue)
        self.coordinated.setChecked(s.coordinated if s.coordinated is not None else defaults.coordinated)
        self.crossing_signals.setValue(s.crossing_signals if s.crossing_signals is not None else defaults.crossing_signals)
        self.pf.setValue(s.pf_override or 0)
        self.fcw.setValue(s.fcw_override or 0)

    def set_defaults(self) -> None:
        defaults = self.project.settings
        self.analysis_period.setValue(defaults.analysis_period_h)
        self.base_saturation.setValue(defaults.base_saturation_flow)
        self.sat_adjustment.setValue(defaults.saturation_adjustment)
        self.initial_queue.setValue(defaults.initial_queue)
        self.coordinated.setChecked(defaults.coordinated)
        self.crossing_signals.setValue(defaults.crossing_signals)
        self.pf.setValue(defaults.pf_override or 0)
        self.fcw.setValue(defaults.fcw_override or 0)

    def apply_to_segment(self) -> None:
        s = self.segment
        s.analysis_period_h = self.analysis_period.value()
        s.base_saturation_flow = self.base_saturation.value()
        s.saturation_adjustment = self.sat_adjustment.value()
        s.initial_queue = self.initial_queue.value()
        s.coordinated = self.coordinated.isChecked()
        s.crossing_signals = self.crossing_signals.value()
        s.pf_override = self.pf.value() or None
        s.fcw_override = self.fcw.value() or None


class InputPage(QWidget):
    COLUMNS = [
        "비교구간 ID", "도로 구분", "가로명", "시점", "↔", "종점", "길이(km)", "주기(초)", "녹색(초)",
        "주이동류 교통량", "보고서 교통량", "PHF", "본선 차로수(편도)", "기능등급", "간선도로 유형", "정류장수", "진출입로수",
    ]

    def __init__(self, project: ArterialProject) -> None:
        super().__init__()
        self.project = project
        self.current_key: tuple[str, int] | None = None
        root = QVBoxLayout(self); root.setContentsMargins(18, 18, 18, 16)
        title = QLabel("상황·연도별 분석구간을 입력해 주세요"); title.setObjectName("pageTitle")
        root.addWidget(title)

        project_row = QHBoxLayout()
        self.project_name = QLineEdit(); self.project_name.setMinimumWidth(260)
        self.current_year = QSpinBox(); self.current_year.setRange(2000, 2200); self.current_year.setFixedWidth(92)
        project_row.addWidget(QLabel("프로젝트명")); project_row.addWidget(self.project_name, 1)
        project_row.addWidget(QLabel("현황연도")); project_row.addWidget(self.current_year)
        root.addLayout(project_row)

        selector_row = QHBoxLayout()
        self.future_years = QLineEdit(); self.future_years.setPlaceholderText("예: 2033, 2037"); self.future_years.setMinimumWidth(180)
        self.scenario = QComboBox(); self.scenario.addItems(SCENARIOS)
        self.year = QComboBox()
        selector_row.addWidget(QLabel("장래 분석연도")); selector_row.addWidget(self.future_years, 1)
        selector_row.addSpacing(12); selector_row.addWidget(QLabel("분석 상황")); selector_row.addWidget(self.scenario)
        selector_row.addWidget(QLabel("연도")); selector_row.addWidget(self.year)
        root.addLayout(selector_row)
        note = QLabel("화살표 한 행이 한 방향 구간입니다. 계산에는 주이동류 교통량을, 성과품 표에는 보고서 교통량을 사용합니다.")
        note.setObjectName("infoBar"); root.addWidget(note)
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        widths = [95, 190, 100, 125, 44, 125, 80, 80, 80, 120, 115, 65, 120, 90, 105, 75, 80]
        for i, width in enumerate(widths): self.table.setColumnWidth(i, width)
        self.table.horizontalHeader().setStretchLastSection(False)
        root.addWidget(card("1. 구간 입력", self.table), 1)
        tools = QHBoxLayout()
        self.add_pair = QPushButton("양방향 구간 추가")
        self.delete = QPushButton("선택 행 삭제")
        self.detail = QPushButton("선택 구간 상세조건")
        self.reset = QPushButton("선택 행 기본값 초기화")
        self.copy = QPushButton("현재 표를 다른 상황·연도로 복사")
        tools.addWidget(self.add_pair); tools.addWidget(self.delete); tools.addWidget(self.detail); tools.addWidget(self.reset); tools.addStretch()
        root.addLayout(tools)
        copy_row = QHBoxLayout(); copy_row.addWidget(self.copy); copy_row.addStretch()
        root.addLayout(copy_row)
        nav = QHBoxLayout(); self.next_button = QPushButton("입력 확인")
        self.next_button.setObjectName("primaryButton")
        nav.addStretch(); nav.addWidget(self.next_button); root.addLayout(nav)
        self.scenario.currentTextChanged.connect(self._selector_changed)
        self.year.currentTextChanged.connect(self._selector_changed)
        self.add_pair.clicked.connect(self.add_direction_pair)
        self.delete.clicked.connect(self.delete_selected)
        self.detail.clicked.connect(self.edit_details)
        self.reset.clicked.connect(self.reset_selected)
        self.copy.clicked.connect(self.copy_current)
        self.load_project_info()

    def load_project_info(self) -> None:
        self.project_name.setText(self.project.name)
        self.current_year.setValue(self.project.current_year)
        self.future_years.setText(", ".join(map(str, self.project.future_years)))

    def apply_project_info(self) -> None:
        years = [int(token.strip()) for token in self.future_years.text().replace(";", ",").split(",") if token.strip()]
        if not years:
            raise ValueError("장래 분석연도를 한 개 이상 입력해 주세요.")
        old_current = self.project.current_year
        new_current = self.current_year.value()
        self.project.name = self.project_name.text().strip() or APP_NAME
        self.project.current_year = new_current
        self.project.future_years = sorted(set(years))
        if old_current != new_current:
            for segment in self.project.segments:
                if segment.scenario == "현황" and segment.year == old_current:
                    segment.year = new_current

    def refresh_selectors(self) -> None:
        self.apply_project_info()
        scenario = self.scenario.currentText() or "현황"
        year = self.year.currentText()
        self.year.blockSignals(True)
        self.year.clear(); self.year.addItems([str(y) for y in self.project.valid_years_for(scenario)])
        if year and year in [self.year.itemText(i) for i in range(self.year.count())]: self.year.setCurrentText(year)
        self.year.blockSignals(False)
        self._selector_changed()

    def _selector_changed(self) -> None:
        if self.current_key:
            self.save_table(*self.current_key)
        scenario = self.scenario.currentText()
        valid = [str(y) for y in self.project.valid_years_for(scenario)] if scenario else []
        if self.year.count() == 0 or any(self.year.itemText(i) not in valid for i in range(self.year.count())):
            self.year.blockSignals(True); self.year.clear(); self.year.addItems(valid); self.year.blockSignals(False)
        if not self.year.currentText(): return
        self.current_key = scenario, int(self.year.currentText())
        self.load_table(*self.current_key)

    @staticmethod
    def _item(value: object) -> QTableWidgetItem:
        return QTableWidgetItem(str(value))

    def load_table(self, scenario: str, year: int) -> None:
        rows = self.project.rows(scenario, year)
        self.table.setRowCount(0)
        for segment in rows:
            self._append_segment(segment)

    def _append_segment(self, s: SegmentInput) -> None:
        values = [s.comparison_id, s.road_category, s.road_name, s.start_name, s.direction, s.end_name, s.length_km,
                  s.cycle_s, s.green_s, s.main_volume, s.report_volume, s.phf, s.lanes, s.functional_class,
                  s.arterial_type_override, s.bus_stops, s.access_points]
        row = self.table.rowCount(); self.table.insertRow(row)
        for column, value in enumerate(values):
            item = self._item(value); item.setData(Qt.UserRole, s.uid if column == 0 else None)
            if column == 4: item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, column, item)

    def save_table(self, scenario: str | None = None, year: int | None = None) -> None:
        if scenario is None or year is None:
            if not self.current_key: return
            scenario, year = self.current_key
        old_by_uid = {segment.uid: segment for segment in self.project.rows(scenario, int(year))}
        rows: list[SegmentInput] = []
        for r in range(self.table.rowCount()):
            text = lambda c: (self.table.item(r, c).text().strip() if self.table.item(r, c) else "")
            uid = self.table.item(r, 0).data(Qt.UserRole) if self.table.item(r, 0) else None
            old = old_by_uid.get(uid)
            rows.append(SegmentInput(
                uid=uid or uuid4().hex, comparison_id=text(0) or f"구간-{r // 2 + 1:02d}", scenario=scenario, year=int(year),
                road_category=text(1) if text(1) in ROAD_CATEGORIES else ROAD_CATEGORIES[0], road_name=text(2), start_name=text(3),
                direction=text(4) if text(4) in ("→", "←") else "→", end_name=text(5), length_km=float(text(6) or 0),
                cycle_s=float(text(7) or 0), green_s=float(text(8) or 0), main_volume=float(text(9) or 0),
                report_volume=float(text(10) or text(9) or 0), phf=float(text(11) or 0), lanes=int(float(text(12) or 0)),
                functional_class=text(13) if text(13) in FUNCTIONAL_CLASSES else "중간규격",
                arterial_type_override=text(14) if text(14) in (*ARTERIAL_TYPES, "자동") else "자동",
                bus_stops=int(float(text(15) or 0)), access_points=int(float(text(16) or 0)),
                saturation_adjustment=old.saturation_adjustment if old else None,
                initial_queue=old.initial_queue if old else None,
                pf_override=old.pf_override if old else None,
                fcw_override=old.fcw_override if old else None,
                analysis_period_h=old.analysis_period_h if old else None,
                base_saturation_flow=old.base_saturation_flow if old else None,
                coordinated=old.coordinated if old else None,
                crossing_signals=old.crossing_signals if old else None,
            ))
        self.project.replace_rows(scenario, int(year), rows)

    def add_direction_pair(self) -> None:
        number = max(1, self.table.rowCount() // 2 + 1)
        scenario, year = self.current_key or ("현황", self.project.current_year)
        base = dict(comparison_id=f"구간-{number:02d}", scenario=scenario, year=year, road_name="가로명",
                    start_name="기점교차로", end_name="종점교차로", length_km=1.0, cycle_s=120, green_s=50,
                    phf=1.0, lanes=2, main_volume=500, report_volume=500)
        self._append_segment(SegmentInput(uid=uuid4().hex, direction="→", **base))
        self._append_segment(SegmentInput(uid=uuid4().hex, direction="←", **base))
        self.table.scrollToBottom()

    def delete_selected(self) -> None:
        for row in sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def _selected_rows(self) -> list[int]:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not rows and self.table.currentRow() >= 0:
            rows = [self.table.currentRow()]
        return rows

    def edit_details(self) -> None:
        rows = self._selected_rows()
        if len(rows) != 1:
            QMessageBox.information(self, "상세조건", "상세조건을 편집할 행 하나를 선택해 주세요.")
            return
        try:
            self.save_table()
        except ValueError as exc:
            QMessageBox.warning(self, "입력 확인", str(exc)); return
        uid = self.table.item(rows[0], 0).data(Qt.UserRole)
        segment = next((item for item in self.project.segments if item.uid == uid), None)
        if segment is None:
            return
        dialog = SegmentDetailDialog(segment, self.project, self)
        if dialog.exec() == QDialog.Accepted:
            dialog.apply_to_segment()

    def reset_selected(self) -> None:
        rows = self._selected_rows()
        if not rows:
            QMessageBox.information(self, "기본값 초기화", "초기화할 행을 선택해 주세요.")
            return
        try:
            self.save_table()
        except ValueError as exc:
            QMessageBox.warning(self, "입력 확인", str(exc)); return
        uids = {self.table.item(row, 0).data(Qt.UserRole) for row in rows}
        defaults = self.project.settings
        for segment in self.project.segments:
            if segment.uid not in uids:
                continue
            segment.length_km = 1.0; segment.cycle_s = 120.0; segment.green_s = 50.0
            segment.main_volume = 500.0; segment.report_volume = 500.0; segment.phf = 1.0; segment.lanes = 2
            segment.functional_class = "중간규격"; segment.arterial_type_override = "자동"
            segment.bus_stops = 0; segment.access_points = 0
            segment.analysis_period_h = defaults.analysis_period_h
            segment.base_saturation_flow = defaults.base_saturation_flow
            segment.saturation_adjustment = defaults.saturation_adjustment
            segment.initial_queue = defaults.initial_queue
            segment.coordinated = defaults.coordinated
            segment.crossing_signals = defaults.crossing_signals
            segment.pf_override = defaults.pf_override; segment.fcw_override = defaults.fcw_override
        if self.current_key:
            self.load_table(*self.current_key)
        QMessageBox.information(self, "기본값 초기화", f"선택한 {len(rows)}개 행의 분석 입력값을 기본값으로 초기화했습니다.")

    def copy_current(self) -> None:
        try: self.save_table()
        except ValueError as exc:
            QMessageBox.warning(self, "입력 확인", str(exc)); return
        if not self.current_key: return
        dialog = CopyDialog(self.project, *self.current_key, self)
        if dialog.exec() != QDialog.Accepted: return
        target_scenario, target_year = dialog.scenario.currentText(), int(dialog.year.currentText())
        if (target_scenario, target_year) == self.current_key:
            QMessageBox.information(self, "복사", "현재 표와 대상이 같습니다."); return
        count = self.project.copy_rows(*self.current_key, target_scenario, target_year)
        QMessageBox.information(self, "복사 완료", f"{count}개 방향 구간을 복사했습니다.")


class ConfirmPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self); root.setContentsMargins(18, 18, 18, 16)
        title = QLabel("입력자료와 자동 판정값을 확인해 주세요"); title.setObjectName("pageTitle"); root.addWidget(title)
        self.info = QLabel(); self.info.setObjectName("infoBar"); self.info.setWordWrap(True); root.addWidget(self.info)
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(["상황", "연도", "가로명", "구간", "주이동류", "보고서 교통량", "유형", "노변마찰", "V/c", "예상 LOS"])
        self.table.verticalHeader().setVisible(False); self.table.setEditTriggers(QTableWidget.NoEditTriggers); self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(card("2. 입력 확인", self.table), 1)
        nav = QHBoxLayout(); self.prev_button = QPushButton("이전"); self.next_button = QPushButton("전체 분석 실행"); self.next_button.setObjectName("primaryButton")
        nav.addWidget(self.prev_button); nav.addStretch(); nav.addWidget(self.next_button); root.addLayout(nav)

    def refresh(self, project: ArterialProject, results: list[AnalysisResult]) -> None:
        self.table.setRowCount(len(results))
        warning_count = 0
        for row, r in enumerate(results):
            s = r.segment; warning_count += len(r.warnings)
            values = [s.scenario, s.year, s.road_name, f"{s.start_name} {s.direction} {s.end_name}", f"{s.main_volume:,.0f}",
                      f"{s.report_volume:,.0f}", r.arterial_type, r.roadside_friction, f"{r.vc_ratio:.2f}", r.los]
            for col, value in enumerate(values): self.table.setItem(row, col, QTableWidgetItem(str(value)))
        self.info.setText(
            f"총 {len(results)}개 방향 구간 · 자동 도로유형 및 노변마찰 판정 적용 · 검토 알림 {warning_count}건\n"
            "분석식은 도로용량편람(2013) 제12장, 용량·포화도 정의는 제8장을 적용합니다."
        )


class ResultsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.project: ArterialProject | None = None
        self.results: list[AnalysisResult] = []
        root = QVBoxLayout(self); root.setContentsMargins(18, 18, 18, 16)
        self.hero = QLabel(); self.hero.setObjectName("resultHero"); self.hero.setWordWrap(True); root.addWidget(self.hero)
        controls = QHBoxLayout()
        self.report_kind = QComboBox(); self.report_kind.addItems(["현황 표", "장래년도 통합 - 사업 미시행시", "장래년도 통합 - 사업 시행시", "장래년도 통합 - 개선대책 이행시", "미시행·시행 비교", "시행·개선 비교"])
        self.report_year = QComboBox()
        controls.addWidget(QLabel("성과품 표")); controls.addWidget(self.report_kind, 1); controls.addWidget(QLabel("비교연도")); controls.addWidget(self.report_year)
        root.addLayout(controls)
        export_row = QHBoxLayout(); export_row.addStretch()
        self.copy_png = QPushButton("표 이미지 복사"); self.save_png = QPushButton("PNG 저장"); self.save_xlsx = QPushButton("Excel 저장")
        export_row.addWidget(self.copy_png); export_row.addWidget(self.save_png); export_row.addWidget(self.save_xlsx)
        root.addLayout(export_row)
        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(["상황", "연도", "가로명", "구간", "유형", "교통량", "V/c", "지체(초)", "속도(km/h)", "LOS", "검토 알림"])
        self.table.verticalHeader().setVisible(False); self.table.setEditTriggers(QTableWidget.NoEditTriggers); self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents); self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(card("3. 분석 결과", self.table), 1)
        nav = QHBoxLayout(); self.prev_button = QPushButton("입력 확인으로"); self.restart_button = QPushButton("처음으로"); self.restart_button.setObjectName("primaryButton")
        nav.addWidget(self.prev_button); nav.addStretch(); nav.addWidget(self.restart_button); root.addLayout(nav)
        self.copy_png.clicked.connect(self.copy_report)
        self.save_png.clicked.connect(self.save_report_png)
        self.save_xlsx.clicked.connect(self.save_report_xlsx)

    def refresh(self, project: ArterialProject, results: list[AnalysisResult]) -> None:
        self.project, self.results = project, results
        self.report_year.clear(); self.report_year.addItems([str(y) for y in project.future_years])
        self.table.setRowCount(len(results))
        worst = None
        rank = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5, "FF": 6, "FFF": 7}
        for row, r in enumerate(results):
            worst = r if worst is None or rank[r.los] > rank[worst.los] else worst
            s = r.segment
            values = [s.scenario, s.year, s.road_name, f"{s.start_name} {s.direction} {s.end_name}", r.arterial_type,
                      f"{s.report_volume:,.0f}", f"{r.vc_ratio:.2f}", f"{r.control_delay_s:.1f}", f"{r.speed_kmh:.1f}", r.los, " · ".join(r.warnings)]
            for col, value in enumerate(values): self.table.setItem(row, col, QTableWidgetItem(str(value)))
        if worst:
            self.hero.setText(f"분석 완료  |  최저 서비스수준 {worst.los}\n{worst.segment.road_name} · {worst.segment.start_name} {worst.segment.direction} {worst.segment.end_name} · 평균속도 {worst.speed_kmh:.1f} km/h")
        else:
            self.hero.setText("분석할 구간이 없습니다.")

    def _spec(self):
        if self.project is None: raise ValueError("분석 결과가 없습니다.")
        year = int(self.report_year.currentText()) if self.report_year.currentText() else None
        return report_for(self.project, self.results, self.report_kind.currentText(), year)

    def copy_report(self) -> None:
        image = render_report_image(self._spec())
        QGuiApplication.clipboard().setImage(image)
        QMessageBox.information(self, "복사 완료", "성과품 표 이미지를 클립보드에 복사했습니다.")

    def save_report_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "PNG 저장", f"{self._spec().title}.png", "PNG 이미지 (*.png)")
        if path and not render_report_image(self._spec()).save(path): QMessageBox.warning(self, "저장 실패", "PNG 파일을 저장하지 못했습니다.")

    def save_report_xlsx(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Excel 저장", f"{self._spec().title}.xlsx", "Excel 통합문서 (*.xlsx)")
        if not path: return
        try: export_xlsx(self._spec(), path)
        except Exception as exc: QMessageBox.critical(self, "저장 실패", f"Excel 파일을 저장하지 못했습니다.\n{exc}")


class GuidelinePage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self); root.setContentsMargins(18, 14, 18, 14)
        title = QLabel("도로용량편람(2013) 적용 기준과 계산 공식"); title.setObjectName("pageTitle"); root.addWidget(title)
        intro = QLabel("제12장 도시 및 교외간선도로와 제8장 신호교차로 산식을 기준으로 프로그램의 자동판정, 계산순서, 입력자료와 적용 한계를 정리했습니다. 표·본문이 충돌하는 항목은 프로그램 적용기준을 별도로 표시합니다.")
        intro.setObjectName("infoBar"); intro.setWordWrap(True); root.addWidget(intro)
        tabs = QTabWidget(); tabs.setDocumentMode(True); root.addWidget(tabs, 1)
        tabs.addTab(self._page(self._overview_sections()), "분석범위·절차")
        tabs.addTab(self._page(self._classification_sections()), "유형·순행시간")
        tabs.addTab(self._page(self._formula_sections()), "지체·속도 공식")
        tabs.addTab(self._page(self._los_sections()), "서비스수준")
        tabs.addTab(self._page(self._input_sections()), "입력·검토 기준")

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text); label.setWordWrap(True); label.setTextFormat(Qt.RichText)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse); label.setOpenExternalLinks(False)
        return label

    def _page(self, sections: list[tuple[str, str]]) -> QScrollArea:
        area = QScrollArea(); area.setWidgetResizable(True); area.setFrameShape(QFrame.NoFrame)
        body = QWidget(); layout = QVBoxLayout(body); layout.setContentsMargins(4, 10, 8, 12); layout.setSpacing(10)
        for heading, text in sections: layout.addWidget(card(heading, self._label(text)))
        layout.addStretch(); area.setWidget(body); return area

    @staticmethod
    def _overview_sections() -> list[tuple[str, str]]:
        return [
            ("적용 대상과 분석단위", "<b>대상</b>: 신호교차로가 설치된 도시·교외 간선도로의 일반차로 직진 교통류.<br>"
             "<b>기본단위</b>: 한 신호교차로에서 다음 신호교차로까지의 <b>한 방향 구간</b>. 양방향은 서로 다른 분석행으로 계산합니다.<br>"
             "편람상 일반적인 간선도로는 신호교차로 간격 3km 이하, 평균 300~500m, 편도 2차로 이상을 전제로 합니다. 이 범위를 벗어나면 적용 가능성을 별도로 검토해야 합니다."),
            ("7단계 분석절차", "① 분석대상 위치·연장 설정 → ② 기능등급·도로여건 및 간선도로 유형 결정 → ③ 신호교차로 사이 한 방향 구간 분류 → ④ 노변마찰과 구간길이에 따른 순행시간 산정 → ⑤ 직진 차로군의 평균제어지체 계산 → ⑥ 순행시간과 지체로 평균통행속도 계산 → ⑦ 유형별 속도기준으로 서비스수준 판정"),
            ("프로그램 계산범위", "<b>지원</b>: 일반차로 구간별 평균통행속도·LOS, 현황/미시행/시행/개선 비교, PF·횡단신호·초기대기차량·포화교통류율의 구간별 조건, 부록용 세부 계산표.<br>"
             "<b>별도 검토</b>: 교차로 용량의 정밀 산정은 제8장 입력값을 사용해야 하며, 중앙버스전용차로는 제12장 별도 절차(표 12-11 및 식 12-10~12)를 적용하므로 현재 일반차로 프로그램의 직접 분석대상이 아닙니다."),
            ("교통량 적용원칙", "편람 분석의 원칙은 <b>직진 교통류가 사용하는 주요 차로군</b>입니다. 프로그램의 ‘주이동류 교통량’은 계산에 사용하고, ‘보고서 교통량’은 성과품에 표시합니다. 회전류가 사실상 주이동류인 특수 교차로에서 다른 교통량을 사용할 경우 적용 근거를 보고서 또는 메모에 남겨야 합니다."),
        ]

    @staticmethod
    def _classification_sections() -> list[tuple[str, str]]:
        return [
            ("기능등급 판단", "<table cellspacing='0' cellpadding='6' border='1'>"
             "<tr><th>구분</th><th>고규격</th><th>중간규격</th><th>저규격</th></tr>"
             "<tr><td>이동성</td><td>매우 중요</td><td>중요</td><td>보통</td></tr>"
             "<tr><td>접근관리</td><td>고</td><td>중</td><td>저</td></tr>"
             "<tr><td>주 통행목적</td><td>장거리 통과</td><td>도시부 접근</td><td>도시부 내부</td></tr>"
             "<tr><td>신호교차로</td><td>2개/km 이하</td><td>1~3개/km</td><td>2개/km 이상</td></tr>"
             "<tr><td>주변 개발</td><td>저밀도</td><td>중간·혼재</td><td>고밀도 업무·상업</td></tr></table>"
             "기준이 혼재하면 주변개발 정도, 도로 기능, 접근관리와 차로수를 함께 보고 공학적으로 판단합니다."),
            ("도로여건 자동판정과 지침 내 불일치", "<b>프로그램 적용기준</b>: 본문과 예제 1에 따라 고규격은 편도 2차로 ‘보통’, 3차로 이상 ‘양호’; 중·저규격은 편도 2~3차로 ‘보통’, 4차로 이상이면서 접근부 직진차로 2개 이상일 때 ‘양호’로 판정합니다.<br>"
             "<font color='#9A4D00'><b>주의:</b> 표 12-3의 인쇄 내용은 이 본문 기준과 차로수 경계가 반대로 기재되어 있습니다. 예제 1은 중간규격 편도 3차로를 ‘보통→유형 II’로 판정하므로 프로그램은 본문·예제 기준을 채택합니다. 자동판정이 현장조건과 다르면 도로여건을 수동 선택하고 근거를 확인하십시오.</font>"),
            ("자유속도와 간선도로 유형", "<table cellspacing='0' cellpadding='6' border='1'>"
             "<tr><th>기능등급</th><th>양호 자유속도</th><th>보통 자유속도</th><th>양호 유형</th><th>보통 유형</th></tr>"
             "<tr><td>고규격</td><td>80km/h</td><td>80km/h</td><td>I</td><td>I</td></tr>"
             "<tr><td>중간규격</td><td>80km/h</td><td>70km/h</td><td>I</td><td>II</td></tr>"
             "<tr><td>저규격</td><td>70km/h</td><td>60km/h</td><td>II</td><td>III</td></tr></table>"),
            ("노변마찰 판정 - 표 12-6", "정류장수와 진출입로수는 반드시 <b>분석구간 개수 ÷ 분석길이(km)</b>로 환산합니다. 버스정류장이 2개/km 초과이면 모든 유형에서 ‘대’. 진출입로는 유형 I 2개/km 초과, 유형 II 3개/km 초과, 유형 III 4개/km 초과이면 ‘대’이며, 둘 중 하나라도 ‘대’이면 노변마찰 ‘대’를 적용합니다."),
            ("km당 순행시간 - 표 12-5 (초/km)", "<table cellspacing='0' cellpadding='4' border='1'>"
             "<tr><th rowspan='2'>구간거리</th><th colspan='2'>유형 I</th><th colspan='2'>유형 II</th><th colspan='2'>유형 III</th></tr>"
             "<tr><th>대</th><th>소</th><th>대</th><th>소</th><th>대</th><th>소</th></tr>"
             "<tr><td>≤0.1</td><td>108</td><td>86</td><td>143</td><td>102</td><td>178</td><td>119</td></tr>"
             "<tr><td>≤0.2</td><td>80</td><td>66</td><td>100</td><td>75</td><td>119</td><td>85</td></tr>"
             "<tr><td>≤0.3</td><td>71</td><td>59</td><td>85</td><td>67</td><td>99</td><td>74</td></tr>"
             "<tr><td>≤0.4</td><td>66</td><td>56</td><td>77</td><td>63</td><td>88</td><td>69</td></tr>"
             "<tr><td>≤0.5</td><td>63</td><td>54</td><td>73</td><td>60</td><td>83</td><td>65</td></tr>"
             "<tr><td>≤0.6</td><td>61</td><td>53</td><td>70</td><td>58</td><td>79</td><td>63</td></tr>"
             "<tr><td>≤0.7</td><td>60</td><td>52</td><td>68</td><td>57</td><td>75</td><td>62</td></tr>"
             "<tr><td>≤0.8</td><td>59</td><td>51</td><td>66</td><td>56</td><td>74</td><td>61</td></tr>"
             "<tr><td>≤0.9</td><td>58</td><td>50</td><td>65</td><td>55</td><td>72</td><td>60</td></tr>"
             "<tr><td>&gt;0.9</td><td>58</td><td>50</td><td>65</td><td>54</td><td>72</td><td>58</td></tr></table>"
             "프로그램은 경계 구간값을 <b>보간하지 않고</b> 그대로 적용합니다. 순행시간(초)=표의 초/km×분석길이(km)."),
        ]

    @staticmethod
    def _formula_sections() -> list[tuple[str, str]]:
        return [
            ("교통류율·포화교통류율·용량", "<b>설계교통류율</b> V = 시간교통량 VH ÷ PHF<br>"
             "<b>포화교통류율</b> s = 기본 포화교통류율 s0 × 종합보정계수 × 차로수<br>"
             "<b>용량</b> c = s × (g/C), <b>V/c</b> = V ÷ c, <b>q/s</b> = V ÷ s.<br>"
             "제12장 계획용 개략식은 c=1,800×N×(g/C)이지만 기존도로 정밀분석에는 제8장 보정 포화교통류율을 사용하는 것이 원칙입니다. 프로그램 기본 s0=2,200pcphgpl은 구간 상세조건에서 변경할 수 있습니다."),
            ("균일제어지체 d1 - 식 12-3", "d1 = 0.5×C×(1-g/C)² ÷ [1-min(1,X)×g/C]<br>"
             "C는 주기(초), g는 유효녹색시간(초), X는 해당 직진 차로군의 포화도입니다. 프로그램은 제8장 정의에 따라 <b>X=V/c</b>를 사용하고 q/s는 참고값으로 별도 표시합니다."),
            ("증분지체 d2 - 식 12-4", "d2 = 900×T×[(X-1)+√{(X-1)²+4X/(cT)}]<br>"
             "T는 분석기간(시간), c는 차로군 용량입니다. 기본 분석기간은 0.25시간입니다. V/c가 표시값 기준 1.10 이상이거나 15분을 넘는 장기 과포화에서는 편람도 합리적인 지체 추정이 어렵다고 명시하므로 프로그램이 경고합니다."),
            ("초기대기차량 추가지체 d3 - 식 12-5", "Qb가 0이면 d3=0입니다. 초기대기차량이 분석기간 안에 해소되면 d3=1,800×Qb²/[cT(c-V)], 기간 뒤에도 감소하며 남으면 d3=3,600×Qb/c-1,800×T(1-X), 더 늘어나는 경우 d3=3,600×Qb/c를 적용합니다. 프로그램은 용량·도착교통량·해소가능 대수로 세 경우를 자동 구분합니다."),
            ("평균제어지체와 횡단신호", "<b>d = d1×PF×fcw + d2 + d3</b><br>"
             "<table cellspacing='0' cellpadding='5' border='1'><tr><th>횡단신호 수</th><th>0</th><th>1</th><th>2 이상</th></tr>"
             "<tr><td>비연동 fcw</td><td>1.0</td><td>1.0</td><td>1.1</td></tr><tr><td>연동 fcw</td><td>1.0</td><td>1.1</td><td>1.2</td></tr></table>"
             "PF는 비연동 기본 1.0입니다. 연동이면 옵셋·통행시간·g/C 또는 도착형태 자료로 산정해야 하며, 자료 없이 연동만 선택한 경우 프로그램은 PF=1.0 적용 경고를 남깁니다. 중간 횡단신호가 비연동이면 간선 연동효과도 사실상 상실되므로 PF=1.0을 검토합니다."),
            ("총소요시간과 평균통행속도 - 식 12-9", "순행시간 = km당 순행시간×구간길이<br>총소요시간 = 순행시간+d<br><b>평균통행속도(km/h) = 3,600×구간길이(km) ÷ 총소요시간(초)</b><br>"
             "여러 연속 구간을 통합할 때는 단순 속도평균이 아니라 총길이와 총시간으로 계산해야 합니다. 프로그램의 개별 구간표는 각 신호교차로 접근지체를 한 번씩 포함합니다."),
        ]

    @staticmethod
    def _los_sections() -> list[tuple[str, str]]:
        return [
            ("유형별 서비스수준 속도기준 - 표 12-10", "<table cellspacing='0' cellpadding='6' border='1'>"
             "<tr><th>LOS</th><th>유형 I<br>(80km/h)</th><th>유형 II<br>(70km/h)</th><th>유형 III<br>(60km/h)</th></tr>"
             "<tr><td>A</td><td>≥67</td><td>≥60</td><td>≥49</td></tr><tr><td>B</td><td>≥51</td><td>≥46</td><td>≥39</td></tr>"
             "<tr><td>C</td><td>≥37</td><td>≥33</td><td>≥29</td></tr><tr><td>D</td><td>≥28</td><td>≥25</td><td>≥20</td></tr>"
             "<tr><td>E</td><td>≥21</td><td>≥18</td><td>≥12</td></tr><tr><td>F</td><td>≥10</td><td>≥10</td><td>≥8</td></tr>"
             "<tr><td>FF</td><td>≥6</td><td>≥6</td><td>≥5</td></tr><tr><td>FFF</td><td>&lt;6</td><td>&lt;6</td><td>&lt;5</td></tr></table>단위: km/h"),
            ("서비스수준 해석", "A: 자유흐름·최소 신호지체 / B: 약간의 제약, 정지지체 작음 / C: 안전운행 가능하나 조작 제약과 대기행렬 증가 / D: 교통량 증가에 민감하고 신호·연동 영향 큼 / E: 큰 접근지체와 매우 낮은 속도 / F: 주요 교차로 소통장애 / FF: 전방 신호 통과에 평균 2~3주기 / FFF: 3주기 이상이 필요한 극심한 혼잡."),
            ("비교결과를 읽는 방법", "교통량이 늘어도 차로수 증가, g/C 개선, PF 개선 또는 유형 변경으로 평균통행속도가 좋아질 수 있습니다. 반대로 시설등급이 유형 III→I로 좋아지면 운전자 기대속도 기준도 높아져 실제 속도는 상승했는데 LOS가 같거나 나빠질 수 있습니다. 따라서 비교표에서는 교통량뿐 아니라 V/c, 지체, 차로수, g/C, 유형 변화를 함께 확인해야 합니다."),
            ("수동 평균통행속도", "현장 속도조사나 별도 시뮬레이션 결과를 반영해 평균통행속도를 직접 변경할 수 있지만 편람 원계산값은 보존됩니다. 변경값은 붉은색으로 표시되고 날짜·시간·변경 사유가 기록되며 모든 비교·통합표에 반영됩니다. 근거 없는 목표값 맞추기에는 사용하지 마십시오."),
        ]

    @staticmethod
    def _input_sections() -> list[tuple[str, str]]:
        return [
            ("필수 입력자료", "<b>분석길이(m)</b>: 실제 공식 계산용. <b>표기길이(m)</b>: 보고서·부록 표시용.<br>"
             "<b>본선 차로수(편도)</b>: 직진 주이동류가 이용 가능한 차로수와 일치하는지 확인.<br>"
             "<b>기능등급·도로여건</b>: 토지이용, 이동성, 접근관리, 신호밀도와 차로수로 판단.<br>"
             "<b>주기·녹색시간</b>: 가능하면 유효녹색시간 사용. <b>주이동류 교통량</b>: 계산용 정수 대/시. <b>PHF</b>: 0 초과 1 이하.<br>"
             "<b>정류장·진출입로·횡단신호</b>: 해당 분석구간 안의 실제 개수. <b>Qb</b>: 분석 시작시 남아 있는 대기차량."),
            ("상세조건 적용순서", "구간별 상세값이 있으면 프로젝트 기본값보다 우선합니다. 적용대상은 분석기간 T, 기본 포화교통류율, 종합 포화교통류율 보정계수, 초기대기차량 Qb, 연동여부, PF, 중간 신호횡단보도 수와 fcw입니다. 0 또는 미입력의 의미가 다른 항목이 있으므로 상세창 안내를 확인하십시오."),
            ("현황·미시행·시행·개선 구성", "현황은 조사도로망, 미시행은 우리 사업을 제외한 장래도로망(타 사업 준공에 따른 구조변경 가능), 시행은 우리 사업 및 내부도로 반영, 개선은 시행안에 개선대책을 더한 상태입니다. 같은 연도의 동일 비교구간만 직접 비교하며, 연도별 구조가 달라지면 구간 구조 변경 알림을 확인합니다."),
            ("분석 전 체크리스트", "□ 양방향 교차로명·번호와 방향이 맞는가<br>□ 분석길이와 보고서 표기길이가 의도대로 구분됐는가<br>□ 기능등급·도로여건·유형이 주변환경과 맞는가<br>□ 중·저규격 ‘양호’이면 접근부 직진차로가 2개 이상인가<br>□ 정류장·진출입로 수가 구간 전체 개수인가<br>□ 주기·유효녹색시간·PHF·교통량의 시간대가 동일한가<br>□ 기존도로는 제8장 보정 포화교통류율을 사용했는가<br>□ 연동 PF와 초기대기차량의 근거가 있는가<br>□ V/c 1.0 초과 및 1.10 이상 경고를 확인했는가<br>□ 수동속도에는 조사자료와 변경 사유가 기록됐는가"),
            ("결과 검토 체크리스트", "교통량 증가 시 일반적으로 V/c·지체는 증가하고 속도는 감소해야 합니다. 결과가 반대라면 차로수, g/C, PF, 포화교통류율, 도로유형 또는 수동조정이 달라졌는지 먼저 확인합니다. 짧은 구간·낮은 g/C·신호횡단보도·큰 노변마찰은 저교통량에서도 낮은 평균속도를 만들 수 있습니다. 기존 현황은 가능하면 현장 통행시간·속도·대기행렬로 보정 타당성을 확인하십시오."),
            ("적용 한계", "편람 모형은 평균적인 고정신호 운영상태와 대안 비교에 적합합니다. 사고·공사·불법주정차·악천후·철도건널목·복잡한 감응제어·긴 과포화·상류 대기행렬 역류·중앙버스전용차로 등은 별도 현장조사나 미시교통 시뮬레이션이 필요할 수 있습니다. 결과는 교차로 분석자료 및 교통운영계획과 함께 검토해야 합니다."),
        ]


class Workflow(QWidget):
    def __init__(self, project: ArterialProject) -> None:
        super().__init__()
        self.project = project
        self.results: list[AnalysisResult] = []
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.steps = QLabel(); self.steps.setObjectName("stepBar"); layout.addWidget(self.steps)
        self.stack = QStackedWidget(); layout.addWidget(self.stack, 1)
        self.input_page = InputPage(project); self.confirm_page = ConfirmPage(); self.results_page = ResultsPage()
        for page in (self.input_page, self.confirm_page, self.results_page): self.stack.addWidget(page)
        self.input_page.next_button.clicked.connect(lambda: self.go(1))
        self.confirm_page.prev_button.clicked.connect(lambda: self.go(0)); self.confirm_page.next_button.clicked.connect(lambda: self.go(2))
        self.results_page.prev_button.clicked.connect(lambda: self.go(1)); self.results_page.restart_button.clicked.connect(lambda: self.go(0))
        self.load_project(project)

    def load_project(self, project: ArterialProject) -> None:
        self.project = project; self.input_page.project = project
        self.input_page.current_key = None; self.input_page.load_project_info(); self.input_page.refresh_selectors(); self.go(0)

    def commit(self) -> None:
        self.input_page.save_table()
        old_key = self.input_page.current_key
        self.input_page.apply_project_info()
        if old_key and old_key[0] == "현황":
            self.input_page.current_key = ("현황", self.project.current_year)
        self.input_page.refresh_selectors()

    def go(self, index: int) -> None:
        try:
            if self.stack.currentIndex() == 0:
                self.commit()
            if index >= 1:
                self.results = self.project.analyze_all()
                self.confirm_page.refresh(self.project, self.results)
            if index == 2: self.results_page.refresh(self.project, self.results)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "입력 확인", str(exc)); return
        self.stack.setCurrentIndex(index)
        labels = ["○ 구간 입력", "○ 입력 확인", "○ 분석 결과"]
        labels[index] = labels[index].replace("○", "●")
        self.steps.setText("     ".join(labels))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        load_korean_font()
        self.project = ArterialProject(); self.project.add_starter_rows()
        self.path: str | None = None; self.dirty = False
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}"); self.resize(1280, 820); self.setMinimumSize(900, 650)
        icon_path = resource_path("assets/interchange.ico")
        if Path(icon_path).exists(): self.setWindowIcon(QIcon(icon_path))
        self.tabs = QTabWidget(); self.workflow = Workflow(self.project)
        self.tabs.addTab(self.workflow, "분석"); self.tabs.addTab(GuidelinePage(), "지침·공식"); self.setCentralWidget(self.tabs)
        self._create_menu(); self.statusBar().showMessage(f"{APP_NAME} v{APP_VERSION}   ·   {APP_AUTHOR}")

    def _create_menu(self) -> None:
        menu = self.menuBar().addMenu("프로젝트")
        actions = [("새 프로젝트", self.new_project, "Ctrl+N"), ("열기", self.open_project, "Ctrl+O"), ("저장", self.save_project, "Ctrl+S"), ("다른 이름으로 저장", self.save_as, "Ctrl+Shift+S")]
        for text, slot, shortcut in actions:
            action = QAction(text, self); action.setShortcut(shortcut); action.triggered.connect(slot); menu.addAction(action)
        menu.addSeparator(); quit_action = QAction("종료", self); quit_action.triggered.connect(self.close); menu.addAction(quit_action)
        help_menu = self.menuBar().addMenu("도움말")
        about = QAction("프로그램 정보", self); about.triggered.connect(lambda: QMessageBox.about(self, APP_NAME, f"<h2>{APP_NAME}</h2><p>v{APP_VERSION}</p><p>도로용량편람(2013) 기반 정식판</p><p>{APP_AUTHOR}</p>")); help_menu.addAction(about)

    def new_project(self) -> None:
        project = ArterialProject(); project.add_starter_rows(); self.project = project; self.path = None; self.workflow.load_project(project)

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "프로젝트 열기", "", PROJECT_FILTER)
        if not path: return
        try: project = ArterialProject.load(path)
        except Exception as exc: QMessageBox.critical(self, "열기 실패", str(exc)); return
        self.project = project; self.path = path; self.workflow.load_project(project); self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} - {Path(path).name}")

    def save_project(self) -> bool:
        if not self.path: return self.save_as()
        try: self.workflow.commit(); self.project.save(self.path)
        except Exception as exc: QMessageBox.critical(self, "저장 실패", str(exc)); return False
        self.statusBar().showMessage(f"저장 완료: {self.path}", 5000); return True

    def save_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "프로젝트 저장", self.project.name + ".ara1", PROJECT_FILTER)
        if not path: return False
        if not path.lower().endswith(".ara1"): path += ".ara1"
        self.path = path; return self.save_project()


STYLE = """
QWidget { font-family: "Noto Sans KR", "Malgun Gothic"; font-size: 10pt; color:#172033; }
QMainWindow, QStackedWidget { background:#F5F7FA; }
QMenuBar { background:white; padding:4px 8px; } QMenuBar::item:selected { background:#EAF2FF; }
QTabWidget::pane { border:0; } QTabBar::tab { background:white; padding:11px 20px; color:#5E6A7D; border:0; }
QTabBar::tab:selected { color:#1261C9; font-weight:700; border-bottom:3px solid #2375E8; }
QFrame#card { background:white; border:1px solid #DCE3EC; border-radius:14px; }
QLabel#cardTitle { font-size:12pt; font-weight:700; color:#16243A; }
QLabel#pageTitle { font-size:19pt; font-weight:800; color:#172033; padding:4px 0 6px 0; }
QLabel#infoBar { background:#FFF5D8; color:#8A5800; border-radius:9px; padding:10px 13px; }
QLabel#stepBar { background:white; color:#64748B; padding:14px 22px; border-bottom:1px solid #E2E8F0; }
QLabel#resultHero { background:#E7F0FF; border:1px solid #2375E8; border-radius:16px; color:#1261C9; font-size:14pt; font-weight:700; padding:17px 22px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background:white; border:1px solid #CBD6E4; border-radius:7px; padding:6px 8px; min-height:20px; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border:1px solid #2375E8; }
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width:0px; height:0px; border:0; }
QPushButton { background:white; border:1px solid #CBD6E4; border-radius:8px; padding:8px 13px; font-weight:600; }
QPushButton:hover { background:#EFF5FF; border-color:#8DB8F3; }
QPushButton#primaryButton { background:#2375E8; color:white; border-color:#2375E8; padding:9px 18px; }
QTableWidget { background:white; alternate-background-color:#F7F9FC; border:0; gridline-color:#D8E0E9; selection-background-color:#DCEBFF; selection-color:#172033; }
QHeaderView::section { background:#E9EEF4; color:#29384D; border:0; border-right:1px solid #CBD4DF; border-bottom:1px solid #B8C4D2; padding:8px 6px; font-weight:700; }
QStatusBar { background:white; color:#536273; }
"""


def main() -> int:
    app = QApplication(sys.argv)
    load_korean_font()
    app.setApplicationName(APP_NAME); app.setApplicationVersion(APP_VERSION); app.setStyleSheet(STYLE)
    window = MainWindow(); window.show()
    return app.exec()
