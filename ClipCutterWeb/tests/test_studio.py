"""Source-level web-only request and receipt boundary tests."""
import hashlib
import tempfile
from pathlib import Path
import unittest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.main import create_app
from app.modules.studio.contracts import JobRequest
from app.modules.studio.store import Store
import test_admin_security

FILE="https://drive.google.com/file/d/abcdef123456789/view"
FOLDER="https://drive.google.com/drive/folders/abcdef123456789"
API="/api/v1/studio"

def request(kind="extractor",key="a"*32):
    settings={"kind":kind}
    if kind=="extractor": settings.update(mode="reference",reference_link=FOLDER)
    return {"input":{"source":FILE,"source_kind":"video","output_folder":FOLDER},
            "settings":settings,"request_id":key}

class ContractTests(unittest.TestCase):
    def test_both_kinds(self):
        self.assertEqual(JobRequest.model_validate(request()).settings.kind,"extractor")
        self.assertEqual(JobRequest.model_validate(request("analyzer")).settings.kind,"analyzer")
    def test_invalid_sources_and_settings(self):
        for url in ["http://drive.google.com/file/d/abcdef123456789/view","https://drive.google.com.evil.test/file/d/abcdef123456789/view","https://drive.google.com@evil.test/file/d/abcdef123456789/view","https://drive.google.com/evil"]:
            p=request();p["input"]["source"]=url
            with self.assertRaises(ValidationError):JobRequest.model_validate(p)
        p=request();p["settings"].update(mode="manual",ranges=[{"start_ms":0,"end_ms":3000},{"start_ms":1000,"end_ms":4000}])
        with self.assertRaises(ValidationError):JobRequest.model_validate(p)
        p=request();p["settings"].update(minimum_ms=4000,maximum_ms=2000)
        with self.assertRaises(ValidationError):JobRequest.model_validate(p)
        p=request("analyzer");p["settings"]["ignore_regions"]=[{"x":.9,"y":0.0,"w":.3,"h":.1}]
        with self.assertRaises(ValidationError):JobRequest.model_validate(p)
        p=request();p["owner"]="other"
        with self.assertRaises(ValidationError):JobRequest.model_validate(p)

class LedgerTests(unittest.TestCase):
    def test_persistence_and_verified_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            s=Store("owner",root); other=Store("other",root)
            job=s.create(JobRequest.model_validate(request()))
            jid=job["id"];self.assertEqual(job["state"],"awaiting_input")
            self.assertEqual(Store("owner",root).get(jid),job)
            self.assertEqual(s.create(JobRequest.model_validate(request()))["id"],jid)
            with self.assertRaises(HTTPException):other.get(jid)
            self.assertEqual(s.output_list(jid),[])
            for a,b in [("awaiting_input","staging"),("staging","ready"),("ready","processing"),("processing","delivering")]:
                s.transition(jid,a,b,"Actual event")
            out=s.root/"outputs"/jid;out.mkdir(parents=True,mode=0o700)
            (out/"result.json").write_bytes(b"{}")
            manifest=[{"name":"result.json","size":2,"sha256":"0"*64,"media_type":"application/json"}]
            with self.assertRaises(ValueError):s.publish_verified_outputs(jid,manifest)
            self.assertEqual(s.output_list(jid),[])
            manifest[0]["sha256"]=hashlib.sha256(b"{}").hexdigest()
            self.assertEqual(s.publish_verified_outputs(jid,manifest)["state"],"completed")
            self.assertEqual(s.output_path(jid,"result.json")[0],out/"result.json")
            with self.assertRaises(HTTPException):other.output_path(jid,"result.json")
            with self.assertRaises(HTTPException):s.output_path(jid,"../result.json")
            with self.assertRaises(HTTPException):s.cancel(jid)

class StudioWebTests(unittest.TestCase):
    setUp=test_admin_security.LocalAdminSecurityTests.setUp
    _form=test_admin_security.LocalAdminSecurityTests._form
    _login=test_admin_security.LocalAdminSecurityTests._login
    _signed_in=test_admin_security.LocalAdminSecurityTests._signed_in
    _post=test_admin_security.LocalAdminSecurityTests._post

    def test_admission_security_and_cancel(self):
        self.assertEqual(self.client.get(API+"/requests?kind=extractor").status_code,401)
        csrf=self._signed_in()
        self.assertEqual(self._post(API+"/requests","invalid",request()).status_code,403)
        response=self._post(API+"/requests",csrf,request())
        self.assertEqual(response.status_code,201,response.text)
        job=response.json();jid=job["id"]
        self.assertEqual(job["state"],"awaiting_input")
        self.assertIsNone(job["progress"])
        self.assertEqual(self._post(API+"/requests",csrf,request()).json()["id"],jid)
        changed=request();changed["settings"]["threshold"]=.6
        self.assertEqual(self._post(API+"/requests",csrf,changed).status_code,409)
        self.assertEqual(self._post(API+"/requests",csrf,request("analyzer","b"*32)).status_code,201)
        self.assertEqual(len(self.client.get(API+"/requests?kind=extractor").json()["requests"]),1)
        self.assertEqual(len(self.client.get(API+"/requests?kind=analyzer").json()["requests"]),1)
        self.assertEqual(self.client.get(API+"/requests/"+jid+"/outputs").json(),{"outputs":[]})
        self.assertEqual(self.client.get(API+"/requests/"+jid+"/outputs/clip.mp4").status_code,404)
        self.assertFalse(self.client.get(API+"/capabilities").json()["worker_dispatch"])
        self.assertEqual(self._post(API+"/requests/"+jid+"/cancel",csrf).json()["state"],"cancelled")
        with TestClient(create_app(),base_url=test_admin_security.ORIGIN) as other:
            other.cookies.set(test_admin_security.COOKIE,self.client.cookies.get(test_admin_security.COOKIE))
            self.assertEqual(other.get(API+"/requests/"+jid).json()["state"],"cancelled")
