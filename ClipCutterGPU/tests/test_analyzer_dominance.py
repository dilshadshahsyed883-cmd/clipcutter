import unittest
from worker.analyzer.dominance import selected_indices,subtract_ranges
from worker.web_contract import Analyzer

class DominanceTests(unittest.TestCase):
    def test_single_equal_and_empty(self):
        b=(0,0,100,100)
        self.assertEqual(selected_indices([b],2.5),({0},"single"))
        self.assertEqual(selected_indices([b,b],2.5),(set(),"similar_size"))
        self.assertEqual(selected_indices([],2.5),(set(),"no_face"))
    def test_area_ratio_and_multiple(self):
        big=(0,0,100,100); small=(0,0,40,40); middle=(0,0,70,70)
        self.assertEqual(selected_indices([small,big,small],2.5),({1},"dominant"))
        self.assertEqual(selected_indices([big,middle,small],2.5),(set(),"similar_size"))
        self.assertEqual(selected_indices([big,middle],2.0),({0},"dominant"))
        self.assertEqual(selected_indices([big,(0,0,50,80)],2.5),({0},"dominant"))
    def test_rejected_cells_split_timeline(self):
        self.assertEqual(subtract_ranges([[0,10]],[[2,3],[5,7]]),[[0,2],[3,5],[7,10]])
        self.assertEqual(subtract_ranges([[0,3],[5,8]],[[2,6]]),[[0,2],[6,8]])
    def test_default_and_bounds(self):
        self.assertEqual(Analyzer().dominant_face_ratio,2.5)
        with self.assertRaises(ValueError):Analyzer(dominant_face_ratio=1)
