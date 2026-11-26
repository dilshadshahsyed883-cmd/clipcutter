import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from app.modules.studio.gpu import GPUSettings
from app.modules.studio.store import Store
from app.modules.studio.scheduler import Control,authorized,Scheduler
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
