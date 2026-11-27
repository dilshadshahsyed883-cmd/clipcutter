import tempfile
import unittest
from pathlib import Path
from studio import json_timeline as t
from studio.json_timeline_export import request

class GapExportTests(unittest.TestCase):
    def test_leading_internal_trailing_gaps_and_audio(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);src=p/'reference.mp4';src.touch();clip=p/'clip.mp4';clip.touch()
            ref=dict(path=str(src),stamp=t.stamp(src),duration=5000000,width=640,height=360,fps=30)
            intervals=[dict(start=i*1000000,end=(i+1)*1000000,people=[]) for i in range(5)]
            rows=[dict(x,selected=None) for x in intervals]
            for i in (1,3):
                rows[i]['selected']=dict(path=str(clip),stamp=t.stamp(clip),trim=0,duration=5000000,speed=1.)
            plan=dict(format=t.FORMAT,reference=ref,intervals=intervals,rows=rows,people={})
            def probe(_):return dict(duration=5,videoDuration=5,w=640,h=360,hasAudio=True,audioDuration=5)
            payload=request(plan,'Test','original',None,probe)['payload']
            self.assertEqual([(x['start'],x['end']) for x in payload['images']],[(1,2),(3,4)])
            self.assertEqual(payload['timelineDuration'],5)
            self.assertEqual(payload['voice']['dur'],5)
            self.assertTrue(payload['allowTimelineGaps'])
            self.assertIsNone(request(plan,'Test','none',None,probe)['payload']['voice'])
            clip.unlink()
            with self.assertRaises(ValueError):request(plan,'Test','none',None,probe)
