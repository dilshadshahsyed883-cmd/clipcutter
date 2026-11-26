"""Synthetic, owner-scoped profile retention and reuse tests."""
import hashlib
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from pydantic import ValidationError
from app.modules.studio.contracts import JobRequest
from app.modules.studio.store import Store
from app.modules.studio.intake import stage
from app.modules.studio.profiles import SaveProfile,save,listing,delete
from app.modules.studio.dispatch import Dispatcher
from test_batch_intake import Bridge,VIDEO,REF
from test_gpu_dispatch import Fake

class Profiles(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name).resolve();self.store=Store("owner",self.base)
        p=patch("app.modules.studio.intake.RESERVE",0);p.start();self.addCleanup(p.stop)
        self.bridge=Bridge([("source.mp4",VIDEO)])
    def req(self,key,**settings):
        return JobRequest.model_validate({"request_id":key*32,"input":{"source":"https://drive.google.com/file/d/abcdefghijk/view"},
             "settings":{"kind":"analyzer",**settings}})
    def original(self):
        j=self.store.create(self.req("a",reference_link="https://drive.google.com/file/d/abcdefghijk/view"))
        stage(self.store,j["id"],self.bridge)
        self.assertEqual(self.store.get(j["id"])["state"],"ready")
        return j["id"]
    def test_save_reuse_and_delete(self):
        jid=self.original();value=SaveProfile(job_id=jid,label="Set A")
        p=save(self.store,value);pid=p["id"]
        self.assertEqual(save(self.store,value),p)
        self.assertEqual(listing(self.store)[0]["reference_count"],1)
        self.assertEqual(listing(Store("other",self.base)),[])
        with self.assertRaises(HTTPException):Store("other",self.base).create(self.req("b",profile_id=pid))
        q=self.store.create(self.req("b",profile_id=pid))
        with self.assertRaises(HTTPException):delete(self.store,pid)
        stage(self.store,q["id"],self.bridge)
        self.assertEqual(self.store.get(q["id"])["state"],"ready")
        root=self.store.root/"inputs"/q["id"]
        refs=[x for x in json.loads((root/"manifest.json").read_text())["files"] if x["role"]=="reference"]
        self.assertEqual(len(refs),1);self.assertEqual((root/refs[0]["file"]).read_bytes(),REF)
        delete(self.store,pid)
        self.assertEqual(listing(self.store),[])
        self.assertEqual((root/refs[0]["file"]).read_bytes(),REF)
        d=Dispatcher(self.store,Fake());d.prepare(q["id"])
        m=json.loads(d._row(q["id"])["manifest"])
        self.assertEqual(m["action"],"analyze")
        self.assertEqual(m["job"]["references_sha256"],[hashlib.sha256(REF).hexdigest()])
        self.assertEqual(m["job"]["request"]["settings"]["profile_id"],pid)
    def test_tamper_and_exclusive_reference(self):
        jid=self.original()
        root=self.store.root/"inputs"/jid
        ref=next(root.glob("reference-*.jpg"));ref.write_bytes(b"tampered")
        with self.assertRaises(HTTPException):save(self.store,SaveProfile(job_id=jid,label="Set"))
        with self.assertRaises(ValidationError):self.req("b",profile_id="1"*32,reference_link="https://drive.google.com/file/d/abcdefghijk/view")
        self.assertEqual(listing(self.store),[])
