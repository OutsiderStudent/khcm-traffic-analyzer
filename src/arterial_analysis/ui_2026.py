"""Project-scoped 2026 corridor editor and traceable results."""
import html
import re
from dataclasses import dataclass
from PySide6.QtCore import Signal, Qt, QMimeData
from PySide6.QtGui import QKeySequence, QShortcut
from pathlib import Path
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QComboBox, QCheckBox, QFileDialog, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QTableWidget,
    QHeaderView, QGridLayout, QTextBrowser, QTabWidget, QApplication, QMessageBox, QInputDialog, QAbstractItemView)
from .engine import ROAD_CATEGORIES
from .engine_2026 import Corridor2026, Subsegment2026, END_TYPES, analyze_corridor, official_example
from .network_2026 import add_node, connect_nodes, insert_node


@dataclass
class DiagramLink:
    uid: str
    start_name: str
    start_number: str
    start_key: tuple[str, str]
    end_name: str
    end_number: str
    end_key: tuple[str, str]
    road_name: str
    road_category: str
    metric_text: str = ""
    direction: str = "→"


def corridor_links(corridor):
    category = ROAD_CATEGORIES[2 if corridor.road_category == "내부도로" else 0]
    start = (corridor.start_name.strip(), corridor.start_id.strip())
    start_key = (f"{END_TYPES[0]} ID", start[1]) if start[1] else ("시점", "0")
    for row, segment in enumerate(corridor.subsegments):
        end = (segment.end_name.strip(), segment.end_id.strip() if segment.end_type != END_TYPES[2] else "")
        end_key = (f"{segment.end_type} ID", end[1]) if end[1] else ("소구간 종점", str(row))
        if any(start) and any(end):
            label = f"소구간 {row + 1}"
            length = float(segment.length_m or 0)
            if length > 0:
                label += f" · {length:,.0f} m"
            metrics = []
            if corridor.method == "delay" and segment.end_type != END_TYPES[2]:
                delay = segment.delay_s
                metrics.append("지체 미입력" if delay is None else f"지체 {delay:g}초")
            if segment.end_type == END_TYPES[0] and segment.capacity_vph is not None:
                metrics.append(f"용량 {segment.capacity_vph:,.1f}대/시")
            yield DiagramLink(str(row), *start, start_key, *end, end_key, label, category, " · ".join(metrics))
        start, start_key = end, end_key


class CorridorPage(QWidget):
    changed = Signal()

    def __init__(self, project, diagram_factory):
        super().__init__()
        self.project = project
        self.loading = False
        self.diagram_factory = diagram_factory
        self.diagram_dialog = None
        self.road_dialog = None
        self.connecting = False
        self.connection_start = None
        self.selected_node = None
        root = QVBoxLayout(self)
        title = QLabel("도시부 간선도로")
        title.setObjectName("cardTitle")
        root.addWidget(title)
        bar = QHBoxLayout()
        self.selector = QComboBox(); self.selector.setMinimumWidth(230)
        bar.addWidget(self.selector, 1)
        root.addLayout(bar)
        toolbar=QGridLayout()
        tool_index=0
        for label, callback in (("구간 추가", self.add_corridor), ("대안 복사", self.copy_corridor), ("반대 방향 복사", self.reverse_corridor), ("구간 삭제", self.remove_corridor),
                                ("편람 예제", self.add_examples), ("2013 자료 가져오기", self.import_legacy)):
            button = QPushButton(label); button.clicked.connect(callback); toolbar.addWidget(button,tool_index//3,tool_index%3);tool_index+=1
        root.addLayout(toolbar)
        self.tabs = QTabWidget(); self.tabs.setObjectName("connectedTabs")
        root.addWidget(self.tabs, 1)
        editor = QWidget(); layout = QVBoxLayout(editor)
        self.tabs.addTab(editor, "1. 구간 설정")
        form = QGridLayout(); form.setHorizontalSpacing(16)
        self.name = QLineEdit(); self.start = QLineEdit()
        self.start_id = QLineEdit()
        self.start_id.setPlaceholderText("선택 입력")
        self.scenario = QComboBox(); self.scenario.addItems(["현황", "사업 미시행시", "사업 시행시", "개선대책 이행시"])
        self.year = QSpinBox(); self.year.setRange(1900, 2200)
        self.category = QComboBox(); self.category.addItems(["외부도로", "내부도로"])
        self.lanes = QSpinBox(); self.lanes.setRange(0, 20);self.lanes.setSpecialValueText("미입력")
        self.method = QComboBox(); self.method.addItems(["직진이동류 평균접근지체", "차량별 구간통행시간", "차량별 구간통행속도"])
        self.times = QLineEdit(); self.times.setPlaceholderText("차량별 통행시간(초), 예: 398, 396, 379")
        self.speeds=QLineEdit();self.speeds.setPlaceholderText("차량별 구간통행속도(km/h), 예: 20, 30, 25")
        self.source=QLineEdit();self.source.setPlaceholderText("조사명 또는 교차로 분석자료명")
        self.survey_date=QLineEdit();self.survey_date.setPlaceholderText("조사 일시·분석 시간대")
        fields = (("분석구간명",self.name),("시점",self.start),("분석 상황",self.scenario),
                              ("연도",self.year),("도로 구분",self.category),("최소 기본 차로수(편도)",self.lanes),
                              ("자료 출처",self.source),("조사·분석 일시",self.survey_date))
        for i,(label,widget) in enumerate(fields):
            form.addWidget(QLabel(label),i//2,(i%2)*2);form.addWidget(widget,i//2,(i%2)*2+1)
        form.addWidget(QLabel("시점 교차로 ID"),4,0);form.addWidget(self.start_id,4,1)
        form.setColumnStretch(1,1);form.setColumnStretch(3,1)
        layout.addLayout(form)
        self.urban=QCheckBox("도시부 또는 도시부로 진·출입하는 도로")
        self.signals=QCheckBox("분석구간의 평면교차로·횡단보도는 신호로 운영")
        self.boundaries=QCheckBox("구간 경계 밖 교차로의 영향을 피하도록 경계를 정하고, 시·종점을 통과하는 직진 이동류를 분석")
        for checkbox in (self.urban,self.signals,self.boundaries):layout.addWidget(checkbox);checkbox.toggled.connect(self.commit)
        scope_note=QLabel("편람 적용 조건: 길이 1.5km 이상 · 신호 3개 이상 · 평균 신호 간격 3km 이하 · 편도 기본·직진 차로수 2개 이상")
        scope_note.setWordWrap(True);layout.addWidget(scope_note);layout.addStretch()
        next_button=QPushButton("자료 입력");next_button.clicked.connect(lambda:self.tabs.setCurrentIndex(1));layout.addWidget(next_button)
        create_network=QPushButton("관계도 (F6)")
        create_network.clicked.connect(self.show_diagram);layout.addWidget(create_network)
        data_page=QWidget();layout=QVBoxLayout(data_page);self.tabs.addTab(data_page,"2. 소구간·조사자료")
        self.method_form = QFormLayout()
        self.method_form.addRow("속도 산정 방법", self.method)
        self.method_form.addRow("차량별 통행시간(초)", self.times)
        self.method_form.addRow("차량별 통행속도(km/h)", self.speeds)
        layout.addLayout(self.method_form)
        self.method_note = QLabel()
        self.method_note.setWordWrap(True)
        layout.addWidget(self.method_note)
        self.table = QTableWidget(0,9)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setHorizontalHeaderLabels(["종점", "길이\n(m)", "제한속도\n(km/h)", "종점 유형", "직진 가능\n차로수", "평균접근지체\n(초)", "직진 용량\n(대/시, 선택)", "종점 ID\n(선택)", "접근 방향 코드\n(선택)"])
        self.table.horizontalHeader().setMinimumSectionSize(145)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3,QHeaderView.Fixed);self.table.setColumnWidth(3,195)
        self.table.horizontalHeader().setMinimumHeight(48)
        self.table.verticalHeader().setDefaultSectionSize(36)
        layout.addWidget(self.table,1)
        actions = QHBoxLayout()
        back = QPushButton("이전")
        back.setObjectName("backButton")
        back.setToolTip("구간 설정으로 이동")
        back.clicked.connect(lambda: self.tabs.setCurrentIndex(0))
        actions.addWidget(back)
        for label, callback in (("소구간 추가",self.add_row),("소구간 삭제",self.remove_row),("위로",lambda:self.move_row(-1)),("아래로",lambda:self.move_row(1)),("분석",self.analyze)):
            button=QPushButton(label); button.clicked.connect(callback); actions.addWidget(button)
            if label=="분석":button.setObjectName("primaryButton")
        diagram_button = QPushButton("관계도 (F6)")
        diagram_button.clicked.connect(self.show_diagram)
        actions.addWidget(diagram_button)
        actions.addStretch(); layout.addLayout(actions)
        self.diagram_shortcut = QShortcut(QKeySequence("F6"), self)
        self.diagram_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.diagram_shortcut.activated.connect(self.show_diagram)
        self.changed.connect(self.refresh_diagram)
        self.table.currentCellChanged.connect(lambda *_: self.refresh_diagram())
        result_page=QWidget(); result_layout=QVBoxLayout(result_page)
        self.result=QTextBrowser();self.result.setOpenLinks(False);self.result.anchorClicked.connect(self.focus_missing); result_layout.addWidget(self.result)
        copy=QPushButton("계산 결과 복사"); copy.clicked.connect(self.copy_result)
        result_actions = QHBoxLayout()
        back_to_data = QPushButton("이전")
        back_to_data.setObjectName("backButton")
        back_to_data.setToolTip("소구간·조사자료로 이동")
        back_to_data.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        result_actions.addWidget(back_to_data)
        result_actions.addWidget(copy);export=QPushButton("결과 저장");export.clicked.connect(self.export_result);result_actions.addWidget(export);result_actions.addStretch();result_layout.addLayout(result_actions); self.tabs.addTab(result_page,"3. 분석 결과")
        self.selector.currentIndexChanged.connect(self.load_corridor)
        for w in (self.name,self.start,self.start_id,self.times,self.speeds,self.source,self.survey_date):w.textEdited.connect(self.commit)
        for w in (self.scenario,self.category,self.method):w.currentIndexChanged.connect(self.commit)
        for w in (self.year,self.lanes):w.valueChanged.connect(self.commit)
        guide=QTextBrowser();guide.setHtml(GUIDE_2026);self.tabs.addTab(guide,"지침·계산식")
        self.load_project(project)

    def load_project(self, project):
        self.project=project; self.loading=True; self.selector.clear()
        for c in project.corridors_2026:self.selector.addItem(c.get("name", "분석구간"))
        self.loading=False; self.load_corridor(self.selector.currentIndex())

    def current(self):
        i=self.selector.currentIndex()
        return Corridor2026.from_dict(self.project.corridors_2026[i]) if i>=0 else None

    def load_corridor(self,index):
        if self.loading:return
        self.cancel_connection()
        self.loading=True
        c=self.current() or Corridor2026()
        self.start_id.setText(c.start_id)
        for w,value in ((self.name,c.name),(self.start,c.start_name),(self.times,", ".join(map(str,c.travel_times_s)))):w.setText(value)
        self.scenario.setCurrentText(c.scenario);self.year.setValue(c.year);self.category.setCurrentText(c.road_category)
        self.lanes.setValue(c.lanes);self.method.setCurrentIndex({"delay":0,"survey":1,"speeds":2}.get(c.method,0))
        self.speeds.setText(", ".join(map(str,c.travel_speeds_kmh)));self.source.setText(c.data_source);self.survey_date.setText(c.survey_date)
        self.urban.setChecked(c.urban_road_confirmed);self.signals.setChecked(c.signal_control_confirmed);self.boundaries.setChecked(c.boundaries_confirmed)
        self.table.setRowCount(0)
        for s in c.subsegments:self.append_row(s)
        for tab in range(3):self.tabs.setTabEnabled(tab,index>=0)
        self.update_method_fields(c.method)
        self.result.setPlainText("자료를 입력한 뒤 분석을 눌러 주세요.")
        self.loading=False
        self.refresh_diagram()
        if self.road_dialog and self.road_dialog.isVisible() and not getattr(self.road_dialog,'saving',False):self.road_dialog.load()

    def update_method_fields(self, method):
        self.method_form.setRowVisible(self.times, method == "survey")
        self.method_form.setRowVisible(self.speeds, method == "speeds")
        self.table.setColumnHidden(5, method != "delay")
        note = "진행 방향 순서대로 소구간을 입력하세요."
        if method == "delay":
            note += " 시점 신호는 제외하고 종점 신호는 포함하세요.\n해당 방향의 직진이동류 평균접근지체를 입력하세요."
        self.method_note.setText(note)
        for row in range(self.table.rowCount()):
            end_type = self.table.cellWidget(row, 3).currentText()
            self.table.cellWidget(row, 5).setEnabled(method == "delay" and end_type != END_TYPES[2])
            for column in (4, 6):
                self.table.cellWidget(row, column).setEnabled(end_type == END_TYPES[0])

    def append_row(self,s):
        row=self.table.rowCount();self.table.insertRow(row)
        name=QLineEdit(s.end_name)
        length=QDoubleSpinBox();length.setRange(0,100000);length.setDecimals(2);length.setValue(s.length_m)
        speed=QDoubleSpinBox();speed.setRange(0,200);speed.setValue(s.speed_limit_kmh)
        kind=QComboBox();kind.addItems(END_TYPES);kind.setCurrentText(s.end_type)
        lanes=QSpinBox();lanes.setRange(0,20);lanes.setSpecialValueText("미입력");lanes.setValue(s.through_lanes)
        delay=QDoubleSpinBox();delay.setRange(-1,100000);delay.setDecimals(2);delay.setSpecialValueText("미입력");delay.setValue(-1 if s.delay_s is None else s.delay_s)
        capacity=QDoubleSpinBox();capacity.setRange(-1,100000);capacity.setDecimals(1);capacity.setSpecialValueText("미입력");capacity.setValue(-1 if s.capacity_vph is None else s.capacity_vph)
        length.setSpecialValueText("미입력");speed.setSpecialValueText("미입력")
        end_id = QLineEdit(s.end_id)
        approach_id = QLineEdit(s.approach_id)
        end_id.setToolTip("교차로 분석 자료에서 사용하는 종점 ID")
        approach_id.setToolTip("종점에 들어오는 방향의 코드. 교차로 분석 자료와 같은 코드를 사용하세요.")
        for col,w in enumerate((name,length,speed,kind,lanes,delay,capacity,end_id,approach_id)):
            self.table.setCellWidget(row,col,w)
            if isinstance(w,QLineEdit):w.textEdited.connect(self.commit)
            elif isinstance(w,QComboBox):w.currentIndexChanged.connect(self.commit)
            else:w.valueChanged.connect(self.commit)

    def commit(self,*args):
        if self.loading or self.selector.currentIndex()<0:return
        c=Corridor2026(name=self.name.text(),start_name=self.start.text(),scenario=self.scenario.currentText(),
            year=self.year.value(),road_category=self.category.currentText(),lanes=self.lanes.value(),
            method=("delay","survey","speeds")[self.method.currentIndex()],
            urban_road_confirmed=self.urban.isChecked(),signal_control_confirmed=self.signals.isChecked(),boundaries_confirmed=self.boundaries.isChecked(),data_source=self.source.text(),survey_date=self.survey_date.text())
        c.start_id = self.start_id.text().strip()
        old = self.current()
        c.diagram_nodes = old.diagram_nodes
        # Preserve partially typed survey input in the project; validate on analysis.
        raw=self.times.text()
        c.travel_times_s=[t for t in re.split(r"[,;\s]+",raw.strip()) if t]
        c.travel_speeds_kmh=[t for t in re.split(r"[,;\s]+",self.speeds.text().strip()) if t]
        for row in range(self.table.rowCount()):
            n,l,s,k,la,d,cap,end_id,approach_id=[self.table.cellWidget(row,col) for col in range(9)]
            c.subsegments.append(Subsegment2026(n.text(),l.value(),s.value(),k.currentText(),la.value(),None if d.value()<0 else d.value(),None if cap.value()<0 else cap.value(),end_id.text().strip(),approach_id.text().strip()))
        net=next((n for n in self.project.networks_2026 if n['id']==old.network_id),None)
        if (c.start_id,[(s.end_id,s.length_m,s.speed_limit_kmh) for s in c.subsegments]) != (old.start_id,[(s.end_id,s.length_m,s.speed_limit_kmh) for s in old.subsegments]):
            c.travel_times_s=[];c.travel_speeds_kmh=[];c.boundaries_confirmed=False
        if net and any(n['id']==c.start_id for n in net['nodes']) and all(any(e['id']==p['edge'] for e in net['edges']) for p in old.network_path) and (c.scenario,c.year,c.road_category)==(old.scenario,old.year,old.road_category) and c.start_id==old.start_id and [s.end_id for s in c.subsegments]==[s.end_id for s in old.subsegments]:
            from .road_network import synchronize, node_by_id
            c.network_id=old.network_id;c.network_path=old.network_path
            node_by_id(net,c.start_id)['name']=c.start_name
            for s,p in zip(c.subsegments,c.network_path):
                edge=next(e for e in net['edges'] if e['id']==p['edge'])
                edge.update(length=s.length_m,speed=s.speed_limit_kmh)
                node_by_id(net,s.end_id)['name']=s.end_name
                edge['ba' if p['reverse'] else 'ab'].update(lanes=s.through_lanes,delay=s.delay_s,capacity=s.capacity_vph,approach=s.approach_id)
        self.project.corridors_2026[self.selector.currentIndex()]=c.to_dict()
        if c.network_id:
            synchronize(self.project,net)
        if c.travel_times_s!=[t for t in re.split(r"[,;\s]+",self.times.text().strip()) if t]:self.times.setText(', '.join(map(str,c.travel_times_s)))
        if c.travel_speeds_kmh!=[t for t in re.split(r"[,;\s]+",self.speeds.text().strip()) if t]:self.speeds.setText(', '.join(map(str,c.travel_speeds_kmh)))
        self.selector.setItemText(self.selector.currentIndex(),c.name)
        self.update_method_fields(c.method)
        self.result.setPlainText("입력이 바뀌었습니다. 다시 분석해 주세요.")
        self.changed.emit()

    def show_diagram(self):
        from .network_editor import RoadNetworkDialog
        if self.current() is None:self.add_corridor()
        if self.road_dialog is None:self.road_dialog=RoadNetworkDialog(self)
        self.road_dialog.load();self.road_dialog.show();self.road_dialog.raise_();self.road_dialog.activateWindow()

    def show_legacy_diagram(self):
        if self.current() is None:
            return
        if self.diagram_dialog is None:
            self.diagram_dialog = self.diagram_factory(self.window())
            self.diagram_dialog.zoom_out.setText("-")
            self.diagram_dialog.diagram.edgeSelected.connect(self.select_diagram_row)
            self.diagram_dialog.diagram.editing_enabled = True
            self.diagram_dialog.diagram.nodeSelected.connect(self.diagram_node_clicked)
            self.diagram_dialog.diagram.empty_text = "교차로 추가를 눌러 관계도를 만드세요."
            controls = QHBoxLayout()
            for text, action in (("교차로 추가", self.add_diagram_node), ("연결", self.begin_connection),
                                 ("구간에 삽입", self.insert_diagram_node), ("연결 전 교차로 삭제", self.delete_diagram_node)):
                button = QPushButton(text); button.clicked.connect(action); controls.addWidget(button)
            self.diagram_dialog.layout().insertLayout(1, controls)
            self.diagram_status = QLabel("연결: 시작 원 → 종점 원 순서로 클릭하세요. Ctrl+클릭으로도 시작할 수 있습니다. Esc: 연결 취소")
            self.diagram_status.setWordWrap(True)
            self.diagram_dialog.layout().insertWidget(2, self.diagram_status)
            self.diagram_escape = QShortcut(QKeySequence("Escape"), self.diagram_dialog)
            self.diagram_escape.activated.connect(self.cancel_connection)
            self.diagram_undo = QShortcut(QKeySequence("Ctrl+Z"), self.diagram_dialog)
            self.diagram_undo.activated.connect(self.window().undo_project)
            self.diagram_redo = QShortcut(QKeySequence("Ctrl+Y"), self.diagram_dialog)
            self.diagram_redo.activated.connect(self.window().redo_project)
        self.diagram_dialog.show()
        self.refresh_diagram()
        self.diagram_dialog.raise_()
        self.diagram_dialog.activateWindow()

    def refresh_diagram(self):
        if self.loading or self.diagram_dialog is None or not self.diagram_dialog.isVisible():
            return
        corridor = self.current()
        if corridor is None:
            self.diagram_dialog.hide()
            return
        title = f"{corridor.name} · {corridor.scenario}({corridor.year})"
        links = list(corridor_links(corridor))
        # Self-links contribute isolated nodes without creating road edges.
        from .network_2026 import route_nodes
        for key, name, number in route_nodes(corridor):
            links.append(DiagramLink("",name,number,key,name,number,key,"",ROAD_CATEGORIES[0]))
        for node in corridor.diagram_nodes:
            key = ('신호교차로 ID', node['id'])
            links.append(DiagramLink("",node['name'],"",key,node['name'],"",key,"",ROAD_CATEGORIES[0]))
        self.diagram_dialog.diagram.set_segments(links, title, str(self.table.currentRow()))
        for index, node in enumerate(self.diagram_dialog.diagram.nodes.values(), 1):
            if re.fullmatch(r"[0-9a-f]{32}", node['key'][1]): node['number'] = str(index)

    def save_diagram_change(self, corridor):
        index = self.selector.currentIndex()
        self.project.corridors_2026[index] = corridor.to_dict()
        self.load_corridor(index)
        self.changed.emit()

    def add_diagram_node(self):
        name, accepted = QInputDialog.getText(self.diagram_dialog, "교차로 추가", "교차로명")
        if not accepted or not name.strip(): return
        c = self.current()
        self.selected_node = add_node(c, name)
        self.cancel_connection()
        self.save_diagram_change(c)
        self.diagram_status.setText(f"{name.strip()} 추가됨 · 연결을 누르거나 Ctrl+클릭으로 연결하세요.")

    def cancel_connection(self):
        self.connecting = False
        self.connection_start = None
        if self.diagram_dialog:
            self.diagram_dialog.diagram.connection_source = None
            self.diagram_dialog.diagram.connection_cursor = None
            self.diagram_dialog.diagram.update()

    def begin_connection(self):
        self.cancel_connection()
        self.connecting = True
        self.diagram_status.setText("시작 교차로를 클릭한 다음 종점 교차로를 클릭하세요. 현재 분석구간의 끝에서 연장합니다.")

    def diagram_node_clicked(self, key, control):
        self.selected_node = key
        self.diagram_dialog.diagram.selected_node_key = key
        self.diagram_dialog.diagram.update()
        if control and not self.connecting: self.begin_connection()
        if not self.connecting:
            self.diagram_status.setText("교차로 선택됨 · 구간에 삽입하려면 연결선을 선택한 뒤 ‘구간에 삽입’을 누르세요.")
            return
        if self.connection_start is None:
            self.connection_start = key
            self.diagram_dialog.diagram.connection_source = key
            self.diagram_status.setText("종점 교차로를 클릭하세요. Esc: 연결 취소")
            return
        start = self.connection_start
        self.cancel_connection()
        c = self.current()
        # Validate topology before asking for road data.
        try:
            probe = Corridor2026.from_dict(c.to_dict())
            connect_nodes(probe, start, key, 1, 1)
        except ValueError as error:
            self.diagram_status.setText(str(error)); return
        length, ok = QInputDialog.getDouble(self.diagram_dialog, "구간 연결", "구간길이(m)", 0, 0, 100000, 2)
        if not ok: return
        speed, ok = QInputDialog.getDouble(self.diagram_dialog, "구간 연결", "제한속도(km/h)", 0, 0, 200, 0)
        if not ok: return
        try: connect_nodes(c, start, key, length, speed)
        except ValueError as error:
            self.diagram_status.setText(str(error)); return
        self.save_diagram_change(c)
        self.diagram_status.setText("소구간이 추가되었습니다. 차로수·직진 지체를 입력하고 구간 경계를 확인하세요. 기존 구간 조사값은 초기화되었습니다.")

    def insert_diagram_node(self):
        c = self.current(); row = self.table.currentRow()
        if not any(('신호교차로 ID', n['id']) == self.selected_node for n in c.diagram_nodes) or not 0 <= row < len(c.subsegments):
            self.diagram_status.setText("연결 전 교차로 원과 삽입할 연결선을 차례로 선택하세요."); return
        first, ok = QInputDialog.getDouble(self.diagram_dialog, "교차로 삽입", "시점 → 새 교차로 길이(m)", 0, 0, 100000, 2)
        if not ok: return
        second, ok = QInputDialog.getDouble(self.diagram_dialog, "교차로 삽입", "새 교차로 → 기존 종점 길이(m)", 0, 0, 100000, 2)
        if not ok: return
        try: insert_node(c, self.selected_node, row, first, second)
        except ValueError as error:
            self.diagram_status.setText(str(error)); return
        self.cancel_connection(); self.save_diagram_change(c)
        self.diagram_status.setText("교차로를 삽입했습니다. 새 교차로의 차로수·직진 지체와 제한속도를 확인하세요. 기존 구간 조사값은 초기화되었습니다.")

    def delete_diagram_node(self):
        c = self.current()
        nodes = [n for n in c.diagram_nodes if ('신호교차로 ID', n['id']) != self.selected_node]
        if len(nodes) == len(c.diagram_nodes):
            self.diagram_status.setText("연결 전 교차로를 선택하세요. 연결된 소구간은 입력표에서 삭제할 수 있습니다."); return
        c.diagram_nodes = nodes
        self.cancel_connection(); self.save_diagram_change(c)

    def select_diagram_row(self, uids):
        rows = sorted(int(uid) for uid in uids)
        if not rows:
            return
        current = self.table.currentRow()
        row = next((row for row in rows if row > current), rows[0])
        if 0 <= row < self.table.rowCount():
            self.tabs.setCurrentIndex(1)
            self.table.selectRow(row)
            self.table.scrollTo(self.table.model().index(row, 0), QAbstractItemView.PositionAtCenter)

    def add_corridor(self):
        self.project.corridors_2026.append(Corridor2026(year=self.project.current_year).to_dict())
        self.load_project(self.project);self.selector.setCurrentIndex(self.selector.count()-1);self.tabs.setCurrentIndex(0);self.changed.emit()

    def copy_corridor(self):
        corridor = self.current()
        if corridor is None:
            return
        scenarios = [self.scenario.itemText(i) for i in range(self.scenario.count())]
        scenario, accepted = QInputDialog.getItem(self, "대안 복사", "분석 상황", scenarios, self.scenario.currentIndex(), False)
        if not accepted:
            return
        year, accepted = QInputDialog.getInt(self, "대안 복사", "분석 연도", corridor.year, 1900, 2200)
        if not accepted:
            return
        corridor.scenario = scenario
        corridor.network_id = "";corridor.network_path = []
        corridor.year = year
        corridor.name = f"{corridor.name} ({scenario} {year})"
        corridor.method = "delay"
        corridor.data_source = corridor.survey_date = ""
        corridor.travel_times_s.clear()
        corridor.travel_speeds_kmh.clear()
        for segment in corridor.subsegments:
            segment.delay_s = segment.capacity_vph = None
        self.project.corridors_2026.append(corridor.to_dict())
        self.load_project(self.project)
        self.selector.setCurrentIndex(self.selector.count()-1)
        self.tabs.setCurrentIndex(0)
        self.changed.emit()

    def reverse_corridor(self):
        c=self.current()
        if c is None or not c.subsegments:return
        old=c.subsegments
        names=[c.start_name]+[s.end_name for s in old];ids=[c.start_id]+[s.end_id for s in old]
        c.start_name=names[-1];c.start_id=ids[-1];c.name+=' (반대 방향)'
        c.subsegments=[Subsegment2026(end_name=names[i],end_id=ids[i],length_m=old[i].length_m,speed_limit_kmh=old[i].speed_limit_kmh,end_type=END_TYPES[0] if i==0 else old[i-1].end_type) for i in range(len(old)-1,-1,-1)]
        c.network_id='';c.network_path=[];c.method='delay';c.travel_times_s=[];c.travel_speeds_kmh=[]
        c.boundaries_confirmed=False;c.data_source='';c.survey_date=''
        self.project.corridors_2026.append(c.to_dict());self.load_project(self.project);self.selector.setCurrentIndex(self.selector.count()-1);self.changed.emit()

    def remove_corridor(self):
        i=self.selector.currentIndex()
        if i<0:return
        if QMessageBox.question(self,"구간 삭제","선택한 분석구간을 삭제하시겠습니까?")!=QMessageBox.Yes:return
        del self.project.corridors_2026[i];self.load_project(self.project);self.changed.emit()

    def add_row(self):
        self.loading=True;self.append_row(Subsegment2026());self.loading=False;self.commit()

    def remove_row(self):
        row=self.table.currentRow()
        if row>=0:self.table.removeRow(row);self.commit()

    def move_row(self, delta):
        row=self.table.currentRow();target=row+delta
        if row<0 or not 0<=target<self.table.rowCount():return
        self.commit();c=self.current();c.subsegments[row],c.subsegments[target]=c.subsegments[target],c.subsegments[row]
        c.network_id='';c.network_path=[];c.boundaries_confirmed=False;c.travel_times_s=[];c.travel_speeds_kmh=[]
        self.project.corridors_2026[self.selector.currentIndex()]=c.to_dict()
        self.load_corridor(self.selector.currentIndex());self.table.selectRow(target);self.changed.emit()

    def copy_result(self):
        mime=QMimeData();mime.setText(self.result.toPlainText());mime.setHtml(self.result.toHtml());QApplication.clipboard().setMimeData(mime)

    def export_result(self):
        if not self.analyze():return
        path,_=QFileDialog.getSaveFileName(self,"분석 결과 저장","2026_간선도로_분석결과.html","HTML 문서 (*.html)")
        if not path:return
        try:Path(path if path.lower().endswith(".html") else path+".html").write_text(self.result.toHtml(),encoding="utf-8")
        except OSError as exc:QMessageBox.warning(self,"저장 실패",str(exc))

    def add_examples(self):
        self.project.corridors_2026.extend(official_example(i).to_dict() for i in (1,2,3))
        self.load_project(self.project);self.selector.setCurrentIndex(self.selector.count()-3);self.tabs.setCurrentIndex(0);self.changed.emit()

    def import_legacy(self):
        groups={}
        for s in self.project.segments:
            key=f"{s.scenario}({s.year}) · {s.road_category} · {s.road_name} {s.direction}"
            groups.setdefault(key,[]).append(s)
        if not groups:
            QMessageBox.information(self,"입력 가져오기","이 프로젝트에 2013 입력자료가 없습니다.");return
        key,ok=QInputDialog.getItem(self,"2013 입력 가져오기","가로와 진행방향",list(groups),0,False)
        if not ok:return
        rows=groups[key]
        def endpoints(s):
            a=(s.start_number,s.start_name);b=(s.end_number,s.end_name)
            return (a,b) if s.direction=="→" else (b,a)
        # Require a single connected directed chain, not arbitrary table order.
        starts=[s for s in rows if endpoints(s)[0] not in {endpoints(t)[1] for t in rows}]
        ordered=[]
        if len(starts)==1:
            ordered=[starts[0]]
            while len(ordered)<len(rows):
                nxt=[s for s in rows if s not in ordered and endpoints(s)[0]==endpoints(ordered[-1])[1]]
                if len(nxt)!=1:break
                ordered.append(nxt[0])
        if len(ordered)!=len(rows):
            QMessageBox.information(self,"구간 확인","연속된 한 방향 구간으로 연결되지 않습니다. 2026 입력에서 분석구간을 직접 구성하세요.");return
        first=ordered[0]
        c=Corridor2026(name=first.road_name,scenario=first.scenario,year=first.year,
            road_category="내부도로" if first.road_category=="사업지 내부도로" else "외부도로",
            start_name=endpoints(first)[0][1],start_id=endpoints(first)[0][0],lanes=min(s.lanes for s in rows),
            subsegments=[Subsegment2026(endpoints(s)[1][1],s.length_km*1000,s.speed_limit_kmh or 0,END_TYPES[0],s.lanes,end_id=endpoints(s)[1][0]) for s in ordered])
        self.project.corridors_2026.append(c.to_dict());self.load_project(self.project)
        self.selector.setCurrentIndex(self.selector.count()-1);self.changed.emit()
        QMessageBox.information(self,"입력 가져오기","길이·제한속도·차로수를 가져왔습니다. 종점 유형과 직진 가능 차로수를 확인하고, 접근지체 또는 조사 통행시간을 입력하세요.")

    def analyze(self):
        self.commit();c=self.current()
        if c is None:return
        try:r=analyze_corridor(c)
        except (ValueError,TypeError) as exc:
            issues=[]
            for i,s in enumerate(c.subsegments):
                for col,bad,label in [(0,not s.end_name.strip(),'종점'),(1,s.length_m<=0,'구간길이'),(2,s.speed_limit_kmh<=0,'제한속도'),(4,s.end_type==END_TYPES[0] and s.through_lanes<2,'직진 가능 차로수'),(5,c.method=='delay' and s.end_type!=END_TYPES[2] and s.delay_s is None,'평균접근지체')]:
                    if bad:issues.append(f'<li><a href="input:{i}:{col}">소구간 {i+1} · {label}</a></li>')
            self.result.setHtml(f'<h3>분석할 수 없습니다.</h3><p>{html.escape(str(exc))}</p><p><a href="settings:">구간 설정 확인</a></p><ul>{"".join(issues)}</ul>');self.tabs.setCurrentIndex(2);return False
        esc=html.escape
        method_text={"survey":"차량별 통행시간 평균 (식 12-2)","speeds":"차량별 통행속도의 조화평균 (식 12-2 환산)","delay":"순행시간 + 직진이동류 접근지체 (식 12-3)"}[c.method]
        samples=c.travel_times_s if c.method=="survey" else c.travel_speeds_kmh
        survey_html=(f"<h3>조사자료</h3><p>표본 {r.sample_count}대 · {'초' if c.method=='survey' else 'km/h'}: {esc(', '.join(map(str,samples)))}</p>" if c.method!="delay" else "")
        capacity_html=f"<h3>용량 분석 (제12장 2.1)</h3><p>{r.capacity_vph:,.1f} 대/시 · 용량 결정 교차로: {esc(', '.join(r.bottlenecks))}</p>" if r.capacity_vph is not None else "<h3>용량 분석</h3><p>미산정 — 모든 신호교차로의 직진 용량을 입력하세요.</p>"
        review_html="<h3>검토 사항</h3>"+"".join(f"<p>{esc(w)}</p>" for w in r.warnings) if r.warnings else ""
        limits="".join(f"<tr><td>{g}</td><td>{v:.2f} 이상</td></tr>" for g,v in r.thresholds.items())
        details="".join(f"<tr><td>{i}</td><td>{esc(s.end_name)}</td><td>{s.length_m:g}</td><td>{s.speed_limit_kmh:g}</td><td>{esc(s.end_type)}</td><td>{3.6*s.length_m/s.speed_limit_kmh:.2f}</td><td>{s.delay_s if c.method=="delay" and s.delay_s is not None and s.end_type!=END_TYPES[2] else '—'}</td><td>{s.capacity_vph if s.capacity_vph is not None and s.end_type==END_TYPES[0] else '—'}</td></tr>" for i,s in enumerate(c.subsegments,1))
        self.result.setHtml(f"<h2>{esc(c.name)} · {esc(c.scenario)}({c.year})</h2>"
            f"<p><b>2026 도로용량편람 · 제12장 도시부 간선도로 (베타)</b></p>"
            f"<p>{esc(c.road_category)} · {esc(c.start_name)} → {esc(c.subsegments[-1].end_name)}</p>"
            f"<h3>평균통행속도 {r.speed_kmh:.1f} km/h · 서비스수준 “{r.los}”</h3>"
            f"<p>총 길이 {r.length_m:,.0f} m · 신호교차로 {r.intersections}개 · 신호횡단보도 {r.crossings}개<br>평균 신호 간격 {r.length_m/(r.intersections+r.crossings):,.1f} m · 최소 기본 차로수 {c.lanes}차로</p>"
            "<p>적용 조건 확인: 도시부·진출입 도로 / 평면교차로·횡단보도 신호 운영 / 분석 경계·직진이동류 확인</p>"
            f"<p>순행시간 {r.running_time_s:.2f}초 · 평균통행시간 {r.total_time_s:.2f}초<br>"
            f"산정 방법: {method_text}</p>"
            f"<p>자료 출처: {esc(c.data_source) or '미기록'} · 조사·분석 일시: {esc(c.survey_date) or '미기록'}</p>{survey_html}{capacity_html}"
            f"<h3>소구간 계산</h3><table border='1' cellspacing='0' cellpadding='7'><tr><th>번호</th><th>종점</th><th>길이(m)</th><th>제한속도(km/h)</th><th>종점 유형</th><th>순행시간(초)</th><th>접근지체(초)</th><th>직진 용량(대/시)</th></tr>{details}</table>"
            f"<h3>서비스수준 기준 (식 12-1)</h3><table border='1' cellspacing='0' cellpadding='7'><tr><th>등급</th><th>최저 평균통행속도(km/h)</th></tr>{limits}<tr><td>F</td><td>{r.thresholds['E']:.2f} 미만</td></tr></table>"
            f"{review_html}<p>등급 판정에는 반올림 전 값을 사용합니다. 시점 교차로는 신호 수에 포함하지 않습니다.</p>")
        self.tabs.setCurrentIndex(2)
        return True

    def focus_missing(self,url):
        value=url.toString()
        if value.startswith('settings:'):self.tabs.setCurrentIndex(0);return
        if value.startswith('input:'):
            _,row,col=value.split(':');row=int(row);col=int(col)
            if 0<=row<self.table.rowCount():
                self.tabs.setCurrentIndex(1);self.table.setCurrentCell(row,col);self.table.scrollTo(self.table.model().index(row,col));self.table.cellWidget(row,col).setFocus()


GUIDE_2026 = """<h2>2026 도로용량편람 · 도시부 간선도로</h2>
<p>제12장 3절의 순서에 따라 한 방향의 간선이동류를 분석합니다.</p>
<h3>1. 분석 대상과 구간 설정</h3>
<p>도시부 또는 도시부 진·출입 도로로, 편도 기본 2차로 이상이고 신호교차로에서 직진 가능한 차로가 2개 이상이어야 합니다.
평면교차로·횡단보도는 신호로 운영되고 교통신호의 평균 간격은 3km 이하여야 합니다.
분석 길이는 1.5km 이상, 신호교차로·신호횡단보도는 합계 3개 이상입니다.</p>
<p>시점 교차로는 제외하고 종점 교차로는 포함합니다. 경계 바깥 교차로의 영향이 없는 지점을 경계로 설정하세요.
회전하거나 중간에 진·출입하는 이동류는 분석 대상에 포함하지 않습니다.</p>
<h3>2. 소구간 구성</h3><p>신호교차로·신호횡단보도의 하류 경계와 제한속도 변경지점에서 나눕니다.
인접하여 설치된 여러 횡단보도를 하나로 취급하는 경우 하류 횡단보도를 기준으로 구분합니다.
소구간은 진행방향 순서로 입력하고, 길이는 경계 사이의 거리(m)를 사용합니다.</p>
<h3>3. 서비스수준 기준표 · 식 12-1</h3><p>각 등급의 최저 평균통행속도 = 3.6 × 총 길이 / (순행시간 + 신호교차로 수 × 등급별 지체 + 신호횡단보도 수 × 등급별 지체)</p>
<p>A~E의 등급별 지체는 신호교차로 15, 30, 50, 70, 100초, 신호횡단보도 5, 10, 17, 23, 33초입니다. E 기준 미만이면 F입니다.</p>
<h3>4. 평균통행속도</h3><p><b>조사자료 · 식 12-2:</b> 3.6 × 총 길이(m) / 차량별 통행시간의 산술평균(초). 개별 차량 속도를 산술평균하지 않습니다. 동일한 분석구간의 차량별 통행속도가 있으면 각 값을 통행시간으로 환산한 뒤 평균합니다(속도의 조화평균).</p>
<p><b>접근지체 · 식 12-3:</b> 3.6 × 총 길이(m) / (소구간 순행시간 합계 + 직진이동류 평균접근지체 합계).
소구간 순행시간 = 3.6 × 소구간 길이(m) / 제한속도(km/h).</p>
<p>접근지체는 조사자료 또는 별도 교통신호 분석 결과를 입력합니다. 이 베타 버전은 2026 제8장의 교차로 지체 자체를 계산하지 않습니다.
2013의 지체 계산값과 교차로 LOS 참고등급을 2026 접근지체로 자동 변환하지 않습니다.</p>
<h3>5. 용량 분석 · 제12장 2.1</h3><p>각 신호교차로의 해당 방향 직진 용량 중 가장 작은 값을 구간 용량으로 사용합니다. 직진 용량은 제8장에 따라 별도로 산정한 값(대/시)을 입력합니다. 신호횡단보도와 제한속도 변경지점의 값은 이 최솟값 선정에 포함하지 않습니다. 일부 교차로의 값이 없으면 용량은 미산정으로 표시하고 LOS는 별도로 판정합니다.</p>
<h3>6. 판정과 검토</h3><p>계산된 속도를 해당 구간의 기준표와 비교합니다. 계산과 판정에는 반올림 전 값을 사용합니다.
‘편람 예제’에서 예제 1~3을 불러와 20.0km/h·D, 20.1km/h·D, 26.3km/h·C를 확인할 수 있습니다.</p>
<p>출처: 2026 도로용량편람 제12장, 683~707쪽. 2013 자료와 2026 자료는 프로젝트 안에 별도로 저장됩니다.</p>"""
