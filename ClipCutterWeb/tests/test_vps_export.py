"""CPU-only export unit and optional real FFmpeg smoke tests."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from app.modules.studio.contracts import Extractor
from app.modules.studio.vps_export import partitions,encode,local_job
from unittest.mock import patch

class VpsExportTests(unittest.TestCase):
    def test_default_and_framing_guard(self):
        self.assertTrue(Extractor(mode="manual",ranges=[{"start_ms":0,"end_ms":1000}]).gpu_clip_extraction)
        with self.assertRaises(ValueError):
            Extractor(mode="manual",ranges=[{"start_ms":0,"end_ms":1000}],gpu_clip_extraction=False,framing="dynamic")
        self.assertTrue(local_job({"settings":{"kind":"extractor","mode":"manual","gpu_clip_extraction":False}}))
        self.assertFalse(local_job({"settings":{"kind":"extractor","mode":"reference","gpu_clip_extraction":False}}))

    def test_limits(self):
        self.assertEqual(partitions(1000,8000,2500,4000),[(1000,4500),(4500,8000)])
        self.assertEqual(partitions(0,2000,2500,4000),[])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),"FFmpeg not installed")
    def test_real_cpu_encode(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);source=root/"source.mp4";out=root/"out";out.mkdir()
            subprocess.run(["ffmpeg","-nostdin","-v","error","-f","lavfi","-i","color=c=blue:s=128x96:r=25:d=3",
                "-c:v","libx264","-threads","1","-pix_fmt","yuv420p",str(source)],check=True,timeout=30)
            s=Extractor(mode="manual",ranges=[{"start_ms":400,"end_ms":2000}],gpu_clip_extraction=False,
                        include_audio=False).model_dump()
            with patch("app.modules.studio.vps_export.RESERVE",0):
                items=encode(source,s,s["ranges"],out,lambda:False,lambda *_:None)
            self.assertEqual(len(items),1)
            self.assertTrue((out/items[0]["name"]).is_file())
            self.assertAlmostEqual(items[0]["duration_ms"],1600,delta=100)
