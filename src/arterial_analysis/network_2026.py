"""Manual editing of a directed corridor; no inferred survey or signal values."""
from uuid import uuid4
from .engine_2026 import END_TYPES, Subsegment2026


def route_nodes(c):
    nodes = []
    if c.start_name.strip() or c.start_id.strip():
        nodes.append((('신호교차로 ID', c.start_id) if c.start_id else ('시점', '0'), c.start_name, c.start_id))
    for i, s in enumerate(c.subsegments):
        key = (f'{s.end_type} ID', s.end_id) if s.end_id and s.end_type != END_TYPES[2] else ('소구간 종점', str(i))
        nodes.append((key, s.end_name, s.end_id))
    return nodes


def add_node(c, name):
    name = name.strip()
    if not name:
        raise ValueError('교차로명을 입력하세요.')
    node = {'id': uuid4().hex, 'name': name}
    c.diagram_nodes.append(node)
    return ('신호교차로 ID', node['id'])


def invalidate_route_survey(c):
    # Whole-route samples cannot describe a changed route.
    c.travel_times_s.clear()
    c.travel_speeds_kmh.clear()
    c.boundaries_confirmed = False


def connect_nodes(c, start, end, length, speed):
    if start == end:
        raise ValueError('서로 다른 교차로를 선택하세요.')
    if length <= 0 or speed <= 0:
        raise ValueError('구간길이와 제한속도를 입력하세요.')
    pending = {('신호교차로 ID', n['id']): n for n in c.diagram_nodes}
    route = route_nodes(c)
    if c.subsegments and (not route or start != route[-1][0]):
        raise ValueError('현재 분석구간의 마지막 교차로에서 연결하세요. 다른 경로는 별도 분석구간으로 만드세요.')
    if not c.subsegments and route and start != route[0][0]:
        raise ValueError('현재 시점 교차로에서 연결하세요.')
    if end not in pending:
        raise ValueError('아직 연결하지 않은 교차로를 종점으로 선택하세요.')
    if not route:
        if start not in pending:
            raise ValueError('시점 교차로를 선택하세요.')
        c.start_name, c.start_id = pending[start]['name'], pending[start]['id']
    target = pending[end]
    c.subsegments.append(Subsegment2026(end_name=target['name'], end_id=target['id'], length_m=length, speed_limit_kmh=speed))
    c.diagram_nodes = [n for n in c.diagram_nodes if ('신호교차로 ID', n['id']) not in (start, end)]
    invalidate_route_survey(c)


def insert_node(c, key, row, first_length, second_length):
    node = next((n for n in c.diagram_nodes if ('신호교차로 ID', n['id']) == key), None)
    if node is None or not 0 <= row < len(c.subsegments):
        raise ValueError('연결 전 교차로와 삽입할 구간을 선택하세요.')
    if first_length <= 0 or second_length <= 0:
        raise ValueError('나뉜 두 구간의 길이를 모두 입력하세요.')
    old = c.subsegments[row]
    new = Subsegment2026(end_name=node['name'], end_id=node['id'], length_m=first_length, speed_limit_kmh=old.speed_limit_kmh)
    old.length_m = second_length
    c.subsegments.insert(row, new)
    c.diagram_nodes.remove(node)
    invalidate_route_survey(c)
