"""Exact-image contract and synthetic CPU export gate. No GPU claim."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import tempfile
from threading import Event
from worker.job import Staged, run
from worker.extractor.vendor.limits import bounded_parts
from worker.extractor.vendor.video_probe import probe_video

def main():
    expected=os.environ["EXPECTED_SOURCE_SHA"]
    assert os.environ["CLIPCUTTER_SOURCE_SHA"]==expected
    installed=Path("/opt/clipcutter")
    source=Path("/src")
    for folder in ("worker","tests"):
        actual={p.relative_to(installed) for p in (installed/folder).rglob("*.py")}
        wanted={p.relative_to(source) for p in (source/folder).rglob("*.py")}
        assert actual==wanted, (actual-wanted,wanted-actual)
        for rel in actual:
            assert hashlib.sha256((installed/rel).read_bytes()).digest()==hashlib.sha256((source/rel).read_bytes()).digest(),str(rel)
    for ms in range(0,15001,37):
        parts=bounded_parts(ms/1000,2.5,4)
        assert all(2500<=round((b-a)*1000)<=4000 for a,b in parts)
    source_link="https://drive.google.com/file/d/abcdef123456789/view"
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        video=root/"source.video"
        subprocess.run(["ffmpeg","-nostdin","-v","error","-f","lavfi","-i","testsrc2=size=160x96:rate=25",
            "-t","6","-c:v","libx264","-pix_fmt","yuv420p","-f","mp4",str(video)],check=True,timeout=60)
        digest=hashlib.sha256(video.read_bytes()).hexdigest()
        req={"version":1,"job_id":"a"*32,"source_sha256":digest,"request":{"request_id":"b"*32,
            "input":{"source":source_link,"source_kind":"video"},"settings":{"kind":"extractor","mode":"manual",
            "ranges":[{"start_ms":0,"end_ms":2000},{"start_ms":3000,"end_ms":5000}],"include_audio":False}}}
        Staged.model_validate(req)
        analyzer={**req,"request":{**req["request"],"settings":{"kind":"analyzer","sample_interval_ms":1000}}}
        Staged.model_validate(analyzer)
        (root/"job.json").write_text(json.dumps(req))
        os.environ["CLIPCUTTER_VIDEO_ENCODER"]="cpu"
        os.environ["CLIPCUTTER_USE_GPU"]="0"
        run(root,"export",Event())
        result=json.loads((root/"export-result.json").read_text())
        assert result["state"]=="completed" and len(result["artifacts"])==2
        for item in result["artifacts"]:
            p=root/"outputs"/item["name"]
            assert p.stat().st_size==item["size"]
            assert hashlib.sha256(p.read_bytes()).hexdigest()==item["sha256"]
            assert abs(probe_video(p,include_keyframes=False).duration_ms-2000)<=150
        assert hashlib.sha256(video.read_bytes()).hexdigest()==digest
    return {"source_sha":expected,"contract_version":1,"synthetic_cpu_export":"passed",
        "request_contracts":"passed","source_hashes":"passed","physical_gpu_verified":False,
        "runtime_versions":{x:importlib.metadata.version(x) for x in ("av","numpy","opencv-python-headless","onnxruntime-gpu","pydantic")}}

if __name__=="__main__":
    # Runner emits progress on stdout; retain only JSON report there.
    import contextlib,sys
    with contextlib.redirect_stdout(sys.stderr): report=main()
    print(json.dumps(report,indent=2))
