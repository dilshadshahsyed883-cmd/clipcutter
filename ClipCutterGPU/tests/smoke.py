"""Exact-image contract and synthetic CPU export gate. No GPU claim."""
import hashlib
import csv
from unittest.mock import patch
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
    from worker.model_pins import verify_models
    verify_models(Path("/models"))
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
    # Run both actual packaged ONNX models on CPU, then the full analyzer
    # transport artifact path with deterministic synthetic detections.
    from worker.analyzer.vendor.engine import Engine
    import numpy as np
    import cv2
    engine=Engine(Path("/models"),False,640)
    assert engine.device=="CPUExecutionProvider"
    for session,size in ((engine.det,640),(engine.rec,112)):
        output=session.run(None,{session.get_inputs()[0].name:np.zeros((1,3,size,size),np.float32)})
        assert output and all(np.isfinite(x).all() for x in output)
    # Real detector inference and complete no-face analyzer artifact generation.
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);video=root/"source.video"
        subprocess.run(["ffmpeg","-nostdin","-v","error","-f","lavfi","-i","color=c=black:s=320x240:r=25:d=4",
            "-c:v","libx264","-threads","1","-pix_fmt","yuv420p","-f","mp4",str(video)],check=True,timeout=60)
        digest=hashlib.sha256(video.read_bytes()).hexdigest()
        req={"version":1,"job_id":"c"*32,"source_sha256":digest,"request":{"request_id":"d"*32,
            "input":{"source":source_link,"source_kind":"video"},"settings":{"kind":"analyzer","sample_interval_ms":1000}}}
        (root/"job.json").write_text(json.dumps(req))
        with patch("worker.analyzer.vendor.engine.Engine",return_value=engine):
            run(root,"analyze",Event())
        summary=json.loads((root/"outputs"/"analysis.json").read_text())
        assert summary["people"]==[] and summary["excluded_intervals"]["no_face"]
        assert {x["name"] for x in json.loads((root/"analysis-result.json").read_text())["artifacts"]}=={"analysis.json","timeline.csv"}
    del engine
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);video=root/"source.video"
        subprocess.run(["ffmpeg","-nostdin","-v","error","-f","lavfi","-i","color=c=blue:s=320x240:r=25:d=4",
            "-c:v","libx264","-threads","1","-pix_fmt","yuv420p","-f","mp4",str(video)],check=True,timeout=60)
        digest=hashlib.sha256(video.read_bytes()).hexdigest()
        req["source_sha256"]=digest
        (root/"job.json").write_text(json.dumps(req))
        class Synthetic:
            gpu=False;device="CPUExecutionProvider";warning=""
            def __init__(self):self.i=0
            def get(self,img):
                self.i+=1
                a=(np.array([1.,0.],np.float32),img[:100,:100].copy(),90.,(0,0,100,100),.99)
                b=(np.array([0.,1.],np.float32),img[:100,150:250].copy(),90.,(150,0,250,100),.99)
                small=(b[0],img[:40,150:190].copy(),30.,(150,0,190,40),.99)
                return [a] if self.i==1 else [a,b] if self.i==2 else [a,small] if self.i==3 else []
        with patch("worker.analyzer.vendor.engine.Engine",return_value=Synthetic()):
            run(root,"analyze",Event())
        result=json.loads((root/"analysis-result.json").read_text())
        assert result["state"]=="completed" and result["source_sha256"]==digest
        outputs=root/"outputs";summary=json.loads((outputs/"analysis.json").read_text())
        people=summary["people"];assert len(people)==2
        assert not people[0]["filtered"] and people[1]["filtered"]
        assert len(people[0]["segments"])==2 and summary["excluded_intervals"]["similar_size"] and summary["excluded_intervals"]["no_face"]
        assert people[0]["thumbnail"]=="person_001.jpg"
        assert "embedding" not in json.dumps(summary) and "observations" not in json.dumps(summary)
        with (outputs/"timeline.csv").open() as f:rows=list(csv.DictReader(f))
        assert len(rows)==2 and all(r["person"]=="Person 1" for r in rows)
        assert {a["name"] for a in result["artifacts"]}=={"analysis.json","timeline.csv","person_001.jpg"}
        for a in result["artifacts"]:
            data=(outputs/a["name"]).read_bytes()
            assert len(data)==a["size"] and hashlib.sha256(data).hexdigest()==a["sha256"]
        thumb=cv2.imread(str(outputs/"person_001.jpg"))
        assert thumb is not None and max(thumb.shape[:2])<=256
        assert hashlib.sha256(video.read_bytes()).hexdigest()==digest
    return {"source_sha":expected,"contract_version":2,"synthetic_cpu_export":"passed",
        "analyzer_cpu_model_inference":"passed","analyzer_synthetic_timeline_thumbnail":"passed",
        "packaged_models":"passed","request_contracts":"passed","source_hashes":"passed","physical_gpu_verified":False,
        "runtime_versions":{x:importlib.metadata.version(x) for x in ("av","numpy","opencv-python-headless","onnxruntime-gpu","pydantic")}}

if __name__=="__main__":
    # Runner emits progress on stdout; retain only JSON report there.
    import contextlib,sys
    with contextlib.redirect_stdout(sys.stderr): report=main()
    print(json.dumps(report,indent=2))
