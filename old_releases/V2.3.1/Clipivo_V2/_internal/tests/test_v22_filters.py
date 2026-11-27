import unittest
from v22.filters import DEFAULTS, static_overlay,filter_observations,diverse_refs
from v22.analyzer import intervals,refresh
class FilterTests(unittest.TestCase):
    def obs(self,t,box=(.82,.02,.92,.12),size=60,signature=100):
        return dict(time=t,box_norm=box,face_size=size,confidence=.95,signature=[signature]*64,quality=10,image=f'{t}.jpg')
    def test_static_and_moving(self):
        g={'observations':[self.obs(t) for t in range(10)]}; self.assertTrue(static_overlay(g,10));g['observations']=[self.obs(t,box=(.82,.02,.92,.12),signature=t*15) for t in range(10)];self.assertFalse(static_overlay(g,10))
    def test_filter_restore(self):
        g={'observations':[self.obs(1,size=20),self.obs(2,box=(.3,.3,.5,.5)),self.obs(2.5,box=(.3,.3,.5,.5))]};d={'duration':5,'sample_interval':.5,'filters':dict(DEFAULTS,static=False),'people':[g]};refresh(d);self.assertEqual(g['segments'],[[1.75,2.75]]);self.assertEqual(len(g['observations']),3);g['force_include']=True;refresh(d);self.assertEqual(len(g['segments']),2)
    def test_region(self):
        g={'observations':[self.obs(1),self.obs(1.5)]};d={'duration':5,'sample_interval':.5,'filters':dict(DEFAULTS,regions=[[.8,0,1,.2]])};self.assertEqual(filter_observations(g,d,intervals)[0],[])
    def test_reference_dedup(self):
        self.assertEqual(len(diverse_refs([self.obs(t) for t in range(5)])),1)
