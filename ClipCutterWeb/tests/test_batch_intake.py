import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile
from app.modules.studio.batch import members,unpack,ident
from app.modules.studio.intake import stage
from app.modules.studio.contracts import JobRequest
from app.modules.studio.store import Store
from app.modules.studio.dispatch import Dispatcher
from test_gpu_dispatch import Fake, VIDEO

REF=b"\xff\xd8\xff synthetic"
def zipbytes(files):
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w",compression=zipfile.ZIP_STORED) as z:
        for name,data in files:z.writestr(name,data)
    return b.getvalue()
def sha(b):return hashlib.sha256(b).hexdigest()

class Bridge:
    def __init__(self,files,reference=False):
        self.files=files;self.reference=reference
    def discover(self,link,kind):
        files=[("reference.jpg",REF)] if kind=="image" else self.files
        return [{"id":f"drivefile{i:04d}","name":name,"size":len(data),
                 "md5":hashlib.md5(data,usedforsecurity=False).hexdigest(),"keys":""}
                for i,(name,data) in enumerate(files)]
    def request(self,op,payload,target,kind,remaining):
        row=payload["row"];files=[("reference.jpg",REF)] if kind=="image" else self.files
        name,data=next(x for x in files if x[0]==row["name"])
        target.write_bytes(data)
        return {"name":name,"size":len(data),"sha256":sha(data),
                "md5":hashlib.md5(data,usedforsecurity=False).hexdigest()}

class BatchTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.store=Store("owner",Path(tmp.name).resolve())
        self.reserve=patch("app.modules.studio.batch.RESERVE",0);self.reserve.start();self.addCleanup(self.reserve.stop)
    def create(self,kind="folder",reference=False):
        settings={"kind":"extractor","mode":"reference","reference_link":"https://drive.google.com/file/d/abcdefghijk/view"} if reference else {"kind":"analyzer"}
        url="https://drive.google.com/drive/folders/abcdefghijk" if kind=="folder" else "https://drive.google.com/file/d/abcdefghijk/view"
        return self.store.create(JobRequest.model_validate({"request_id":"a"*32,"input":{"source":url,"source_kind":kind},"settings":settings}))["id"]
    def test_folder_and_duplicate_prevention(self):
        jid=self.create();bridge=Bridge([("A.mp4",VIDEO),("B.mp4",VIDEO+b"2")])
        stage(self.store,jid,bridge)
        self.assertEqual(self.store.get(jid)["state"],"batch_expanded",self.store.get(jid))
        rows=members(self.store,jid)
        self.assertEqual([x["state"] for x in rows],["ready","ready"])
        self.assertEqual([x["label"] for x in rows],["A.mp4","B.mp4"])
        for x in rows:
            m=json.loads((self.store.root/"inputs"/x["id"]/"manifest.json").read_text())
            self.assertEqual(len(m["files"]),1)
            self.assertEqual(x["input"]["source_kind"],"video")
        stage(self.store,jid,bridge)
        self.assertEqual(members(self.store,jid),rows)
        self.assertEqual(Dispatcher(self.store,Fake()).tick(rows[0]["id"]),"staging")
    def test_zip_reference_propagation(self):
        jid=self.create("zip",True)
        stage(self.store,jid,Bridge([("archive.zip",zipbytes([("dir/A.mp4",VIDEO),("B.mp4",VIDEO+b"2"),("readme.txt",b"test")]))]))
        self.assertEqual(self.store.get(jid)["state"],"batch_expanded",self.store.get(jid))
        rows=members(self.store,jid);self.assertEqual(len(rows),2)
        for x in rows:
            root=self.store.root/"inputs"/x["id"]
            m=json.loads((root/"manifest.json").read_text())
            self.assertEqual([i["role"] for i in m["files"]],["source","reference"])
            self.assertEqual((root/"reference-0001.jpg").read_bytes(),REF)
            self.assertEqual(x["settings"]["mode"],"reference")
    def test_corrupt_zip_rejects_whole_batch(self):
        jid=self.create("zip")
        b=zipbytes([("A.mp4",VIDEO),("notes.txt",b"CRC_SENTINEL")]).replace(b"CRC_SENTINEL",b"CRC_CORRUPT!")
        stage(self.store,jid,Bridge([("archive.zip",b)]))
        self.assertEqual(self.store.get(jid)["state"],"failed")
        self.assertEqual(members(self.store,jid),[])
    def test_traversal_rejected(self):
        jid=self.create("zip")
        stage(self.store,jid,Bridge([("archive.zip",zipbytes([("../outside.mp4",VIDEO)]))]))
        self.assertEqual(self.store.get(jid)["state"],"failed")
        self.assertEqual(members(self.store,jid),[])
    def test_invalid_video_rejects_all(self):
        jid=self.create()
        stage(self.store,jid,Bridge([("A.mp4",VIDEO),("B.mp4",b"invalid")]))
        self.assertEqual(self.store.get(jid)["state"],"failed")
        self.assertEqual(members(self.store,jid),[])
    def test_storage_limit(self):
        jid=self.create("zip")
        with patch("app.modules.studio.batch.JOB_LIMIT",1):
            stage(self.store,jid,Bridge([("archive.zip",zipbytes([("A.mp4",VIDEO)]))]))
        self.assertEqual(self.store.get(jid)["state"],"failed")
        self.assertEqual(members(self.store,jid),[])
