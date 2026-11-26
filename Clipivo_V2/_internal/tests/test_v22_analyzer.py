import unittest,tempfile,json
from pathlib import Path
import numpy as np
from v22.analyzer import intervals,assign,merge_groups,split_group,save_project
class Tests(unittest.TestCase):
    def test_intervals(self): self.assertEqual(intervals([0,.5,1,3],4,.5),[[0,1.25],[2.75,3.25]])
    def test_assign_and_simultaneous(self):
        groups=[]; e=np.array([1.,0.]); i=assign(groups,e,set(),.45); groups[i]['_sum']+=e
        self.assertEqual(assign(groups,e,set(),.45),0); self.assertEqual(assign(groups,e,{0},.45),1)
    def test_merge_split_persist(self):
        def g(i,t):return dict(id=str(i),name='P'+str(i),observations=[dict(time=t,image='a.jpg',quality=1,embedding=[1.,0.])],ignored=False)
        d=dict(duration=5,sample_interval=.5,people=[g(1,1),g(2,3)])
        merge_groups(d,['1','2']);self.assertEqual(len(d['people']),1);self.assertEqual(len(d['people'][0]['segments']),2)
        split_group(d,'1',[1]);self.assertEqual(len(d['people']),2)
        with tempfile.TemporaryDirectory() as tmp:
            save_project(tmp,d);self.assertEqual(len(json.loads((Path(tmp)/'analysis.json').read_text())['people']),2);self.assertTrue((Path(tmp)/'timeline.csv').exists())
if __name__=='__main__':unittest.main()
