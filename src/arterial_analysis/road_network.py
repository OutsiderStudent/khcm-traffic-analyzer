"""Physical bidirectional roads, independent of directed analysis paths."""
from copy import deepcopy
from math import isfinite
from uuid import uuid4
from .engine_2026 import Corridor2026, Subsegment2026, END_TYPES


def new_network(scenario, year, category):
    return dict(id=uuid4().hex, scenario=scenario, year=year, category=category, nodes=[], edges=[])


def node_by_id(net, uid):
    return next(n for n in net['nodes'] if n['id'] == uid)


def direction_data():
    return dict(lanes=0, delay=None, capacity=None, approach='', movement='직진')


def add_intersection(net, name, x=0, y=0, uid=None):
    if not name.strip(): raise ValueError('교차로명을 입력하세요.')
    uid = uid or uuid4().hex
    if any(n['id'] == uid for n in net['nodes']): raise ValueError('이미 있는 교차로 ID입니다.')
    net['nodes'].append(dict(id=uid, name=name.strip(), x=float(x), y=float(y)))
    return uid


def connect(net, a, b, length, speed, name=''):
    node_by_id(net,a); node_by_id(net,b)
    if a == b: raise ValueError('서로 다른 교차로를 연결하세요.')
    if any({e['a'],e['b']} == {a,b} for e in net['edges']): raise ValueError('이미 연결된 구간입니다.')
    if not all(isfinite(v) and v > 0 for v in (length,speed)): raise ValueError('길이와 제한속도는 0보다 커야 합니다.')
    edge=dict(id=uuid4().hex,a=a,b=b,length=length,speed=speed,name=name,ab=direction_data(),ba=direction_data())
    net['edges'].append(edge)
    return edge


def path_between(net, nodes):
    if len(nodes)<2 or len(set(nodes))!=len(nodes): raise ValueError('서로 다른 교차로를 진행 순서대로 2개 이상 선택하세요.')
    result=[]
    for a,b in zip(nodes,nodes[1:]):
        edge=next((e for e in net['edges'] if {e['a'],e['b']}=={a,b}),None)
        if edge is None: raise ValueError('선택한 교차로 사이에 연결 구간이 없습니다.')
        result.append(dict(edge=edge['id'],reverse=edge['a']!=a))
    return result


def reverse_path(path):
    return [dict(edge=p['edge'],reverse=not p['reverse']) for p in reversed(path)]


def corridor_from_path(net, path, name):
    c=Corridor2026(name=name,scenario=net['scenario'],year=net['year'],road_category=net['category'],network_id=net['id'],network_path=deepcopy(path))
    last=None
    for p in path:
        edge=next(e for e in net['edges'] if e['id']==p['edge'])
        a,b=(edge['b'],edge['a']) if p['reverse'] else (edge['a'],edge['b'])
        if last is not None and a!=last: raise ValueError('분석 경로가 이어지지 않습니다.')
        if last is None: c.start_id=a;c.start_name=node_by_id(net,a)['name']
        last=b
        data=edge['ba' if p['reverse'] else 'ab']
        # A network may represent turns, but chapter 12 must not analyse them as through movements.
        if data['movement']!='직진': raise ValueError('회전 이동류가 포함된 경로는 2026 직진 간선도로 분석 대상이 아닙니다.')
        c.subsegments.append(Subsegment2026(end_name=node_by_id(net,b)['name'],length_m=edge['length'],speed_limit_kmh=edge['speed'],through_lanes=data['lanes'],delay_s=data['delay'],capacity_vph=data['capacity'],end_id=b,approach_id=data['approach']))
    if not c.subsegments: raise ValueError('분석 경로를 선택하세요.')
    c.lanes=min(s.through_lanes for s in c.subsegments)
    return c


def synchronize(project, net):
    """Refresh linked paths, preserving user scope/source and invalidating changed surveys."""
    for i,raw in enumerate(project.corridors_2026):
        old=Corridor2026.from_dict(raw)
        if old.network_id!=net['id']: continue
        try: new=corridor_from_path(net,old.network_path,old.name)
        except (ValueError,StopIteration):
            # Keep the user's record but make stale results impossible to analyse.
            old.boundaries_confirmed=False;old.subsegments=[]
            project.corridors_2026[i]=old.to_dict();continue
        same_geometry=(old.start_id,[(s.end_id,s.length_m,s.speed_limit_kmh) for s in old.subsegments]) == (new.start_id,[(s.end_id,s.length_m,s.speed_limit_kmh) for s in new.subsegments])
        for attr in ('urban_road_confirmed','signal_control_confirmed','data_source','survey_date','method'):
            setattr(new,attr,getattr(old,attr))
        new.lanes=old.lanes
        new.boundaries_confirmed=old.boundaries_confirmed if same_geometry else False
        if same_geometry:
            new.travel_times_s=old.travel_times_s;new.travel_speeds_kmh=old.travel_speeds_kmh
        project.corridors_2026[i]=new.to_dict()


def split_edge(project, net, eid, node, first, second):
    edge=next(e for e in net['edges'] if e['id']==eid)
    if node in (edge['a'],edge['b']): raise ValueError('구간 중간에 넣을 다른 교차로를 선택하세요.')
    if any(node in (e['a'],e['b']) for e in net['edges']): raise ValueError('아직 연결하지 않은 교차로를 선택하세요.')
    if min(first,second)<=0: raise ValueError('나뉜 두 구간의 길이를 입력하세요.')
    one=connect(net,edge['a'],node,first,edge['speed'],edge['name'])
    two=connect(net,node,edge['b'],second,edge['speed'],edge['name'])
    # Existing end approaches stay at their actual intersection, never copied onto the new one.
    one['ba']=deepcopy(edge['ba']);two['ab']=deepcopy(edge['ab'])
    net['edges'].remove(edge)
    for raw in project.corridors_2026:
        if raw.get('network_id')!=net['id']:continue
        path=[]
        for p in raw.get('network_path',[]):
            if p['edge']!=eid:path.append(p)
            elif p['reverse']:path.extend([dict(edge=two['id'],reverse=True),dict(edge=one['id'],reverse=True)])
            else:path.extend([dict(edge=one['id'],reverse=False),dict(edge=two['id'],reverse=False)])
        raw['network_path']=path
    synchronize(project,net)


def import_corridor(net, c):
    """Import existing directed input without inventing the opposite approach data."""
    from .network_2026 import route_nodes
    nodes=route_nodes(c);ids=[]
    for i,(key,name,number) in enumerate(nodes):
        # Names are not identity. Preserve explicit IDs only within this scope.
        uid=number or uuid4().hex
        if not any(n['id']==uid for n in net['nodes']):add_intersection(net,name or '미입력',i*260,0,uid)
        ids.append(uid)
    path=[]
    for i,s in enumerate(c.subsegments):
        if i+1>=len(ids) or s.end_type!=END_TYPES[0]:
            raise ValueError('횡단보도·제한속도 변경지점이 있는 기존 구간은 입력표에서 유지하세요. 관계도에는 교차로로 구성된 경로를 가져올 수 있습니다.')
        edge=next((e for e in net['edges'] if {e['a'],e['b']}==set(ids[i:i+2])),None)
        if edge is None:edge=connect(net,ids[i],ids[i+1],s.length_m,s.speed_limit_kmh)
        reverse=edge['a']!=ids[i];edge['ba' if reverse else 'ab']=dict(lanes=s.through_lanes,delay=s.delay_s,capacity=s.capacity_vph,approach=s.approach_id,movement='직진')
        path.append(dict(edge=edge['id'],reverse=reverse))
    c.network_id=net['id'];c.network_path=path
    return c
