import unittest
import tempfile
from pathlib import Path
from threading import Event
from pydantic import ValidationError
from worker.extractor.contracts import Options, ReviewManifest, ScanManifest
from worker.extractor.vendor.limits import bounded_parts
from worker.extractor.runner import local_file, verify, publish
import hashlib
import test_admin_security

class ContractTests(unittest.TestCase):
    def test_limits(self):
        self.assertIsNone(Options().minimum_ms)
        self.assertEqual(Options(minimum_ms=2500,maximum_ms=4000).maximum_ms,4000)
        for kwargs in (dict(minimum_ms=2500),dict(minimum_ms=4000,maximum_ms=2500),
                       dict(minimum_ms=2500,maximum_ms=4000,stitched=True),
                       dict(minimum_ms=2500,maximum_ms=4000,mode="copy")):
            with self.assertRaises(ValidationError): Options(**kwargs)
        for length in range(0,15000,37):
            parts=bounded_parts(length/1000,2.5,4)
            self.assertTrue(all(2500<=round((b-a)*1000)<=4000 for a,b in parts))
            self.assertLessEqual(sum(round((b-a)*1000) for a,b in parts),length)
    def test_reviews(self):
        digest="a"*64
        with self.assertRaises(ValidationError):
            ReviewManifest(source_sha256=digest,ranges=[{"start_ms":0,"end_ms":2000},{"start_ms":1000,"end_ms":3000}])
        with self.assertRaises(ValidationError):
            ScanManifest(source_sha256=digest,references_sha256=["bad"])
        with self.assertRaises(ValidationError):
            ReviewManifest(source_sha256=digest,ranges=[{"start_ms":0,"end_ms":2000}],options={"framing":"dynamic"})
    def test_staging_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            p=root/"source.video";p.write_bytes(b"video")
            self.assertEqual(local_file(root,p.name,100),p)
            verify(p,hashlib.sha256(b"video").hexdigest(),Event())
            with self.assertRaises(ValueError):verify(p,"a"*64,Event())
            cancel=Event();cancel.set()
            with self.assertRaises(InterruptedError):verify(p,"a"*64,cancel)
            (root/"link").symlink_to(p)
            with self.assertRaises(ValueError):local_file(root,"link",100)
            publish(root,"result.json",{"ok":True})
            with self.assertRaises(FileExistsError):publish(root,"result.json",{"ok":False})
            self.assertIn("true",(root/"result.json").read_text())

class WebOptionsTests(unittest.TestCase):
    setUp=test_admin_security.LocalAdminSecurityTests.setUp
    _form=test_admin_security.LocalAdminSecurityTests._form
    _login=test_admin_security.LocalAdminSecurityTests._login
    _signed_in=test_admin_security.LocalAdminSecurityTests._signed_in
    _post=test_admin_security.LocalAdminSecurityTests._post
    def test_protected_settings(self):
        self.assertEqual(self.client.get("/api/v1/extractor/capabilities").status_code,401)
        csrf=self._signed_in()
        self.assertFalse(self.client.get("/api/v1/extractor/capabilities").json()["dispatch_enabled"])
        self.assertEqual(self._post("/api/v1/extractor/options","invalid",{}).status_code,403)
        res=self._post("/api/v1/extractor/options",csrf,{"minimum_ms":2500,"maximum_ms":4000})
        self.assertEqual(res.status_code,200,res.text)
        self.assertFalse(res.json()["dispatch_enabled"])
        self.assertEqual(self._post("/api/v1/extractor/options",csrf,{"minimum_ms":4000,"maximum_ms":2000}).status_code,422)
