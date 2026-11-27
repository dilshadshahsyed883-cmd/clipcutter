import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from worker.transport import Worker,ApiError,canonical

def sha(data):return hashlib.sha256(data).hexdigest()
VIDEO=b"synthetic input bytes"

def manifest(data=VIDEO):
    return {"action":"export","job":{"version":1,"job_id":"a"*32,"source_sha256":sha(data),"request":{
        "request_id":"b"*32,"input":{"source":"https://drive.google.com/file/d/abcdef123456789/view","source_kind":"video"},
        "settings":{"kind":"extractor","mode":"manual","ranges":[{"start_ms":0,"end_ms":2000}]}}},
        "files":{"source.video":{"size":len(data),"sha256":sha(data)}}}

def launch(a,root,action):
    output=root/"outputs";output.mkdir()
    data=b"verified fake output";(output/"clip.mp4").write_bytes(data)
    (root/"export-result.json").write_text(json.dumps({"state":"completed","source_sha256":sha(VIDEO),
        "artifacts":[{"name":"clip.mp4","size":len(data),"sha256":sha(data)}]}))

class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.a="c"*32
        self.w=Worker(self.root,lambda:True,launch=launch,concurrency=1);self.addCleanup(self.w.shutdown)
    def stage(self):
        self.w.create(self.a,manifest())
        self.w.put(self.a,"source.video",0,VIDEO,sha(VIDEO))
    def wait_terminal(self,w=None):
        w=w or self.w
        for _ in range(300):
            r=w.snapshot(self.a)
            if r["state"] in {"completed","failed","cancelled"}:return r
            time.sleep(.01)
        self.fail("Worker did not become terminal")
    def test_success_replay_and_ack(self):
        self.stage()
        self.assertEqual(self.w.create(self.a,manifest())["uploaded"]["source.video"],len(VIDEO))
        self.assertEqual(self.w.put(self.a,"source.video",0,VIDEO,sha(VIDEO)),{"offset":len(VIDEO)})
        self.w.start(self.a)
        result=self.wait_terminal();self.assertEqual(result["state"],"completed",result)
        self.assertEqual(self.w.fetch(self.a,"clip.mp4",0,8),b"verified")
        self.assertEqual(self.w.metrics()["undelivered"],1)
        with self.assertRaises(ApiError):self.w.purge(self.a,"wrong")
        self.w.purge(self.a,result["result_sha256"])
        self.assertFalse((self.root/self.a/"input").exists())
        timing=self.w.snapshot(self.a)["timing"]
        fields=("staging_at","queued_at","running_at","input_verified_at","processing_started_at",
                "processing_finished_at","completed_at","purged_at")
        values=[timing[name] for name in fields]
        self.assertEqual(values,sorted(values))
        self.assertEqual(self.w.create(self.a,manifest())["timing"],timing)
        restored=Worker(self.root,lambda:True,launch=launch,concurrency=1)
        self.addCleanup(restored.shutdown)
        self.assertEqual(restored.snapshot(self.a)["timing"],timing)
        self.assertEqual(self.w.start(self.a)["state"],"completed")
        self.assertEqual(self.w.metrics()["undelivered"],0)
    def test_youtube_staged_contract(self):
        m=manifest()
        m["job"]["request"]["input"]={"source_kind":"youtube","source":"https://www.youtube.com/watch?v=NMeVJDrpQO8"}
        m["job"]["request"]["settings"]["include_audio"]=False
        self.w.create(self.a,m)
        self.w.put(self.a,"source.video",0,VIDEO,sha(VIDEO))
        self.w.start(self.a)
        self.assertEqual(self.wait_terminal()["state"],"completed")
    def test_conflict_partial_bad_hash(self):
        self.w.create(self.a,manifest())
        with self.assertRaises(ApiError):self.w.create(self.a,manifest(b"other"))
        with self.assertRaises(ApiError):self.w.start(self.a)
        with self.assertRaises(ApiError):self.w.put(self.a,"source.video",0,VIDEO,"0"*64)
        with self.assertRaises(ApiError):self.w.put(self.a,"../escape",0,VIDEO,sha(VIDEO))
        with self.assertRaises(ApiError):self.w.put(self.a,"source.video",1,VIDEO,sha(VIDEO))
        self.w.put(self.a,"source.video",0,VIDEO,sha(VIDEO))
        with self.assertRaises(ApiError):self.w.put(self.a,"source.video",0,b"x",sha(b"x"))
    def test_complete_digest_verification(self):
        self.w.create(self.a,manifest())
        wrong=b"x"*len(VIDEO)
        self.w.put(self.a,"source.video",0,wrong,sha(wrong));self.w.start(self.a)
        self.assertIn("digest mismatch",self.wait_terminal()["error"])
    def test_cancel_and_discard(self):
        self.stage();self.assertEqual(self.w.cancel(self.a)["state"],"cancelled")
        with self.assertRaises(ApiError):self.w.purge(self.a,"wrong")
        self.assertTrue(self.w.purge(self.a,"discard-failed")["purged"])
    def test_not_ready(self):
        self.w.ready=lambda:False
        with self.assertRaises(ApiError) as cm:self.w.create(self.a,manifest())
        self.assertEqual(cm.exception.code,503)
    def test_restart_interrupted_attempt(self):
        self.stage()
        with self.w.lock:self.w.change(self.w.get(self.a),state="running")
        second=Worker(self.root,lambda:True,launch=launch)
        self.assertEqual(second.snapshot(self.a)["state"],"failed")
        self.assertEqual(second.start(self.a)["state"],"failed")
    def test_two_slots_and_independent_preload(self):
        entered=Event();release=Event()
        def slow(a,root,action):
            if self.w.metrics()["active_renders"]==2:entered.set()
            release.wait(3)
            launch(a,root,action)
        self.w.shutdown()
        self.w=Worker(self.root,lambda:True,launch=slow,concurrency=2)
        self.addCleanup(self.w.shutdown)
        ids=["c"*32,"d"*32,"e"*32]
        try:
            for a in ids:
                self.w.create(a,manifest())
                self.w.put(a,"source.video",0,VIDEO,sha(VIDEO))
            self.w.start(ids[0]);self.w.start(ids[1])
            self.assertTrue(entered.wait(2))
            metrics=self.w.metrics()
            self.assertEqual((metrics["active_renders"],metrics["staging"],metrics["concurrency"]),(2,1,2))
            with self.assertRaises(ApiError) as cm:self.w.start(ids[2])
            self.assertEqual(cm.exception.code,429)
            self.assertEqual(self.w.cancel(ids[2])["state"],"cancelled")
        finally:release.set()
        for a in ids[:2]:
            for _ in range(300):
                if self.w.snapshot(a)["state"]=="completed":break
                time.sleep(.01)
            self.assertEqual(self.w.snapshot(a)["state"],"completed")
        self.assertEqual(self.w.metrics()["undelivered"],2)

    def test_running_cancel_and_single_slot(self):
        entered=Event();release=Event()
        def slow(a,root,action):
            entered.set();release.wait(3);raise InterruptedError("Cancelled")
        self.w.launch=slow;self.stage();self.w.start(self.a)
        self.assertTrue(entered.wait(2))
        b="d"*32;self.w.create(b,manifest());self.w.put(b,"source.video",0,VIDEO,sha(VIDEO))
        try:
            self.assertEqual(self.w.metrics()["active_renders"],1)
            with self.assertRaises(ApiError):self.w.start(b)
            self.w.cancel(self.a)
        finally:release.set()
        self.assertEqual(self.wait_terminal()["state"],"cancelled")

if __name__=="__main__":unittest.main()
