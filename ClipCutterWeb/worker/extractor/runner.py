"""Headless extractor worker, source-only. Queue and remote dispatch are later steps."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
from threading import Event

from .contracts import ScanManifest, ReviewManifest

MAX_JSON = 2 * 1024 * 1024
MAX_REFERENCE = 16 * 1024 * 1024
MAX_VIDEO = 20 * 1024**3

def local_file(root: Path, name: str, limit: int) -> Path:
    path = root / name
    if path.is_symlink() or not path.is_file() or path.resolve().parent != root:
        raise ValueError(f"Missing or unsafe staged file: {name}")
    if not 0 < path.stat().st_size <= limit:
        raise ValueError(f"Staged file size invalid: {name}")
    return path

def verify(path: Path, expected: str, cancel: Event):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if cancel.is_set():
                raise InterruptedError("Cancelled")
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError(f"Staged file digest mismatch: {path.name}")

def references(root, hashes, cancel):
    result=[]
    for i, digest in enumerate(hashes, 1):
        p=local_file(root, f"reference-{i:02d}.img", MAX_REFERENCE)
        verify(p,digest,cancel)
        result.append((p.name,p.read_bytes()))
    return result

def engine():
    # No implicit downloader or default unlicensed model pack.
    if os.environ.get("CLIPCUTTER_MODEL_LICENSE_CONFIRMED") != "1":
        raise RuntimeError("Operator must provision compatible licensed detector and recognizer weights")
    from .vendor.face_engine import InsightFaceEngine
    from .vendor.downloads import find_face_models
    model_dir=find_face_models()
    if model_dir is None:
        raise RuntimeError("Worker model directory is missing required files")
    instance=InsightFaceEngine(model_dir, use_gpu=os.environ.get("CLIPCUTTER_USE_GPU")=="1")
    status=instance.status()
    if not status.available:
        raise RuntimeError(status.detail)
    return instance

def event(stage, done, total, message):
    print(json.dumps({"stage":stage,"done":int(done),"total":int(total),"message":str(message)}),flush=True)

def publish(root, name, payload):
    # No overwrite of a prior successful result.
    target=root/name
    temp=root/(name+".tmp")
    with temp.open("x",encoding="utf-8") as f:
        json.dump(payload,f,ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.link(temp,target)
    finally:
        temp.unlink()

def run(root: Path, action: str, cancel: Event):
    from .vendor.video_probe import probe_video
    from .vendor.batch import analyse_video_for_characters, BatchCharacterTarget, track_person_in_clips, validate_export
    from .vendor.models import ClipRange
    from .vendor.export import export_ranges, OutputShape, snap_to_keyframes
    root=root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Staged job directory required")
    manifest=local_file(root, "scan.json" if action=="scan" else "review.json", MAX_JSON)
    req=(ScanManifest if action=="scan" else ReviewManifest).model_validate_json(manifest.read_bytes())
    source=local_file(root,"source.video",MAX_VIDEO)
    verify(source,req.source_sha256,cancel)
    info=probe_video(source,include_keyframes=False)
    if info.duration_ms<=0 or info.width<=0 or info.height<=0:
        raise ValueError("Source is not a valid video")
    opts=req.options
    refs=references(root,req.references_sha256,cancel)
    if cancel.is_set(): raise InterruptedError("Cancelled")
    if action=="scan":
        e=engine()
        result=analyse_video_for_characters(source,e,[BatchCharacterTarget("target","Target",refs,opts.threshold)],
            duration_ms=info.duration_ms,quality=opts.scan_quality,cancelled=cancel.is_set,
            progress=lambda d,t,m:event("scan",d,t,m),
            refine_progress=lambda d,t:event("refine",d,t,"Refining appearances"))
        if cancel.is_set(): raise InterruptedError("Cancelled")
        ranges=[{"start_ms":r.start_ms,"end_ms":r.end_ms,"origin":r.origin} for r in result[0].ranges
            if 0<=r.start_ms<r.end_ms<=info.duration_ms]
        publish(root,"scan-result.json",{"source_sha256":req.source_sha256,"duration_ms":info.duration_ms,
             "state":"review" if ranges else "no_match","ranges":ranges})
        return
    # Explicit reviewed A/B ranges; scanning is optional for manual cutting.
    ranges=[ClipRange(r.start_ms,r.end_ms) for r in sorted(req.ranges,key=lambda r:r.start_ms)]
    if any(r.end_ms>info.duration_ms for r in ranges):
        raise ValueError("Reviewed clip exceeds source duration")
    if req.framing_requested:
        e=engine()
        matrix=e.reference_matrix(refs)
        track_person_in_clips(source,e,"target",matrix,opts.threshold,ranges,cancelled=cancel.is_set,
            progress=lambda d,t:event("tracking",d,t,"Tracking target"))
    if cancel.is_set(): raise InterruptedError("Cancelled")
    output=root/"outputs"
    scratch=root/"scratch"
    output.mkdir(mode=0o700,exist_ok=False)
    scratch.mkdir(mode=0o700,exist_ok=False)
    os.environ["CLIPCUTTER_WORKER_SCRATCH"]=str(scratch)
    shape=OutputShape(quality=opts.quality,max_short_side=opts.max_short_side,framing=opts.framing,
                      frame_size=(info.width,info.height))
    if opts.mode=="copy" and not shape.needs_reencode():
        ranges=snap_to_keyframes(source,ranges)
    limits=None if opts.minimum_ms is None else (opts.minimum_ms/1000,opts.maximum_ms/1000)
    paths=export_ranges(source,ranges,output,opts.mode,opts.stitched,include_audio=opts.include_audio,
        progress=lambda d,t,m:event("export",d,t,m),cancel_event=cancel,source_fps=info.fps,
        source_video_bitrate_kbps=info.video_bitrate_kbps,shape=shape,clip_limits=limits,
        video_encoder="cpu",output_name="clip")
    artifacts=[]
    for path in paths:
        if cancel.is_set(): raise InterruptedError("Cancelled")
        validate_export(path)
        actual=probe_video(path,include_keyframes=False).duration_ms
        if limits and not opts.minimum_ms<=actual<=opts.maximum_ms:
            raise RuntimeError("Verified output does not meet strict duration limits")
        digest=hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda:f.read(1024*1024),b""):
                if cancel.is_set(): raise InterruptedError("Cancelled")
                digest.update(chunk)
        artifacts.append({"name":path.name,"size":path.stat().st_size,"duration_ms":actual,"sha256":digest.hexdigest()})
    if not artifacts: raise RuntimeError("No verified outputs")
    if cancel.is_set(): raise InterruptedError("Cancelled")
    publish(root,"export-result.json",{"state":"completed","source_sha256":req.source_sha256,"artifacts":artifacts})

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["scan","export"])
    parser.add_argument("job_dir",type=Path)
    args=parser.parse_args()
    cancel=Event()
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,lambda *_:cancel.set())
    try:
        run(args.job_dir,args.action,cancel)
    except Exception as exc:
        event("cancelled" if cancel.is_set() else "failed",0,0,str(exc))
        return 130 if cancel.is_set() else 1
    return 0

if __name__=="__main__":
    raise SystemExit(main())
