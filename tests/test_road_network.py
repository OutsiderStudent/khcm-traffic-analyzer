import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QPointF, QEvent, Qt, QUrl
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from arterial_analysis import road_network as m
from arterial_analysis.engine_2026 import analyze_corridor, Corridor2026
from arterial_analysis.project import ArterialProject
from arterial_analysis.network_editor import half_arrows
from arterial_analysis.app_fast import MainWindow
from arterial_analysis.recovery import write_recovery, read_recovery

APP=QApplication.instance() or QApplication([])


class RoadModelTest(unittest.TestCase):
    def setUp(self):
        self.net=m.new_network('현황',2026,'외부도로')
        self.ids=[m.add_intersection(self.net,f'교차로 {i}',i*300,0) for i in range(4)]
        self.edges=[m.connect(self.net,a,b,600,50) for a,b in zip(self.ids,self.ids[1:])]
        for e in self.edges:
            e['ab'].update(lanes=2,delay=30,capacity=1500)
            e['ba'].update(lanes=2,delay=50,capacity=1400)
    def test_bidirectional_paths_use_destination_direction(self):
        path=m.path_between(self.net,self.ids)
        forward=m.corridor_from_path(self.net,path,'순방향');back=m.corridor_from_path(self.net,m.reverse_path(path),'역방향')
        self.assertEqual([s.delay_s for s in forward.subsegments],[30]*3)
        self.assertEqual([s.delay_s for s in back.subsegments],[50]*3)
        self.assertEqual(back.start_id,self.ids[-1]);self.assertEqual(back.subsegments[-1].end_id,self.ids[0])
        for c in (forward,back):
            c.urban_road_confirmed=c.signal_control_confirmed=c.boundaries_confirmed=True
        self.assertGreater(analyze_corridor(forward).speed_kmh,analyze_corridor(back).speed_kmh)
    def test_right_hand_half_arrows(self):
        for a,b in [(QPointF(0,0),QPointF(100,0)),(QPointF(0,0),QPointF(0,100)),(QPointF(30,70),QPointF(-30,-10))]:
            forward,back=half_arrows(a,b)
            for direction,arrow in [(b-a,forward),(a-b,back)]:
                tail,tip,wing=arrow;delta=tip-tail;offset=(tip+tail)/2-(a+b)/2
                self.assertGreater(delta.x()*direction.x()+delta.y()*direction.y(),0)
                self.assertGreater(direction.x()*offset.y()-direction.y()*offset.x(),0)
                self.assertAlmostEqual((tip-tail).manhattanLength(),(back[1]-back[0]).manhattanLength())
    def test_split_preserves_end_approaches_and_both_routes(self):
        p=ArterialProject();path=m.path_between(self.net,self.ids)
        p.corridors_2026=[m.corridor_from_path(self.net,x,'경로').to_dict() for x in (path,m.reverse_path(path))]
        middle=m.add_intersection(self.net,'새 교차로',150,0)
        m.split_edge(p,self.net,self.edges[0]['id'],middle,200,400)
        for raw in p.corridors_2026:
            c=Corridor2026.from_dict(raw);self.assertEqual(len(c.subsegments),4)
            added=next(s for s in c.subsegments if s.end_id==middle);self.assertIsNone(added.delay_s)
        self.assertEqual(p.corridors_2026[0]['subsegments'][1]['delay_s'],30)
        self.assertEqual(p.corridors_2026[1]['subsegments'][-1]['delay_s'],50)
    def test_branches_path_selection_turns_and_duplicates(self):
        branch=m.add_intersection(self.net,'분기',300,300);m.connect(self.net,self.ids[1],branch,400,40)
        self.assertEqual(len(m.path_between(self.net,[self.ids[0],self.ids[1],branch])),2)
        with self.assertRaises(ValueError):m.connect(self.net,self.ids[1],self.ids[0],600,50)
        self.edges[0]['ab']['movement']='좌회전'
        with self.assertRaises(ValueError):m.corridor_from_path(self.net,m.path_between(self.net,self.ids),'회전')
    def test_rename_preserves_survey_geometry_change_clears_it(self):
        p=ArterialProject();c=m.corridor_from_path(self.net,m.path_between(self.net,self.ids),'경로');c.travel_times_s=[200];c.boundaries_confirmed=True
        p.corridors_2026=[c.to_dict()];self.net['nodes'][0]['name']='변경'
        m.synchronize(p,self.net);self.assertEqual(p.corridors_2026[0]['travel_times_s'],[200])
        self.edges[0]['length']=700;m.synchronize(p,self.net)
        self.assertEqual(p.corridors_2026[0]['travel_times_s'],[]);self.assertFalse(p.corridors_2026[0]['boundaries_confirmed'])
    def test_deleted_edge_cannot_leave_valid_stale_result(self):
        p=ArterialProject();p.corridors_2026=[m.corridor_from_path(self.net,m.path_between(self.net,self.ids),'경로').to_dict()]
        self.net['edges'].pop();m.synchronize(p,self.net)
        self.assertEqual(p.corridors_2026[0]['subsegments'],[])
    def test_atomic_save_and_recovery_roundtrip(self):
        p=ArterialProject();p.networks_2026=[self.net]
        with tempfile.TemporaryDirectory() as d:
            original=Path(d)/'project.ara1';p.save(original);before=original.read_bytes()
            backup=Path(d)/'recovery.json';write_recovery(backup,p,str(original));restored,source=read_recovery(backup)
            self.assertEqual(restored.networks_2026,[self.net]);self.assertEqual(original.read_bytes(),before)
            with patch('pathlib.Path.replace',side_effect=OSError('locked')):
                with self.assertRaises(OSError):p.save(original)
            self.assertEqual(original.read_bytes(),before)


class RoadEditorTest(unittest.TestCase):
    def setUp(self):
        self.window=MainWindow();self.window.project.analysis_edition='2026';self.window.sync_edition()
        self.page=self.window.beta_page;self.page.add_corridor();self.page.show_diagram();self.editor=self.page.road_dialog
    def tearDown(self):
        APP.clipboard().clear();self.window.deleteLater();APP.sendPostedEvents(None,QEvent.DeferredDelete);APP.processEvents()
    def test_click_creates_both_directions_and_undo(self):
        e=self.editor;a=m.add_intersection(e.net,'시청',0,0);b=m.add_intersection(e.net,'공원',400,0);e.save(False);e.draw();APP.processEvents()
        values=dict(a=a,b=b,name='중앙로',length=600,speed=50,ab=m.direction_data(),ba=m.direction_data())
        with patch.object(e,'road_form',return_value=values):
            QTest.mouseClick(e.view.viewport(),Qt.LeftButton,Qt.ControlModifier,e.view.mapFromScene(e.nodes[a].pos()))
            QTest.mouseClick(e.view.viewport(),Qt.LeftButton,Qt.NoModifier,e.view.mapFromScene(e.nodes[b].pos()))
        self.assertEqual(len(e.net['edges']),1)
        self.assertEqual(len(self.page.project.corridors_2026),3)
        self.window.undo_project();self.assertEqual(len(e.net['edges']),0)
        self.window.redo_project();self.assertEqual(len(e.net['edges']),1)
    def test_table_change_updates_linked_reverse_geometry(self):
        e=self.editor;a=m.add_intersection(e.net,'A',0,0);b=m.add_intersection(e.net,'B',400,0)
        edge=m.connect(e.net,a,b,600,50)
        self.page.project.corridors_2026.extend(m.corridor_from_path(e.net,[dict(edge=edge['id'],reverse=r)],str(r)).to_dict() for r in (False,True))
        e.save();self.page.selector.setCurrentIndex(1);self.page.table.cellWidget(0,1).setValue(700)
        self.assertEqual(self.page.project.corridors_2026[2]['subsegments'][0]['length_m'],700)
        self.assertEqual(edge['length'],700)
    def test_missing_input_link_and_theme_menu(self):
        self.page.add_row();self.assertFalse(self.page.analyze())
        self.page.focus_missing(QUrl('input:0:1'));self.assertEqual(self.page.tabs.currentIndex(),1)
        menus=[a.text() for a in self.window.menuBar().actions()];self.assertNotIn('보기',menus);self.assertIn('설정',menus)
        for theme in ('light','dark','system'):self.window.set_theme_mode(theme,False)
