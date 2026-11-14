import unittest
from arterial_analysis.engine_2026 import Corridor2026, official_example, analyze_corridor
from arterial_analysis.network_2026 import add_node, connect_nodes, insert_node, route_nodes
from arterial_analysis.project import ArterialProject


class ManualNetworkTest(unittest.TestCase):
    def test_connect_save_restore_and_same_names(self):
        c = Corridor2026()
        a = add_node(c, '교차로'); b = add_node(c, '교차로'); spare = add_node(c, '미연결')
        connect_nodes(c, a, b, 500, 50)
        p = ArterialProject(); p.corridors_2026 = [c.to_dict()]
        restored = Corridor2026.from_dict(ArterialProject.from_dict(p.to_dict()).corridors_2026[0])
        self.assertEqual([n[0] for n in route_nodes(restored)], [a,b])
        self.assertEqual(restored.diagram_nodes[0]['id'], spare[1])
        self.assertEqual(restored.subsegments[0].length_m, 500)
        self.assertIsNone(restored.subsegments[0].delay_s)
        self.assertIsNone(restored.subsegments[0].capacity_vph)
        self.assertEqual(restored.subsegments[0].through_lanes, 0)

    def test_reject_branch_self_loop_and_duplicate_without_mutation(self):
        c = Corridor2026(); a = add_node(c,'A'); b = add_node(c,'B'); d = add_node(c,'D')
        connect_nodes(c,a,b,300,40)
        before=c.to_dict()
        for start,end in [(a,d),(b,b),(b,a)]:
            with self.assertRaises(ValueError): connect_nodes(c,start,end,300,40)
            self.assertEqual(c.to_dict(),before)
        connect_nodes(c,b,d,400,50)
        self.assertEqual(len(c.subsegments),2)

    def test_insert_preserves_downstream_signal_and_invalidates_survey(self):
        c=official_example(1); c.subsegments[0].approach_id='EB'; c.subsegments[0].capacity_vph=1600
        key=add_node(c,'새 교차로'); insert_node(c,key,0,200,300)
        self.assertEqual([s.length_m for s in c.subsegments[:2]],[200,300])
        self.assertIsNone(c.subsegments[0].delay_s)
        self.assertEqual(c.subsegments[1].delay_s,44.5)
        self.assertEqual(c.subsegments[1].capacity_vph,1600)
        self.assertEqual(c.subsegments[1].approach_id,'EB')
        self.assertFalse(c.travel_times_s)
        self.assertFalse(c.boundaries_confirmed)

    def test_pending_nodes_do_not_change_analysis(self):
        c=official_example(); before=analyze_corridor(c)
        add_node(c,'미연결'); self.assertEqual(analyze_corridor(c),before)
