import tempfile,unittest
from pathlib import Path
from app.modules.studio.auto_intake import run_once
from app.modules.studio.scheduler import Control
from app.modules.studio.store import Store
from app.modules.studio.contracts import JobRequest
from app.modules.studio.intake import stage
from test_studio import request,StudioWebTests,API
from test_drive_intake import FakeBridge

class AutoIntakeTests(unittest.TestCase):
    def test_queue_pause_resume_and_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store("owner",Path(d).resolve())
            p=request("analyzer");p["input"].pop("output_folder")
            first=s.create(JobRequest.model_validate(p))["id"]
            p["request_id"]="b"*32
            second=s.create(JobRequest.model_validate(p))["id"]
            control=Control(s);control.set_paused(True)
            calls=[]
            def worker(store,jid):
                calls.append(jid);stage(store,jid,FakeBridge())
            self.assertFalse(run_once(s,worker))
            self.assertEqual(s.get(first)["state"],"awaiting_input")
            control.set_paused(False)
            self.assertTrue(run_once(s,worker))
            self.assertEqual(calls,[first])
            self.assertEqual(s.get(first)["state"],"ready")
            s.transition(second,"awaiting_input","staging","interrupted")
            self.assertTrue(run_once(Store("owner",Path(d).resolve()),worker))
            self.assertEqual(s.get(second)["state"],"ready")
            self.assertFalse(run_once(s,worker))
            self.assertEqual(calls,[first,second])
    def test_stage_checks_pause(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store("owner",Path(d).resolve());job=s.create(JobRequest.model_validate(request("analyzer")))
            Control(s).set_paused(True);stage(s,job["id"],FakeBridge())
            self.assertEqual(s.get(job["id"])["state"],"awaiting_input")

class QueueWebTests(unittest.TestCase):
    setUp=StudioWebTests.setUp
    _form=StudioWebTests._form
    _login=StudioWebTests._login
    _signed_in=StudioWebTests._signed_in
    _post=StudioWebTests._post
    def test_owner_queue_controls(self):
        self.assertEqual(self.client.post(API+"/queue/pause").status_code,403)
        csrf=self._signed_in()
        self.assertEqual(self._post(API+"/queue/pause","invalid",{}).status_code,403)
        self.assertTrue(self._post(API+"/queue/pause",csrf,{}).json()["paused"])
        for kind in ("extractor","analyzer"):
            self.assertTrue(self.client.get(API+"/requests?kind="+kind).json()["paused"])
        self.assertFalse(self._post(API+"/queue/resume",csrf,{}).json()["paused"])
