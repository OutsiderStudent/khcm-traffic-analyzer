from __future__ import annotations

import html
import re
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QEvent, QMimeData, QRect, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QColor, QDoubleValidator, QFontDatabase, QGuiApplication, QIcon, QIntValidator, QKeySequence, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
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
    QSpinBox,
    QStackedWidget,
    QStyle,
    QStyleOptionButton,
    QStyledItemDelegate,
    QTabBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTableView,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .app import GuidelinePage
from .engine import (
    ARTERIAL_TYPES,
    FUNCTIONAL_CLASSES,
    ROAD_CATEGORIES,
    AnalysisResult,
    SegmentInput,
    analyze_segment,
    arterial_type,
    los_for_speed,
    road_condition,
)
from .project import ArterialProject
from .reports import (ReportSpec,SEGMENT_GROUP,SEGMENT_HEADER_SPANS,SEGMENT_MERGE_COLUMNS,SEGMENT_WIDTHS,_segment_cells,comparison_report,future_report,render_report_image)


APP_NAME = "도시·교외간선도로 분석"
APP_VERSION = "1.1.0"
APP_AUTHOR = "made by NYH"
APP_EMAIL = "dmecyh@naver.com"
PROJECT_FILTER = "간선도로 분석 프로젝트 (*.ara1)"
SCENARIO_LABEL = {"현황": "현황", "사업 미시행시": "미시행", "사업 시행시": "시행", "개선대책 이행시": "개선"}
SCENARIO_ORDER = {"현황": 0, "사업 미시행시": 1, "사업 시행시": 2, "개선대책 이행시": 3}
EXTERNAL = ROAD_CATEGORIES[0]
INTERNAL = ROAD_CATEGORIES[2]


def resource_path(relative: str) -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return str(base / relative)


def load_font() -> None:
    path = resource_path("assets/NotoSansKR.ttf")
    if Path(path).exists():
        QFontDatabase.addApplicationFont(path)


def make_card(title: str, child: QWidget) -> QFrame:
    frame = QFrame(); frame.setObjectName("card")
    layout = QVBoxLayout(frame); layout.setContentsMargins(18, 14, 18, 16)
    heading = QLabel(title); heading.setObjectName("cardTitle")
    layout.addWidget(heading); layout.addWidget(child)
    return frame


def clear_tab_bar(tab_bar: QTabBar) -> None:
    while tab_bar.count():
        tab_bar.removeTab(0)


class NumericDelegate(QStyledItemDelegate):
    def __init__(self, integer: bool, minimum: float, maximum: float, decimals: int = 2, parent=None) -> None:
        super().__init__(parent); self.integer = integer; self.minimum = minimum; self.maximum = maximum; self.decimals = decimals

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent); editor.setAlignment(Qt.AlignRight)
        if self.integer:
            editor.setValidator(QIntValidator(int(self.minimum), int(self.maximum), editor))
        else:
            validator = QDoubleValidator(self.minimum, self.maximum, self.decimals, editor)
            validator.setNotation(QDoubleValidator.StandardNotation); editor.setValidator(validator)
        return editor

    def setEditorData(self, editor, index) -> None:
        editor.setText(str(index.data() or "").replace(",", "")); editor.selectAll()

    def setModelData(self, editor, model, index) -> None:
        raw = editor.text().replace(",", "").strip() or "0"
        value = int(raw) if self.integer else float(raw)
        if self.integer:
            model.setData(index, f"{value:,}")
        else:
            model.setData(index, f"{value:.{self.decimals}f}")


class ComboDelegate(QStyledItemDelegate):
    def __init__(self, options, editable: bool = True, parent=None) -> None:
        super().__init__(parent); self.options = options; self.editable = editable

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent); editor.setEditable(self.editable)
        editor.setMaxVisibleItems(14); editor.view().setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        values = self.options() if callable(self.options) else self.options
        editor.addItems([str(value) for value in values if str(value)])
        editor.setFocus(Qt.MouseFocusReason)
        popup_timer=QTimer(editor); popup_timer.setSingleShot(True); popup_timer.timeout.connect(editor.showPopup); popup_timer.start(0)
        return editor

    def setEditorData(self, editor, index) -> None:
        editor.setCurrentText(str(index.data() or ""))

    def setModelData(self, editor, model, index) -> None:
        model.setData(index, editor.currentText().strip())


class CenterCheckDelegate(QStyledItemDelegate):
    """선택 셀 중앙에 고대비 체크박스를 그린다."""

    def paint(self,painter,option,index):
        state=index.data(Qt.CheckStateRole); checked=state in (Qt.Checked,Qt.CheckState.Checked,2); size=18
        rect=QRect(option.rect.center().x()-size//2,option.rect.center().y()-size//2,size,size)
        painter.save(); painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#9AA9BC"),1.4)); painter.setBrush(QColor("#2375E8") if checked else QColor("#FFFFFF")); painter.drawRoundedRect(rect,4,4)
        if checked:
            painter.setPen(QPen(QColor("#FFFFFF"),3.0,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin)); painter.drawLine(rect.left()+4,rect.center().y(),rect.left()+8,rect.bottom()-4); painter.drawLine(rect.left()+8,rect.bottom()-4,rect.right()-3,rect.top()+4)
        painter.restore()

    def editorEvent(self,event,model,option,index):
        activate=event.type()==QEvent.MouseButtonRelease or (event.type()==QEvent.KeyPress and event.key() in (Qt.Key_Space,Qt.Key_Select))
        if not activate:return False
        state=index.data(Qt.CheckStateRole); checked=state in (Qt.Checked,Qt.CheckState.Checked,2); model.setData(index,Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked,Qt.CheckStateRole); return True


class FrozenInputTable(QTableWidget):
    """교차로명까지 7개 열을 엑셀의 틀 고정처럼 유지한다."""

    def __init__(self,rows,columns,freeze_count=7,parent=None):
        super().__init__(rows,columns,parent); self.freeze_count=freeze_count; self.frozen=QTableView(self); self.frozen.setModel(self.model()); self.frozen.setSelectionModel(self.selectionModel())
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn); self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.frozen.setFrameShape(QFrame.NoFrame); self.frozen.setStyleSheet("QTableView{border:0;background:white;}")
        self.frozen.verticalHeader().hide(); self.frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.frozen.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.frozen.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel); self.frozen.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel); self.frozen.setEditTriggers(QAbstractItemView.AllEditTriggers)
        for col in range(columns): self.frozen.setColumnHidden(col,col>=freeze_count)
        self.frozen.show(); self.frozen.raise_(); self.verticalScrollBar().valueChanged.connect(self.frozen.verticalScrollBar().setValue); self.frozen.verticalScrollBar().valueChanged.connect(self.verticalScrollBar().setValue); self.horizontalHeader().sectionResized.connect(self._sync_width)

    def set_shared_delegate(self,column,delegate):
        """각 뷰에 별도 delegate를 둬 고정 영역 편집기가 즉시 닫히지 않게 한다."""
        self.setItemDelegateForColumn(column,delegate)
        if isinstance(delegate,ComboDelegate):
            frozen_delegate=ComboDelegate(delegate.options,delegate.editable,self.frozen)
        elif isinstance(delegate,CenterCheckDelegate):
            frozen_delegate=CenterCheckDelegate(self.frozen)
        else:
            frozen_delegate=delegate
        self.frozen.setItemDelegateForColumn(column,frozen_delegate)

    def _sync_width(self,column,_old,new):
        if column<self.freeze_count:self.frozen.setColumnWidth(column,new);self._update_frozen_geometry()

    def _update_frozen_geometry(self):
        width=sum(self.columnWidth(col) for col in range(self.freeze_count))
        header_h=self.horizontalHeader().height(); rows_h=sum(self.rowHeight(row) for row in range(self.rowCount()))
        height=min(self.viewport().height()+header_h,header_h+rows_h+1)
        self.frozen.setGeometry(self.frameWidth(),self.frameWidth(),max(0,width-1),max(header_h,height))

    def resizeEvent(self,event): super().resizeEvent(event); self._update_frozen_geometry()


class CopyableTable(QTableWidget):
    """선택 셀을 HWP 표에 붙이기 좋은 TSV와 HTML 표로 복사한다."""

    def __init__(self, rows=0, columns=0, parent=None) -> None:
        super().__init__(rows, columns, parent)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.Copy):
            self.copy_selection(); return
        super().keyPressEvent(event)

    def copy_selection(self) -> None:
        indexes = self.selectedIndexes()
        if not indexes:
            return
        selected = {(index.row(), index.column()) for index in indexes}
        min_row, max_row = min(r for r, _ in selected), max(r for r, _ in selected)
        min_col, max_col = min(c for _, c in selected), max(c for _, c in selected)
        plain_rows: list[str] = []
        html_rows: list[str] = []
        covered: set[tuple[int, int]] = set()
        for row in range(min_row, max_row + 1):
            plain_cells: list[str] = []
            html_cells: list[str] = []
            for column in range(min_col, max_col + 1):
                value = self.item(row, column).text() if self.item(row, column) and (row, column) in selected else ""
                plain_cells.append(value)
                if (row, column) in covered:
                    continue
                row_span, col_span = self.rowSpan(row, column), self.columnSpan(row, column)
                for rr in range(row, row + row_span):
                    for cc in range(column, column + col_span):
                        if (rr, cc) != (row, column): covered.add((rr, cc))
                span = (f' rowspan="{row_span}"' if row_span > 1 else "") + (f' colspan="{col_span}"' if col_span > 1 else "")
                html_cells.append(f"<td{span}>{html.escape(value)}</td>")
            plain_rows.append("\t".join(plain_cells))
            html_rows.append("<tr>" + "".join(html_cells) + "</tr>")
        mime = QMimeData(); mime.setText("\n".join(plain_rows))
        mime.setHtml("<table border='1' cellspacing='0' cellpadding='3'>" + "".join(html_rows) + "</table>")
        QGuiApplication.clipboard().setMimeData(mime)


class EditableTabBar(QTabBar):
    """이미 선택된 탭의 문구를 한 번 클릭하면 편집 요청을 보낸다."""

    activeLabelClicked = Signal(int)

    def mousePressEvent(self,event):
        self._pressed_current=self.currentIndex(); super().mousePressEvent(event)

    def mouseReleaseEvent(self,event):
        index=self.tabAt(event.position().toPoint()); super().mouseReleaseEvent(event)
        if index>=0 and index==getattr(self,"_pressed_current",-1): self.activeLabelClicked.emit(index)


class AddAnalysisTabDialog(QDialog):
    def __init__(self, parent=None, scenario="사업 미시행시", year=2033, scenario_locked=False) -> None:
        super().__init__(parent); self.setWindowTitle("분석 탭 추가")
        layout = QFormLayout(self)
        self.scenario = QComboBox(); self.scenario.addItems(["현황", "사업 미시행시", "사업 시행시", "개선대책 이행시"])
        self.scenario.setCurrentText(scenario); self.scenario.setEnabled(not scenario_locked)
        self.year = QSpinBox(); self.year.setRange(2000, 2200); self.year.setValue(year)
        layout.addRow("분석 상황", self.scenario); layout.addRow("분석연도", self.year)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("적용"); buttons.button(QDialogButtonBox.Cancel).setText("취소")
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addRow(buttons)


class SegmentDetailDialog(QDialog):
    """기본 표에서 분리한 구간별 분석조건과 도로변 마찰요소."""

    def __init__(self, segment: SegmentInput, project: ArterialProject, parent=None) -> None:
        super().__init__(parent); self.segment=segment; self.project=project
        self.setWindowTitle("구간별 상세조건"); self.setMinimumWidth(480)
        root=QVBoxLayout(self); title=QLabel(f"{segment.road_name} · {segment.start_name} {segment.direction} {segment.end_name}"); title.setObjectName("cardTitle"); root.addWidget(title)
        form=QFormLayout()
        self.bus=QSpinBox(); self.bus.setRange(0,99); self.bus.setSuffix(" 개")
        self.access=QSpinBox(); self.access.setRange(0,999); self.access.setSuffix(" 개")
        self.period=QDoubleSpinBox(); self.period.setRange(.05,4); self.period.setDecimals(2); self.period.setSuffix(" 시간")
        self.base=QDoubleSpinBox(); self.base.setRange(500,4000); self.base.setDecimals(0); self.base.setSuffix(" pcphgpl")
        self.sat=QDoubleSpinBox(); self.sat.setRange(.1,2); self.sat.setDecimals(3)
        self.queue=QSpinBox(); self.queue.setRange(0,10000); self.queue.setSuffix(" 대")
        self.coordinated=QCheckBox("연동신호 적용")
        self.crossing=QSpinBox(); self.crossing.setRange(0,20); self.crossing.setSuffix(" 개")
        self.pf=QDoubleSpinBox(); self.pf.setRange(0,3); self.pf.setDecimals(3); self.pf.setSpecialValueText("자동/1.0")
        self.fcw=QDoubleSpinBox(); self.fcw.setRange(0,3); self.fcw.setDecimals(3); self.fcw.setSpecialValueText("자동")
        for label,widget in (("정류장 수",self.bus),("진출입로 수",self.access),("분석기간 T",self.period),("기본 포화교통류율",self.base),("통합 포화교통류율 보정계수",self.sat),("초기 대기차량 Qb",self.queue),("신호 연동",self.coordinated),("구간 중간 횡단신호",self.crossing),("연동보정계수 PF",self.pf),("횡단신호보정계수 fcw",self.fcw)): form.addRow(label,widget)
        root.addLayout(form)
        buttons=QDialogButtonBox(QDialogButtonBox.RestoreDefaults|QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.RestoreDefaults).setText("기본값"); buttons.button(QDialogButtonBox.Ok).setText("적용"); buttons.button(QDialogButtonBox.Cancel).setText("취소")
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self.set_defaults); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)
        self.load_values()

    def load_values(self):
        s,d=self.segment,self.project.settings; self.bus.setValue(s.bus_stops); self.access.setValue(s.access_points)
        self.period.setValue(s.analysis_period_h if s.analysis_period_h is not None else d.analysis_period_h); self.base.setValue(s.base_saturation_flow if s.base_saturation_flow is not None else d.base_saturation_flow)
        self.sat.setValue(s.saturation_adjustment if s.saturation_adjustment is not None else d.saturation_adjustment); self.queue.setValue(int(s.initial_queue if s.initial_queue is not None else d.initial_queue))
        self.coordinated.setChecked(s.coordinated if s.coordinated is not None else d.coordinated); self.crossing.setValue(s.crossing_signals if s.crossing_signals is not None else d.crossing_signals); self.pf.setValue(s.pf_override or 0); self.fcw.setValue(s.fcw_override or 0)

    def set_defaults(self):
        d=self.project.settings; self.bus.setValue(0); self.access.setValue(0); self.period.setValue(d.analysis_period_h); self.base.setValue(d.base_saturation_flow); self.sat.setValue(d.saturation_adjustment); self.queue.setValue(int(d.initial_queue)); self.coordinated.setChecked(d.coordinated); self.crossing.setValue(d.crossing_signals); self.pf.setValue(d.pf_override or 0); self.fcw.setValue(d.fcw_override or 0)

    def apply_to_segment(self):
        s=self.segment; s.bus_stops=self.bus.value(); s.access_points=self.access.value(); s.analysis_period_h=self.period.value(); s.base_saturation_flow=self.base.value(); s.saturation_adjustment=self.sat.value(); s.initial_queue=float(self.queue.value()); s.coordinated=self.coordinated.isChecked(); s.crossing_signals=self.crossing.value(); s.pf_override=self.pf.value() or None; s.fcw_override=self.fcw.value() or None


class SpeedAdjustmentDialog(QDialog):
    def __init__(self, result: AnalysisResult, parent=None) -> None:
        super().__init__(parent); self.result=result; self.setWindowTitle("평균통행속도 수동조정"); self.setMinimumWidth(470)
        root=QVBoxLayout(self); note=QLabel(f"편람 원계산값 {result.calculated_speed_kmh:.1f} km/h · 현재 적용값 {result.speed_kmh:.1f} km/h\n변경값은 모든 비교·통합·부록 표에 반영되고 수동조정으로 표시됩니다."); note.setObjectName("infoBar"); root.addWidget(note)
        form=QFormLayout(); self.speed=QDoubleSpinBox(); self.speed.setRange(0.1,200); self.speed.setDecimals(1); self.speed.setSuffix(" km/h"); self.speed.setValue(result.speed_kmh)
        self.reason=QTextEdit(); self.reason.setPlaceholderText("변경 근거와 사유를 반드시 입력해 주세요."); self.reason.setMinimumHeight(90)
        form.addRow("적용 평균통행속도",self.speed); form.addRow("변경 사유",self.reason); root.addLayout(form)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); buttons.button(QDialogButtonBox.Ok).setText("변경 적용"); buttons.button(QDialogButtonBox.Cancel).setText("취소"); buttons.accepted.connect(self._accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)

    def _accept(self):
        if not self.reason.toPlainText().strip(): QMessageBox.warning(self,"변경 사유","변경 사유를 입력해 주세요."); return
        self.accept()


class InputPage(QWidget):
    changed = Signal()
    COMBO_COLUMNS = {1, 3, 4, 6, 10, 11, 18, 19}
    HEADERS = ["선택", "가로명", "교차로\n번호", "교차로명", "↔", "교차로\n번호", "교차로명", "분석길이\n(m)", "표기길이\n(m)", "본선 차로수\n(편도)", "기능등급", "도로여건", "간선도로\n유형", "주기\n(초)", "녹색시간\n(초)", "주이동류 교통량\n(대/시)", "보고서 교통량\n(대/시)", "PHF", "교차로 서비스수준\n(LOS, 참고)", "접근로 서비스수준\n(LOS, 참고)", "평균통행속도\n(km/h)", "서비스수준\n(LOS)", "상세"]
    NUMERIC_COLUMNS = {7, 8, 9, 13, 14, 15, 16, 17, 20}
    READ_ONLY_COLUMNS = {0, 12, 20, 21, 22}

    def __init__(self, project: ArterialProject) -> None:
        super().__init__(); self.project = project; self.current_key: tuple[str, int] | None = None; self._changing_tabs = False; self._segment_clipboard: list[dict] = []
        root = QVBoxLayout(self); root.setContentsMargins(16, 14, 16, 14)
        title = QLabel("상황·연도별 분석구간을 입력해 주세요"); title.setObjectName("pageTitle"); root.addWidget(title)
        self.analysis_tabs = EditableTabBar(); self.analysis_tabs.setExpanding(False); self.analysis_tabs.setDrawBase(False); self.analysis_tabs.setTabsClosable(False)
        self.analysis_tabs.setToolTip("+ 탭으로 상황·연도를 추가하고, 선택된 탭 문구를 클릭하면 연도를 변경할 수 있습니다.")
        root.addWidget(self.analysis_tabs)
        self.change_notice = QLabel(); self.change_notice.setObjectName("changeNotice"); self.change_notice.setWordWrap(True); self.change_notice.hide(); root.addWidget(self.change_notice)
        note = QLabel("화살표 한 행이 한 방향 구간입니다. 이름은 기존 목록에서 선택하거나 새로 입력할 수 있습니다. 숫자 칸에는 숫자만 입력됩니다.")
        note.setObjectName("infoBar"); root.addWidget(note)
        self.road_tabs = QTabWidget()
        self.external_table = self._make_table(); self.internal_table = self._make_table()
        self.road_tabs.addTab(make_card("외부도로", self.external_table), "외부도로")
        self.road_tabs.addTab(make_card("내부도로", self.internal_table), "내부도로")
        root.addWidget(self.road_tabs, 1)
        buttons1 = QHBoxLayout()
        self.add_pair = QPushButton("양방향 구간 추가"); self.copy_segments = QPushButton("선택 구간 복사"); self.paste_segments = QPushButton("구간 붙여넣기"); self.delete = QPushButton("선택 행 삭제")
        self.reset = QPushButton("선택 행 기본값 초기화")
        for button in (self.add_pair,self.copy_segments,self.paste_segments,self.delete,self.reset): buttons1.addWidget(button)
        buttons1.addStretch(); root.addLayout(buttons1)
        nav = QHBoxLayout(); nav.addStretch(); self.next_button = QPushButton("분석 실행"); self.next_button.setObjectName("primaryButton"); nav.addWidget(self.next_button); root.addLayout(nav)
        self.analysis_tabs.currentChanged.connect(self._tab_changed)
        self.analysis_tabs.activeLabelClicked.connect(self._edit_tab_year)
        self.add_pair.clicked.connect(self.add_direction_pair); self.delete.clicked.connect(self.delete_selected)
        self.copy_segments.clicked.connect(self.copy_selected_segments); self.paste_segments.clicked.connect(self.paste_copied_segments)
        self.reset.clicked.connect(self.reset_selected)
        self.refresh_tabs()

    def _make_table(self) -> QTableWidget:
        table = FrozenInputTable(0, len(self.HEADERS)); table.setHorizontalHeaderLabels(self.HEADERS)
        table.verticalHeader().setVisible(False); table.setAlternatingRowColors(True); table.setSelectionBehavior(QAbstractItemView.SelectItems); table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.horizontalHeader().setFixedHeight(62); table.frozen.horizontalHeader().setFixedHeight(62)
        widths = [46, 108, 52, 135, 40, 52, 135, 86, 86, 108, 86, 82, 92, 74, 82, 126, 126, 64, 122, 122, 132, 104, 70]
        for index, width in enumerate(widths): table.setColumnWidth(index, width)
        for col,delegate in ((0,CenterCheckDelegate(table)),(1,ComboDelegate(self.road_names,True,table)),(3,ComboDelegate(self.intersection_names,True,table)),(4,ComboDelegate(["→","←"],False,table)),(6,ComboDelegate(self.intersection_names,True,table))): table.set_shared_delegate(col,delegate)
        table.setItemDelegateForColumn(10,ComboDelegate(list(FUNCTIONAL_CLASSES),False,table)); table.setItemDelegateForColumn(11,ComboDelegate(["자동","양호","보통"],False,table)); table.setItemDelegateForColumn(18,ComboDelegate(["","A","B","C","D","E","F","FF","FFF"],True,table)); table.setItemDelegateForColumn(19,ComboDelegate(["","A","B","C","D","E","F","FF","FFF"],True,table))
        for col in (7,8,15,16): table.setItemDelegateForColumn(col,NumericDelegate(True,0 if col in (15,16) else 1,1000000,parent=table))
        table.setItemDelegateForColumn(9,NumericDelegate(True,1,99,parent=table))
        for col in (13,14): table.setItemDelegateForColumn(col,NumericDelegate(False,1,1000,1,table))
        table.setItemDelegateForColumn(17,NumericDelegate(False,0.01,1,2,table))
        table.horizontalHeaderItem(10).setToolTip(self._functional_class_tooltip())
        table.itemChanged.connect(lambda item, source=table: self._item_changed(source, item))
        table.cellPressed.connect(lambda row,col,source=table:self._activate_combo(source,source,row,col))
        table.frozen.pressed.connect(lambda index,source=table:self._activate_combo(source,source.frozen,index.row(),index.column()))
        return table

    def _activate_combo(self, table: FrozenInputTable, view: QTableView, row: int, column: int) -> None:
        """드롭다운 셀은 첫 클릭의 press 단계에서 편집기와 목록을 즉시 연다."""
        if column not in self.COMBO_COLUMNS or row < 0 or not table.item(row,column): return
        index=table.model().index(row,column); view.setCurrentIndex(index)
        self._begin_combo_edit(table,view,row,column)

    def _begin_combo_edit(self, table: FrozenInputTable, view: QTableView, row: int, column: int) -> None:
        index=table.model().index(row,column)
        if view is table: table.editItem(table.item(row,column))
        else: view.edit(index)

    @staticmethod
    def _functional_class_tooltip() -> str:
        return ("기능등급 선택 참고 (도로용량편람 2013 표 12-2·12-3)\n"
                "고규격: 이동성 매우 중요 · 접근관리수준 고 · 자유속도 기준 80km/h\n"
                "중간규격: 이동성 중요 · 접근관리수준 중 · 자유속도 기준 70km/h\n"
                "저규격: 이동성 보통 · 접근관리수준 저 · 자유속도 기준 60km/h\n"
                "※ 자유속도만으로 정하지 않고 연결도로, 주 통행목적, 진출입·신호 밀도와 주변 개발정도를 함께 판단합니다.")

    def road_names(self) -> list[str]:
        return sorted({s.road_name for s in self.project.segments if s.road_name})

    def intersection_names(self) -> list[str]:
        return sorted({name for s in self.project.segments for name in (s.start_name, s.end_name) if name})

    def active_table(self) -> QTableWidget:
        return self.external_table if self.road_tabs.currentIndex() == 0 else self.internal_table

    def _tab_label(self, key: tuple[str, int], changed=False) -> str:
        return f"{'● ' if changed else ''}{SCENARIO_LABEL[key[0]]}({key[1]})"

    def refresh_tabs(self, select_key: tuple[str, int] | None = None) -> None:
        current = select_key or self.current_key
        self._changing_tabs = True; clear_tab_bar(self.analysis_tabs)
        keys = self.project.tab_keys()
        for key in keys:
            index = self.analysis_tabs.addTab(self._tab_label(key, bool(self.structure_changes(key))))
            self.analysis_tabs.setTabData(index, key)
            self.analysis_tabs.setTabTextColor(index,{"현황":QColor("#475569"),"사업 미시행시":QColor("#2563EB"),"사업 시행시":QColor("#059669"),"개선대책 이행시":QColor("#D97706")}[key[0]])
            if key[0]!="현황":
                close=QToolButton(self.analysis_tabs); close.setText("×"); close.setObjectName("tabCloseButton"); close.setFixedSize(18,22); close.setCursor(Qt.PointingHandCursor); close.setToolTip("탭 삭제")
                close.clicked.connect(lambda _=False,k=key:self._delete_analysis_key(k)); self.analysis_tabs.setTabButton(index,QTabBar.ButtonPosition.RightSide,close)
        plus = self.analysis_tabs.addTab("+"); self.analysis_tabs.setTabData(plus, None)
        self.analysis_tabs.setTabButton(plus,QTabBar.ButtonPosition.RightSide,None)
        target = next((i for i, key in enumerate(keys) if key == current), 0)
        self.analysis_tabs.setCurrentIndex(target); self._changing_tabs = False
        if keys:
            self._load_key(keys[target])

    def _default_source(self, scenario: str, year: int) -> tuple[str, int] | None:
        keys = self.project.tab_keys()
        if scenario == "사업 미시행시":
            previous = [key for key in keys if key[0] == scenario and key[1] < year]
            return max(previous, key=lambda key: key[1]) if previous else next((key for key in keys if key[0] == "현황"), None)
        if scenario == "사업 시행시":
            previous = [key for key in keys if key[0] == scenario and key[1] < year]
            if previous: return max(previous, key=lambda key: key[1])
            return next((key for key in keys if key == ("사업 미시행시", year)), None)
        if scenario == "개선대책 이행시":
            return next((key for key in keys if key == ("사업 시행시", year)), None)
        return None

    def _tab_changed(self, index: int) -> None:
        if self._changing_tabs or index < 0: return
        key = self.analysis_tabs.tabData(index)
        if key is None:
            previous = self.current_key
            dialog = AddAnalysisTabDialog(self, year=(previous[1] if previous else self.project.current_year))
            if dialog.exec() != QDialog.Accepted:
                self.refresh_tabs(previous); return
            key = (dialog.scenario.currentText(), dialog.year.value())
            if key in self.project.tab_keys():
                QMessageBox.information(self, "탭 추가", "같은 상황과 연도의 탭이 이미 있습니다."); self.refresh_tabs(key); return
            self.save_current(); self.project.ensure_tab(*key)
            source = self._default_source(*key)
            if source: self.project.copy_rows(*source, *key)
            self.changed.emit()
            self.refresh_tabs(key); return
        self.save_current(); self._load_key(tuple(key))

    def _edit_tab_year(self, index: int) -> None:
        key = self.analysis_tabs.tabData(index)
        if key is None: return
        scenario, old_year = tuple(key)
        dialog = AddAnalysisTabDialog(self, scenario, old_year, True)
        if dialog.exec() != QDialog.Accepted or dialog.year.value() == old_year: return
        new_key = (scenario, dialog.year.value())
        if new_key in self.project.tab_keys():
            QMessageBox.information(self, "연도 변경", "같은 상황과 연도의 탭이 이미 있습니다."); return
        self.save_current()
        for segment in self.project.segments:
            if (segment.scenario, segment.year) == (scenario, old_year): segment.year = new_key[1]
        for item in self.project.analysis_tabs:
            if (item["scenario"], int(item["year"])) == (scenario, old_year): item["year"] = new_key[1]
        if scenario == "현황": self.project.current_year = new_key[1]
        self.changed.emit()
        self.refresh_tabs(new_key)

    def _delete_analysis_tab(self,index: int) -> None:
        key=self.analysis_tabs.tabData(index)
        if key:self._delete_analysis_key(tuple(key))

    def _delete_analysis_key(self,key: tuple[str,int]) -> None:
        if not key or key[0]=="현황":return
        scenario,year=tuple(key)
        if QMessageBox.question(self,"분석 탭 삭제",f"{SCENARIO_LABEL[scenario]}({year}) 탭과 입력된 구간을 삭제하시겠습니까?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        self.save_current(); self.project.segments=[s for s in self.project.segments if (s.scenario,s.year)!=(scenario,year)]; self.project.analysis_tabs=[item for item in self.project.analysis_tabs if (item.get("scenario"),int(item.get("year",0)))!=(scenario,year)]
        used_years={int(item["year"]) for item in self.project.analysis_tabs if item.get("scenario")!="현황"}; used_years.update(s.year for s in self.project.segments if s.scenario!="현황"); self.project.future_years=sorted(used_years)
        self.changed.emit(); self.refresh_tabs()

    def _load_key(self, key: tuple[str, int]) -> None:
        self.current_key = key
        show_internal=key[0] in ("사업 시행시","개선대책 이행시"); self.road_tabs.setTabVisible(1,show_internal)
        if not show_internal:self.road_tabs.setCurrentIndex(0)
        self._load_table(self.external_table, [s for s in self.project.rows(*key) if s.road_category != INTERNAL])
        self._load_table(self.internal_table, [s for s in self.project.rows(*key) if s.road_category == INTERNAL])
        changes = self.structure_changes(key)
        if changes:
            self.change_notice.setText(f"이전 {SCENARIO_LABEL[key[0]]} 연도 대비 구간 구조 변경 {len(changes)}건 · " + " / ".join(changes[:3]))
            self.change_notice.show()
        else: self.change_notice.hide()
        index = self.analysis_tabs.currentIndex()
        if index >= 0 and self.analysis_tabs.tabData(index) is not None:
            self.analysis_tabs.setTabText(index, self._tab_label(key, bool(changes)))

    def _load_table(self, table: QTableWidget, rows: list[SegmentInput]) -> None:
        table.blockSignals(True); table.clearSpans(); table.frozen.clearSpans(); table.setRowCount(0)
        for segment in rows: self._append_segment(table, segment)
        self._merge_pairs(table); table.blockSignals(False); table._update_frozen_geometry()

    def _append_segment(self, table: QTableWidget, s: SegmentInput) -> None:
        report_length=s.length_km if s.report_length_km is None else s.report_length_km
        try: live=analyze_segment(s,self.project.settings); speed=f"{live.speed_kmh:.1f}"; los=live.los
        except (ValueError,TypeError): speed="확인"; los="-"
        report_volume=s.main_volume if s.report_volume is None else s.report_volume
        values = ["", s.road_name, str(s.start_number), s.start_name, s.direction, str(s.end_number), s.end_name, f"{round(s.length_km*1000):,}", f"{round(report_length*1000):,}", s.lanes, s.functional_class, s.road_condition_override, self._auto_type(s.functional_class, s.lanes, s.road_condition_override), f"{s.cycle_s:.1f}", f"{s.green_s:.1f}", f"{int(round(s.main_volume)):,}", f"{int(round(report_volume)):,}", f"{s.phf:.2f}", s.intersection_los, s.approach_los, speed, los, ""]
        row = table.rowCount(); table.insertRow(row)
        for col, value in enumerate(values):
            item = QTableWidgetItem(str(value)); item.setData(Qt.UserRole, s.uid if col == 0 else None); item.setData(Qt.UserRole+1,s.comparison_id if col==0 else None)
            item.setTextAlignment((Qt.AlignRight if col in self.NUMERIC_COLUMNS else Qt.AlignCenter) | Qt.AlignVCenter)
            if col == 0: item.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable|Qt.ItemIsSelectable); item.setCheckState(Qt.Unchecked)
            if col in self.READ_ONLY_COLUMNS: item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            if col == 12: item.setBackground(QColor("#E9EEF4"))
            if col == 10: item.setToolTip(self._functional_class_tooltip())
            if col == 11: item.setToolTip(f"자동 판정: {road_condition(s.functional_class, s.lanes)} · 중·저규격 양호는 접근부 직진차로 2개 이상 여부 확인")
            if col in (20,21): item.setBackground(QColor("#DDF4FF")); item.setForeground(QColor("#075985"))
            if s.manual_speed_kmh is not None and col in (20,21): item.setBackground(QColor("#FFF0F0")); item.setForeground(QColor("#D7191C")); item.setToolTip("분석결과에서 수동조정된 값")
            if col in (18,19): item.setBackground(QColor("#FFF8DD")); item.setToolTip("교차로 분석자료를 참고해 입력하는 값이며 간선도로 공식 계산값과 구분됩니다.")
            table.setItem(row, col, item)
        pair_color=["#DCEBFF","#E8F5E9","#FFF1D6","#F3E8FF"][sum(ord(ch) for ch in s.comparison_id)%4]; table.item(row,0).setBackground(QColor(pair_color)); table.item(row,0).setToolTip("같은 색은 연결된 양방향 구간입니다.")
        button=QPushButton("상세"); button.setObjectName("detailButton"); button.clicked.connect(lambda _=False, uid=s.uid:self.edit_details(uid)); table.setCellWidget(row,22,button)

    @staticmethod
    def _auto_type(functional: str, lanes: int, condition_override: str = "자동") -> str:
        functional=functional if functional in FUNCTIONAL_CLASSES else "중간규격"
        condition=condition_override if condition_override in ("양호","보통") else road_condition(functional,max(1,lanes))
        result = arterial_type(functional, condition)
        return result.replace("유형 ", "유형")

    @staticmethod
    def _merge_pairs(table: FrozenInputTable) -> None:
        table.clearSpans(); table.frozen.clearSpans(); row=0
        while row<table.rowCount():
            item=table.item(row,0); identity=item.data(Qt.UserRole+1) if item else None; end=row+1
            while end<table.rowCount() and table.item(end,0) and table.item(end,0).data(Qt.UserRole+1)==identity: end+=1
            if identity and end-row>1:
                for col in (0,1,2,3,5,6): table.setSpan(row,col,end-row,1); table.frozen.setSpan(row,col,end-row,1)
            row=end

    def _item_changed(self, table: QTableWidget, item: QTableWidgetItem) -> None:
        if item.column() in self.NUMERIC_COLUMNS: item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        else: item.setTextAlignment(Qt.AlignCenter)
        if item.column() in (9, 10, 11):
            table.blockSignals(True)
            try: lanes = int(float(table.item(item.row(), 9).text().replace(",","")))
            except (ValueError, AttributeError): lanes = 2
            functional = table.item(item.row(), 10).text() if table.item(item.row(), 10) else "중간규격"
            condition = table.item(item.row(), 11).text() if table.item(item.row(), 11) else "자동"
            table.item(item.row(), 12).setText(self._auto_type(functional, lanes, condition)); table.blockSignals(False)
        if item.column() in (2,3,5,6): self._sync_pair(table,item)
        self._refresh_live_row(table,item.row()); self.changed.emit()

    def _sync_pair(self, table: QTableWidget, item: QTableWidgetItem) -> None:
        identity=table.item(item.row(),0).data(Qt.UserRole+1)
        if not identity:return
        table.blockSignals(True)
        for row in range(table.rowCount()):
            if row!=item.row() and table.item(row,0).data(Qt.UserRole+1)==identity:
                table.item(row,item.column()).setText(item.text())
        table.blockSignals(False)

    def _refresh_live_row(self, table: QTableWidget, row: int) -> None:
        try:
            old={s.uid:s for s in self.project.segments}; segment=self._segment_from_row(table,row,EXTERNAL if table is self.external_table else INTERNAL,old)
            result=analyze_segment(segment,self.project.settings); speed=f"{result.speed_kmh:.1f}"; los=result.los; tip=f"편람 원계산 {result.calculated_speed_kmh:.1f} km/h"
            error=False
        except (ValueError,TypeError) as exc: speed="확인"; los="-"; tip=str(exc) or "입력값을 확인해 주세요."; error=True
        table.blockSignals(True); table.item(row,20).setText(speed); table.item(row,21).setText(los); table.item(row,20).setToolTip(tip)
        manual=any(s.uid==table.item(row,0).data(Qt.UserRole) and s.manual_speed_kmh is not None for s in self.project.segments)
        for col in (20,21): table.item(row,col).setBackground(QColor("#FFE5E5" if error or manual else "#DDF4FF")); table.item(row,col).setForeground(QColor("#B91C1C" if error or manual else "#075985")); table.item(row,col).setToolTip(tip)
        table.blockSignals(False)

    def save_current(self) -> None:
        if not self.current_key: return
        scenario, year = self.current_key
        old = {s.uid: s for s in self.project.rows(scenario, year)}
        rows = self._rows_from_table(self.external_table, EXTERNAL, old) + self._rows_from_table(self.internal_table, INTERNAL, old)
        self.project.replace_rows(scenario, year, rows)

    def _rows_from_table(self, table: QTableWidget, category: str, old: dict[str, SegmentInput]) -> list[SegmentInput]:
        rows: list[SegmentInput] = []
        for row in range(table.rowCount()):
            try:
                segment=self._segment_from_row(table,row,category,old)
            except ValueError as exc:
                raise ValueError(f"{row + 1}행 숫자 입력값을 확인해 주세요: {exc}") from exc
            rows.append(segment)
        return rows

    def _segment_from_row(self,table,row,category,old):
        text=lambda col:table.item(row,col).text().strip() if table.item(row,col) else ""
        number=lambda col:float(text(col).replace(",","") or 0)
        uid=table.item(row,0).data(Qt.UserRole) or uuid4().hex; previous=old.get(uid); comparison_id=previous.comparison_id if previous else table.item(row,0).data(Qt.UserRole+1) or f"auto-{uuid4().hex[:10]}"
        return SegmentInput(uid=uid,comparison_id=comparison_id,scenario=self.current_key[0],year=self.current_key[1],road_category=category,road_name=text(1),start_number=text(2),start_name=text(3),direction=text(4) if text(4) in ("→","←") else "→",end_number=text(5),end_name=text(6),length_km=number(7)/1000,report_length_km=number(8)/1000,lanes=int(number(9)),functional_class=text(10) if text(10) in FUNCTIONAL_CLASSES else "중간규격",road_condition_override=text(11) if text(11) in ("자동","양호","보통") else "자동",arterial_type_override="자동",cycle_s=number(13),green_s=number(14),main_volume=int(number(15)),report_volume=int(number(16)),phf=number(17),bus_stops=previous.bus_stops if previous else 0,access_points=previous.access_points if previous else 0,intersection_los=text(18),approach_los=text(19),manual_speed_kmh=previous.manual_speed_kmh if previous else None,speed_adjustment_history=list(previous.speed_adjustment_history) if previous else [],saturation_adjustment=previous.saturation_adjustment if previous else None,initial_queue=previous.initial_queue if previous else None,pf_override=previous.pf_override if previous else None,fcw_override=previous.fcw_override if previous else None,analysis_period_h=previous.analysis_period_h if previous else None,base_saturation_flow=previous.base_saturation_flow if previous else None,coordinated=previous.coordinated if previous else None,crossing_signals=previous.crossing_signals if previous else None)

    def add_direction_pair(self) -> None:
        table = self.active_table(); number = table.rowCount() // 2 + 1; scenario, year = self.current_key or ("현황", self.project.current_year)
        common = dict(comparison_id=f"auto-{uuid4().hex[:10]}", scenario=scenario, year=year, road_category=INTERNAL if table is self.internal_table else EXTERNAL, road_name="가로명", start_number="", start_name="기점교차로", end_number="", end_name="종점교차로", length_km=1, report_length_km=1, cycle_s=120, green_s=50, main_volume=500, report_volume=500, phf=1, lanes=2)
        table.blockSignals(True)
        self._append_segment(table, SegmentInput(uid=uuid4().hex, direction="→", **common))
        self._append_segment(table, SegmentInput(uid=uuid4().hex, direction="←", **common))
        self._merge_pairs(table); table.blockSignals(False); table._update_frozen_geometry(); table.scrollToBottom()

    def selected_rows(self) -> list[int]:
        table=self.active_table(); selected_ids={table.item(row,0).data(Qt.UserRole+1) for row in range(table.rowCount()) if table.item(row,0) and table.item(row,0).checkState()==Qt.Checked}
        return [row for row in range(table.rowCount()) if table.item(row,0) and table.item(row,0).data(Qt.UserRole+1) in selected_ids]

    def copy_selected_segments(self) -> None:
        rows=self.selected_rows(); table=self.active_table()
        if not rows: QMessageBox.information(self,"구간 복사","복사할 구간을 체크박스로 선택해 주세요."); return
        self.save_current(); uids={table.item(row,0).data(Qt.UserRole) for row in rows}
        self._segment_clipboard=[s.to_dict() for s in self.project.rows(*self.current_key) if s.uid in uids]
        QMessageBox.information(self,"구간 복사",f"{len(self._segment_clipboard)}개 방향 구간을 복사했습니다. 원하는 탭에서 붙여넣어 주세요.")

    def paste_copied_segments(self) -> None:
        if not self._segment_clipboard: QMessageBox.information(self,"구간 붙여넣기","먼저 체크박스로 구간을 선택해 복사해 주세요."); return
        table=self.active_table(); scenario,year=self.current_key; category=INTERNAL if table is self.internal_table else EXTERNAL; identities={}
        clones=[]
        for data in self._segment_clipboard:
            clone=SegmentInput.from_dict(data); clone.uid=uuid4().hex; clone.comparison_id=identities.setdefault(clone.comparison_id,f"auto-{uuid4().hex[:10]}"); clone.scenario=scenario; clone.year=year; clone.road_category=category; clone.manual_speed_kmh=None; clone.speed_adjustment_history=[]; clones.append(clone)
        table.blockSignals(True)
        for clone in clones:self._append_segment(table,clone)
        self._merge_pairs(table); table.blockSignals(False); table._update_frozen_geometry(); table.scrollToBottom(); self.changed.emit()

    def delete_selected(self) -> None:
        table = self.active_table()
        if not self.selected_rows(): QMessageBox.information(self,"행 삭제","왼쪽 체크박스로 삭제할 행을 선택해 주세요."); return
        for row in reversed(self.selected_rows()): table.removeRow(row)
        self._merge_pairs(table); table._update_frozen_geometry()

    def edit_details(self,uid: str) -> None:
        self.save_current()
        segment = next((s for s in self.project.segments if s.uid == uid), None)
        if not segment: return
        dialog = SegmentDetailDialog(segment, self.project, self)
        if dialog.exec() == QDialog.Accepted: dialog.apply_to_segment(); self._load_key(self.current_key); self.changed.emit()

    def reset_selected(self) -> None:
        rows = self.selected_rows(); table = self.active_table()
        if not rows: QMessageBox.information(self, "초기화", "초기화할 행을 선택해 주세요."); return
        self.save_current(); uids = {table.item(row, 0).data(Qt.UserRole) for row in rows}; defaults = self.project.settings
        for s in self.project.segments:
            if s.uid not in uids: continue
            s.length_km=1; s.report_length_km=1; s.cycle_s=120; s.green_s=50; s.main_volume=500; s.report_volume=500; s.phf=1; s.lanes=2; s.functional_class="중간규격"; s.road_condition_override="자동"; s.bus_stops=0; s.access_points=0; s.intersection_los=""; s.approach_los=""; s.manual_speed_kmh=None; s.speed_adjustment_history=[]
            s.analysis_period_h=defaults.analysis_period_h; s.base_saturation_flow=defaults.base_saturation_flow; s.saturation_adjustment=defaults.saturation_adjustment; s.initial_queue=defaults.initial_queue; s.coordinated=defaults.coordinated; s.crossing_signals=defaults.crossing_signals; s.pf_override=defaults.pf_override; s.fcw_override=defaults.fcw_override
        self._load_key(self.current_key)

    def structure_changes(self, key: tuple[str, int]) -> list[str]:
        scenario, year = key
        if scenario not in ("사업 미시행시", "사업 시행시"): return []
        previous_years = [tab_year for tab_scenario, tab_year in self.project.tab_keys() if tab_scenario == scenario and tab_year < year]
        if not previous_years: return []
        previous = max(previous_years)
        def mapping(rows): return {(s.comparison_id, s.direction): s for s in rows}
        before, after = mapping(self.project.rows(scenario, previous)), mapping(self.project.rows(scenario, year))
        changes: list[str] = []
        labels = [("road_category","도로영역"),("road_name","가로명"),("start_number","시점번호"),("start_name","시점"),("end_number","종점번호"),("end_name","종점"),("length_km","구간길이"),("lanes","차로수"),("functional_class","기능등급"),("bus_stops","정류장수"),("access_points","진출입로수")]
        for identity in sorted(set(before) | set(after)):
            a, b = before.get(identity), after.get(identity)
            if a is None: changes.append(f"신규 {b.road_name} {b.direction}"); continue
            if b is None: changes.append(f"삭제 {a.road_name} {a.direction}"); continue
            different = [label for field, label in labels if getattr(a, field) != getattr(b, field)]
            if different: changes.append(f"{b.road_name} {b.direction}: {', '.join(different)}")
        return changes


def scenario_spec(project: ArterialProject, results: list[AnalysisResult], key: tuple[str, int]) -> ReportSpec:
    rows = [r for r in results if (r.segment.scenario, r.segment.year) == key]
    rows.sort(key=lambda r: (r.segment.road_category, r.segment.road_name, r.segment.comparison_id, 0 if r.segment.direction == "→" else 1))
    return ReportSpec(
        title=f"{SCENARIO_LABEL[key[0]]}({key[1]}) 도시·교외간선도로 분석결과",
        groups=[SEGMENT_GROUP,("분석결과",["도로유형","구간거리\n(km)","교통량\n(대/시)","평균통행속도\n(km/h)","서비스수준\n(LOS)"])],
        rows=[[*_segment_cells(r),r.arterial_type.replace("유형 ","유형"),f"{(r.segment.report_length_km if r.segment.report_length_km is not None else r.segment.length_km):.1f}",f"{(r.segment.report_volume if r.segment.report_volume is not None else r.segment.main_volume):,.0f}",f"{r.speed_kmh:.1f}",r.los] for r in rows],
        widths=[*SEGMENT_WIDTHS,*([100]*5)],
        row_uids=[r.segment.uid for r in rows],row_categories=[r.segment.road_category for r in rows],highlight_cells={(i,9) for i,r in enumerate(rows) if r.segment.manual_speed_kmh is not None},header_spans=SEGMENT_HEADER_SPANS,row_pair_ids=[r.segment.comparison_id for r in rows],body_merge_columns=SEGMENT_MERGE_COLUMNS,
    )


def detail_spec(results: list[AnalysisResult], key: tuple[str, int]) -> ReportSpec:
    rows = [r for r in results if (r.segment.scenario, r.segment.year) == key]
    rows.sort(key=lambda r: (r.segment.road_category, r.segment.road_name, r.segment.comparison_id, 0 if r.segment.direction == "→" else 1))
    type_name = lambda value: {"유형 I": "유형1", "유형 II": "유형2", "유형 III": "유형3"}.get(value, value)
    return ReportSpec(
        title=f"{SCENARIO_LABEL[key[0]]}({key[1]}) 세부 계산결과",
        groups=[SEGMENT_GROUP,("세부 계산결과",["구간길이\n(km)","유형","g/C","V\n(대/시)","V/c","q/s^a","균일제어지체\n(d1)","연동보정계수\n(PF)","증분지체\n(d2)","추가지체\n(d3)","구간 순행시간\n(초)","차량당 평균제어지체\n(d)","총소요시간\n(초)","평균통행속도\n(km/h)","서비스수준\n(LOS)"])],
        rows=[[*_segment_cells(r),f"{(r.segment.report_length_km if r.segment.report_length_km is not None else r.segment.length_km):.1f}",type_name(r.arterial_type),f"{r.segment.green_s/r.segment.cycle_s:.2f}",f"{r.segment.main_volume:,.0f}",f"{r.vc_ratio:.2f}",f"{r.qs_ratio:.2f}",f"{r.uniform_delay_s:.2f}",f"{r.pf:.2f}",f"{r.incremental_delay_s:.2f}",f"{r.initial_queue_delay_s:.2f}",f"{r.running_time_s:.2f}",f"{r.control_delay_s:.2f}",f"{r.total_time_s:.2f}",f"{r.speed_kmh:.1f}",r.los] for r in rows],
        widths=[*SEGMENT_WIDTHS,*([100]*15)],
        row_uids=[r.segment.uid for r in rows],row_categories=[r.segment.road_category for r in rows],highlight_cells={(i,19) for i,r in enumerate(rows) if r.segment.manual_speed_kmh is not None},header_spans=SEGMENT_HEADER_SPANS,row_pair_ids=[r.segment.comparison_id for r in rows],body_merge_columns=SEGMENT_MERGE_COLUMNS,
    )


def populate_spec(table: CopyableTable, spec: ReportSpec) -> None:
    columns = len(spec.headers); table.clear(); table.setColumnCount(columns); table.setRowCount(2)
    table.horizontalHeader().setVisible(False); table.setEditTriggers(QAbstractItemView.NoEditTriggers); table.clearSpans()
    column = 0
    for group, headers in spec.groups:
        item = QTableWidgetItem(group); item.setTextAlignment(Qt.AlignCenter); table.setItem(0, column, item)
        if len(headers) > 1: table.setSpan(0, column, 1, len(headers))
        for header in headers:
            header_item = QTableWidgetItem(header); header_item.setTextAlignment(Qt.AlignCenter); table.setItem(1, column, header_item); column += 1
    for start,span,label in spec.header_spans:
        table.item(1,start).setText(label)
        if span>1: table.setSpan(1,start,1,span)
    visual_rows=[]; last_category=None
    for data_index,row in enumerate(spec.rows):
        category=spec.row_categories[data_index] if data_index<len(spec.row_categories) else ""
        if category and category!=last_category:
            vr=table.rowCount(); table.insertRow(vr); table.setSpan(vr,0,1,columns); section=QTableWidgetItem("■ 내부도로" if category==INTERNAL else "■ 외부도로"); section.setTextAlignment(Qt.AlignLeft|Qt.AlignVCenter); section.setBackground(QColor("#DCE7F5")); section.setForeground(QColor("#1E3A5F")); table.setItem(vr,0,section); last_category=category
        row_index=table.rowCount(); table.insertRow(row_index); visual_rows.append((data_index,row_index))
        for col, value in enumerate(row):
            text = str(value)
            numeric = bool(re.fullmatch(r"[+-]?[\d,]+(?:\.\d+)?%?", text))
            segment_column=col<6
            item = QTableWidgetItem(text); item.setTextAlignment((Qt.AlignCenter if segment_column or not numeric else Qt.AlignRight) | Qt.AlignVCenter); table.setItem(row_index, col, item)
            if (data_index,col) in spec.highlight_cells: item.setForeground(QColor("#D7191C")); item.setBackground(QColor("#FFF0F0")); item.setFont(table.font()); item.setToolTip("수동조정값")
        if spec.row_uids and data_index<len(spec.row_uids): table.item(row_index,0).setData(Qt.UserRole,spec.row_uids[data_index])
        if spec.row_warnings and data_index<len(spec.row_warnings) and spec.row_warnings[data_index]:
            for col in range(columns):
                if table.item(row_index,col): table.item(row_index,col).setBackground(QColor("#FFF1D6")); table.item(row_index,col).setToolTip(spec.row_warnings[data_index])
        if spec.row_details and data_index<len(spec.row_details):
            detail_row=table.rowCount(); table.insertRow(detail_row); table.setSpan(detail_row,0,1,columns); detail_text=(spec.row_warnings[data_index]+" · " if data_index<len(spec.row_warnings) and spec.row_warnings[data_index] else "")+spec.row_details[data_index]; detail_item=QTableWidgetItem(""); detail_item.setData(Qt.UserRole,detail_text); detail_item.setBackground(QColor("#F7FAFC")); detail_item.setForeground(QColor("#475569")); table.setItem(detail_row,0,detail_item); table.setRowHidden(detail_row,True)
            button=QPushButton("검토 ▼" if not (data_index<len(spec.row_warnings) and spec.row_warnings[data_index]) else "확인 필요 ▼"); button.setObjectName("reviewButton"); button.clicked.connect(lambda _=False,r=detail_row,b=button:self_toggle_detail(table,r,b)); table.setCellWidget(row_index,columns-1,button)
    # 양방향 한 쌍의 공통 구간정보는 세로 병합하고 방향만 분리한다.
    if not spec.row_details:
        start=0
        while start<len(visual_rows):
            data_index,visual=visual_rows[start]; identity=spec.row_pair_ids[data_index] if data_index<len(spec.row_pair_ids) else str(spec.rows[data_index][0]); end=start+1
            while end<len(visual_rows):
                next_data,next_visual=visual_rows[end]; next_identity=spec.row_pair_ids[next_data] if next_data<len(spec.row_pair_ids) else str(spec.rows[next_data][0])
                if next_identity!=identity or next_visual!=visual_rows[end-1][1]+1: break
                end+=1
            if end-start>1:
                for col in (spec.body_merge_columns or (0,)): table.setSpan(visual,col,end-start,1)
            start=end
    for col, width in enumerate(spec.widths): table.setColumnWidth(col, width)
    table.setRowHeight(0, 34); table.setRowHeight(1, 46)


def self_toggle_detail(table: QTableWidget,row: int,button: QPushButton) -> None:
    opening=table.isRowHidden(row); item=table.item(row,0)
    if item:item.setText(str(item.data(Qt.UserRole) or "") if opening else "")
    table.setRowHidden(row,not opening)
    if opening: table.resizeRowToContents(row); table.setRowHeight(row,max(42,table.rowHeight(row)))
    button.setText(("접기 ▲" if opening else "검토 ▼"))


class ResultsPage(QWidget):
    changed = Signal()
    def __init__(self) -> None:
        super().__init__(); self.project=None; self.results=[]; self.current_spec=None; self.scope=[]
        root = QVBoxLayout(self); root.setContentsMargins(16, 14, 16, 14)
        hero_row=QHBoxLayout(); self.hero = QLabel(); self.hero.setObjectName("resultHero"); self.hero.setWordWrap(True); hero_row.addWidget(self.hero,1); self.copy_hero=QPushButton("문구 복사"); self.copy_hero.setObjectName("primaryButton"); hero_row.addWidget(self.copy_hero); root.addLayout(hero_row)
        self.save_notice=QLabel("분석 결과를 확인한 뒤 프로젝트를 저장해 주세요."); self.save_notice.setObjectName("saveNotice"); root.addWidget(self.save_notice)
        self.tabs = QTabBar(); self.tabs.setExpanding(False); self.tabs.setDrawBase(False); root.addWidget(self.tabs)
        hint = QHBoxLayout(); copy_note = QLabel("표 범위를 선택한 뒤 Ctrl+C로 한글 표에 붙여넣을 수 있습니다. 평균통행속도 셀을 더블클릭하면 근거를 남기고 조정할 수 있습니다."); copy_note.setObjectName("copyNote"); hint.addWidget(copy_note); hint.addStretch(); root.addLayout(hint)
        self.table = CopyableTable(); root.addWidget(make_card("2. 분석 결과", self.table), 1)
        nav = QHBoxLayout(); self.back = QPushButton("구간 입력으로"); self.detail = QPushButton("부록용 세부 계산"); self.detail.setObjectName("primaryButton"); nav.addWidget(self.back); nav.addStretch(); nav.addWidget(self.detail); root.addLayout(nav)
        self.tabs.currentChanged.connect(self.show_tab); self.copy_hero.clicked.connect(lambda:QGuiApplication.clipboard().setText(self.hero.text())); self.table.itemDoubleClicked.connect(self.edit_speed)

    def refresh(self, project: ArterialProject, results: list[AnalysisResult]) -> None:
        self.project, self.results = project, results; self.tabs.blockSignals(True); clear_tab_bar(self.tabs)
        for key in project.tab_keys():
            index = self.tabs.addTab(f"{SCENARIO_LABEL[key[0]]}({key[1]})"); self.tabs.setTabData(index, ("scenario", *key))
            self.tabs.setTabTextColor(index,{"현황":QColor("#475569"),"사업 미시행시":QColor("#2563EB"),"사업 시행시":QColor("#059669"),"개선대책 이행시":QColor("#D97706")}[key[0]])
        scenarios = {scenario for scenario, _ in project.tab_keys()}
        for scenario in ("사업 미시행시", "사업 시행시", "개선대책 이행시"):
            if scenario in scenarios:
                index = self.tabs.addTab(f"장래통합-{SCENARIO_LABEL[scenario]}"); self.tabs.setTabData(index, ("future", scenario))
        years = sorted({year for scenario, year in project.tab_keys() if scenario != "현황"})
        for year in years:
            keys = set(project.tab_keys())
            if ("사업 미시행시", year) in keys and ("사업 시행시", year) in keys:
                index = self.tabs.addTab(f"미시행-시행 비교({year})"); self.tabs.setTabData(index, ("compare_nb", year))
            if ("사업 시행시", year) in keys and ("개선대책 이행시", year) in keys:
                index = self.tabs.addTab(f"시행-개선 비교({year})"); self.tabs.setTabData(index, ("compare_im", year))
        self.tabs.blockSignals(False); self.tabs.setCurrentIndex(0); self.show_tab(0)

    def show_tab(self, index: int) -> None:
        if not self.project or index < 0: return
        data = self.tabs.tabData(index)
        if data[0] == "scenario":
            key = (data[1], data[2]); self.current_spec = scenario_spec(self.project, self.results, key)
            self.scope = [r for r in self.results if (r.segment.scenario, r.segment.year) == key]
        elif data[0] == "future":
            scenario = data[1]; self.current_spec = future_report(self.project, self.results, scenario)
            self.scope = [r for r in self.results if r.segment.scenario == scenario]
        elif data[0] == "compare_nb":
            year = data[1]; self.current_spec = comparison_report(self.project, self.results, year, "사업 미시행시", "사업 시행시")
            self.scope = [r for r in self.results if r.segment.scenario == "사업 시행시" and r.segment.year == year]
        else:
            year = data[1]; self.current_spec = comparison_report(self.project, self.results, year, "사업 시행시", "개선대책 이행시")
            self.scope = [r for r in self.results if r.segment.scenario == "개선대책 이행시" and r.segment.year == year]
        populate_spec(self.table, self.current_spec); self.update_hero()
        if data[0]=="scenario":
            for row in range(self.table.rowCount()):
                first=self.table.item(row,0)
                if not first:continue
                uid=first.data(Qt.UserRole); result=next((r for r in self.results if r.segment.uid==uid),None)
                if result and result.segment.manual_speed_kmh is not None and self.table.item(row,9):
                    history=result.segment.speed_adjustment_history[-1] if result.segment.speed_adjustment_history else {}
                    self.table.item(row,9).setToolTip(f"수동조정 · 원계산 {result.calculated_speed_kmh:.1f} km/h\n{history.get('changed_at','')}\n{history.get('reason','')}")

    def update_hero(self) -> None:
        if not self.scope: self.hero.setText("분석할 구간이 없습니다."); return
        rank = {"A":0,"B":1,"C":2,"D":3,"E":4,"F":5,"FF":6,"FFF":7}
        speeds = [r.speed_kmh for r in self.scope]; grades = [r.los for r in self.scope]
        best, worst = min(grades, key=lambda value: rank[value]), max(grades, key=lambda value: rank[value])
        self.hero.setText(f"도시 및 교외간선도로의 평균통행속도는 {min(speeds):.1f}~{max(speeds):.1f}km/h, 서비스수준은 “{best}”~“{worst}”로 분석되었음")

    def edit_speed(self,item: QTableWidgetItem) -> None:
        data=self.tabs.tabData(self.tabs.currentIndex())
        if not data or data[0]!="scenario" or item.column()!=9:return
        uid=self.table.item(item.row(),0).data(Qt.UserRole) if self.table.item(item.row(),0) else None
        result=next((r for r in self.results if r.segment.uid==uid),None)
        if not result:return
        dialog=SpeedAdjustmentDialog(result,self)
        if dialog.exec()!=QDialog.Accepted:return
        segment=result.segment; old=segment.manual_speed_kmh if segment.manual_speed_kmh is not None else result.calculated_speed_kmh
        segment.manual_speed_kmh=dialog.speed.value(); segment.speed_adjustment_history.append({"changed_at":datetime.now().astimezone().isoformat(timespec="seconds"),"original_calculated_speed_kmh":round(result.calculated_speed_kmh,3),"previous_applied_speed_kmh":round(old,3),"new_applied_speed_kmh":round(dialog.speed.value(),3),"reason":dialog.reason.toPlainText().strip()})
        current=self.tabs.currentIndex(); self.results=self.project.analyze_all(); self.refresh(self.project,self.results); self.tabs.setCurrentIndex(min(current,self.tabs.count()-1)); self.changed.emit()


class DetailPage(QWidget):
    def __init__(self) -> None:
        super().__init__(); self.project=None; self.results=[]; self.current_spec=None
        root=QVBoxLayout(self); root.setContentsMargins(16,14,16,14)
        title=QLabel("부록용 세부 계산결과"); title.setObjectName("pageTitle"); root.addWidget(title)
        self.tabs=QTabBar(); self.tabs.setExpanding(False); self.tabs.setDrawBase(False); root.addWidget(self.tabs)
        note_row=QHBoxLayout(); note=QLabel("세부 계산표는 셀 복사와 고해상도 이미지 복사를 지원합니다. V는 계산에 사용한 주이동류 교통량입니다."); note.setObjectName("infoBar"); note_row.addWidget(note,1); self.copy_image=QPushButton("부록 이미지 복사"); self.copy_image.setObjectName("primaryButton"); note_row.addWidget(self.copy_image); root.addLayout(note_row)
        self.table=CopyableTable(); root.addWidget(make_card("3. 세부 계산결과",self.table),1)
        nav=QHBoxLayout(); self.back=QPushButton("분석 결과로"); self.input=QPushButton("구간 입력으로"); nav.addWidget(self.back); nav.addStretch(); nav.addWidget(self.input); root.addLayout(nav)
        self.tabs.currentChanged.connect(self.show_tab); self.copy_image.clicked.connect(self.copy_appendix_image)

    def refresh(self,project,results):
        self.project,self.results=project,results; self.tabs.blockSignals(True); clear_tab_bar(self.tabs)
        for key in project.tab_keys():
            i=self.tabs.addTab(f"{SCENARIO_LABEL[key[0]]}({key[1]})"); self.tabs.setTabData(i,key)
        self.tabs.blockSignals(False); self.tabs.setCurrentIndex(0); self.show_tab(0)

    def show_tab(self,index):
        if index<0:return
        key=tuple(self.tabs.tabData(index)); self.current_spec=detail_spec(self.results,key); populate_spec(self.table,self.current_spec)

    def copy_appendix_image(self):
        if not self.current_spec:return
        compact_spec=replace(self.current_spec,widths=[max(42,int(width*.62)) for width in self.current_spec.widths])
        image=render_report_image(compact_spec,scale=2.5,include_title=False,compact=True); image.setDotsPerMeterX(16000); image.setDotsPerMeterY(16000); QGuiApplication.clipboard().setPixmap(QPixmap.fromImage(image)); QMessageBox.information(self,"이미지 복사","한글 문서 폭에 맞춘 고해상도 부록 표 이미지를 복사했습니다. 한글에 바로 붙여넣을 수 있습니다.")


class Workflow(QWidget):
    changed = Signal()
    def __init__(self,project):
        super().__init__(); self.project=project; self.results=[]
        layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        self.steps=QLabel(); self.steps.setObjectName("stepBar"); layout.addWidget(self.steps)
        self.stack=QStackedWidget(); layout.addWidget(self.stack,1)
        self.input=InputPage(project); self.results_page=ResultsPage(); self.detail_page=DetailPage()
        for page in (self.input,self.results_page,self.detail_page):self.stack.addWidget(page)
        self.input.next_button.clicked.connect(lambda:self.go(1)); self.results_page.back.clicked.connect(lambda:self.go(0)); self.results_page.detail.clicked.connect(lambda:self.go(2)); self.detail_page.back.clicked.connect(lambda:self.go(1)); self.detail_page.input.clicked.connect(lambda:self.go(0))
        self.input.changed.connect(self.changed); self.results_page.changed.connect(self.changed)
        self.go(0)

    def load_project(self,project):
        self.project=project; self.input.project=project; self.input.current_key=None; self.input.refresh_tabs(); self.go(0)

    def commit(self): self.input.save_current()

    def go(self,index):
        try:
            if self.stack.currentIndex()==0:self.commit()
            if index>=1:
                self.results=self.project.analyze_all(); self.results_page.refresh(self.project,self.results)
            if index==2:self.detail_page.refresh(self.project,self.results)
            if index==1:self.changed.emit()
        except (ValueError,TypeError) as exc:
            QMessageBox.warning(self,"입력 확인",str(exc));return
        self.stack.setCurrentIndex(index); labels=["○ 구간 입력","○ 분석 결과","○ 세부 계산결과"]; labels[index]=labels[index].replace("○","●"); self.steps.setText("     ".join(labels))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); load_font(); self.project=ArterialProject(); self.project.add_starter_rows(); self.path=None
        self.dirty=False; self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}"); self.resize(1280,820); self.setMinimumSize(900,650)
        icon=resource_path("assets/arterial-analysis-icon.ico")
        if Path(icon).exists():self.setWindowIcon(QIcon(icon))
        self.tabs=QTabWidget(); self.workflow=Workflow(self.project); self.tabs.addTab(self.workflow,"분석"); self.tabs.addTab(GuidelinePage(),"지침·공식"); self.setCentralWidget(self.tabs)
        self.workflow.changed.connect(self.mark_dirty)
        menu=self.menuBar().addMenu("프로젝트")
        for label,slot,shortcut in (("새 프로젝트",self.new,"Ctrl+N"),("열기",self.open,"Ctrl+O"),("저장",self.save,"Ctrl+S"),("다른 이름으로 저장",self.save_as,"Ctrl+Shift+S")):
            action=QAction(label,self);action.setShortcut(shortcut);action.triggered.connect(slot);menu.addAction(action)
        help_menu=self.menuBar().addMenu("도움말"); about=QAction("프로그램 정보",self); about.triggered.connect(self.show_about); help_menu.addAction(about)
        self.statusBar().showMessage(f"{APP_NAME} v{APP_VERSION}   ·   {APP_AUTHOR}   ·   {APP_EMAIL}")

    def show_about(self):
        QMessageBox.about(self,"프로그램 정보",f"<h2>{APP_NAME}</h2><p>v{APP_VERSION}</p><p>도로용량편람(2013) 기반</p><p>{APP_AUTHOR}<br>{APP_EMAIL}</p>")

    def new(self):
        if not self.confirm_discard():return
        project=ArterialProject();project.add_starter_rows();self.project=project;self.path=None;self.workflow.load_project(project)
        self.dirty=False; self.update_title()

    def open(self):
        if not self.confirm_discard():return
        path,_=QFileDialog.getOpenFileName(self,"프로젝트 열기","",PROJECT_FILTER)
        if not path:return
        try:self.project=ArterialProject.load(path);self.path=path;self.workflow.load_project(self.project);self.dirty=False;self.update_title()
        except Exception as exc:QMessageBox.critical(self,"열기 실패",str(exc))

    def save(self):
        if not self.path:return self.save_as()
        try:self.workflow.commit();self.project.save(self.path);self.dirty=False;self.update_title();self.statusBar().showMessage("프로젝트를 저장했습니다.",4000);return True
        except Exception as exc:QMessageBox.critical(self,"저장 실패",str(exc));return False

    def save_as(self):
        path,_=QFileDialog.getSaveFileName(self,"프로젝트 저장","도시교외간선도로분석.ara1",PROJECT_FILTER)
        if not path:return False
        if not path.lower().endswith(".ara1"):path+=".ara1"
        self.path=path;return self.save()

    def mark_dirty(self): self.dirty=True; self.update_title(); self.statusBar().showMessage("저장되지 않은 변경사항이 있습니다.")

    def update_title(self): self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}{' *' if self.dirty else ''}"+(f" - {Path(self.path).name}" if self.path else ""))

    def confirm_discard(self):
        if not self.dirty:return True
        box=QMessageBox(self); box.setIcon(QMessageBox.Question); box.setWindowTitle("저장 확인"); box.setText("분석 결과와 변경사항이 저장되지 않았습니다. 지금 저장하시겠습니까?"); box.setStandardButtons(QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel); box.setDefaultButton(QMessageBox.Save)
        box.button(QMessageBox.Save).setText("저장"); box.button(QMessageBox.Discard).setText("저장안함"); box.button(QMessageBox.Cancel).setText("취소"); answer=box.exec()
        if answer==QMessageBox.Save:return bool(self.save())
        return answer==QMessageBox.Discard

    def closeEvent(self,event):
        if self.confirm_discard():event.accept()
        else:event.ignore()


COMBO_ARROW=resource_path("assets/combo-chevron.svg").replace("\\","/")
STYLE="""
QWidget{font-family:"Noto Sans KR","Malgun Gothic";font-size:10pt;color:#172033} QMainWindow,QStackedWidget{background:#F5F7FA}
QDialog,QMessageBox,QFileDialog{background:#F5F7FA;color:#172033} QDialog QLabel,QMessageBox QLabel,QFileDialog QLabel{color:#172033;background:transparent} QTextEdit{background:white;color:#172033;border:1px solid #CBD6E4;border-radius:7px;padding:6px}
QMenuBar{background:white;color:#172033;padding:4px 8px} QMenuBar::item{background:transparent;color:#172033;padding:6px 10px} QMenuBar::item:selected{background:#EAF2FF;color:#1261C9;border-radius:5px} QMenu{background:white;color:#172033;border:1px solid #CBD6E4;padding:5px} QMenu::item{background:transparent;color:#172033;padding:7px 28px 7px 10px;border-radius:4px} QMenu::item:selected{background:#EAF2FF;color:#1261C9}
QTabWidget::pane{border:0} QTabBar{background:transparent;border:0} QTabBar::tear{width:0;height:0} QTabBar::tab{background:white;padding:10px 9px 10px 12px;color:#5E6A7D;border:1px solid #E2E8F0;border-bottom:0;border-top-left-radius:7px;border-top-right-radius:7px} QTabBar::tab:selected{color:#1261C9;font-weight:700;background:#EAF2FF;border-color:#8DB8F3} QToolButton#tabCloseButton{background:transparent;border:0;padding:0;margin:0 4px 0 1px;color:#64748B;font-size:12pt;font-weight:600} QToolButton#tabCloseButton:hover{color:#C62828;background:#FEECEC;border-radius:7px}
QFrame#card{background:white;border:1px solid #DCE3EC;border-radius:14px} QLabel#cardTitle{font-size:12pt;font-weight:700} QLabel#pageTitle{font-size:19pt;font-weight:800;padding:3px 0 5px} QLabel#infoBar{background:#FFF5D8;color:#8A5800;border-radius:9px;padding:9px 12px} QLabel#changeNotice{background:#FFE8D5;color:#9A3E00;border:1px solid #FFB779;border-radius:8px;padding:8px 11px} QLabel#copyNote{color:#536273;padding:4px}
QLabel#stepBar{background:white;color:#64748B;padding:13px 20px;border-bottom:1px solid #E2E8F0} QLabel#resultHero{background:#E7F0FF;border:1px solid #2375E8;border-radius:16px;color:#1261C9;font-size:13pt;font-weight:700;padding:16px 20px}
QLabel#saveNotice{background:#FFF7D6;color:#8A5800;border:1px solid #F2D681;border-radius:8px;padding:7px 11px}
QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox{background:white;color:#172033;border:1px solid #CBD6E4;border-radius:7px;padding:6px 30px 6px 8px;min-height:20px} QLineEdit{padding-right:8px} QSpinBox,QDoubleSpinBox{padding-right:8px} QComboBox::drop-down{subcontrol-origin:padding;subcontrol-position:top right;width:28px;border-left:1px solid #D8E0E9;border-top-right-radius:7px;border-bottom-right-radius:7px;background:#F7FAFC} QComboBox::drop-down:hover{background:#EAF2FF} QComboBox::down-arrow{image:url("__COMBO_ARROW__");width:12px;height:8px} QComboBox QAbstractItemView{background:white;color:#172033;border:1px solid #9FB2C8;selection-background-color:#DCEBFF;selection-color:#1261C9;outline:0;padding:3px} QSpinBox::up-button,QSpinBox::down-button,QDoubleSpinBox::up-button,QDoubleSpinBox::down-button{width:0;height:0;border:0}
QPushButton{background:white;border:1px solid #CBD6E4;border-radius:8px;padding:8px 12px;font-weight:600} QPushButton:hover{background:#EFF5FF;border-color:#8DB8F3} QPushButton#primaryButton{background:#2375E8;color:white;border-color:#2375E8;padding:9px 18px}
QPushButton#detailButton{background:#2375E8;color:white;border-color:#2375E8;padding:5px 8px} QPushButton#reviewButton{background:#FFF4DD;color:#9A4D00;border-color:#F2B96D;padding:4px 7px}
QTableWidget{background:white;alternate-background-color:#F7F9FC;border:0;gridline-color:#D8E0E9;selection-background-color:#DCEBFF;selection-color:#172033} QHeaderView::section{background:#E9EEF4;color:#29384D;border:0;border-right:1px solid #CBD4DF;border-bottom:1px solid #B8C4D2;padding:7px 5px;font-weight:700;text-align:center}
QScrollBar:horizontal{background:#EEF2F6;height:14px;margin:0;border:0;border-radius:7px} QScrollBar::handle:horizontal{background:#9EACBC;min-width:48px;border-radius:7px;margin:2px} QScrollBar::handle:horizontal:hover{background:#6F8298} QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{width:0;border:0;background:transparent} QScrollBar::add-page:horizontal,QScrollBar::sub-page:horizontal{background:transparent}
QScrollBar:vertical{background:#EEF2F6;width:13px;margin:0;border:0;border-radius:6px} QScrollBar::handle:vertical{background:#9EACBC;min-height:38px;border-radius:6px;margin:2px} QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;border:0;background:transparent} QStatusBar{background:white;color:#536273}
""".replace("__COMBO_ARROW__",COMBO_ARROW)


def apply_light_palette(app: QApplication) -> None:
    palette=QPalette()
    for role,color in ((QPalette.Window,"#F5F7FA"),(QPalette.WindowText,"#172033"),(QPalette.Base,"#FFFFFF"),(QPalette.AlternateBase,"#F7F9FC"),(QPalette.Text,"#172033"),(QPalette.Button,"#FFFFFF"),(QPalette.ButtonText,"#172033"),(QPalette.Highlight,"#DCEBFF"),(QPalette.HighlightedText,"#1261C9"),(QPalette.ToolTipBase,"#FFFFFF"),(QPalette.ToolTipText,"#172033")):
        palette.setColor(role,QColor(color))
    palette.setColor(QPalette.Disabled,QPalette.Text,QColor("#7B8796")); palette.setColor(QPalette.Disabled,QPalette.ButtonText,QColor("#7B8796"))
    app.setPalette(palette)


def main():
    QApplication.setAttribute(Qt.AA_DontUseNativeDialogs,True)
    app=QApplication(sys.argv);app.setStyle("Fusion");apply_light_palette(app);load_font();app.setApplicationName(APP_NAME);app.setApplicationVersion(APP_VERSION);app.setStyleSheet(STYLE);window=MainWindow();window.show();return app.exec()
