import hashlib,json,tempfile,unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from fastapi import UploadFile,HTTPException
from app.modules.studio.contracts import JobRequest
from app.modules.studio.store import Store
from app.modules.studio.uploads import create_uploaded,stage_uploads,discard_uploads
from test_studio import request,FILE,FOLDER

class DirectReferenceTests(unittest.TestCase):
    def test_detect_links(self):
        p=request();p["input"].pop("source_kind")
        self.assertEqual(JobRequest.model_validate(p).input.source_kind,"auto")
        p["input"]["source"]=FOLDER
        self.assertEqual(JobRequest.model_validate(p).input.source_kind,"folder")
        p["input"]["source"]="https://youtu.be/abcdefghijk";p["settings"]["include_audio"]=False
        self.assertEqual(JobRequest.model_validate(p).input.source_kind,"youtube")
    def test_upload_and_stage(self):
        p=request();p["settings"].pop("reference_link")
        data=bytes([137,80,78,71,13,10,26,10])+b"test"
        def image(content=data):return UploadFile(filename="ref.png",file=BytesIO(content))
        with tempfile.TemporaryDirectory() as d,patch("app.modules.studio.uploads.RESERVE",0):
            root=Path(d).resolve();s=Store("owner",root)
            with self.assertRaises(HTTPException):create_uploaded(s,json.dumps(p),[image(b"invalid")])
            j=create_uploaded(s,json.dumps(p),[image()])
            self.assertEqual(j["settings"]["reference_uploads"],[hashlib.sha256(data).hexdigest()])
            self.assertEqual(create_uploaded(s,json.dumps(p),[image()])["id"],j["id"])
            tmp=root/"stage";tmp.mkdir();manifest=[]
            self.assertEqual(stage_uploads(s,j["id"],j["settings"]["reference_uploads"],tmp,manifest,1000),len(data))
            self.assertEqual((tmp/manifest[0]["file"]).read_bytes(),data)
            discard_uploads(s,j["id"])
            self.assertFalse((s.root/"reference-uploads"/p["request_id"]).exists())
    def test_resolution_preserves_idempotency(self):
        p=request();p["input"].pop("source_kind")
        with tempfile.TemporaryDirectory() as d:
            s=Store("owner",Path(d).resolve());req=JobRequest.model_validate(p)
            j=s.create(req);s.transition(j["id"],"awaiting_input","staging","test")
            s.resolve_source(j["id"],"video")
            self.assertEqual(s.create(req)["id"],j["id"])
