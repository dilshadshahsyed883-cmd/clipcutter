import os
from threading import Event
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from app.modules.studio.gpu import GPUSettings
from app.modules.studio.store import Store
from app.modules.studio.scheduler import Control,authorized,Scheduler,policy_only_change
from app.modules.studio.lifecycle import LifecycleError
from test_gpu_dispatch import DispatchTests,Fake,request
from test_gpu_lifecycle import FakeSalad

class SchedulerControlTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.store=Store("owner",Path(tmp.name).resolve())
        self.cfg=GPUSettings(salad_organization="voice-generation",salad_project="default",
             salad_container_group="clipcutter-gpu",worker_gateway="https://example.salad.cloud")
        self.c=Control(self.store)
    def test_reload_only_policy_not_target(self):
        self.assertTrue(policy_only_change(self.cfg,self.cfg.model_copy(update={"auto_start":True,"image_pull_threshold":12})))
        self.assertFalse(policy_only_change(self.cfg,self.cfg.model_copy(update={"worker_gateway":"https://other.salad.cloud"})))
        self.assertTrue(policy_only_change(self.cfg,self.cfg.model_copy(update={"parallel":2})))

    def test_default_gate(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertFalse(authorized(self.store,self.cfg))
            with self.assertRaises(LifecycleError):self.c.command("start",self.cfg)
    def test_durable_commands(self):
        env={"CLIPCUTTER_SCHEDULER_ENABLED":"1","CLIPCUTTER_LIFECYCLE_ENABLED":"1","CLIPCUTTER_APPROVED_OWNER":"owner",
          "CLIPCUTTER_APPROVED_SALAD_GROUP":"/organizations/voice-generation/projects/default/containers/clipcutter-gpu",
          "CLIPCUTTER_APPROVED_WORKER_GATEWAY":"https://example.salad.cloud"}
        with patch.dict(os.environ,env,clear=True):
            self.assertTrue(authorized(self.store,self.cfg))
            with self.assertRaises(LifecycleError):self.c.command("start",self.cfg)
            self.c.mark("ready")
            self.assertEqual(self.c.command("start",self.cfg)["action"],"start")
            self.c.mark("ready","start")
            self.assertTrue(self.c.command("pause",self.cfg)["paused"])
            self.assertTrue(Control(self.store).snapshot()["paused"])
            self.assertFalse(self.c.command("resume",self.cfg)["paused"])
            self.assertTrue(self.c.command("stop",self.cfg)["paused"])
            with self.assertRaises(LifecycleError):self.c.command("resume",self.cfg)
            self.assertEqual(self.c.command("retry",self.cfg)["action"],"stop")
            self.c.mark("stopped","stop")
            self.assertIsNone(self.c.snapshot()["action"])

class PipelineLaneTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.store=Store("owner",Path(tmp.name).resolve())
        self.cfg=GPUSettings(parallel=2)
        self.scheduler=Scheduler(self.store,FakeSalad(),Fake(),self.cfg)
        self.addCleanup(self.scheduler.close)
        self.release=Event()
        self.addCleanup(self.release.set)
        self.rows=[]
        for key,phase in (("a","processing"),("b","delivering"),("c",None)):
            job=self.store.create(request(key*32))
            self.store.transition(job["id"],"awaiting_input","staging","intake")
            self.store.transition(job["id"],"staging","ready","verified",100)
            if phase:
                self.store.transition(job["id"],"ready","processing","processing")
                if phase=="delivering":
                    self.store.transition(job["id"],"processing","delivering","delivery")
            self.rows.append(dict(id=job["id"],state=phase or "ready",phase=phase,
                                  payload=json.dumps(request(key*32).model_dump()),command=None))
        self.record={"status":"worker_busy","pipeline_version":1,"concurrency":2,
                     "worker_counts":{"active_renders":1,"staging":0,"undelivered":1}}
        self.entered=[Event(),Event(),Event()]

    def fake_tick(self,jid,**options):
        index=next(i for i,row in enumerate(self.rows) if row["id"]==jid)
        self.entered[index].set()
        self.release.wait(3)
        return "ok"

    def test_three_lanes_overlap_and_keep_jobs_distinct(self):
        s=self.scheduler
        with patch.object(s,"_jobs",return_value=self.rows),patch.object(s.lifecycle,"tick",return_value="worker_busy"),patch.object(s.lifecycle,"snapshot",return_value=self.record),patch.object(s.dispatch,"tick",side_effect=self.fake_tick):
            try:
                s.tick()
                self.assertEqual(set(s.flights),{"upload","observe","delivery"})
                self.assertEqual(len({jid for jid,_ in s.flights.values()}),3)
                self.assertTrue(all(event.wait(1) for event in self.entered))
                s.control.set_paused(True)
                self.assertFalse(s._may_start(2))
            finally:self.release.set()

    def test_unknown_remote_activity_does_not_admit_new_job(self):
        s=self.scheduler
        self.record["worker_counts"]["staging"]=1
        with patch.object(s,"_jobs",return_value=self.rows),patch.object(s.lifecycle,"tick",return_value="worker_busy"),patch.object(s.lifecycle,"snapshot",return_value=self.record),patch.object(s.dispatch,"tick",side_effect=self.fake_tick):
            try:
                s.tick()
                self.assertNotIn("upload",s.flights)
                self.assertIn("delivery",s.flights)
            finally:self.release.set()

class PauseDispatchTests(unittest.TestCase):
    def setUp(self):DispatchTests.setUp(self)
    def test_pause_no_remote_create_or_start(self):
        self.assertEqual(self.dispatch.tick(self.jid,allow_start=False),"paused")
        self.assertEqual(self.client.creates,0)
        self.assertEqual(self.dispatch.tick(self.jid),"staging")
        self.assertEqual(self.dispatch.tick(self.jid,allow_start=False),"paused")
        self.assertEqual(self.client.starts,0)
        self.assertEqual(self.dispatch.tick(self.jid),"running")
        self.client.finish()
        with patch("app.modules.studio.dispatch.RESERVE",0):
            self.assertEqual(self.dispatch.tick(self.jid,allow_start=False),"delivering")
            self.assertEqual(self.dispatch.tick(self.jid,allow_start=False),"published")
        self.assertEqual(self.dispatch.tick(self.jid,allow_start=False),"acknowledged")

if __name__=="__main__":unittest.main()
