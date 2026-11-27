import json
import tempfile
import unittest
from pathlib import Path
from studio import json_timeline as t

class JsonTimelineTests(unittest.TestCase):
    def test_boundaries_gaps_mapping_and_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); source=p/'source.mp4';source.touch()
            folder=p/'footage';folder.mkdir();(folder/'Alice').mkdir()
            (folder/'Alice'/'a.mp4').write_bytes(b'a')
            (folder/'general.mp4').write_bytes(b'g')
            inp=p/'analysis.json'
            data={'version':2,'source':str(source),'duration':10,'sample_interval':.5,
                  'people':[{'id':'a','name':'Alice','segments':[[0,3],[3.5,7]]},
                            {'id':'b','name':'Bob','segments':[[7,10]]}]}
            inp.write_text(json.dumps(data))
            original=inp.read_bytes()
            def probe(path):
                dur=10 if Path(path)==source else 4
                return dict(duration=dur,videoDuration=dur,w=640,h=360,fps=30)
            imported=t.load_analysis(inp,probe)
            media,warnings=t.scan_folder(folder,imported['people'],probe)
            self.assertEqual(len(media),2)
            self.assertIsNone(next(m for m in media if m['relative']=='general.mp4')['person'])
            plan=t.generate(imported,folder,media,t.options(),3)
            self.assertEqual([r['start'] for r in plan['rows']],[0,3000000,3500000,7000000])
            self.assertTrue(plan['rows'][1]['auto_gap_fill'])
            self.assertIsNotNone(plan['rows'][1]['selected'])
            self.assertIsNone(plan['rows'][-1]['selected'])
            self.assertEqual(plan['rows'][-1]['end'],10000000)
            out=p/'timeline.json';t.save_plan(out,plan)
            self.assertEqual(t.open_plan(out),plan)
            with self.assertRaises(ValueError):t.save_plan(inp,plan)
            self.assertEqual(inp.read_bytes(),original)
            self.assertEqual(t.generate(imported,folder,media,t.options(),3),plan)
            no_reuse=t.generate(imported,folder,media,t.options(reuse=False),3)
            self.assertEqual(sum(bool(r['selected']) for r in no_reuse['rows']),1)
    def test_overlap_and_short_ranges_remain_manual(self):
        imp={'analysis_path':'analysis.json','analysis_sha256':'x','reference':{'path':'source','duration':5000000},'people':{'a':{},'b':{}},
             'intervals':[{'start':0,'end':1000000,'people':['a']},{'start':1000000,'end':5000000,'people':['a','b']}]}
        p=t.generate(imp,'.',[],t.options(),1)
        self.assertEqual(len(p['rows']),2)
        self.assertTrue(all(r['selected'] is None for r in p['rows']))
        p['rows'][0]['end']+=1
        with self.assertRaises(ValueError):t.validate(p)

if __name__=='__main__':unittest.main()
