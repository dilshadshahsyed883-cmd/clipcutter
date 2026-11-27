import copy
import json
import tempfile
import unittest
from pathlib import Path
from studio import json_timeline as t
from studio.json_timeline_export import request

def media(path,pid,duration):
    return dict(path=path,relative=path,person=pid,duration=t.us(duration),stamp=[path,1,1,1])

def fixture(lengths, ids=None):
    ids=ids or [['a'] for _ in lengths]
    intervals=[];at=0
    for length,people in zip(lengths,ids):
        end=at+t.us(length);intervals.append(dict(start=at,end=end,people=people));at=end
    return dict(analysis_path='analysis.json',analysis_sha256='fixture',
                reference=dict(path='reference.mp4',duration=at,fps=30),
                people={'a':dict(name='Alice',ignored=False),'b':dict(name='Bob',ignored=False)},intervals=intervals)

class AuditRegression(unittest.TestCase):
    def test_short_boundary_preserved_and_subframe_gap(self):
        plan=t.generate(fixture([.01,1,4.2]),'.',[media('long','a',5)],t.options(),1)
        self.assertIsNone(plan['rows'][0]['selected'])
        self.assertIsNotNone(plan['rows'][1]['selected'])
        self.assertEqual(plan['rows'][1]['reason'],'Short boundary preserved')
        self.assertEqual(sum(r['end']-r['start'] for r in plan['rows']),t.us(5.21))
        self.assertTrue(all(r['end']-r['start']<=t.us(4) for r in plan['rows']))
    def test_same_person_gap_max_never_bypasses_clip_max(self):
        imp=fixture([3,7,3],[['a'],[],['a']])
        plan=t.generate(imp,'.',[media('a','a',8)],t.options(gap_max=8),9)
        self.assertEqual(sum(r['end']-r['start'] for r in plan['rows'] if r['auto_gap_fill']),t.us(7))
        self.assertTrue(all(r['end']-r['start']<=t.us(4) for r in plan['rows']))
        different=t.generate(fixture([3,.5,3],[['a'],[],['b']]),'.',[media('a','a',8)],t.options(),9)
        self.assertIsNone(different['rows'][1]['selected'])
    def test_speed_options(self):
        imp=fixture([3])
        for duration,expected in [(2.4,.8),(3.3,1.1),(5,1.)]:
            p=t.generate(imp,'.',[media('x','a',duration)],t.options(),1)
            self.assertAlmostEqual(p['rows'][0]['selected']['speed'],expected)
        p=t.generate(imp,'.',[media('x','a',3.3)],t.options(max_speed=1.05),1)
        self.assertEqual(p['rows'][0]['selected']['speed'],1.)
        p=t.generate(imp,'.',[media('x','a',3.3)],t.options(speed_adjust=False),1)
        self.assertEqual(p['rows'][0]['selected']['speed'],1.)
        p['rows'][0]['selected']['speed']=.9
        with self.assertRaises(ValueError):t.validate(p)
        p=t.generate(imp,'.',[media('x','a',2.1)],t.options(),1)
        self.assertIsNone(p['rows'][0]['selected'])
    def test_reserve_long_source_with_reuse_off(self):
        imp=fixture([2.5,4])
        for seed in range(25):
            p=t.generate(imp,'.',[media('short','a',2.5),media('long','a',4)],t.options(reuse=False),seed)
            self.assertEqual([r['selected']['path'] for r in p['rows']],['short','long'])
    def test_reference_relink_and_cache(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'original.mp4';source.write_bytes(b'original')
            analysis=root/'analysis.json'
            analysis.write_text(json.dumps(dict(version=2,source=str(source),source_stamp=t.stamp(source),duration=3,sample_interval=.5,people=[dict(id='a',name='Alice',segments=[[0,3]])])))
            original=analysis.read_bytes();new=root/'moved.mp4';source.rename(new)
            calls=[]
            def probe(p):
                calls.append(p)
                return dict(duration=3,videoDuration=3,w=640,h=360,fps=30,hasAudio=True,audioDuration=2.9)
            with self.assertRaises(t.ReferenceRelinkRequired):t.load_analysis(analysis,probe)
            imported=t.load_analysis(analysis,probe,new)
            self.assertEqual(imported['reference']['path'],str(new))
            self.assertEqual(analysis.read_bytes(),original)
            folder=root/'footage';folder.mkdir();sub=folder/'Alice';sub.mkdir();(sub/'a.mp4').write_bytes(b'a')
            m,_=t.scan_folder(folder,imported['people'],probe)
            before=len(calls);m2,_=t.scan_folder(folder,imported['people'],probe,cached=m)
            self.assertEqual(m,m2);self.assertEqual(len(calls),before)
            plan=t.generate(imported,folder,m,t.options(),1)
            payload=request(plan,'test','original',None,probe)['payload']
            self.assertEqual(payload['timelineDuration'],3)
            self.assertEqual(payload['voice']['dur'],2.9)
            new.unlink()
            self.assertIsNone(request(plan,'test','none',None,probe)['payload']['voice'])
            with self.assertRaises(ValueError):request(plan,'test','original',None,probe)
            wrong=root/'wrong.mp4';wrong.write_bytes(b'wrong')
            with self.assertRaises(ValueError):t.relink_reference(plan,wrong,probe)
