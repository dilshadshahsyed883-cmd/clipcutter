import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from pydantic import ValidationError

from app.modules.studio.contracts import JobRequest, youtube_link
from app.modules.studio.intake import stage
from app.modules.studio.store import Store
from app.modules.studio import youtube

URL="https://www.youtube.com/watch?v=NMeVJDrpQO8"

class YoutubeTests(unittest.TestCase):
    def test_urls(self):
        self.assertEqual(youtube_link(URL+"&list=abc"),URL)
        self.assertEqual(youtube_link("https://youtu.be/NMeVJDrpQO8"),URL)
        for bad in ("https://youtube.com.evil.test/watch?v=NMeVJDrpQO8",
                    "http://youtube.com/watch?v=NMeVJDrpQO8","https://www.youtube.com/playlist?list=abc",
                    URL+"&v=NMeVJDrpQO8","https://www.youtube.com@evil.test/watch?v=NMeVJDrpQO8"):
            with self.subTest(bad=bad),self.assertRaises(ValueError):youtube_link(bad)

    def test_contract(self):
        p={"request_id":"a"*32,"input":{"source":URL,"source_kind":"youtube"},
           "settings":{"kind":"extractor","mode":"manual","ranges":[{"start_ms":0,"end_ms":1000}]}}
        with self.assertRaises(ValidationError):JobRequest.model_validate(p)
        p["settings"]["include_audio"]=False
        self.assertEqual(JobRequest.model_validate(p).input.source,URL)

    def test_command(self):
        args=youtube.command(URL,Path("/private"),1000)
        self.assertIn("--no-playlist",args)
        self.assertIn("bv[height<=1080][ext=mp4]",args)
        self.assertEqual(args[-2:],["--",URL])
        self.assertNotIn("--cookies-from-browser",args)

    def test_stage_and_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Store("owner",Path(tmp).resolve())
            def job(key):
                return s.create(JobRequest.model_validate({"request_id":key*32,
                    "input":{"source":URL,"source_kind":"youtube"},"settings":{"kind":"analyzer"}}))["id"]
            def fake(store,url,target,remaining):
                data=b"\x00\x00\x00\x18ftypmp42"
                target.write_bytes(data)
                return {"name":"source.mp4","size":len(data),"sha256":hashlib.sha256(data).hexdigest(),
                        "md5":hashlib.md5(data,usedforsecurity=False).hexdigest()}
            jid=job("a")
            with patch("app.modules.studio.youtube.download",side_effect=fake):
                stage(s,jid)
            self.assertEqual(s.get(jid)["state"],"ready")
            m=json.loads((s.root/"inputs"/jid/"manifest.json").read_text())
            self.assertEqual(m["files"][0]["youtube_id"],"NMeVJDrpQO8")
            bad=job("b")
            with patch("app.modules.studio.youtube.download",side_effect=RuntimeError("YouTube authentication rejected")):
                stage(s,bad)
            self.assertEqual(s.get(bad)["state"],"failed")
            self.assertTrue(s.get(bad)["message"].startswith("YouTube intake:"))
