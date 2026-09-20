from __future__ import annotations

import ctypes
import math
import re
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QEvent, QMimeData, QPointF, QRectF, QSettings, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QGuiApplication, QIcon, QKeySequence, QPainter, QPalette, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QMainWindow,
    QInputDialog, QLineEdit, QMessageBox, QPushButton, QSpinBox, QStackedWidget, QTabBar, QTabWidget, QTableWidgetItem,
    QToolButton, QVBoxLayout, QWidget)

from .app import GuidelinePage
from .app_v2 import (APP_AUTHOR, APP_EMAIL, CopyableTable, CenterCheckDelegate, EditableTabBar,
    FrozenInputTable, NumericDelegate, ResultsPage, SegmentDetailDialog, STYLE, clear_tab_bar,
    load_font, make_card, resource_path)
from .engine import FUNCTIONAL_CLASSES, ROAD_CATEGORIES, SegmentInput, analyze_segment, arterial_type, road_condition
from .excel_links import SUPPORTED_EXTENSIONS, active_selection, list_sheets, normalize_cell, open_and_activate, read_saved_cell, read_saved_cells
from .project import ArterialProject
from .updater import UpdateController


APP_NAME = "도시·교외간선도로 분석"
APP_VERSION = "1.3.2"
PROJECT_FILTER = "간선도로 분석 프로젝트 (*.ara1)"
SCENARIO_LABEL = {"현황":"현황","사업 미시행시":"미시행","사업 시행시":"시행","개선대책 이행시":"개선"}
SCENARIO_COLORS = {"현황":"#475569","사업 미시행시":"#2563EB","사업 시행시":"#059669","개선대책 이행시":"#D97706"}
EXTERNAL, INTERNAL = ROAD_CATEGORIES[0], ROAD_CATEGORIES[2]


def build_network_graph(segments):
    """양방향 분석행을 교차로 노드와 무방향 가로구간으로 정리한다."""
    nodes={};edges={}
    def node(number,name):
        number=str(number or "").strip();name=str(name or "").strip()
        if not number and not name:return None
        key=("번호",number) if number else ("이름",name)
        saved=nodes.setdefault(key,{"key":key,"number":number,"name":name})
        if number:saved["number"]=number
        if name:saved["name"]=name
        return key
    for segment in segments:
        start=node(segment.start_number,segment.start_name);end=node(segment.end_number,segment.end_name)
        if start is None or end is None or start==end:continue
        pair=tuple(sorted((start,end),key=lambda value:(value[0],value[1])))
        edge=edges.setdefault(pair,{"start":pair[0],"end":pair[1],"roads":set(),"categories":set(),"uids":set()})
        if segment.road_name:edge["roads"].add(segment.road_name)
        edge["categories"].add(segment.road_category);edge["uids"].add(segment.uid)
    return nodes,list(edges.values())


class NetworkDiagramWidget(QWidget):
    edgeSelected=Signal(object)
    def __init__(self,parent=None):
        super().__init__(parent);self.nodes={};self.edges=[];self.title="";self.highlight_uids=set();self._hit_edges=[];self.setMinimumSize(660,420);self.setMouseTracking(True)
    def set_segments(self,segments,title="",highlight_uid=""):
        self.nodes,self.edges=build_network_graph(segments);self.title=title;self.highlight_uids={str(x) for x in (highlight_uid if isinstance(highlight_uid,(set,list,tuple)) else [highlight_uid]) if x};self.update()
    @staticmethod
    def _sort_key(key):
        value=key[1]
        try:return (0,float(value))
        except ValueError:return (1,value)
    def _positions(self,rect):
        keys=sorted(self.nodes,key=self._sort_key);count=len(keys);positions={}
        if count==1:positions[keys[0]]=rect.center();return positions
        if count==2:
            y=rect.center().y();positions[keys[0]]=QPointF(rect.left()+rect.width()*.22,y);positions[keys[1]]=QPointF(rect.right()-rect.width()*.22,y);return positions
        center=rect.center();radius=min(rect.width(),rect.height())*.39
        for index,key in enumerate(keys):
            angle=-math.pi/2+(2*math.pi*index/count);positions[key]=QPointF(center.x()+radius*math.cos(angle),center.y()+radius*math.sin(angle))
        return positions
    def paintEvent(self,event):
        # Keep hit targets in sync with the current frame, including an empty diagram.
        self._hit_edges=[]
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing);painter.fillRect(self.rect(),QColor("#FFFFFF"))
        painter.setPen(QColor("#334155"));title_font=QFont(painter.font());title_font.setBold(True);title_font.setPointSize(11);painter.setFont(title_font);painter.drawText(QRectF(18,12,self.width()-36,28),Qt.AlignLeft|Qt.AlignVCenter,self.title)
        if not self.edges:
            painter.setPen(QColor("#64748B"));body=QFont(painter.font());body.setBold(False);body.setPointSize(10);painter.setFont(body);painter.drawText(QRectF(30,70,self.width()-60,self.height()-100),Qt.AlignCenter|Qt.TextWordWrap,"교차로 번호와 교차로명을 입력하면 연결 삽도가 자동으로 표시됩니다.")
            return
        painter.setFont(QFont(painter.font().family(),9));painter.setPen(QColor("#2563EB"));painter.drawText(QRectF(18,40,150,22),Qt.AlignLeft|Qt.AlignVCenter,"━ 외부도로")
        painter.setPen(QColor("#059669"));painter.drawText(QRectF(170,40,150,22),Qt.AlignLeft|Qt.AlignVCenter,"━ 내부도로")
        area=QRectF(58,78,max(100,self.width()-116),max(100,self.height()-145));positions=self._positions(area)
        label_font=QFont(painter.font());label_font.setPointSize(9)
        for edge in self.edges:
            first,second=positions[edge["start"]],positions[edge["end"]];highlight=bool(self.highlight_uids&edge["uids"])
            categories=edge["categories"];color=QColor("#7C3AED" if len(categories)>1 else ("#059669" if INTERNAL in categories else "#2563EB"))
            painter.setPen(QPen(QColor("#F59E0B") if highlight else color,4 if highlight else 2));painter.drawLine(first,second)
            roads=" · ".join(sorted(edge["roads"]));mid=(first+second)/2;box=QRectF(mid.x()-78,mid.y()-12,156,24);self._hit_edges.append((edge,first,second,box))
            if roads:
                metrics=painter.fontMetrics();text=metrics.elidedText(roads,Qt.ElideRight,150);painter.fillRect(box,QColor(255,255,255,225));painter.setPen(QColor("#475569"));painter.setFont(label_font);painter.drawText(box,Qt.AlignCenter,text)
        node_font=QFont(painter.font());node_font.setBold(True);node_font.setPointSize(11);name_font=QFont(painter.font());name_font.setPointSize(8)
        highlighted_nodes=set()
        for edge in self.edges:
            if self.highlight_uids&edge["uids"]:highlighted_nodes.update((edge["start"],edge["end"]))
        for key,point in positions.items():
            node=self.nodes[key];active=key in highlighted_nodes;painter.setBrush(QColor("#FFF7E0") if active else "#EFF6FF");painter.setPen(QPen(QColor("#F59E0B") if active else QColor("#1D4ED8"),3 if active else 2));painter.drawEllipse(point,24,24)
            label=node["number"] or node["name"][:4];painter.setFont(node_font);painter.setPen(QColor("#172033"));painter.drawText(QRectF(point.x()-22,point.y()-22,44,44),Qt.AlignCenter,label)
            if node["name"]:
                painter.setFont(name_font);text=painter.fontMetrics().elidedText(node["name"],Qt.ElideRight,125);painter.drawText(QRectF(point.x()-65,point.y()+28,130,20),Qt.AlignCenter,text)
    @staticmethod
    def _distance(point,start,end):
        dx=end.x()-start.x();dy=end.y()-start.y();length=dx*dx+dy*dy
        if not length:return math.hypot(point.x()-start.x(),point.y()-start.y())
        ratio=max(0,min(1,((point.x()-start.x())*dx+(point.y()-start.y())*dy)/length));x=start.x()+ratio*dx;y=start.y()+ratio*dy
        return math.hypot(point.x()-x,point.y()-y)
    def _edge_at(self,point):
        candidates=[]
        for edge,start,end,label in self._hit_edges:
            distance=0 if label.adjusted(-5,-5,5,5).contains(point) else self._distance(point,start,end)
            if distance<=14:candidates.append((distance,edge))
        return min(candidates,key=lambda value:value[0])[1] if candidates else None
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            edge=self._edge_at(event.position())
            if edge:
                self.highlight_uids=set(edge["uids"]);self.update();self.edgeSelected.emit(set(edge["uids"]));event.accept();return
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        edge=self._edge_at(event.position());self.setCursor(Qt.PointingHandCursor if edge else Qt.ArrowCursor)
        self.setToolTip("입력표에서 이 가로구간 선택" if edge else "");super().mouseMoveEvent(event)


class NetworkDiagramDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle("구간 연결 삽도");self.resize(820,600);self.setMinimumSize(700,500)
        layout=QVBoxLayout(self);note=QLabel("입력표에서 선택한 구간은 주황색으로 강조됩니다. 삽도의 선이나 가로명을 클릭하면 입력표의 해당 구간이 선택됩니다.");note.setObjectName("infoBar");layout.addWidget(note)
        self.diagram=NetworkDiagramWidget();layout.addWidget(self.diagram,1);buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.button(QDialogButtonBox.Close).setText("닫기");buttons.rejected.connect(self.hide);layout.addWidget(buttons)
    def closeEvent(self,event):event.ignore();self.hide()


def excel_link_icon() -> QIcon:
    pixmap=QPixmap(14,14);pixmap.fill(Qt.transparent);painter=QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing);painter.setPen(Qt.NoPen);painter.setBrush(QColor("#107C41"));painter.drawRoundedRect(0,0,14,14,2,2)
    font=QFont("Arial",8,QFont.Bold);painter.setFont(font);painter.setPen(QColor("white"));painter.drawText(pixmap.rect(),Qt.AlignCenter,"X");painter.end()
    return QIcon(pixmap)


def blank_project(year=2026):
    project=ArterialProject(current_year=int(year),future_years=[]);project.add_starter_rows()
    for s in project.segments:
        s.road_name=s.start_name=s.end_name=s.start_number=s.end_number="";s.length_km=0;s.lanes=0;s.cycle_s=0;s.green_s=0;s.main_volume=0;s.report_length_km=None;s.report_volume=None;s.phf=1.0;s.functional_class="저규격";s.road_condition_override="보통";s.arterial_type_override="자동";s.blank_fields=["length_km","lanes","cycle_s","green_s","main_volume"]
    return project


from PySide6.QtWidgets import QStyledItemDelegate


class FastComboDelegate(QStyledItemDelegate):
    def __init__(self, values, editable=True, table=None, parent=None):
        super().__init__(parent); self.values=values; self.editable=editable;self.table=table
    def createEditor(self,parent,option,index):
        editor=QComboBox(parent); editor.setEditable(self.editable); editor.setInsertPolicy(QComboBox.NoInsert)
        values=self.values() if callable(self.values) else self.values; editor.addItems([str(v) for v in values if str(v)])
        if editor.lineEdit():
            editor.completer().setFilterMode(Qt.MatchContains);editor.completer().setCaseSensitivity(Qt.CaseInsensitive)
        self._install_nav(editor,index);return editor
    def setEditorData(self,editor,index): editor.setCurrentText(str(index.data() or "")); editor.lineEdit().selectAll() if editor.lineEdit() else None
    def setModelData(self,editor,model,index): model.setData(index,editor.currentText().strip())
    def _install_nav(self,editor,index):
        for target in (editor,editor.lineEdit()):
            if target:target.setProperty("navRow",index.row());target.setProperty("navCol",index.column());target.setProperty("navEditor",editor);target.installEventFilter(self)
    def eventFilter(self,obj,event):
        if event.type()==QEvent.KeyPress and event.key() in (Qt.Key_Tab,Qt.Key_Backtab,Qt.Key_Return,Qt.Key_Enter):
            editor=obj.property("navEditor") or obj;back=event.key()==Qt.Key_Backtab or bool(event.modifiers()&Qt.ShiftModifier);row=int(obj.property("navRow"));col=int(obj.property("navCol"));self.commitData.emit(editor);self.closeEditor.emit(editor,QStyledItemDelegate.NoHint)
            if self.table:QTimer.singleShot(0,lambda:self.table.move_from(row,col,-1 if back else 1))
            return True
        return super().eventFilter(obj,event)


class BlankNumericDelegate(NumericDelegate):
    def __init__(self,integer,minimum,maximum,decimals=2,table=None,parent=None):super().__init__(integer,minimum,maximum,decimals,parent);self.table=table
    def createEditor(self,parent,option,index):
        editor=super().createEditor(parent,option,index)
        editor.setStyleSheet("QLineEdit{padding:0 4px;min-height:0;border:2px solid #2375E8;border-radius:0;background:white;color:#172033;selection-background-color:#DCEBFF;selection-color:#172033;}")
        palette=editor.palette();palette.setColor(QPalette.Base,QColor("white"));palette.setColor(QPalette.Text,QColor("#172033"));palette.setColor(QPalette.Highlight,QColor("#DCEBFF"));palette.setColor(QPalette.HighlightedText,QColor("#172033"));editor.setPalette(palette);editor.setAutoFillBackground(True)
        editor.setProperty("navRow",index.row());editor.setProperty("navCol",index.column());editor.installEventFilter(self);return editor
    def eventFilter(self,obj,event):
        if event.type()==QEvent.KeyPress and event.key() in (Qt.Key_Tab,Qt.Key_Backtab,Qt.Key_Return,Qt.Key_Enter):
            back=event.key()==Qt.Key_Backtab or bool(event.modifiers()&Qt.ShiftModifier);row=int(obj.property("navRow"));col=int(obj.property("navCol"));self.commitData.emit(obj);self.closeEditor.emit(obj,QStyledItemDelegate.NoHint)
            if self.table:QTimer.singleShot(0,lambda:self.table.move_from(row,col,-1 if back else 1))
            return True
        return super().eventFilter(obj,event)
    def setModelData(self,editor,model,index):
        raw=editor.text().replace(",","").strip()
        if not raw:model.setData(index,"");return
        value=int(raw) if self.integer else float(raw);value=max(self.minimum,min(self.maximum,value))
        model.setData(index,f"{value:,}" if self.integer else f"{value:.{self.decimals}f}")


class GreenTimeDelegate(BlankNumericDelegate):
    """입력 중에도 주기를 초과하는 녹색시간을 받지 않는 편집기."""
    def createEditor(self,parent,option,index):
        cycle=index.model().data(index.sibling(index.row(),10),Qt.DisplayRole)
        try:maximum=int(str(cycle or "0").replace(",","") or 0)
        except ValueError:maximum=0
        old_maximum=self.maximum;self.maximum=max(0,maximum)
        editor=super().createEditor(parent,option,index);self.maximum=old_maximum
        return editor
    def setModelData(self,editor,model,index):
        cycle=model.data(index.sibling(index.row(),10),Qt.DisplayRole)
        try:maximum=int(str(cycle or "0").replace(",","") or 0)
        except ValueError:maximum=0
        old_maximum=self.maximum;self.maximum=max(0,maximum)
        super().setModelData(editor,model,index);self.maximum=old_maximum


class FastInputTable(FrozenInputTable):
    linkRequested=Signal(int); detailRequested=Signal(int); refreshRequested=Signal(); compareRequested=Signal(); toggleOptionalRequested=Signal()
    addRequested=Signal(); deleteRequested=Signal(); tabNextRequested=Signal(int); commitRequested=Signal(int,int,bool)
    def __init__(self,rows,columns,parent=None):
        super().__init__(rows,columns,7,parent); self.frozen.installEventFilter(self)
    def eventFilter(self,obj,event):
        if obj is self.frozen and event.type()==QEvent.KeyPress:
            self.setCurrentCell(self.frozen.currentIndex().row(),self.frozen.currentIndex().column())
            self.keyPressEvent(event); return event.isAccepted()
        return super().eventFilter(obj,event)
    def keyPressEvent(self,event):
        row,col=self.currentRow(),self.currentColumn(); mods=event.modifiers(); key=event.key()
        if row>=0 and col in self._editable_columns() and col in (7,8,10,11,12,13,17,18) and event.text() and re.fullmatch(r"[0-9.]",event.text()):
            self.editItem(self.item(row,col));editor=QApplication.focusWidget()
            if isinstance(editor,QLineEdit):editor.insert(event.text());editor.update();editor.repaint()
            event.accept();return
        if key==Qt.Key_F2 and row>=0: self.editItem(self.item(row,col)); event.accept(); return
        if key==Qt.Key_F5: self.refreshRequested.emit(); event.accept(); return
        if key==Qt.Key_F7: self.toggleOptionalRequested.emit(); event.accept(); return
        if key==Qt.Key_F8: self.compareRequested.emit(); event.accept(); return
        if key in (Qt.Key_Return,Qt.Key_Enter) and mods&Qt.ControlModifier:self._fill(True);event.accept();return
        if key==Qt.Key_Down and mods&Qt.AltModifier and row>=0:self.editItem(self.item(row,col));event.accept();return
        if key in (Qt.Key_Return,Qt.Key_Enter,Qt.Key_Tab,Qt.Key_Backtab):
            backwards=key==Qt.Key_Backtab or bool(mods&Qt.ShiftModifier)
            self.commitRequested.emit(row,col,backwards)
            self._move_editable(-1 if backwards else 1); event.accept(); return
        if key==Qt.Key_Delete: self._clear_selected(); event.accept(); return
        if mods&Qt.ControlModifier and key==Qt.Key_C: self._copy(); event.accept(); return
        if mods&Qt.ControlModifier and key==Qt.Key_X: self._copy(); self._clear_selected(); event.accept(); return
        if mods&Qt.ControlModifier and key==Qt.Key_V: self._paste(); event.accept(); return
        if mods&Qt.ControlModifier and key in (Qt.Key_D,Qt.Key_R): self._fill(key==Qt.Key_D); event.accept(); return
        if mods&Qt.ControlModifier and key in (Qt.Key_Plus,Qt.Key_Equal): self.addRequested.emit(); event.accept(); return
        if mods&Qt.ControlModifier and key==Qt.Key_Minus: self.deleteRequested.emit(); event.accept(); return
        if mods&Qt.ShiftModifier and key==Qt.Key_Space: self._select_pair(); event.accept(); return
        super().keyPressEvent(event)
    def _editable_columns(self): return [c for c in (1,2,3,4,5,6,7,8,10,11,12,13,17,18,19,20) if not self.isColumnHidden(c)]
    def _move_editable(self,delta):
        if self.rowCount()==0:return
        cols=self._editable_columns(); current=(self.currentRow(),self.currentColumn()); positions=[]
        for row in range(self.rowCount()):
            identity=self.item(row,0).data(Qt.UserRole+1) if self.item(row,0) else None
            previous=self.item(row-1,0).data(Qt.UserRole+1) if row>0 and self.item(row-1,0) else None
            for col in cols:
                if row>0 and identity==previous and col in (1,2,3,5,6):continue
                positions.append((row,col))
        if not positions:return
        try:index=positions.index(current)
        except ValueError:index=0 if delta>0 else len(positions)-1
        else:index=max(0,min(len(positions)-1,index+delta))
        row,col=positions[index];self.setCurrentCell(row,col);self.scrollToItem(self.item(row,col));self.editItem(self.item(row,col))
    def move_from(self,row,col,delta):
        self.setCurrentCell(row,col);self.commitRequested.emit(row,col,delta<0);self._move_editable(delta)
    def _copy(self):
        indexes=self.selectedIndexes()
        if not indexes:return
        r0,r1=min(i.row() for i in indexes),max(i.row() for i in indexes); c0,c1=min(i.column() for i in indexes),max(i.column() for i in indexes)
        selected={(i.row(),i.column()) for i in indexes}; lines=[]
        for r in range(r0,r1+1): lines.append("\t".join(self.item(r,c).text() if (r,c) in selected and self.item(r,c) else "" for c in range(c0,c1+1)))
        QGuiApplication.clipboard().setText("\n".join(lines))
    def _paste(self):
        text=QGuiApplication.clipboard().text(); start_r,start_c=self.currentRow(),self.currentColumn()
        if not text or start_r<0:return
        self.blockSignals(True)
        for dr,line in enumerate(text.splitlines()):
            if start_r+dr>=self.rowCount():break
            for dc,value in enumerate(line.split("\t")):
                col=start_c+dc
                if col>=self.columnCount() or col not in self._editable_columns():continue
                self.item(start_r+dr,col).setText(value.strip())
        self.blockSignals(False)
        for r in range(start_r,min(self.rowCount(),start_r+len(text.splitlines()))): self.commitRequested.emit(r,start_c,False)
    def _clear_selected(self):
        self.blockSignals(True)
        for index in self.selectedIndexes():
            if index.column() in self._editable_columns(): self.item(index.row(),index.column()).setText("")
        self.blockSignals(False)
        for row in sorted({i.row() for i in self.selectedIndexes()}): self.commitRequested.emit(row,self.currentColumn(),False)
    def _fill(self,down):
        indexes=self.selectedIndexes()
        if not indexes:return
        r0,c0=min(i.row() for i in indexes),min(i.column() for i in indexes); value=self.item(r0,c0).text()
        self.blockSignals(True)
        for i in indexes:
            if i.column() in self._editable_columns(): self.item(i.row(),i.column()).setText(value)
        self.blockSignals(False)
        for row in sorted({i.row() for i in indexes}): self.commitRequested.emit(row,c0,False)
    def _select_pair(self):
        item=self.item(self.currentRow(),0); identity=item.data(Qt.UserRole+1) if item else None
        for row in range(self.rowCount()):
            if self.item(row,0).data(Qt.UserRole+1)==identity:self.selectRow(row)


class AddTabDialog(QDialog):
    def __init__(self,parent=None,scenario="사업 미시행시",year=2033,locked=False):
        super().__init__(parent); self.setWindowTitle("분석 탭 추가" if not locked else "분석연도 변경"); form=QFormLayout(self)
        self.scenario=QComboBox(); self.scenario.addItems(list(SCENARIO_LABEL)); self.scenario.setCurrentText(scenario); self.scenario.setEnabled(not locked)
        self.year=QSpinBox(); self.year.setRange(2000,2200); self.year.setValue(year); self.year.selectAll()
        form.addRow("분석 상황",self.scenario); form.addRow("분석연도",self.year)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); buttons.button(QDialogButtonBox.Ok).setText("적용");buttons.button(QDialogButtonBox.Cancel).setText("취소");buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);form.addRow(buttons)


class FastDetailDialog(SegmentDetailDialog):
    def __init__(self,segment,project,parent=None):
        QDialog.__init__(self,parent); self.segment=segment; self.project=project; self.setWindowTitle("구간별 상세조건"); self.setMinimumWidth(540)
        root=QVBoxLayout(self); title=QLabel(f"{segment.road_name} · {segment.start_name} {segment.direction} {segment.end_name}"); title.setObjectName("cardTitle"); root.addWidget(title)
        form=QFormLayout(); self.functional=QComboBox();self.functional.addItems(FUNCTIONAL_CLASSES);self.functional.setCurrentText(segment.functional_class)
        self.condition=QComboBox();self.condition.addItems(["보통","양호","자동"]);self.condition.setCurrentText(segment.road_condition_override)
        self.arterial=QComboBox();self.arterial.addItems(["자동","유형 I","유형 II","유형 III"]);self.arterial.setCurrentText(segment.arterial_type_override)
        self.bus=QSpinBox();self.bus.setRange(0,99);self.bus.setValue(segment.bus_stops)
        self.access=QSpinBox();self.access.setRange(0,999);self.access.setValue(segment.access_points)
        self.crossing=QSpinBox();self.crossing.setRange(0,20);self.crossing.setValue(segment.crossing_signals or 0)
        self.period=QDoubleSpinBox();self.period.setRange(.05,4);self.period.setDecimals(2);self.period.setValue(segment.analysis_period_h or project.settings.analysis_period_h)
        self.base=QDoubleSpinBox();self.base.setRange(500,4000);self.base.setDecimals(0);self.base.setValue(segment.base_saturation_flow or project.settings.base_saturation_flow)
        self.sat=QDoubleSpinBox();self.sat.setRange(.1,2);self.sat.setDecimals(3);self.sat.setValue(segment.saturation_adjustment or project.settings.saturation_adjustment)
        self.queue=QSpinBox();self.queue.setRange(0,10000);self.queue.setValue(int(segment.initial_queue or 0))
        self.coordinated=QCheckBox("연동신호 적용");self.coordinated.setChecked(bool(segment.coordinated))
        self.pf=QDoubleSpinBox();self.pf.setRange(0,3);self.pf.setDecimals(3);self.pf.setSpecialValueText("자동/1.0");self.pf.setValue(segment.pf_override or 0)
        self.fcw=QDoubleSpinBox();self.fcw.setRange(0,3);self.fcw.setDecimals(3);self.fcw.setSpecialValueText("자동");self.fcw.setValue(segment.fcw_override or 0)
        rows=(("기능등급",self.functional),("도로여건",self.condition),("간선도로 유형",self.arterial),("버스정류장 수",self.bus),("진출입로 수",self.access),("신호횡단보도 수",self.crossing),("분석기간 T(시간)",self.period),("기본 포화교통류율",self.base),("포화교통류율 보정계수",self.sat),("초기 대기차량",self.queue),("신호 연동",self.coordinated),("연동보정계수 PF",self.pf),("횡단신호보정계수 fcw",self.fcw))
        for label,widget in rows:form.addRow(label,widget)
        root.addLayout(form); note=QLabel("기본값은 저규격·보통이며, 간선도로 유형은 편람 표 12-3·12-4 조합으로 자동 판정합니다.");note.setObjectName("infoBar");root.addWidget(note)
        buttons=QDialogButtonBox(QDialogButtonBox.RestoreDefaults|QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.RestoreDefaults).setText("기본값");buttons.button(QDialogButtonBox.Ok).setText("적용");buttons.button(QDialogButtonBox.Cancel).setText("취소");buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self.defaults);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);root.addWidget(buttons)
    def defaults(self):self.functional.setCurrentText("저규격");self.condition.setCurrentText("보통");self.arterial.setCurrentText("자동");self.bus.setValue(0);self.access.setValue(0);self.crossing.setValue(0);self.period.setValue(.25);self.base.setValue(2200);self.sat.setValue(1);self.queue.setValue(0);self.coordinated.setChecked(False);self.pf.setValue(0);self.fcw.setValue(0)
    def apply_to_segment(self):
        s=self.segment;s.functional_class=self.functional.currentText();s.road_condition_override=self.condition.currentText();s.arterial_type_override=self.arterial.currentText();s.bus_stops=self.bus.value();s.access_points=self.access.value();s.crossing_signals=self.crossing.value();s.analysis_period_h=self.period.value();s.base_saturation_flow=self.base.value();s.saturation_adjustment=self.sat.value();s.initial_queue=float(self.queue.value());s.coordinated=self.coordinated.isChecked();s.pf_override=self.pf.value() or None;s.fcw_override=self.fcw.value() or None


class InputPage(QWidget):
    changed=Signal()
    HEADERS=["선택","가로명","교차로\n번호","교차로명","↔","교차로\n번호","교차로명","구간길이\n(m)","본선\n차로수\n(편도)","유형\n번호","주기\n(초)","녹색시간\n(초)","교통량\n(대/시)","PHF","평균\n통행속도\n(km/h)","서비스수준\n(LOS)","상세","보고서\n구간길이\n(m)","보고서\n교통량\n(대/시)","교차로\n서비스수준\n(LOS)\n(참고)","접근로\n서비스수준\n(LOS)\n(참고)"]
    INTEGER={7,8,10,11,12,17,18}; NUMERIC={7,8,10,11,12,13,14,17,18}; READONLY={0,9,14,15,16}
    def __init__(self,project):
        super().__init__();self.project=project;self.current_key=None;self._changing=False;self._clipboard=[];self._link_table=None;self._link_row=-1;self.diagram_dialog=None
        root=QVBoxLayout(self);root.setContentsMargins(16,12,16,10);title=QLabel("상황·연도별 분석구간 입력");title.setObjectName("pageTitle");root.addWidget(title)
        self.analysis_tabs=EditableTabBar();self.analysis_tabs.setExpanding(False);self.analysis_tabs.setDrawBase(False);root.addWidget(self.analysis_tabs)
        source=QHBoxLayout();self.source_label=QLabel("교통량 원본: 연결 안 됨");self.source_label.setObjectName("copyNote");source.addWidget(self.source_label,1);self.choose_source=QPushButton("Excel 원본 선택");self.open_source=QPushButton("원본 열기");self.refresh_source=QPushButton("새로고침 (F5)");self.sheet=QComboBox();self.sheet.setMinimumWidth(150)
        for widget in (self.choose_source,self.open_source,self.sheet,self.refresh_source):source.addWidget(widget)
        root.addLayout(source);self.formula=QLabel("Excel 연결: 교통량 셀 선택 → = → Excel 셀 클릭 → Enter  (디스크에 저장된 값 반영)");self.formula.setObjectName("formulaBar");root.addWidget(self.formula)
        self.change_notice=QLabel();self.change_notice.setObjectName("changeNotice");self.change_notice.hide();root.addWidget(self.change_notice)
        self.compare_bar=QLabel();self.compare_bar.setObjectName("compareBar");self.compare_bar.hide();root.addWidget(self.compare_bar)
        self.road_tabs=QTabWidget();self.external=self._make_table();self.internal=self._make_table();self.road_tabs.addTab(make_card("외부도로",self.external),"외부도로");self.road_tabs.addTab(make_card("내부도로",self.internal),"내부도로");root.addWidget(self.road_tabs,1)
        buttons=QHBoxLayout();self.add=QPushButton("양방향 구간 추가");self.copy=QPushButton("선택 구간 복사");self.paste=QPushButton("구간 붙여넣기");self.delete=QPushButton("선택 행 삭제");self.reset=QPushButton("선택 행 초기화");self.diagram_button=QPushButton("구간 연결 삽도 (F6)");self.optional=QPushButton("보조 입력 펼치기 (F7)")
        for b in (self.add,self.copy,self.paste,self.delete,self.reset,self.diagram_button,self.optional):buttons.addWidget(b)
        buttons.addStretch();self.next_button=QPushButton("분석 결과 보기");self.next_button.setObjectName("primaryButton");buttons.addWidget(self.next_button);root.addLayout(buttons)
        shortcuts=QLabel("Enter/Tab 다음 셀  ·  방향키 이동  ·  = Excel 셀 연결  ·  Ctrl+H 연결 경로 일괄 변경  ·  Ctrl+C/V 복사·붙여넣기  ·  F5 새로고침  ·  F6 연결 삽도  ·  F7 보조열  ·  F8 비교  ·  F1 단축키")
        shortcuts.setObjectName("shortcutBar");root.addWidget(shortcuts)
        self.analysis_tabs.currentChanged.connect(self._tab_changed);self.analysis_tabs.activeLabelClicked.connect(self._edit_year);self.choose_source.clicked.connect(self.choose_excel);self.open_source.clicked.connect(self.open_excel);self.refresh_source.clicked.connect(self.refresh_links);self.sheet.currentTextChanged.connect(self.sheet_changed)
        self.add.clicked.connect(self.add_pair);self.copy.clicked.connect(self.copy_selected);self.paste.clicked.connect(self.paste_selected);self.delete.clicked.connect(self.delete_selected);self.reset.clicked.connect(self.reset_selected);self.diagram_button.clicked.connect(self.show_network_diagram);self.optional.clicked.connect(self.toggle_optional)
        self._diagram_shortcut=QShortcut(QKeySequence("F6"),self);self._diagram_shortcut.setContext(Qt.WidgetWithChildrenShortcut);self._diagram_shortcut.activated.connect(self.show_network_diagram);self.changed.connect(self.refresh_network_diagram);self.refresh_tabs()
    def _make_table(self):
        t=FastInputTable(0,len(self.HEADERS));t.setHorizontalHeaderLabels(self.HEADERS);t.verticalHeader().hide();t.setAlternatingRowColors(True);t.setSelectionMode(QAbstractItemView.ExtendedSelection);t.setSelectionBehavior(QAbstractItemView.SelectItems);t.setEditTriggers(QAbstractItemView.AllEditTriggers);t.setIconSize(QSize(14,14));t.frozen.setIconSize(QSize(14,14));t.horizontalHeader().setFixedHeight(76);t.frozen.horizontalHeader().setFixedHeight(76)
        header_font=t.horizontalHeader().font();header_font.setPointSize(9);t.horizontalHeader().setFont(header_font);t.frozen.horizontalHeader().setFont(header_font)
        widths=[40,88,42,106,32,42,106]+[76]*14
        for c,w in enumerate(widths):t.setColumnWidth(c,w)
        t.set_shared_delegate(0,CenterCheckDelegate(t))
        for c,values,editable in ((1,self.road_names,True),(3,self.intersection_names,True),(4,["→","←"],False),(6,self.intersection_names,True)):
            t.setItemDelegateForColumn(c,FastComboDelegate(values,editable,t,t));t.frozen.setItemDelegateForColumn(c,FastComboDelegate(values,editable,t,t.frozen))
        for c in (7,10,12,17,18):t.setItemDelegateForColumn(c,BlankNumericDelegate(True,0,10000000,table=t,parent=t))
        t.setItemDelegateForColumn(8,BlankNumericDelegate(True,0,10,table=t,parent=t))
        t.setItemDelegateForColumn(11,GreenTimeDelegate(True,0,10000,table=t,parent=t))
        t.setItemDelegateForColumn(13,BlankNumericDelegate(False,0,1,2,table=t,parent=t))
        for c in (19,20):t.setItemDelegateForColumn(c,FastComboDelegate(["","A","B","C","D","E","F","FF","FFF"],True,t,t))
        for c in (17,18,19,20):t.setColumnHidden(c,True)
        t._excel_link_shortcut=QShortcut(QKeySequence("="),t);t._excel_link_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        t._excel_link_shortcut.activated.connect(lambda table=t:table.linkRequested.emit(table.currentRow()) if table.currentRow()>=0 and table.currentColumn()==12 else None)
        t._replace_link_shortcut=QShortcut(QKeySequence("Ctrl+H"),t);t._replace_link_shortcut.setContext(Qt.WidgetWithChildrenShortcut);t._replace_link_shortcut.activated.connect(lambda table=t:self.replace_excel_sources(table))
        t.itemChanged.connect(lambda item,table=t:self.item_changed(table,item));t.currentCellChanged.connect(lambda r,c,pr,pc,table=t:(self.commit_row(table,pr,pc) if pr>=0 else None,self.cell_selected(table,r,c)));t.cellPressed.connect(lambda r,c,table=t:self.open_combo_on_click(table,table,r,c));t.frozen.pressed.connect(lambda index,table=t:self.open_combo_on_click(table,table.frozen,index.row(),index.column()));t.linkRequested.connect(lambda row,table=t:self.start_link(table,row));t.refreshRequested.connect(self.refresh_links);t.compareRequested.connect(self.toggle_compare);t.toggleOptionalRequested.connect(self.toggle_optional);t.addRequested.connect(self.add_pair);t.deleteRequested.connect(self.delete_selected);t.commitRequested.connect(lambda row,col,back,table=t:self.commit_row(table,row,col,back))
        return t
    def open_combo_on_click(self,table,view,row,col):
        if col not in (1,3,4,6,19,20) or not table.item(row,col):return
        index=table.model().index(row,col);view.setCurrentIndex(index);view.edit(index)
        QTimer.singleShot(0,lambda:next((w.showPopup() for w in view.findChildren(QComboBox) if w.isVisible()),None))
    def active_table(self):return self.external if self.road_tabs.currentIndex()==0 else self.internal
    def road_names(self):return sorted({s.road_name for s in self.project.segments if s.road_name})
    def intersection_names(self):return sorted({x for s in self.project.segments for x in (s.start_name,s.end_name) if x})
    def tab_label(self,key):return f"{SCENARIO_LABEL[key[0]]}({key[1]})"
    def refresh_tabs(self,select=None):
        current=select or self.current_key;self._changing=True;clear_tab_bar(self.analysis_tabs);keys=self.project.tab_keys()
        for key in keys:
            i=self.analysis_tabs.addTab(self.tab_label(key));self.analysis_tabs.setTabData(i,key);self.analysis_tabs.setTabTextColor(i,QColor(SCENARIO_COLORS[key[0]]))
            if key[0]!="현황":b=QToolButton(self.analysis_tabs);b.setText("×");b.setObjectName("tabCloseButton");b.setFixedSize(18,22);b.clicked.connect(lambda _=False,k=key:self.delete_tab(k));self.analysis_tabs.setTabButton(i,QTabBar.RightSide,b)
        i=self.analysis_tabs.addTab("+");self.analysis_tabs.setTabData(i,None);target=next((n for n,k in enumerate(keys) if k==current),0);self.analysis_tabs.setCurrentIndex(target);self._changing=False
        if keys:self.load_key(keys[target])
    def _default_source(self,scenario,year):
        keys=self.project.tab_keys()
        if scenario=="사업 미시행시":
            previous=[k for k in keys if k[0]==scenario and k[1]<year];return max(previous,key=lambda k:k[1]) if previous else next((k for k in keys if k[0]=="현황"),None)
        if scenario=="사업 시행시":
            previous=[k for k in keys if k[0]==scenario and k[1]<year];return max(previous,key=lambda k:k[1]) if previous else next((k for k in keys if k==("사업 미시행시",year)),None)
        if scenario=="개선대책 이행시":return next((k for k in keys if k==("사업 시행시",year)),None)
    def _tab_changed(self,index):
        if self._changing or index<0:return
        key=self.analysis_tabs.tabData(index)
        if key is None:
            old=self.current_key;dialog=AddTabDialog(self,year=old[1] if old else 2033)
            if dialog.exec()!=QDialog.Accepted:self.refresh_tabs(old);return
            key=(dialog.scenario.currentText(),dialog.year.value())
            if key in self.project.tab_keys():QMessageBox.information(self,"탭 추가","같은 상황과 연도가 이미 있습니다.");self.refresh_tabs(key);return
            self.save_current();self.project.ensure_tab(*key);source=self._default_source(*key)
            if source:self.project.copy_rows(*source,*key)
            self.changed.emit();self.refresh_tabs(key);return
        self.save_current();self.load_key(tuple(key))
    def _edit_year(self,index):
        key=self.analysis_tabs.tabData(index)
        if key is None:return
        scenario,old=tuple(key);d=AddTabDialog(self,scenario,old,True)
        if d.exec()!=QDialog.Accepted or d.year.value()==old:return
        new=(scenario,d.year.value())
        if new in self.project.tab_keys():QMessageBox.information(self,"연도 변경","같은 상황과 연도가 이미 있습니다.");return
        self.save_current()
        for s in self.project.segments:
            if (s.scenario,s.year)==(scenario,old):s.year=new[1]
        for info in self.project.analysis_tabs:
            if (info.get("scenario"),int(info.get("year",0)))==(scenario,old):info["year"]=new[1]
        if scenario=="현황":self.project.current_year=new[1]
        self.changed.emit();self.refresh_tabs(new)
    def delete_tab(self,key):
        box=QMessageBox(self)
        box.setWindowTitle("분석 탭 삭제")
        box.setText(f"{self.tab_label(key)} 탭과 입력 구간을 삭제하시겠습니까?")
        box.setIcon(QMessageBox.Question)
        box.setStandardButtons(QMessageBox.Yes|QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        box.button(QMessageBox.Yes).setText("삭제")
        box.button(QMessageBox.No).setText("취소")
        if box.exec()!=QMessageBox.Yes:return
        self.save_current();self.project.segments=[s for s in self.project.segments if (s.scenario,s.year)!=key];self.project.analysis_tabs=[i for i in self.project.analysis_tabs if (i.get("scenario"),int(i.get("year",0)))!=key];self.changed.emit();self.refresh_tabs()
    def load_key(self,key):
        self.current_key=key;show_internal=key[0] in ("사업 시행시","개선대책 이행시");self.road_tabs.setTabVisible(1,show_internal)
        if not show_internal:self.road_tabs.setCurrentIndex(0)
        self.load_table(self.external,[s for s in self.project.rows(*key) if s.road_category!=INTERNAL]);self.load_table(self.internal,[s for s in self.project.rows(*key) if s.road_category==INTERNAL]);self.update_source_bar();self.refresh_network_diagram()
    def load_table(self,t,rows):
        t.blockSignals(True);t.clearSpans();t.frozen.clearSpans();t.setRowCount(0)
        for s in rows:self.append_segment(t,s)
        self.merge_pairs(t);t.blockSignals(False);t._update_frozen_geometry()
    def append_segment(self,t,s):
        missing=set(s.blank_fields);text=lambda field,value,fmt="{}":"" if field in missing else fmt.format(value)
        try:r=analyze_segment(s,self.project.settings) if self.project.is_complete(s) else None
        except Exception:r=None
        condition=s.road_condition_override if s.road_condition_override in ("양호","보통") else road_condition(s.functional_class,s.lanes)
        type_number=(s.arterial_type_override if s.arterial_type_override not in ("","자동") else arterial_type(s.functional_class,condition)).replace("유형 ","유형")
        values=["",s.road_name,s.start_number,s.start_name,s.direction,s.end_number,s.end_name,text("length_km",round(s.length_km*1000),"{:,}"),text("lanes",s.lanes,"{:,}"),type_number,text("cycle_s",round(s.cycle_s),"{:,}"),text("green_s",round(s.green_s),"{:,}"),text("main_volume",round(s.main_volume),"{:,}"),text("phf",s.phf,"{:.2f}"),f"{r.speed_kmh:.1f}" if r else "",r.los if r else "","",("" if s.report_length_km is None else f"{round(s.report_length_km*1000):,}"),("" if s.report_volume is None else f"{round(s.report_volume):,}"),s.intersection_los,s.approach_los]
        row=t.rowCount();t.insertRow(row)
        for c,value in enumerate(values):
            item=QTableWidgetItem(str(value));item.setData(Qt.UserRole,s.uid if c==0 else None);item.setData(Qt.UserRole+1,s.comparison_id if c==0 else None);item.setTextAlignment((Qt.AlignRight if c in self.NUMERIC and c!=8 else Qt.AlignCenter)|Qt.AlignVCenter)
            if c==0:item.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable|Qt.ItemIsSelectable);item.setCheckState(Qt.Unchecked)
            if c in self.READONLY:item.setFlags(item.flags()&~Qt.ItemIsEditable)
            if c in (14,15):item.setBackground(QColor("#DDF4FF"));item.setForeground(QColor("#075985"))
            if c==12 and s.volume_source_cell:
                item.setIcon(excel_link_icon());warning=s.volume_link_status in ("unconfirmed","last_saved");color="#FFF0C2" if warning else ("#FFE5E5" if s.volume_link_error else "#E5F4EA");item.setBackground(QColor(color));item.setToolTip(("Excel 미저장 변경 제외 · 마지막 저장값 연결: " if s.volume_link_status=="last_saved" else "Excel 연결: ")+s.volume_source_cell if not s.volume_link_error else s.volume_link_error)
            t.setItem(row,c,item)
        pair=["#DCEBFF","#E8F5E9","#FFF1D6","#F3E8FF"][sum(ord(ch) for ch in s.comparison_id)%4];t.item(row,0).setBackground(QColor(pair))
        button=QPushButton("상세");button.setObjectName("detailButton");button.clicked.connect(lambda _=False,uid=s.uid:self.edit_details(uid));t.setCellWidget(row,16,button)
    @staticmethod
    def merge_pairs(t):
        t.clearSpans();t.frozen.clearSpans();row=0
        while row<t.rowCount():
            item=t.item(row,0);identity=item.data(Qt.UserRole+1) if item else None;end=row+1
            while end<t.rowCount() and t.item(end,0) and t.item(end,0).data(Qt.UserRole+1)==identity:end+=1
            if identity and end-row>1:
                for lower in range(row+1,end):
                    for col in (1,2,3,5,6):t.item(lower,col).setText(t.item(row,col).text())
                for col in (0,1,2,3,5,6):t.setSpan(row,col,end-row,1);t.frozen.setSpan(row,col,end-row,1)
            row=end
    def parse_row(self,t,row,category,old):
        val=lambda c:t.item(row,c).text().strip() if t.item(row,c) else "";num=lambda c:float(val(c).replace(",","") or 0)
        uid=t.item(row,0).data(Qt.UserRole) or uuid4().hex;previous=old.get(uid);blank=[]
        for field,c in (("length_km",7),("lanes",8),("cycle_s",10),("green_s",11),("main_volume",12),("phf",13)):
            if not val(c):blank.append(field)
        return SegmentInput(uid=uid,comparison_id=previous.comparison_id if previous else t.item(row,0).data(Qt.UserRole+1) or f"auto-{uuid4().hex[:8]}",scenario=self.current_key[0],year=self.current_key[1],road_category=category,road_name=val(1),start_number=val(2),start_name=val(3),direction=val(4) if val(4) in ("→","←") else "→",end_number=val(5),end_name=val(6),length_km=num(7)/1000,report_length_km=(num(17)/1000 if val(17) else None),lanes=min(10,int(num(8))),functional_class=previous.functional_class if previous else "저규격",road_condition_override=previous.road_condition_override if previous else "보통",arterial_type_override=previous.arterial_type_override if previous else "자동",cycle_s=num(10),green_s=min(num(11),num(10)),main_volume=int(round(num(12))),report_volume=(int(round(num(18))) if val(18) else None),phf=max(0,min(1,num(13))),bus_stops=previous.bus_stops if previous else 0,access_points=previous.access_points if previous else 0,intersection_los=val(19),approach_los=val(20),manual_speed_kmh=previous.manual_speed_kmh if previous else None,speed_adjustment_history=list(previous.speed_adjustment_history) if previous else [],saturation_adjustment=previous.saturation_adjustment if previous else None,initial_queue=previous.initial_queue if previous else None,pf_override=previous.pf_override if previous else None,fcw_override=previous.fcw_override if previous else None,analysis_period_h=previous.analysis_period_h if previous else None,base_saturation_flow=previous.base_saturation_flow if previous else None,coordinated=previous.coordinated if previous else None,crossing_signals=previous.crossing_signals if previous else None,blank_fields=blank,volume_source_cell=previous.volume_source_cell if previous else "",volume_source_path=previous.volume_source_path if previous else "",volume_source_sheet=previous.volume_source_sheet if previous else "",volume_link_status=previous.volume_link_status if previous else "",volume_last_value=previous.volume_last_value if previous else None,volume_link_error=previous.volume_link_error if previous else "")
    def save_current(self):
        if not self.current_key:return
        old={s.uid:s for s in self.project.rows(*self.current_key)};rows=[]
        for t,cat in ((self.external,EXTERNAL),(self.internal,INTERNAL)):
            for row in range(t.rowCount()):rows.append(self.parse_row(t,row,cat,old))
        self.project.replace_rows(*self.current_key,rows)
    def commit_row(self,t,row,col,back=False):
        if row<0:return
        self.normalize_numeric(t,row)
        self.save_current();uid=t.item(row,0).data(Qt.UserRole);s=next((x for x in self.project.segments if x.uid==uid),None)
        if s and col==12 and s.volume_link_status=="unconfirmed":s.volume_link_status="ok"
        self.propagate_dictionary(s,col);self.sync_arrival_values(s,col);self.refresh_live(t,row);self.changed.emit()
    def normalize_numeric(self,t,row):
        t.blockSignals(True)
        for c in self.INTEGER:
            raw=t.item(row,c).text().replace(",","").strip()
            if raw:
                try:t.item(row,c).setText(f"{int(round(float(raw))):,}")
                except ValueError:pass
        lanes=t.item(row,8).text().replace(",","").strip()
        if lanes:
            try:t.item(row,8).setText(f"{min(10,max(0,int(round(float(lanes))))):,}")
            except ValueError:pass
        cycle=t.item(row,10).text().replace(",","").strip();green=t.item(row,11).text().replace(",","").strip()
        if cycle and green:
            try:
                maximum=max(0,int(round(float(cycle))));value=min(maximum,max(0,int(round(float(green)))));t.item(row,11).setText(f"{value:,}")
            except ValueError:pass
        raw=t.item(row,13).text().replace(",","").strip()
        if raw:
            try:t.item(row,13).setText(f"{max(0,min(1,float(raw))):.2f}")
            except ValueError:pass
        t.blockSignals(False)
    def item_changed(self,t,item):
        if item.column() in self.NUMERIC and item.column()!=8:item.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter)
        else:item.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)
        if item.column() in (2,3,5,6):
            self.resolve_intersection(t,item);self.sync_pair(t,item)
        if item.column()==12:
            uid=t.item(item.row(),0).data(Qt.UserRole);previous=next((s for s in self.project.segments if s.uid==uid),None)
            if previous and previous.volume_source_cell:previous.volume_source_cell="";previous.volume_source_path="";previous.volume_source_sheet="";previous.volume_link_status="";previous.volume_link_error=""
        self.commit_row(t,item.row(),item.column())
    def resolve_intersection(self,t,item):
        col=item.column();number_col,name_col=(2,3) if col in (2,3) else (5,6);number=t.item(item.row(),number_col).text().strip();name=t.item(item.row(),name_col).text().strip()
        number_to_name={};name_to_number={}
        for s in self.project.segments:
            for no,nm in ((s.start_number,s.start_name),(s.end_number,s.end_name)):
                if no and nm:number_to_name.setdefault(no,nm);name_to_number.setdefault(nm,no)
        conflict=(number and name and number in number_to_name and number_to_name[number]!=name) or (number and name and name in name_to_number and name_to_number[name]!=number)
        if conflict:
            item.setBackground(QColor("#FFE5E5"));item.setToolTip("같은 교차로 번호 또는 이름에 다른 대응값이 있습니다. 기존 대응관계를 확인해 주세요.");return
        t.blockSignals(True)
        if number and not name and number in number_to_name:t.item(item.row(),name_col).setText(number_to_name[number])
        elif name and not number and name in name_to_number:t.item(item.row(),number_col).setText(name_to_number[name])
        t.blockSignals(False)
    def sync_pair(self,t,item):
        identity=t.item(item.row(),0).data(Qt.UserRole+1);t.blockSignals(True)
        for row in range(t.rowCount()):
            if row!=item.row() and t.item(row,0).data(Qt.UserRole+1)==identity:t.item(row,item.column()).setText(item.text())
        t.blockSignals(False)
    def propagate_dictionary(self,s,col):
        if not s:return
        if col==1:
            for other in self.project.segments:
                if other.comparison_id==s.comparison_id:other.road_name=s.road_name
        if col in (2,3,5,6):
            number=s.start_number if col in (2,3) else s.end_number;name=s.start_name if col in (2,3) else s.end_name
            for other in self.project.segments:
                for prefix in ("start","end"):
                    same=(number and getattr(other,f"{prefix}_number")==number) or (name and getattr(other,f"{prefix}_name")==name)
                    if same:setattr(other,f"{prefix}_number",number);setattr(other,f"{prefix}_name",name)
            self.inherit_arrival_defaults(s)
    def inherit_arrival_defaults(self,s):
        arrival=self.arrival(s);candidates=[x for x in self.project.rows(*self.current_key) if x.uid!=s.uid and self.arrival(x)==arrival]
        if not any(arrival) or not candidates:return
        cycles={x.cycle_s for x in candidates if "cycle_s" not in x.blank_fields};phfs={x.phf for x in candidates if "phf" not in x.blank_fields}
        if "cycle_s" in s.blank_fields and len(cycles)==1:s.cycle_s=cycles.pop();s.blank_fields.remove("cycle_s")
        if "phf" in s.blank_fields and len(phfs)==1:s.phf=phfs.pop();s.blank_fields.remove("phf")
        for table in (self.external,self.internal):
            table.blockSignals(True)
            for row in range(table.rowCount()):
                if table.item(row,0).data(Qt.UserRole)==s.uid:
                    if "cycle_s" not in s.blank_fields:table.item(row,10).setText(f"{round(s.cycle_s):,}")
                    if "phf" not in s.blank_fields:table.item(row,13).setText(f"{s.phf:.2f}")
            table.blockSignals(False)
    def arrival(self,s):return (s.end_number,s.end_name) if s.direction=="→" else (s.start_number,s.start_name)
    def sync_arrival_values(self,s,col):
        if not s:return
        arrival=self.arrival(s)
        if col in (10,13,19):
            for other in self.project.rows(*self.current_key):
                if self.arrival(other)==arrival:
                    if col==10:other.cycle_s=s.cycle_s;other.blank_fields=[x for x in other.blank_fields if x!="cycle_s"]
                    elif col==13:other.phf=s.phf;other.blank_fields=[x for x in other.blank_fields if x!="phf"]
                    else:other.intersection_los=s.intersection_los
    def refresh_live(self,t,row):
        uid=t.item(row,0).data(Qt.UserRole);s=next((x for x in self.project.segments if x.uid==uid),None)
        if not s:return
        try:r=analyze_segment(s,self.project.settings) if self.project.is_complete(s) else None;speed=f"{r.speed_kmh:.1f}" if r else "";los=r.los if r else "";tip="" if r else "입력 미완료"
        except Exception as exc:speed="";los="";tip=str(exc)
        t.blockSignals(True);t.item(row,14).setText(speed);t.item(row,15).setText(los)
        for c in (14,15):t.item(row,c).setToolTip(tip);t.item(row,c).setBackground(QColor("#FFF0C2" if tip else "#DDF4FF"))
        t.blockSignals(False)
    def cell_selected(self,t,row,col):
        self.refresh_network_diagram(t.item(row,0).data(Qt.UserRole) if row>=0 and t.item(row,0) else "")
        if row<0 or col!=12:self.formula.setText("Excel 연결: 교통량 셀 선택 → = → Excel 셀 클릭 → Enter  (디스크에 저장된 값 반영)");return
        self.save_current();uid=t.item(row,0).data(Qt.UserRole);s=next((x for x in self.project.segments if x.uid==uid),None);info=self.project.tab_info(*self.current_key)
        path=(s.volume_source_path if s else "") or info.get("source_path","");sheet=(s.volume_source_sheet if s else "") or info.get("source_sheet","")
        if s and s.volume_source_cell and path:
            p=Path(path);self.formula.setText(f"선택 셀 원본: ='{p.parent}\\[{p.name}]{sheet}'!${s.volume_source_cell}")
        else:self.formula.setText("선택 셀 원본: 직접 입력")

    def show_network_diagram(self):
        self.save_current()
        if self.diagram_dialog is None:
            self.diagram_dialog=NetworkDiagramDialog(self.window());self.diagram_dialog.diagram.edgeSelected.connect(self.select_diagram_edge)
        self.diagram_dialog.show();self.refresh_network_diagram();self.diagram_dialog.raise_();self.diagram_dialog.activateWindow()
    def refresh_network_diagram(self,highlight_uid=None):
        if self.diagram_dialog is None or not self.diagram_dialog.isVisible():return
        if highlight_uid is None:
            table=self.active_table();row=table.currentRow();highlight_uid=table.item(row,0).data(Qt.UserRole) if row>=0 and table.item(row,0) else ""
        rows=self.project.rows(*self.current_key) if self.current_key else []
        nodes,edges=build_network_graph(rows);title=f"{self.tab_label(self.current_key)} · 교차로 {len(nodes)}개 · 연결 구간 {len(edges)}개" if self.current_key else "구간 연결 삽도"
        self.diagram_dialog.diagram.set_segments(rows,title,highlight_uid or "")
    def select_diagram_edge(self,uids):
        uid_set={str(uid) for uid in uids};choices=[]
        for index,table in enumerate((self.external,self.internal)):
            rows=[row for row in range(table.rowCount()) if table.item(row,0) and str(table.item(row,0).data(Qt.UserRole)) in uid_set]
            if rows:choices.append((index,table,rows))
        if not choices:return
        active=self.road_tabs.currentIndex();index,table,rows=next((choice for choice in choices if choice[0]==active),choices[0]);self.road_tabs.setCurrentIndex(index)
        table.clearSelection();table.setCurrentCell(rows[0],1)
        for row in rows:
            for column in range(table.columnCount()):
                item=table.item(row,column)
                if item:item.setSelected(True)
        table.scrollToItem(table.item(rows[0],1),QAbstractItemView.PositionAtCenter);table.setFocus(Qt.OtherFocusReason);self.refresh_network_diagram(uid_set)

    def replace_excel_sources(self,t):
        rows=sorted({index.row() for index in t.selectedIndexes()})
        if not rows:QMessageBox.information(self,"연결 경로 일괄 변경","변경할 교통량 셀들을 먼저 선택해 주세요.");return
        self.save_current();uids={t.item(row,0).data(Qt.UserRole) for row in rows};segments=[s for s in self.project.rows(*self.current_key) if s.uid in uids and s.volume_source_cell]
        if not segments:QMessageBox.information(self,"연결 경로 일괄 변경","선택 범위에 Excel 연결 교통량 셀이 없습니다.");return
        info=self.project.tab_info(*self.current_key);recent=segments[0].volume_source_path or info.get("source_path","")
        path,_=QFileDialog.getOpenFileName(self,"선택 연결의 새 Excel 원본",recent,"Excel 통합문서 (*.xlsx *.xls *.xlsm *.xlsb)")
        if not path:return
        try:sheets=list_sheets(path)
        except Exception as exc:QMessageBox.critical(self,"Excel 원본 변경 실패",str(exc));return
        default=segments[0].volume_source_sheet or info.get("source_sheet","");initial=max(0,sheets.index(default)) if default in sheets else 0
        sheet,ok=QInputDialog.getItem(self,"시트 선택","새 원본 시트",sheets,initial,False)
        if not ok or not sheet:return
        resolved=str(Path(path).resolve())
        for s in segments:s.volume_source_path=resolved;s.volume_source_sheet=sheet;s.volume_link_status="unconfirmed";s.volume_link_error=""
        QSettings("NYH","ArterialAnalysis").setValue("recentExcelPath",resolved);self.load_key(self.current_key);self.changed.emit();self.formula.setText(f"선택한 Excel 연결 {len(segments)}개 경로를 변경했습니다. F5로 값을 불러오세요.")
    def add_pair(self):
        t=self.active_table();scenario,year=self.current_key;identity=f"auto-{uuid4().hex[:8]}";common=dict(comparison_id=identity,scenario=scenario,year=year,road_category=INTERNAL if t is self.internal else EXTERNAL,length_km=0,cycle_s=0,green_s=0,main_volume=0,report_volume=None,phf=1.0,lanes=0,functional_class="저규격",road_condition_override="보통",arterial_type_override="자동",blank_fields=["length_km","lanes","cycle_s","green_s","main_volume"])
        t.blockSignals(True);self.append_segment(t,SegmentInput(uid=uuid4().hex,direction="→",**common));self.append_segment(t,SegmentInput(uid=uuid4().hex,direction="←",**common));self.merge_pairs(t);t.blockSignals(False);t._update_frozen_geometry();t.setCurrentCell(t.rowCount()-2,1);t.editItem(t.item(t.rowCount()-2,1));self.changed.emit()
    def selected_rows(self):
        t=self.active_table();ids={t.item(r,0).data(Qt.UserRole+1) for r in range(t.rowCount()) if t.item(r,0).checkState()==Qt.Checked};return [r for r in range(t.rowCount()) if t.item(r,0).data(Qt.UserRole+1) in ids]
    def copy_selected(self):
        rows=self.selected_rows();t=self.active_table()
        if not rows:QMessageBox.information(self,"구간 복사","복사할 구간을 체크해 주세요.");return
        self.save_current();uids={t.item(r,0).data(Qt.UserRole) for r in rows};self._clipboard=[s.to_dict() for s in self.project.rows(*self.current_key) if s.uid in uids]
    def paste_selected(self):
        if not self._clipboard:QMessageBox.information(self,"구간 붙여넣기","먼저 구간을 복사해 주세요.");return
        t=self.active_table();ids={};scenario,year=self.current_key;t.blockSignals(True)
        for data in self._clipboard:
            s=SegmentInput.from_dict(data);s.uid=uuid4().hex;s.comparison_id=ids.setdefault(s.comparison_id,f"auto-{uuid4().hex[:8]}");s.scenario=scenario;s.year=year;s.road_category=INTERNAL if t is self.internal else EXTERNAL;s.manual_speed_kmh=None;s.speed_adjustment_history=[];self.append_segment(t,s)
        self.merge_pairs(t);t.blockSignals(False);t._update_frozen_geometry();self.changed.emit()
    def delete_selected(self):
        t=self.active_table();rows=self.selected_rows()
        if not rows:QMessageBox.information(self,"행 삭제","삭제할 행을 체크해 주세요.");return
        for r in reversed(rows):t.removeRow(r)
        self.merge_pairs(t);self.save_current();self.changed.emit()
    def reset_selected(self):
        t=self.active_table();rows=self.selected_rows()
        if not rows:QMessageBox.information(self,"초기화","초기화할 행을 체크해 주세요.");return
        for r in rows:
            for c in (7,8,10,11,12,17,18,19,20):t.item(r,c).setText("")
            t.item(r,13).setText("1.00")
        self.save_current();self.changed.emit()
    def edit_details(self,uid):
        self.save_current();s=next((x for x in self.project.segments if x.uid==uid),None)
        if not s:return
        d=FastDetailDialog(s,self.project,self)
        if d.exec()==QDialog.Accepted:d.apply_to_segment();self.load_key(self.current_key);self.changed.emit()
    def toggle_optional(self):
        t=self.active_table();show=t.isColumnHidden(17)
        for table in (self.external,self.internal):
            for c in (17,18,19,20):table.setColumnHidden(c,not show)
        self.optional.setText("보조 입력 접기 (F7)" if show else "보조 입력 펼치기 (F7)")
    def toggle_compare(self):
        if self.compare_bar.isVisible():self.compare_bar.hide();return
        self.save_current();scenario,year=self.current_key;before={"사업 시행시":"사업 미시행시","개선대책 이행시":"사업 시행시"}.get(scenario)
        if not before:self.compare_bar.setText("F8 비교는 시행 탭 또는 개선 탭에서 같은 연도의 앞 상황과 비교합니다.");self.compare_bar.show();return
        current=self.project.rows(scenario,year);past={(s.comparison_id,s.direction):s for s in self.project.rows(before,year)};parts=[]
        for s in current[:6]:
            a=past.get((s.comparison_id,s.direction))
            if not a:continue
            try:ar=analyze_segment(a,self.project.settings);br=analyze_segment(s,self.project.settings);parts.append(f"{s.road_name} {s.direction}: 교통량 {a.main_volume:,.0f}→{s.main_volume:,.0f}, 평균통행속도 {ar.speed_kmh:.1f}→{br.speed_kmh:.1f}, LOS {ar.los}→{br.los}")
            except Exception:continue
        self.compare_bar.setText("   |   ".join(parts) if parts else "같은 연도의 비교 가능한 완성 구간이 없습니다.");self.compare_bar.show()
    def choose_excel(self):
        info=self.project.tab_info(*self.current_key);settings=QSettings("NYH","ArterialAnalysis")
        recent=info.get("source_path","") or str(settings.value("recentExcelPath","") or "")
        start=recent if recent and Path(recent).exists() else (str(Path(recent).parent) if recent else "")
        path,_=QFileDialog.getOpenFileName(self,"교통량 원본 Excel 선택",start,"Excel 통합문서 (*.xlsx *.xls *.xlsm *.xlsb)")
        if not path:return
        try:sheets=list_sheets(path)
        except Exception as exc:QMessageBox.critical(self,"Excel 연결 실패",str(exc));return
        resolved=str(Path(path).resolve());settings.setValue("recentExcelPath",resolved);info.update(source_path=resolved,source_relative="",source_sheet=sheets[0] if sheets else "",source_sheets=sheets,source_mtime=Path(path).stat().st_mtime)
        for s in self.project.rows(*self.current_key):
            if s.volume_source_cell:s.volume_link_status="unconfirmed";s.volume_link_error=""
        self.update_source_bar();self.changed.emit()
    def update_source_bar(self):
        if not self.current_key:return
        info=self.project.tab_info(*self.current_key);path=info.get("source_path","");self.source_label.setText(f"교통량 원본: {Path(path).name}" if path else "교통량 원본: 연결 안 됨")
        self.sheet.blockSignals(True);self.sheet.clear()
        if path and Path(path).exists():
            try:self.sheet.addItems(info.get("source_sheets") or list_sheets(path));self.sheet.setCurrentText(info.get("source_sheet",""))
            except Exception:pass
        self.sheet.blockSignals(False)
    def sheet_changed(self,name):
        if not name or not self.current_key:return
        info=self.project.tab_info(*self.current_key)
        if info.get("source_sheet")==name:return
        info["source_sheet"]=name
        for s in self.project.rows(*self.current_key):
            if s.volume_source_cell:s.volume_link_status="unconfirmed"
        self.changed.emit()
    def open_excel(self):
        info=self.project.tab_info(*self.current_key);path=info.get("source_path","")
        if not path:QMessageBox.information(self,"원본 열기","먼저 Excel 원본을 선택해 주세요.");return
        try:open_and_activate(path,info.get("source_sheet",""))
        except Exception as exc:QMessageBox.critical(self,"원본 열기 실패",str(exc))
    def start_link(self,t,row):
        if hasattr(self,"_link_timer") and self._link_timer.isActive():
            self.formula.setText("이미 Excel 셀 연결을 기다리는 중입니다. Excel에서 셀을 선택하고 Enter를 누르세요.");return
        info=self.project.tab_info(*self.current_key)
        if not info.get("source_path"):
            self.choose_excel();info=self.project.tab_info(*self.current_key)
            if not info.get("source_path"):return
        self.formula.setText("연결 대기: Excel에서 연결할 셀을 선택한 뒤 Enter를 누르세요.")
        try:open_and_activate(info["source_path"],info.get("source_sheet",""))
        except Exception as exc:QMessageBox.critical(self,"Excel 연결 실패",str(exc));return
        self._link_table=t;self._link_row=row;self._enter_was_down=False;self._pending_selection=None;self._link_timer=QTimer(self);self._link_timer.timeout.connect(self.poll_link);self._link_timer.start(30)
    def poll_link(self):
        down=bool(ctypes.windll.user32.GetAsyncKeyState(0x0D)&0x8000)
        if down:self._enter_was_down=True;return
        if not self._enter_was_down:
            try:self._pending_selection=active_selection()
            except Exception:pass
            return
        self._link_timer.stop()
        try:path,sheet,address,saved=self._pending_selection or active_selection()
        except Exception as exc:QMessageBox.warning(self,"셀 연결",str(exc));return
        info=self.project.tab_info(*self.current_key);info.update(source_path=path,source_sheet=sheet,source_mtime=Path(path).stat().st_mtime)
        try:value,address=read_saved_cell(path,sheet,address)
        except Exception as exc:QMessageBox.warning(self,"셀값 오류",str(exc));return
        self.save_current();uid=self._link_table.item(self._link_row,0).data(Qt.UserRole);s=next(x for x in self.project.segments if x.uid==uid);default_path=info.get("source_path","");default_sheet=info.get("source_sheet","");s.main_volume=value;s.volume_source_cell=address;s.volume_source_path="" if str(Path(path).resolve()).lower()==str(Path(default_path).resolve()).lower() else path;s.volume_source_sheet="" if sheet==default_sheet and not s.volume_source_path else sheet;s.volume_last_value=value;s.volume_link_status="ok" if saved else "last_saved";s.volume_link_error="";s.blank_fields=[x for x in s.blank_fields if x!="main_volume"]
        self.load_key(self.current_key);self._link_table.setCurrentCell(min(self._link_row+1,self._link_table.rowCount()-1),12);window=self.window();window.showNormal();window.raise_();window.activateWindow();self.changed.emit()
    def refresh_links(self):
        if not self.current_key:return
        self.save_current();info=self.project.tab_info(*self.current_key);path=info.get("source_path","");sheet=info.get("source_sheet","")
        groups={}
        for s in self.project.rows(*self.current_key):
            if s.volume_source_cell:
                source=(s.volume_source_path or path,s.volume_source_sheet or sheet);groups.setdefault(source,[]).append(s)
        for (source_path,source_sheet),segments in groups.items():
            if not source_path or not source_sheet:
                for s in segments:s.volume_link_error="연결 오류: 원본 파일 또는 시트가 지정되지 않았습니다."
                continue
            try:values=read_saved_cells(source_path,source_sheet,[s.volume_source_cell for s in segments])
            except Exception as exc:
                for s in segments:s.volume_link_error=f"연결 오류: {exc}"
                continue
            for s in segments:
                cell=normalize_cell(s.volume_source_cell)
                value,address,error=values.get(cell,(None,cell,"셀을 찾을 수 없습니다."))
                if error:s.volume_link_error=f"연결 오류: {error}";continue
                s.main_volume=value;s.volume_last_value=value;s.volume_source_cell=address;s.volume_link_error="";s.volume_link_status="ok";s.blank_fields=[x for x in s.blank_fields if x!="main_volume"]
        self.load_key(self.current_key);self.changed.emit()


class Workflow(QWidget):
    changed=Signal()
    def __init__(self,project):
        super().__init__();self.project=project;self.results=[];layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);self.steps=QLabel();self.steps.setObjectName("stepBar");layout.addWidget(self.steps);self.stack=QStackedWidget();layout.addWidget(self.stack,1);self.input=InputPage(project);self.results_page=ResultsPage();from .app_v2 import DetailPage;self.detail_page=DetailPage()
        for page in (self.input,self.results_page,self.detail_page):self.stack.addWidget(page)
        self.input.next_button.clicked.connect(lambda:self.go(1));self.results_page.back.clicked.connect(lambda:self.go(0));self.results_page.detail.clicked.connect(lambda:self.go(2));self.detail_page.back.clicked.connect(lambda:self.go(1));self.detail_page.input.clicked.connect(lambda:self.go(0));self.input.changed.connect(self.changed);self.results_page.changed.connect(self.changed);self.go(0)
    def load_project(self,p):self.project=p;self.input.project=p;self.input.current_key=None;self.input.refresh_tabs();self.go(0)
    def commit(self):self.input.save_current()
    def go(self,index):
        if self.stack.currentIndex()==0:self.commit()
        if index>=1:self.results=self.project.analyze_all();self.results_page.refresh(self.project,self.results)
        if index==2:self.detail_page.refresh(self.project,self.results)
        self.stack.setCurrentIndex(index);labels=["○ 구간 입력","○ 분석 결과","○ 세부 계산결과"];labels[index]=labels[index].replace("○","●");self.steps.setText("     ".join(labels))


class ShortcutDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle("키보드 단축키");self.setMinimumWidth(560);layout=QVBoxLayout(self);layout.addWidget(QLabel("Enter / Tab : 입력 확정 후 다음 셀\nShift+Enter / Shift+Tab : 이전 셀\n방향키 : 셀 이동    F2 : 셀 편집    Delete : 내용 지우기\nCtrl+C / V / X : 범위 복사·붙여넣기·잘라내기\nCtrl+D / Ctrl+R : 아래/오른쪽 채우기\nCtrl+H : 선택한 Excel 연결 셀의 파일·시트 경로 일괄 변경\nCtrl+PageUp / PageDown : 분석 탭 이동\nCtrl+T : 분석 탭 추가    Ctrl+숫자패드 +/- : 구간 추가/삭제\n= : 선택 교통량 셀을 Excel 셀에 연결\nF5 : Excel 저장값 일괄 새로고침    F6 : 구간 연결 삽도\nF7 : 보조 입력 열    F8 : 같은 연도 간이 비교"));b=QDialogButtonBox(QDialogButtonBox.Close);b.button(QDialogButtonBox.Close).setText("닫기");b.rejected.connect(self.reject);layout.addWidget(b)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__();load_font();self.project=blank_project();self.path=None;self.dirty=False;self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}");self.resize(1360,840);self.setMinimumSize(960,650);icon=resource_path("assets/arterial-analysis-icon.ico");self.setWindowIcon(QIcon(icon)) if Path(icon).exists() else None
        self.tabs=QTabWidget();self.workflow=Workflow(self.project);self.tabs.addTab(self.workflow,"분석");self.tabs.addTab(GuidelinePage(),"지침·공식");self.setCentralWidget(self.tabs);self.workflow.changed.connect(self.mark_dirty)
        menu=self.menuBar().addMenu("프로젝트")
        for label,slot,shortcut in (("새 프로젝트",self.new,"Ctrl+N"),("열기",self.open,"Ctrl+O"),("저장",self.save,"Ctrl+S"),("다른 이름으로 저장",self.save_as,"Ctrl+Shift+S")):
            a=QAction(label,self);a.setShortcut(shortcut);a.triggered.connect(slot);menu.addAction(a)
        help_menu=self.menuBar().addMenu("도움말");short=QAction("키보드 단축키",self);short.setShortcut("F1");short.triggered.connect(lambda:ShortcutDialog(self).exec());help_menu.addAction(short)
        self.updater=UpdateController(APP_VERSION,self);update_action=QAction("업데이트 확인",self);update_action.triggered.connect(lambda:self.updater.check(True));help_menu.addAction(update_action)
        about=QAction("프로그램 정보",self);about.triggered.connect(self.show_about);help_menu.addAction(about)
        if QGuiApplication.platformName().lower()!="offscreen":QTimer.singleShot(2500,lambda:self.updater.check(False))
        QShortcut(QKeySequence("Ctrl+T"),self,activated=self.add_tab_shortcut);QShortcut(QKeySequence("Ctrl+PgDown"),self,activated=lambda:self.move_analysis_tab(1));QShortcut(QKeySequence("Ctrl+PgUp"),self,activated=lambda:self.move_analysis_tab(-1));self.statusBar().showMessage(f"{APP_NAME} v{APP_VERSION}   ·   {APP_AUTHOR}   ·   {APP_EMAIL}")
    def add_tab_shortcut(self):self.workflow.input.analysis_tabs.setCurrentIndex(self.workflow.input.analysis_tabs.count()-1)
    def move_analysis_tab(self,delta):
        bar=self.workflow.input.analysis_tabs;count=max(1,bar.count()-1);bar.setCurrentIndex((bar.currentIndex()+delta)%count)
    def show_about(self):QMessageBox.about(self,"프로그램 정보",f"<h2>{APP_NAME}</h2><p>v{APP_VERSION}</p><p>도로용량편람(2013) 기반</p><p>{APP_AUTHOR}<br>{APP_EMAIL}</p>")
    def new(self):
        if not self.confirm_discard():return
        d=AddTabDialog(self,"현황",self.project.current_year,True)
        if d.exec()!=QDialog.Accepted:return
        self.project=blank_project(d.year.value());self.path=None;self.workflow.load_project(self.project);self.dirty=False;self.update_title()
    def open(self):
        if not self.confirm_discard():return
        path,_=QFileDialog.getOpenFileName(self,"프로젝트 열기","",PROJECT_FILTER)
        if not path:return
        try:self.project=ArterialProject.load(path);self.path=path;self.resolve_sources();self.workflow.load_project(self.project);self.dirty=False;self.update_title()
        except Exception as exc:QMessageBox.critical(self,"열기 실패",str(exc))
    def save(self):
        if not self.path:return self.save_as()
        try:
            self.workflow.commit();base=Path(self.path).resolve().parent
            for info in self.project.analysis_tabs:
                if info.get("source_path"):
                    try:info["source_relative"]=str(Path(info["source_path"]).resolve().relative_to(base))
                    except ValueError:info["source_relative"]=""
            self.project.save(self.path);self.dirty=False;self.update_title();self.statusBar().showMessage("프로젝트를 저장했습니다.",4000);return True
        except Exception as exc:QMessageBox.critical(self,"저장 실패",str(exc));return False
    def save_as(self):
        path,_=QFileDialog.getSaveFileName(self,"프로젝트 저장","도시교외간선도로분석.ara1",PROJECT_FILTER)
        if not path:return False
        self.path=path if path.lower().endswith(".ara1") else path+".ara1";return self.save()
    def mark_dirty(self):self.dirty=True;self.update_title();self.statusBar().showMessage("저장되지 않은 변경사항이 있습니다.")
    def resolve_sources(self):
        if not self.path:return
        base=Path(self.path).resolve().parent
        for info in self.project.analysis_tabs:
            raw=info.get("source_path","");candidate=Path(raw) if raw else Path()
            if raw and candidate.exists():continue
            relative=info.get("source_relative","");rel_candidate=base/relative if relative else None
            if rel_candidate and rel_candidate.exists():info["source_path"]=str(rel_candidate.resolve());continue
            if raw:
                matches=list(base.rglob(Path(raw).name))
                if len(matches)==1:info["source_path"]=str(matches[0].resolve())
    def event(self,event):
        result=super().event(event)
        if event.type()==QEvent.WindowActivate and hasattr(self,"workflow") and self.workflow.input.current_key:
            info=self.project.tab_info(*self.workflow.input.current_key);path=info.get("source_path","")
            if path and Path(path).exists():
                mtime=Path(path).stat().st_mtime
                if info.get("source_mtime") not in (None,mtime):info["source_mtime"]=mtime;QTimer.singleShot(0,self.workflow.input.refresh_links)
        return result
    def update_title(self):self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}{' *' if self.dirty else ''}"+(f" - {Path(self.path).name}" if self.path else ""))
    def confirm_discard(self):
        if not self.dirty:return True
        box=QMessageBox(self);box.setWindowTitle("저장 확인");box.setText("분석 결과와 변경사항이 저장되지 않았습니다. 지금 저장하시겠습니까?");box.setStandardButtons(QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel);box.button(QMessageBox.Save).setText("저장");box.button(QMessageBox.Discard).setText("저장안함");box.button(QMessageBox.Cancel).setText("취소");answer=box.exec();return bool(self.save()) if answer==QMessageBox.Save else answer==QMessageBox.Discard
    def closeEvent(self,event):
        focus=QApplication.focusWidget()
        if focus:focus.clearFocus()
        try:self.workflow.commit()
        except Exception:pass
        event.accept() if self.confirm_discard() else event.ignore()


FAST_STYLE=STYLE+"""
QLabel#formulaBar{background:#FFFFFF;border:1px solid #D9E2EC;border-radius:6px;padding:6px 10px;color:#475569}
QLabel#shortcutBar{background:#172033;color:white;border-radius:6px;padding:6px 10px;font-size:9pt}
QLabel#compareBar{background:#E8F5E9;color:#176B3A;border:1px solid #8AC9A4;border-radius:7px;padding:7px 10px}
"""
def apply_light_palette(app):
    p=QPalette()
    for role,color in ((QPalette.Window,"#F5F7FA"),(QPalette.WindowText,"#172033"),(QPalette.Base,"#FFFFFF"),(QPalette.Text,"#172033"),(QPalette.Button,"#FFFFFF"),(QPalette.ButtonText,"#172033"),(QPalette.Highlight,"#DCEBFF"),(QPalette.HighlightedText,"#1261C9"),(QPalette.ToolTipBase,"#FFFFFF"),(QPalette.ToolTipText,"#172033")):p.setColor(role,QColor(color))
    app.setPalette(p)
def main():
    QApplication.setAttribute(Qt.AA_DontUseNativeDialogs,True);app=QApplication(sys.argv);app.setStyle("Fusion");apply_light_palette(app);load_font();app.setApplicationName(APP_NAME);app.setApplicationVersion(APP_VERSION);app.setStyleSheet(FAST_STYLE);w=MainWindow();w.show();return app.exec()
