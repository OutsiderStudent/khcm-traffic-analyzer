"""2026 physical road editor. Coordinates are layout only, never measured distances."""
import math
from copy import deepcopy
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QShortcut, QKeySequence
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QGraphicsView,QGraphicsScene,
    QGraphicsEllipseItem,QGraphicsPathItem,QGraphicsItem,QInputDialog,QMenu,QMessageBox,QDialogButtonBox,
    QFormLayout,QDoubleSpinBox,QSpinBox,QLineEdit,QComboBox)
from . import road_network as model


def half_arrows(a,b):
    dx,dy=b.x()-a.x(),b.y()-a.y();length=math.hypot(dx,dy)
    if length<1:return []
    u=QPointF(dx/length,dy/length);right=QPointF(-u.y(),u.x());mid=(a+b)/2
    # Screen Y points down: for eastbound travel the right lane is below the road centre.
    result=[]
    for sign in (1,-1):
        center=mid+right*(12*sign);tip=center+u*(19*sign);tail=center-u*(19*sign)
        wing=tip-u*(9*sign)+right*(6*sign)
        result.append((tail,tip,wing))
    return result


class NodeItem(QGraphicsEllipseItem):
    def __init__(self,editor,node,index):
        super().__init__(-25,-25,50,50);self.editor=editor;self.uid=node['id']
        self.setFlags(QGraphicsItem.ItemIsMovable|QGraphicsItem.ItemIsSelectable|QGraphicsItem.ItemSendsGeometryChanges)
        self.setBrush(QColor('#EFF6FF'));self.setPen(QPen(QColor('#2563EB'),2));self.setZValue(3)
        self.setPos(node['x'],node['y']);self.setToolTip(node['name'])
        number=editor.scene.addText(str(index));number.setParentItem(self);number.setDefaultTextColor(QColor('#163967'));number.setPos(-number.boundingRect().width()/2,-number.boundingRect().height()/2)
        label=editor.scene.addText(node['name']);label.setParentItem(self);label.setDefaultTextColor(QColor('#163967'));label.setPos(-label.boundingRect().width()/2,27)
    def itemChange(self,change,value):
        if change==QGraphicsItem.ItemPositionHasChanged and hasattr(self.editor,'nodes'):
            self.editor.update_lines()
        return super().itemChange(change,value)
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and (event.modifiers()&Qt.ControlModifier or self.editor.mode):
            self.editor.node_click(self.uid,bool(event.modifiers()&Qt.ControlModifier));event.accept();return
        self.editor.selected_node=self.uid;super().mousePressEvent(event)
    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event)
        node=model.node_by_id(self.editor.net,self.uid)
        if (node['x'],node['y'])!=(self.pos().x(),self.pos().y()):
            node['x'],node['y']=self.pos().x(),self.pos().y();self.editor.save(False)
    def mouseDoubleClickEvent(self,event):self.editor.rename_node(self.uid);event.accept()


class EdgeItem(QGraphicsPathItem):
    def __init__(self,editor,edge):
        super().__init__();self.editor=editor;self.edge=edge;self.setZValue(1)
        self.setFlags(QGraphicsItem.ItemIsSelectable);self.setPen(QPen(QColor('#2563EB'),2));self.setToolTip('더블클릭: 양방향 구간 정보')
    def boundingRect(self):return super().boundingRect().adjusted(-105,-55,105,55)
    def paint(self,painter,option,widget=None):
        a=self.editor.nodes[self.edge['a']].pos();b=self.editor.nodes[self.edge['b']].pos()
        color=QColor('#D97706') if self.isSelected() else QColor('#2563EB')
        painter.setPen(QPen(color,2));painter.drawLine(a,b)
        for tail,tip,wing in half_arrows(a,b):painter.drawLine(tail,tip);painter.drawLine(tip,wing)
        mid=(a+b)/2;label=f"{self.edge['name']}  {self.edge['length']:g} m".strip()
        rect=QRectF(mid.x()-100,mid.y()-48,200,24)
        painter.fillRect(rect,QColor('white'));painter.drawText(rect,Qt.AlignCenter,label)
    def mousePressEvent(self,event):self.editor.selected_edge=self.edge['id'];super().mousePressEvent(event)
    def mouseDoubleClickEvent(self,event):self.editor.edit_edge(self.edge['id']);event.accept()


class NetworkView(QGraphicsView):
    def __init__(self,editor):
        super().__init__(editor.scene);self.editor=editor;self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag);self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setMouseTracking(True);self.setBackgroundBrush(QColor('#FFFFFF'))
    def wheelEvent(self,event):
        self.editor.zoom(1.15 if event.angleDelta().y()>0 else 1/1.15);event.accept()
    def mouseMoveEvent(self,event):
        if self.editor.mode=='connect' and self.editor.chain:
            a=self.editor.nodes[self.editor.chain[0]].pos();b=self.mapToScene(event.position().toPoint())
            self.editor.preview.setLine(a.x(),a.y(),b.x(),b.y());self.editor.preview.show()
        super().mouseMoveEvent(event)
    def contextMenuEvent(self,event):
        pos=self.mapToScene(event.pos());item=self.itemAt(event.pos())
        while item is not None and not isinstance(item,(NodeItem,EdgeItem)):item=item.parentItem()
        menu=QMenu(self)
        if isinstance(item,NodeItem):
            menu.addAction('이름 변경',lambda:self.editor.rename_node(item.uid))
            menu.addAction('여기서 연결',lambda:self.editor.start_at(item.uid))
            menu.addAction('교차로 삭제',lambda:self.editor.delete_node(item.uid))
        elif isinstance(item,EdgeItem):
            menu.addAction('양방향 구간 편집',lambda:self.editor.edit_edge(item.edge['id']))
            menu.addAction('교차로 삽입',lambda:self.editor.insert_at(item.edge['id']))
            menu.addAction('연결 삭제',lambda:self.editor.delete_edge(item.edge['id']))
        else:menu.addAction('교차로 추가',lambda:self.editor.add_node(pos))
        menu.exec(event.globalPos())


class RoadNetworkDialog(QDialog):
    def __init__(self,page):
        super().__init__(page.window());self.page=page;self.net=None;self.nodes={};self.edges=[]
        self.mode='';self.chain=[];self.selected_node=None;self.selected_edge=None
        self.setWindowTitle('구간 연결 관계도 · 2026');self.resize(1100,760);self.setMinimumSize(700,500)
        layout=QVBoxLayout(self);bar=QHBoxLayout()
        for title,fn in [('교차로 추가',lambda:self.add_node()),('연결',lambda:self.set_mode('connect')),
            ('경로 선택',lambda:self.set_mode('path')),('경로 확정',self.finish_path),('입력표 가져오기',self.import_current)]:
            b=QPushButton(title);b.clicked.connect(fn);bar.addWidget(b)
        layout.addLayout(bar)
        self.status=QLabel('한 선은 양방향입니다. Ctrl+클릭으로 연결 · 원을 끌어 배치 · 더블클릭으로 편집 · 우클릭으로 삽입·삭제')
        self.status.setWordWrap(True);layout.addWidget(self.status)
        self.scene=QGraphicsScene(self);self.view=NetworkView(self);layout.addWidget(self.view,1)
        footer=QHBoxLayout();self.percent=QLabel('100%')
        for title,fn in [('한눈에 보기',self.fit),('-',lambda:self.zoom(1/1.15)),('100%',self.reset_zoom),('+',lambda:self.zoom(1.15)),('실행 취소',page.window().undo_project),('다시 실행',page.window().redo_project)]:
            b=QPushButton(title);b.clicked.connect(fn);footer.addWidget(b)
        footer.addWidget(self.percent);layout.addLayout(footer)
        arrange=QPushButton('자동 배치');arrange.clicked.connect(self.arrange);footer.insertWidget(1,arrange)
        for seq,fn in [('Escape',lambda:self.set_mode('')),('Ctrl+Z',page.window().undo_project),('Ctrl+Y',page.window().redo_project),('Ctrl+S',page.window().save)]:
            s=QShortcut(QKeySequence(seq),self);s.activated.connect(fn)
    def load(self):
        c=self.page.current()
        if c is None:self.hide();return
        self.net=next((n for n in self.page.project.networks_2026 if (n['scenario'],n['year'],n['category'])==(c.scenario,c.year,c.road_category)),None)
        if self.net is None:
            self.net=model.new_network(c.scenario,c.year,c.road_category)
        self.setWindowTitle(f"구간 연결 관계도 · {c.scenario}({c.year}) · {c.road_category}")
        self.set_mode('');self.draw()
    def save(self,sync=True):
        if not any(n['id']==self.net['id'] for n in self.page.project.networks_2026):self.page.project.networks_2026.append(self.net)
        if sync:model.synchronize(self.page.project,self.net)
        self.saving=True
        try:
            index=self.page.selector.currentIndex();self.page.load_project(self.page.project);self.page.selector.setCurrentIndex(index)
            self.page.changed.emit()
        finally:self.saving=False
    def draw(self):
        self.nodes={};self.edges=[];self.scene.clear()
        for i,n in enumerate(self.net['nodes'],1):
            item=NodeItem(self,n,i);self.scene.addItem(item);self.nodes[n['id']]=item
        for e in self.net['edges']:
            item=EdgeItem(self,e);self.scene.addItem(item);self.edges.append(item)
        self.preview=self.scene.addLine(0,0,0,0,QPen(QColor('#64748B'),2,Qt.DashLine));self.preview.hide()
        self.update_lines()
    def update_lines(self):
        for edge in self.edges:
            a=self.nodes[edge.edge['a']].pos();b=self.nodes[edge.edge['b']].pos()
            path=QPainterPath(a);path.lineTo(b);edge.setPath(path);edge.update()
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-180,-150,180,150))
    def set_mode(self,mode):
        self.mode=mode;self.chain=[]
        if hasattr(self,'preview'):
            try:self.preview.hide()
            except RuntimeError:pass
        if mode:self.status.setText('진행 순서대로 교차로를 클릭하세요. Esc: 취소'+(' · 마지막에 경로 확정' if mode=='path' else ' · 연결 시 양방향 생성'))
    def start_at(self,uid):self.set_mode('connect');self.node_click(uid)
    def node_click(self,uid,control=False):
        self.selected_node=uid
        if control and self.mode!='connect':self.set_mode('connect')
        if not self.mode:return
        if uid in self.chain:self.status.setText('다른 교차로를 선택하세요.');return
        self.chain.append(uid)
        self.nodes[uid].setSelected(True)
        if self.mode=='connect' and len(self.chain)==2:
            a,b=self.chain;self.set_mode('');self.connect_nodes(a,b)
        elif self.mode=='path':self.status.setText(' → '.join(model.node_by_id(self.net,n)['name'] for n in self.chain))
    def add_node(self,pos=None):
        name,ok=QInputDialog.getText(self,'교차로 추가','교차로명')
        if not ok or not name.strip():return
        pos=pos or self.view.mapToScene(self.view.viewport().rect().center())+QPointF(len(self.nodes)*45,len(self.nodes)*35)
        model.add_intersection(self.net,name,pos.x(),pos.y());self.save(False);self.draw()
    def rename_node(self,uid):
        node=model.node_by_id(self.net,uid);name,ok=QInputDialog.getText(self,'교차로 이름','교차로명',text=node['name'])
        if ok and name.strip():node['name']=name.strip();self.save();self.draw()
    def road_form(self,edge):
        dlg=QDialog(self);dlg.setWindowTitle('양방향 구간 정보');layout=QVBoxLayout(dlg);form=QFormLayout();layout.addLayout(form)
        name=QLineEdit(edge.get('name',''));form.addRow('가로명',name)
        length=QDoubleSpinBox();length.setRange(0,100000);length.setValue(edge.get('length',0));length.setSuffix(' m');form.addRow('구간길이',length)
        speed=QDoubleSpinBox();speed.setRange(0,200);speed.setValue(edge.get('speed',0));speed.setSuffix(' km/h');form.addRow('제한속도',speed)
        fields={}
        for direction,a,b in [('ab',edge['a'],edge['b']),('ba',edge['b'],edge['a'])]:
            data=edge.get(direction,model.direction_data())
            form.addRow(QLabel(f"{model.node_by_id(self.net,a)['name']} → {model.node_by_id(self.net,b)['name']}"))
            lanes=QSpinBox();lanes.setRange(0,20);lanes.setSpecialValueText('미입력');lanes.setValue(data['lanes'])
            delay=QDoubleSpinBox();delay.setRange(-1,100000);delay.setSpecialValueText('미입력');delay.setValue(-1 if data['delay'] is None else data['delay'])
            cap=QDoubleSpinBox();cap.setRange(-1,100000);cap.setSpecialValueText('미입력');cap.setValue(-1 if data['capacity'] is None else data['capacity'])
            approach=QLineEdit(data['approach']);move=QComboBox();move.addItems(['직진','좌회전','우회전']);move.setCurrentText(data['movement'])
            for title,w in [('종점 접근 방향',approach),('이동류',move),('직진 가능 차로수',lanes),('평균접근지체(초)',delay),('용량(대/시)',cap)]:form.addRow(title,w)
            fields[direction]=(lanes,delay,cap,approach,move)
        note=QLabel('값은 각 진행방향의 종점 교차로 기준입니다. 회전 이동류는 관계도에 저장할 수 있지만 2026 직진 경로 분석에는 사용할 수 없습니다.');note.setWordWrap(True);layout.addWidget(note)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject);layout.addWidget(buttons)
        if dlg.exec()!=QDialog.Accepted:return None
        if length.value()<=0 or speed.value()<=0:self.status.setText('길이와 제한속도를 입력하세요.');return None
        out=deepcopy(edge);out.update(name=name.text(),length=length.value(),speed=speed.value())
        for key,(lanes,delay,cap,approach,move) in fields.items():out[key]=dict(lanes=lanes.value(),delay=None if delay.value()<0 else delay.value(),capacity=None if cap.value()<0 else cap.value(),approach=approach.text(),movement=move.currentText())
        return out
    def connect_nodes(self,a,b):
        if any({e['a'],e['b']}=={a,b} for e in self.net['edges']):self.status.setText('이미 연결되어 있습니다. 선을 더블클릭해 편집하세요.');return
        values=self.road_form(dict(a=a,b=b))
        if values is None:return
        edge=model.connect(self.net,a,b,values['length'],values['speed']);edge.update(values)
        # Each physical link has both directed subsegments. Combined routes are selected separately.
        for path in ([dict(edge=edge['id'],reverse=False)],[dict(edge=edge['id'],reverse=True)]):
            try:
                start,end=(a,b) if not path[0]['reverse'] else (b,a)
                c=model.corridor_from_path(self.net,path,f"{model.node_by_id(self.net,start)['name']} → {model.node_by_id(self.net,end)['name']}")
                self.page.project.corridors_2026.append(c.to_dict())
            except ValueError:pass
        self.save();self.draw();self.status.setText('양방향 구간을 만들었습니다. 여러 구간을 분석하려면 경로 선택 → 교차로 순서 선택 → 경로 확정. 적용 조건 확인 전에는 분석되지 않습니다.')
    def confirm_impact(self,text):
        return QMessageBox.question(self,'연결 자료 변경',text+'\n연결된 분석구간은 재분석이 필요합니다. 경로·길이가 바뀌면 기존 구간 통행시간·속도 조사값이 초기화됩니다. 계속하시겠습니까?',QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)==QMessageBox.Yes
    def edit_edge(self,eid):
        old=next(e for e in self.net['edges'] if e['id']==eid);new=self.road_form(old)
        if new is None or new==old:return
        if not self.confirm_impact('양방향 구간 정보를 변경합니다.'):return
        old.update(new);self.save();self.draw()
    def finish_path(self):
        try:
            path=model.path_between(self.net,self.chain)
            name,ok=QInputDialog.getText(self,'분석 경로 만들기','분석구간명')
            if not ok or not name.strip():return
            pair=[model.corridor_from_path(self.net,p,name+suffix) for p,suffix in [(path,' →'),(model.reverse_path(path),' ←')]]
        except ValueError as error:self.status.setText(str(error));return
        self.page.project.corridors_2026.extend(c.to_dict() for c in pair);self.save();self.set_mode('');self.status.setText('양방향 분석 경로를 추가했습니다. 입력표에서 편람 적용 조건과 누락값을 확인하세요.')
    def delete_edge(self,eid):
        if not self.confirm_impact('선택한 양방향 연결을 삭제합니다.'):return
        self.net['edges']=[e for e in self.net['edges'] if e['id']!=eid];self.save();self.draw()
    def delete_node(self,uid):
        count=sum(uid in (e['a'],e['b']) for e in self.net['edges'])
        if not self.confirm_impact(f'교차로와 연결 {count}개를 삭제합니다. 양옆 구간을 자동으로 합치지 않습니다.'):return
        self.net['edges']=[e for e in self.net['edges'] if uid not in (e['a'],e['b'])];self.net['nodes']=[n for n in self.net['nodes'] if n['id']!=uid];self.save();self.draw()
    def insert_at(self,eid):
        names=[n for n in self.net['nodes'] if not any(n['id'] in (e['a'],e['b']) for e in self.net['edges'])]
        if not names:self.status.setText('삽입할 교차로를 먼저 추가하세요.');return
        options=[f"{i+1}. {n['name']}" for i,n in enumerate(names)]
        choice,ok=QInputDialog.getItem(self,'교차로 삽입','연결 전 교차로',options,0,False)
        if not ok:return
        first,ok=QInputDialog.getDouble(self,'교차로 삽입','기존 시점 → 새 교차로 길이(m)',0,0,100000,2)
        if not ok:return
        second,ok=QInputDialog.getDouble(self,'교차로 삽입','새 교차로 → 기존 종점 길이(m)',0,0,100000,2)
        if not ok or not self.confirm_impact('기존 선을 두 양방향 구간으로 나눕니다. 새 교차로의 방향별 지체·용량은 미입력입니다.'):return
        try:model.split_edge(self.page.project,self.net,eid,names[options.index(choice)]['id'],first,second)
        except ValueError as error:self.status.setText(str(error));return
        self.save();self.draw()
    def import_current(self):
        c=self.page.current()
        if c.network_id:self.status.setText('이미 관계도에 연결된 분석구간입니다.');return
        net=deepcopy(self.net)
        try:model.import_corridor(net,c)
        except (ValueError,IndexError) as error:self.status.setText(str(error));return
        self.net.clear();self.net.update(net);self.page.project.corridors_2026[self.page.selector.currentIndex()]=c.to_dict()
        self.save(False);self.draw();self.fit()
    def zoom(self,factor):
        scale=self.view.transform().m11()
        if .1<=scale*factor<=4:self.view.scale(factor,factor)
        self.percent.setText(f'{self.view.transform().m11()*100:.0f}%')
    def arrange(self):
        from .app_fast import NetworkDiagramWidget
        helper=NetworkDiagramWidget()
        helper.nodes={('id',n['id']):n for n in self.net['nodes']}
        helper.edges=[dict(start=('id',e['a']),end=('id',e['b'])) for e in self.net['edges']]
        helper._layout_signature=repr(self.net['edges'])
        positions=helper._build_non_crossing_layout()
        size=max(800,len(self.nodes)*260)
        for n in self.net['nodes']:
            p=positions[('id',n['id'])];n['x']=p.x()*size;n['y']=p.y()*size
        helper.deleteLater();self.save(False);self.draw();self.fit()
    def fit(self):self.view.fitInView(self.scene.itemsBoundingRect().adjusted(-45,-45,45,45),Qt.KeepAspectRatio);self.percent.setText(f'{self.view.transform().m11()*100:.0f}%')
    def reset_zoom(self):self.view.resetTransform();self.percent.setText('100%')
    def closeEvent(self,event):event.ignore();self.hide()
