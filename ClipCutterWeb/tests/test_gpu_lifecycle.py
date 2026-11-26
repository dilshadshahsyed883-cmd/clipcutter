"""Lifecycle regressions using fake Salad and worker; no real paid operations."""
from datetime import datetime,timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from app.modules.studio.contracts import JobRequest
from app.modules.studio.store import Store
from app.modules.studio.gpu import GPUSettings
from app.modules.studio.lifecycle import Lifecycle,SaladAPI,LifecycleError

def stamp(t):return datetime.fromtimestamp(t,timezone.utc).isoformat()
IMAGE="ghcr.io/dilshadshahsyed883-cmd/clipcutter-gpu-private-test@sha256:"+"1"*64
GROUP="/organizations/voice-generation/projects/default/containers/clipcutter-gpu"
class FakeSalad:
    path=GROUP;image=IMAGE
    def __init__(self):
        self.state="stopped";self.posts=[];self.fail=False
        self.item={"id":"00000000-0000-4000-8000-000000000001","machine_id":"00000000-0000-4000-8000-000000000002",
                   "version":1,"state":"downloading","ready":False,"update_time":stamp(900),"pulling_progress":.01}
        self.fresh=None
    def group(self):
        return {"replicas":1,"autostart_policy":False,"scheduled_scaling_enabled":False,
                "container":{"image":self.image},"current_state":{"status":self.state}}
    def instances(self):return [dict(self.item)]
    def instance(self,i):return dict(self.fresh or self.item)
    def mutate(self,action,i=None):
        self.posts.append((action,i))
        if self.fail:raise LifecycleError("Ambiguous response")
class Worker:
    def __init__(self):self.metrics={"active_renders":0,"staging":0,"undelivered":0}
    def capabilities(self):return dict(self.metrics)
class Tests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.store=Store("owner",Path(tmp.name).resolve())
        self.api=FakeSalad();self.worker=Worker();self.now=1000
        self.cfg=GPUSettings(auto_start=True)
        self.life=Lifecycle(self.store,self.cfg,self.api,self.worker,lambda:self.now)
    def tick(self,step=4,**kw):
        self.now+=step;return self.life.tick(**kw)
    def job(self,key="a"*32,ready=True):
        req=JobRequest.model_validate({"request_id":key,"input":{"source":"https://drive.google.com/file/d/abcdef123456789/view"},
                                       "settings":{"kind":"analyzer"}})
        jid=self.store.create(req)["id"]
        if ready:
            self.store.transition(jid,"awaiting_input","staging","intake")
            self.store.transition(jid,"staging","ready","verified")
        return jid
    def test_intake_barrier_and_start_journal(self):
        self.job(ready=True);self.job("b"*32,ready=False)
        self.assertEqual(self.tick(),"waiting_for_drive_or_reconciliation")
        self.assertEqual(self.api.posts,[])
        with self.store.connect() as c:c.execute("UPDATE requests SET state='cancelled' WHERE state='awaiting_input'")
        self.api.fail=True
        self.assertEqual(self.tick(),"start_pending_confirmation")
        self.life=Lifecycle(self.store,self.cfg,self.api,self.worker,lambda:self.now)
        self.assertEqual(self.tick(),"start_pending_confirmation")
        self.assertEqual(len(self.api.posts),1)
    def test_download_units_and_fresh_recheck(self):
        self.job();self.api.state="deploying";self.api.item["pulling_progress"]=.30
        self.assertEqual(self.tick(),"downloading_healthy")
        self.assertEqual(self.life.snapshot()["progress"],30)
        self.api.item.update(update_time=stamp(950),pulling_progress=.01)
        self.api.fresh={**self.api.item,"pulling_progress":.12}
        self.assertEqual(self.tick(),"downloading_healthy")
        self.assertEqual(self.api.posts,[])
    def test_reallocation_budget_and_restart(self):
        self.job();self.api.state="deploying"
        for i in range(3):
            self.api.item["version"]=i+1
            self.assertEqual(self.tick(35),"reallocate_pending_confirmation")
        self.api.item["version"]=4
        self.assertEqual(self.tick(35),"retry_cycle_cooldown")
        deadline=self.life.snapshot()["retry_after"]
        self.life=Lifecycle(self.store,self.cfg,self.api,self.worker,lambda:self.now)
        self.assertEqual(self.tick(10),"retry_cycle_cooldown")
        self.now=deadline+1
        self.assertEqual(self.tick(),"reallocate_pending_confirmation")
        self.assertEqual(len(self.api.posts),4)
        self.assertEqual(self.tick(40),"waiting_for_reallocation")
        self.assertEqual(len(self.api.posts),4)
    def test_idle_stop_drains_and_confirms(self):
        self.api.state="running";self.api.item.update(state="running",ready=True)
        self.worker.metrics["undelivered"]=1
        self.assertEqual(self.tick(),"worker_busy")
        self.worker.metrics["undelivered"]=0
        self.assertEqual(self.tick(),"idle_countdown")
        self.assertEqual(self.tick(59),"idle_countdown")
        self.assertEqual(self.tick(4),"stop_pending_confirmation")
        self.assertEqual(self.tick(),"stop_pending_confirmation")
        self.api.state="stopped"
        self.assertEqual(self.tick(),"stopped")
        self.assertEqual(self.api.posts,[("stop",None)])
    def test_idle_reset_on_restart(self):
        self.api.state="running";self.api.item.update(state="running",ready=True)
        self.assertEqual(self.tick(),"idle_countdown")
        self.life=Lifecycle(self.store,self.cfg,self.api,self.worker,lambda:self.now)
        self.assertEqual(self.tick(70),"idle_countdown")
        self.assertEqual(self.api.posts,[])
    def test_manual_no_reallocate(self):
        self.job();self.cfg.auto_start=False;self.api.state="deploying"
        self.assertEqual(self.tick(manual="start"),"slow_download_no_reallocation")
        self.assertEqual(self.api.posts,[])
    def test_uncertain_metrics_no_stop(self):
        self.api.state="running";self.api.item.update(state="running",ready=True)
        self.worker.metrics["staging"]=None
        self.assertEqual(self.tick(100),"worker_busy")
        self.assertEqual(self.api.posts,[])
    def test_live_gate_default_off(self):
        with patch.dict("os.environ",{},clear=True):
            with self.assertRaises(LifecycleError):SaladAPI(self.cfg,"x"*32)

if __name__=="__main__":unittest.main()
