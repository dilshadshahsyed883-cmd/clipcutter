import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.modules.studio.intake import stage, verify_format, Retryable, retry
from app.modules.studio.store import Store
from app.modules.studio.contracts import JobRequest

class FakeBridge:
    def discover(self,link,kind):
        return [{"id":"abcdefghijk","name":"","size":0,"md5":"","keys":""}]
    def request(self,op,payload,target,kind,remaining):
        data=b"\x00\x00\x00\x18ftypmp42"
        target.write_bytes(data)
        return {"name":"video.mp4","size":len(data),"sha256":hashlib.sha256(data).hexdigest(),
                "md5":hashlib.md5(data,usedforsecurity=False).hexdigest()}

class IntakeTests(unittest.TestCase):
    def test_stage_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Store("owner",Path(tmp).resolve())
            j=s.create(JobRequest.model_validate({"request_id":"a"*32,"input":{"source":"https://drive.google.com/file/d/abcdefghijk/view"},"settings":{"kind":"analyzer"}}))
            stage(s,j["id"],FakeBridge())
            self.assertEqual(s.get(j["id"])["state"],"ready")
            self.assertTrue((s.root/"inputs"/j["id"]/"manifest.json").is_file())
            stage(s,j["id"],FakeBridge())
            self.assertEqual(s.get(j["id"])["state"],"ready")
    def test_format_and_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"bad"
            p.write_bytes(b"not a video")
            with self.assertRaises(RuntimeError): verify_format(p,"video",".mp4")
        with patch("app.modules.studio.intake.time.sleep") as sleep:
            n=[]
            def fail():
                n.append(1)
                raise Retryable("temporary")
            with self.assertRaises(Retryable): retry(fail)
            self.assertEqual(len(n),5)
            self.assertEqual(sleep.call_count,4)
