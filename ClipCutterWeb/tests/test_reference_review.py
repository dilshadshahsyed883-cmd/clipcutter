import hashlib
import json
import tempfile
from pathlib import Path
import unittest
from fastapi import HTTPException
from app.modules.studio.contracts import JobRequest
from app.modules.studio.store import Store,safe_dir
from app.modules.studio.dispatch import Dispatcher,canonical,DispatchError
from app.modules.studio.review import Approval,get_review,approve,source_preview

def sha(b):return hashlib.sha256(b).hexdigest()
VIDEO=b"\x00\x00\x00\x18ftypisom synthetic";REF=b"reference"

class Fake:
    origin="https://example.salad.cloud";expected_sha="1"*40
    def __init__(self):self.remote=None;self.attempts=[];self.purges=0;self.starts=0
    def capabilities(self):return {"active_renders":0}
    def create(self,a,m):
        self.attempts.append(a)
        self.remote={"attempt_id":a,"job_id":m["job"]["job_id"],"action":m["action"],
                     "files":m["files"],"uploaded":{n:0 for n in m["files"]},"state":"staging"}
        return self.remote
    def status(self,a):return self.remote
    def put(self,a,n,offset,data):
        self.remote["uploaded"][n]=offset+len(data);return {"offset":offset+len(data)}
    def start(self,a):self.starts+=1;self.remote["state"]="running";return self.remote
    def finish(self):
        result={"state":"review","source_sha256":sha(VIDEO),"duration_ms":5000,
                "ranges":[{"start_ms":1000,"end_ms":3000,"origin":"scan"}]}
        self.remote.update(state="completed",result=result,result_sha256=sha(canonical(result)))
    def purge(self,a,digest):
        assert digest==self.remote["result_sha256"]
        self.purges+=1;self.remote["purged"]=True;return self.remote

class ReviewTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.store=Store("owner",Path(tmp.name).resolve());self.worker=Fake()
        self.jid=self.store.create(JobRequest.model_validate({"request_id":"a"*32,
          "input":{"source":"https://drive.google.com/file/d/abcdef123456789/view"},
          "settings":{"kind":"extractor","mode":"reference","reference_link":"https://drive.google.com/file/d/abcdef987654321/view"}}))["id"]
        self.store.transition(self.jid,"awaiting_input","staging","intake")
        root=safe_dir(safe_dir(self.store.root/"inputs")/self.jid)
        self.root=root;items=[]
        for role,name,data in [("source","source-0001.mp4",VIDEO),("reference","reference-0002.jpg",REF)]:
            (root/name).write_bytes(data);items.append({"role":role,"file":name,"size":len(data),"sha256":sha(data)})
        (root/"manifest.json").write_text(json.dumps({"version":1,"files":items}))
        self.store.transition(self.jid,"staging","ready","verified")
        self.d=Dispatcher(self.store,self.worker)
    def scan(self):
        self.assertEqual(self.d.tick(self.jid),"staging")
        self.assertEqual(self.d.tick(self.jid),"staging")
        self.assertEqual(self.d.tick(self.jid),"running")
        self.worker.finish()
        self.assertEqual(self.d.tick(self.jid),"review_ready")
    def approval(self,start=1000,end=3000):
        return Approval(scan_sha256=get_review(self.store,self.jid)["scan_sha256"],ranges=[{"start_ms":start,"end_ms":end}])
    def test_explicit_review_new_attempt(self):
        self.scan()
        self.assertEqual(self.worker.purges,1)
        self.assertEqual(self.d.tick(self.jid),"review_ready")
        self.assertEqual(self.worker.starts,1)
        a=self.approval(1500,3500);r=approve(self.store,self.jid,a)
        self.assertEqual(r["state"],"ready")
        self.assertEqual(approve(self.store,self.jid,a)["state"],"ready")
        review=json.loads((self.root/"approved-review.json").read_text())
        self.assertEqual(review["ranges"],[{"start_ms":1500,"end_ms":3500}])
        for _ in range(3):self.assertEqual(self.d.tick(self.jid),"staging")
        self.assertEqual(self.d.tick(self.jid),"running")
        self.assertEqual(self.worker.remote["action"],"export")
        self.assertNotEqual(*self.worker.attempts)
    def test_source_preview_owner_scope_and_verified_state(self):
        with self.assertRaises(HTTPException):source_preview(self.store,self.jid)
        self.scan()
        path,media=source_preview(self.store,self.jid)
        self.assertEqual(path,self.root/"source-0001.mp4")
        self.assertEqual(media,"video/mp4")
        with self.assertRaises(HTTPException):source_preview(Store("other",self.store.root.parent.parent),self.jid)
        path.write_bytes(b"changed")
        with self.assertRaises(HTTPException):source_preview(self.store,self.jid)

    def test_vps_review_approval_stays_local(self):
        with self.store.connect() as c:
            p=json.loads(c.execute("SELECT payload FROM requests WHERE id=?",(self.jid,)).fetchone()[0])
            p["settings"]["gpu_clip_extraction"]=False
            c.execute("UPDATE requests SET payload=? WHERE id=?",(json.dumps(p),self.jid))
        self.scan()
        self.assertNotIn("gpu_clip_extraction",json.loads(self.d._row(self.jid)["manifest"])["job"]["request"]["settings"])
        approve(self.store,self.jid,self.approval())
        self.assertEqual(self.d._row(self.jid)["phase"],"vps_new")
        from unittest.mock import patch
        def fake_encode(source,settings,ranges,out,cancel,progress):
            p=out/"clip_001.mp4";p.write_bytes(VIDEO)
            return [{"name":p.name,"size":len(VIDEO),"sha256":sha(VIDEO),"media_type":"video/mp4","duration_ms":2000}]
        with patch("app.modules.studio.vps_export.encode",side_effect=fake_encode):
            self.assertEqual(self.d.tick(self.jid),"acknowledged")
        self.assertEqual(self.worker.starts,1)
        self.assertEqual(self.store.get(self.jid)["state"],"completed")
        from app.modules.studio.output_names import visible
        from app.modules.studio.performance import report
        self.assertEqual(visible(self.store,self.jid)["outputs"][0]["duration_ms"],2000)
        result=report(self.store,24)
        self.assertIn("vps_export | completed",result)
        self.assertIn("VPS delivery and verification:",result)

    def test_range_and_changed_input_rejected(self):
        self.scan()
        with self.assertRaises(HTTPException):approve(self.store,self.jid,self.approval(1000,6000))
        (self.root/"source-0001.mp4").write_bytes(b"changed")
        with self.assertRaises(HTTPException):approve(self.store,self.jid,self.approval())
        self.assertEqual(self.store.get(self.jid)["state"],"review")
    def test_bad_scan_rejected(self):
        for _ in range(3):self.d.tick(self.jid)
        self.worker.finish()
        self.worker.remote["result"]["ranges"][0]["end_ms"]=7000
        self.worker.remote["result_sha256"]=sha(canonical(self.worker.remote["result"]))
        with self.assertRaises(DispatchError):self.d.tick(self.jid)
        self.assertEqual(self.worker.purges,0)
