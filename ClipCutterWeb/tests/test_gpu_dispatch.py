"""Synthetic tests; never contact Salad or a GPU."""
import hashlib
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
from app.modules.studio.contracts import JobRequest
from app.modules.studio.store import Store,safe_dir
from app.modules.studio.dispatch import Dispatcher,WorkerClient,DispatchError,RemoteError,canonical,CHUNK

def sha(b):return hashlib.sha256(b).hexdigest()
VIDEO=b"\x00\x00\x00\x18ftypisom synthetic"
OUT=b'{"people":[]}'
def request(key="a"*32,kind="analyzer"):
    s={"kind":kind}
    if kind=="extractor":s.update(mode="manual",ranges=[{"start_ms":0,"end_ms":2000}])
    return JobRequest.model_validate({"request_id":key,"input":{"source":"https://drive.google.com/file/d/abcdef123456789/view"},"settings":s})

class Fake:
    origin="https://example.salad.cloud";expected_sha="1"*40
    def __init__(self):self.remote=None;self.creates=0;self.starts=0;self.purges=0;self.fail_create=False
    def capabilities(self):return {"active_renders":0}
    def create(self,a,m):
        self.creates+=1
        self.remote={"attempt_id":a,"job_id":m["job"]["job_id"],"action":m["action"],"files":m["files"],
                     "uploaded":{n:0 for n in m["files"]},"state":"staging"}
        if self.fail_create:raise DispatchError("Lost response")
        return self.remote
    def status(self,a):
        if self.remote is None:raise RemoteError(404)
        return self.remote
    def put(self,a,n,offset,data):
        assert data==VIDEO
        self.remote["uploaded"][n]=offset+len(data)
        return {"offset":offset+len(data)}
    def start(self,a):
        self.starts+=1;self.remote["state"]="running";return self.remote
    def finish(self):
        result={"state":"completed","source_sha256":sha(VIDEO),"artifacts":[{"name":"analysis.json","size":len(OUT),"sha256":sha(OUT),"media_type":"application/json"}]}
        self.remote.update(state="completed",result=result,result_sha256=sha(canonical(result)))
    def fetch(self,a,n,offset,length):return OUT[offset:offset+length]
    def cancel(self,a):
        self.remote.update(state="cancelled",error="Cancelled")
        return self.remote
    def purge(self,a,digest):
        assert digest==("discard-failed" if self.remote["state"] in ("failed","cancelled") else self.remote["result_sha256"])
        self.purges+=1;self.remote["purged"]=True;return self.remote

class DispatchTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.store=Store("owner",Path(tmp.name).resolve());self.client=Fake()
        self.jid=self.store.create(request())["id"]
        self.store.transition(self.jid,"awaiting_input","staging","intake")
        root=safe_dir(safe_dir(self.store.root/"inputs")/self.jid)
        (root/"source-0001.mp4").write_bytes(VIDEO)
        (root/"manifest.json").write_text(json.dumps({"version":1,"files":[{"role":"source","file":"source-0001.mp4","size":len(VIDEO),"sha256":sha(VIDEO)}]}))
        self.store.transition(self.jid,"staging","ready","verified",100)
        self.dispatch=Dispatcher(self.store,self.client)
    def test_success_persistent_attempt_and_verified_ack(self):
        self.assertEqual(self.dispatch.tick(self.jid),"staging")
        self.assertEqual(self.dispatch.tick(self.jid),"running")
        self.assertEqual(self.client.starts,1)
        self.assertEqual(self.store.get(self.jid)["state"],"processing")
        self.client.finish()
        with patch("app.modules.studio.dispatch.RESERVE",0):
            self.assertEqual(self.dispatch.tick(self.jid),"delivering")
            self.assertEqual(self.dispatch.tick(self.jid),"published")
        self.assertEqual(self.store.get(self.jid)["state"],"completed")
        self.assertEqual(self.client.purges,0)
        restarted=Dispatcher(self.store,self.client)
        self.assertEqual(restarted.tick(self.jid),"acknowledged")
        self.assertEqual(restarted.tick(self.jid),"acknowledged")
        self.assertEqual(self.client.purges,1)
        self.assertEqual(self.client.creates,1)
        self.assertEqual(self.store.output_path(self.jid,"analysis.json")[0].read_bytes(),OUT)
    def test_performance_report_survives_purge_and_restart(self):
        from app.modules.studio.performance import report
        self.dispatch.tick(self.jid);self.dispatch.tick(self.jid)
        self.client.finish()
        self.client.remote["timing"]={"staging_at":100,"queued_at":105,"running_at":106,
            "input_verified_at":107,"processing_started_at":107,"processing_finished_at":120,
            "completed_at":121,"secret":"never export"}
        with patch("app.modules.studio.dispatch.RESERVE",0):
            self.dispatch.tick(self.jid);self.dispatch.tick(self.jid)
        self.client.remote["timing"]["purged_at"]=125
        Dispatcher(self.store,self.client).tick(self.jid)
        value=report(Store("owner",self.store.root.parent.parent),24)
        self.assertIn(self.jid,value)
        self.assertIn("13.000 s",value)
        self.assertIn("25.000 s",value)
        self.assertNotIn("never export",value)
        self.assertNotIn(self.client.origin,value)
        self.assertNotIn(self.jid,report(Store("other",self.store.root.parent.parent),24))

    def test_gpu_upload_progress_tracks_acknowledged_bytes_across_restart(self):
        def put(a,n,offset,data):
            self.assertEqual(data,VIDEO[offset:offset+len(data)])
            self.client.remote["uploaded"][n]=offset+len(data)
            return {"offset":offset+len(data)}
        with patch("app.modules.studio.dispatch.CHUNK",5),patch.object(self.client,"put",side_effect=put):
            self.assertEqual(self.dispatch.tick(self.jid),"staging")
            job=self.store.get(self.jid)
            self.assertEqual(job["state"],"ready")
            self.assertEqual(job["progress"],500//len(VIDEO))
            self.assertIn("5 / ",job["message"])
            restarted=Dispatcher(self.store,self.client)
            self.assertEqual(restarted.tick(self.jid,allow_start=False),"paused")
            self.assertEqual(self.store.get(self.jid)["progress"],500//len(VIDEO))
            self.assertEqual(restarted.tick(self.jid),"staging")
            self.assertEqual(self.store.get(self.jid)["progress"],1000//len(VIDEO))
            self.assertEqual(self.client.creates,1)
            while self.client.remote["uploaded"]["source.video"]<len(VIDEO):
                self.assertEqual(restarted.tick(self.jid),"staging")
            self.assertEqual(self.store.get(self.jid)["progress"],100)
            self.assertEqual(restarted.tick(self.jid),"running")
            self.assertEqual(self.store.get(self.jid)["state"],"processing")
            self.assertEqual(self.store.get(self.jid)["progress"],0)

    def test_gpu_upload_bad_ack_does_not_advance_progress(self):
        with patch.object(self.client,"put",return_value={"offset":1}):
            with self.assertRaisesRegex(DispatchError,"Unexpected upload acknowledgement"):
                self.dispatch.tick(self.jid)
        self.assertEqual(self.store.get(self.jid)["progress"],0)
        self.assertEqual(self.client.starts,0)

    def test_verified_job_can_use_ready_worker_during_new_intake(self):
        self.store.create(request("b"*32))
        self.assertEqual(self.dispatch.tick(self.jid,allow_during_intake=True),"staging")
        self.assertEqual(self.dispatch.tick(self.jid,allow_during_intake=True),"running")

    def test_measured_processing_and_delivery_progress(self):
        self.dispatch.tick(self.jid)
        self.dispatch.tick(self.jid)
        self.client.remote["progress"]={"stage":"scan","message":"Frames","done":3,"total":10}
        self.dispatch.tick(self.jid)
        self.assertEqual(self.store.get(self.jid)["progress"],30)
        self.client.finish()
        with patch("app.modules.studio.dispatch.RESERVE",0):
            self.assertEqual(self.dispatch.tick(self.jid),"delivering")
        self.assertEqual(self.store.get(self.jid)["progress"],100)

    def test_preload_at_capacity_then_start(self):
        with patch.object(self.client,"capabilities",return_value={"active_renders":2,"concurrency":2,"pipeline_version":1}):
            self.assertEqual(self.dispatch.tick(self.jid,render_limit=2),"staging")
            self.assertEqual(self.dispatch.tick(self.jid,render_limit=2),"preloaded")
            self.assertEqual(self.client.starts,0)
        with patch.object(self.client,"capabilities",return_value={"active_renders":1,"concurrency":2,"pipeline_version":1}):
            self.assertEqual(self.dispatch.tick(self.jid,render_limit=2),"running")
        self.assertEqual(self.client.starts,1)

    def test_parallel_requires_capability(self):
        with self.assertRaisesRegex(DispatchError,"capacity mismatch"):
            self.dispatch.tick(self.jid,render_limit=2)
        self.assertEqual(self.client.creates,0)

    def test_observe_then_independent_delivery(self):
        self.dispatch.tick(self.jid);self.dispatch.tick(self.jid);self.client.finish()
        self.assertEqual(self.dispatch.tick(self.jid,observe_only=True),"output_ready")
        self.assertEqual(self.store.get(self.jid)["state"],"processing")
        with patch("app.modules.studio.dispatch.RESERVE",0):
            self.assertEqual(self.dispatch.tick(self.jid),"delivering")
            self.assertEqual(self.dispatch.tick(self.jid),"published")
        self.assertEqual(self.dispatch.tick(self.jid),"acknowledged")

    def test_cancel_staging_retains_verified_inputs(self):
        self.dispatch.tick(self.jid)
        self.store.gpu_command(self.jid,"cancel")
        self.assertEqual(self.dispatch.tick(self.jid,allow_start=False,observe_only=True),"cancelled_clean")
        self.assertEqual(self.store.get(self.jid)["state"],"cancelled")
        self.assertEqual(self.client.starts,0)
        self.assertEqual(self.client.purges,1)
        self.assertTrue((self.store.root/"inputs"/self.jid/"source-0001.mp4").is_file())

    def test_confirmed_failure_retry_without_redownload(self):
        self.dispatch.tick(self.jid);self.dispatch.tick(self.jid)
        old=self.dispatch._row(self.jid)["attempt_id"]
        self.client.remote.update(state="failed",error="test GPU failure")
        self.assertEqual(self.dispatch.tick(self.jid),"failed_clean")
        self.assertEqual(self.store.get(self.jid)["state"],"failed")
        self.store.gpu_command(self.jid,"retry")
        self.assertEqual(self.dispatch.tick(self.jid,allow_start=False,observe_only=True),"retry_queued")
        self.assertNotEqual(self.dispatch._row(self.jid)["attempt_id"],old)
        self.assertEqual(self.store.get(self.jid)["state"],"ready")
        self.assertEqual(self.dispatch.tick(self.jid),"staging")
        self.assertEqual(self.client.creates,2)

    def test_all_intake_barrier(self):
        self.store.create(request("b"*32))
        with self.assertRaisesRegex(DispatchError,"pending Drive intake"):self.dispatch.tick(self.jid)
        self.assertEqual(self.client.creates,0)
    def test_ambiguous_create_never_recreate_missing(self):
        self.client.fail_create=True
        with self.assertRaises(DispatchError):self.dispatch.tick(self.jid)
        self.client.remote=None
        with self.assertRaises(RemoteError):self.dispatch.tick(self.jid)
        self.assertEqual(self.client.creates,1)
        self.assertEqual(self.store.get(self.jid)["state"],"ready")
    def test_tampered_result_rejected(self):
        self.dispatch.tick(self.jid);self.dispatch.tick(self.jid);self.client.finish()
        self.client.remote["result_sha256"]="0"*64
        with self.assertRaisesRegex(DispatchError,"Invalid result"):self.dispatch.tick(self.jid)
        self.assertEqual(self.client.purges,0)
    def test_youtube_dispatch_requires_approved_capability(self):
        with self.store.connect() as c:
            p=json.loads(c.execute("SELECT payload FROM requests WHERE id=?",(self.jid,)).fetchone()[0])
            p["input"].update(source_kind="youtube",source="https://www.youtube.com/watch?v=NMeVJDrpQO8")
            c.execute("UPDATE requests SET payload=? WHERE id=?",(json.dumps(p),self.jid))
        with patch.dict("os.environ",{"CLIPCUTTER_YOUTUBE_DISPATCH_ENABLED":"0"}):
            with self.assertRaisesRegex(DispatchError,"YouTube"):self.dispatch.tick(self.jid)
        with patch.dict("os.environ",{"CLIPCUTTER_YOUTUBE_DISPATCH_ENABLED":"1"}):
            with self.assertRaisesRegex(DispatchError,"advertise YouTube"):self.dispatch.tick(self.jid)
            self.assertEqual(self.client.creates,0)
            with patch.object(self.client,"capabilities",return_value={"active_renders":0,"source_kinds":["video","youtube"]}):
                self.assertEqual(self.dispatch.tick(self.jid),"staging")
                self.assertEqual(self.dispatch.tick(self.jid),"running")
    def test_drive_delivery_runs_without_blocking_scheduler(self):
        entered=Event();release=Event()
        def deliver(*args):
            entered.set();release.wait(3);return True
        try:
            with patch("app.modules.studio.dispatch.deliver_one",side_effect=deliver) as mocked:
                self.assertFalse(self.dispatch.drive_delivery_tick(self.jid,"folder",None,[]))
                self.assertTrue(entered.wait(2))
                self.assertFalse(self.dispatch.drive_delivery_tick(self.jid,"folder",None,[]))
                self.assertEqual(mocked.call_count,1)
                release.set()
                self.dispatch.delivery_future.result(timeout=2)
                self.assertTrue(self.dispatch.drive_delivery_tick(self.jid,"folder",None,[]))
        finally:
            release.set();self.dispatch.close()
    def test_worker_origin_rejects_untrusted(self):
        with self.assertRaises(DispatchError):WorkerClient("https://example.org","x"*32,"y"*32,"1"*40,approved_gateway="https://example.org")
        with self.assertRaises(DispatchError):WorkerClient("https://a.salad.cloud","x"*32,"y"*32,"1"*40,approved_gateway="https://b.salad.cloud")

if __name__=="__main__":unittest.main()
