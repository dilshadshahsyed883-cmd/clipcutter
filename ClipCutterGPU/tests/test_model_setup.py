import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from worker.model_setup import provision,MODELS

class Response(io.BytesIO):
    def __init__(self,data):
        super().__init__(data);self.headers={"Content-Length":str(len(data))}

class ModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.data={name:("fixture "+name).encode() for name,_ in MODELS}
        self.env={"CLIPCUTTER_MODEL_DIR":str(self.root),"CLIPCUTTER_MODEL_LICENSE_CONFIRMED":"1",
                  "CLIPCUTTER_MODEL_BASE_URL":"https://models.example.invalid/approved"}
        self.env.update({key:hashlib.sha256(self.data[name]).hexdigest() for name,key in MODELS})
        p=patch.dict(os.environ,self.env,clear=True);p.start();self.addCleanup(p.stop)
    def test_local_pins(self):
        for name,content in self.data.items():(self.root/name).write_bytes(content)
        with patch("urllib.request.build_opener") as op:
            self.assertEqual(provision(),self.root);op.assert_not_called()
    def test_download_and_reuse(self):
        with patch("urllib.request.build_opener") as op:
            op.return_value.open.side_effect=lambda req,timeout:Response(self.data[req.full_url.rsplit("/",1)[1]])
            self.assertEqual(provision(),self.root)
            self.assertEqual(op.return_value.open.call_count,2)
            self.assertEqual(provision(),self.root)
            self.assertEqual(op.return_value.open.call_count,2)
        for name,content in self.data.items():self.assertEqual((self.root/name).read_bytes(),content)
    def test_bad_digest_no_publish(self):
        with patch("urllib.request.build_opener") as op:
            op.return_value.open.return_value=Response(b"wrong")
            with self.assertRaisesRegex(RuntimeError,"provisioning failed"):provision()
        self.assertEqual(list(self.root.iterdir()),[])
    def test_no_license_no_network(self):
        with patch.dict(os.environ,{"CLIPCUTTER_MODEL_LICENSE_CONFIRMED":"0"}),patch("urllib.request.build_opener") as op:
            with self.assertRaisesRegex(RuntimeError,"license"):provision()
            op.assert_not_called()
    def test_invalid_local_no_overwrite(self):
        name=MODELS[0][0];p=self.root/name;p.write_bytes(b"bad")
        with patch("urllib.request.build_opener") as op:
            with self.assertRaisesRegex(RuntimeError,"Existing model invalid"):provision()
            op.assert_not_called()
        self.assertEqual(p.read_bytes(),b"bad")
    def test_http_rejected(self):
        with patch.dict(os.environ,{"CLIPCUTTER_MODEL_BASE_URL":"http://models.example.invalid"}):
            with self.assertRaisesRegex(RuntimeError,"HTTPS"):provision()

if __name__=="__main__":unittest.main()
