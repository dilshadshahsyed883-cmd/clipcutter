"""Opt-in real CPU FFmpeg integration; no licensed model is needed for manual cutting."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from threading import Event
import unittest

@unittest.skipUnless(os.environ.get("CLIPCUTTER_RUN_MEDIA_TESTS")=="1","Opt-in worker media test")
class MediaSmokeTests(unittest.TestCase):
    def test_reviewed_manual_export(self):
        from worker.extractor.runner import run
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.fail("FFmpeg tools required")
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            source=root/"source.video"
            subprocess.run(["ffmpeg","-nostdin","-v","error","-f","lavfi","-i","testsrc2=size=160x96:rate=25",
                "-t","6","-c:v","libx264","-pix_fmt","yuv420p","-f","mp4",str(source)],check=True,timeout=60)
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            (root/"review.json").write_text(json.dumps({"source_sha256":digest,
                "ranges":[{"start_ms":0,"end_ms":2000},{"start_ms":3000,"end_ms":5000}],
                "options":{"include_audio":False,"mode":"accurate","stitched":False}}))
            run(root,"export",Event())
            result=json.loads((root/"export-result.json").read_text())
            self.assertEqual(result["state"],"completed")
            self.assertEqual(len(result["artifacts"]),2)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),digest)
            for item in result["artifacts"]:
                path=root/"outputs"/item["name"]
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),item["sha256"])
                self.assertLessEqual(abs(item["duration_ms"]-2000),150)
