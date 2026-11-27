import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from app.modules.studio.store import Store,safe_dir
from app.modules.studio.dispatch import Dispatcher
from app.modules.studio.person_extract import PersonExtraction,queue_person
from test_gpu_dispatch import Fake,request,VIDEO,sha,canonical

class PersonExtractionTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name).resolve();self.store=Store("owner",self.base);self.worker=Fake()
        self.jid=self.store.create(request())["id"]
        self.store.transition(self.jid,"awaiting_input","staging","intake")
        self.root=safe_dir(safe_dir(self.store.root/"inputs")/self.jid)
        (self.root/"source-0001.mp4").write_bytes(VIDEO)
        (self.root/"manifest.json").write_text(json.dumps({"version":1,"files":[{"role":"source","file":"source-0001.mp4","size":len(VIDEO),"sha256":sha(VIDEO)}]}))
        self.store.transition(self.jid,"staging","ready","verified")
        self.d=Dispatcher(self.store,self.worker)
        self.d.tick(self.jid);self.d.tick(self.jid);self.worker.finish()
        self.person="a"*12;self.filtered="b"*12
        self.summary=json.dumps({"source_sha256":sha(VIDEO),"duration":10,"timeline_precision":"sample-cell estimate",
          "people":[{"id":self.person,"name":"Person 1","filtered":False,"segments":[[0.5,1.5],[3,4]],"raw_segments":[[0,5]]},
                    {"id":self.filtered,"name":"Person 2","filtered":True,"segments":[]}] }).encode()
        result=self.worker.remote["result"];result["artifacts"]=[{"name":"analysis.json","size":len(self.summary),"sha256":sha(self.summary),"media_type":"application/json"}]
        self.worker.remote["result_sha256"]=sha(canonical(result))
        with patch("app.modules.studio.dispatch.RESERVE",0),patch.object(self.worker,"fetch",side_effect=lambda a,n,o,l:self.summary[o:o+l]):
            self.d.tick(self.jid);self.d.tick(self.jid)
        self.options=PersonExtraction(request_id="f"*32,gpu_clip_extraction=False,include_audio=False)

    def test_only_verified_accepted_ranges_ready_no_download_and_replay(self):
        with self.assertRaises(HTTPException):queue_person(self.store,self.jid,self.person,self.options)
        self.d.tick(self.jid)
        with patch("app.modules.studio.batch.RESERVE",0):
            child=queue_person(self.store,self.jid,self.person,self.options)
            replay=queue_person(self.store,self.jid,self.person,self.options)
        self.assertEqual(child["id"],replay["id"])
        self.assertEqual(child["state"],"ready")
        self.assertEqual(child["settings"]["mode"],"manual")
        self.assertEqual(child["settings"]["ranges"],[{"start_ms":500,"end_ms":1500},{"start_ms":3000,"end_ms":4000}])
        self.assertFalse(child["settings"]["gpu_clip_extraction"])
        self.assertEqual((self.store.root/"inputs"/child["id"]/"source-0001.mp4").read_bytes(),VIDEO)
        self.assertEqual(self.worker.starts,1)
        self.assertEqual(self.store.list("extractor")[0]["id"],child["id"])
        with self.assertRaises(HTTPException):queue_person(self.store,self.jid,self.person,self.options.model_copy(update={"quality":80}))

    def test_filtered_owner_scope_and_modified_source_rejected(self):
        self.d.tick(self.jid)
        for store,person in [(Store("other",self.base),self.person),(self.store,self.filtered)]:
            with self.assertRaises(HTTPException):queue_person(store,self.jid,person,self.options)
        (self.root/"source-0001.mp4").write_bytes(b"x"*len(VIDEO))
        with patch("app.modules.studio.batch.RESERVE",0):
            with self.assertRaises(HTTPException):queue_person(self.store,self.jid,self.person,self.options)
        self.assertEqual(self.store.list("extractor"),[])
