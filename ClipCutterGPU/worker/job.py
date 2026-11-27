"""Translate a verified staged single-video request into headless worker operations.
No Drive fetching, archive unpacking or public upload API here.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import tempfile
from threading import Event
import time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .web_contract import JobRequest, Extractor, Analyzer
from .extractor.runner import local_file, verify, references, publish, event, MAX_VIDEO, MAX_JSON
from .runtime import require_models

class Staged(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    version:Literal[1]=1
    job_id:str=Field(pattern=r"^[a-f0-9]{32}$")
    request:JobRequest
    source_sha256:str=Field(pattern=r"^[a-f0-9]{64}$")
    references_sha256:list[str]=Field(default_factory=list,max_length=12)
    @model_validator(mode="after")
    def check(self):
        if any(not re.fullmatch(r"[a-f0-9]{64}",x) for x in self.references_sha256):
            raise ValueError("Invalid staged reference digest")
        if bool(self.request.settings.reference_link or self.request.settings.reference_uploads)!=bool(self.references_sha256):
            raise ValueError("Reference staging differs from request")
        if self.request.settings.reference_uploads and self.request.settings.reference_uploads!=self.references_sha256:
            raise ValueError("Uploaded reference digest mismatch")
        if isinstance(self.request.settings,Analyzer) and self.references_sha256:
            raise ValueError("Analyzer reference-profile input awaits explicit profile integration")
        return self

def sha(path,cancel):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            if cancel.is_set():raise InterruptedError("Cancelled")
            h.update(chunk)
    return h.hexdigest()

def run(root,action,cancel):
    root=Path(root).resolve(strict=True)
    job=Staged.model_validate_json(local_file(root,"job.json",MAX_JSON).read_bytes())
    source=local_file(root,"source.video",MAX_VIDEO)
    verify(source,job.source_sha256,cancel)
    settings=job.request.settings
    if isinstance(settings,Extractor):
        from .extractor.runner import run as extract
        from .extractor.contracts import Options
        opts=Options(**{**settings.model_dump(include={"threshold","scan_quality","stitched","include_audio","quality","max_short_side","framing","minimum_ms","maximum_ms"}),"mode":settings.cut_mode}).model_dump()
        common={"options":opts,"source_sha256":job.source_sha256,"references_sha256":job.references_sha256}
        if action=="scan" and settings.mode=="reference":
            publish(root,"scan.json",common)
            extract(root,"scan",cancel)
            return
        if action=="export" and settings.mode=="manual":
            ranges=[r.model_dump() for r in settings.ranges]
        elif action=="export" and settings.mode=="reference":
            # Only trusted dispatcher provides explicit reviewed ranges in a fresh staged attempt.
            from .extractor.contracts import ReviewManifest
            review=ReviewManifest.model_validate_json(local_file(root,"approved-review.json",MAX_JSON).read_bytes())
            if review.model_dump(exclude={"ranges"})!=common:
                raise ValueError("Reviewed request settings or source changed")
            ranges=[r.model_dump() for r in review.ranges]
        else: raise ValueError("Action incompatible with extractor request")
        publish(root,"review.json",{**common,"ranges":ranges})
        extract(root,"export",cancel)
    elif isinstance(settings,Analyzer) and action=="analyze":
        from .extractor.vendor.video_probe import probe_video
        from .analyzer.vendor.analyzer import analyze
        from .analyzer.vendor.engine import Engine
        info=probe_video(source,include_keyframes=False)
        if not 0<info.duration_ms<=7200000: raise ValueError("Analyzer candidate supports source duration up to 2 hours")
        filters={"background":settings.ignore_background_faces,"static":settings.ignore_static_faces,
                 "regions":[[r.x,r.y,r.x+r.w,r.y+r.h] for r in settings.ignore_regions],
                 "dominant_face_ratio":settings.dominant_face_ratio}
        model_dir=require_models(cancel)
        engine=Engine(model_dir,os.environ.get("CLIPCUTTER_USE_GPU","1")=="1",640)
        last=[0.]
        def progress(t,total,device,groups,warning,frames,observed):
            if time.monotonic()-last[0]>=1:
                last[0]=time.monotonic();event("analyze",t*1000,total*1000,f"{device}; {groups} candidate groups")
        output=root/"outputs";output.mkdir(mode=0o700,exist_ok=False)
        thumbnails=[]
        with tempfile.TemporaryDirectory(prefix="analysis-",dir=root) as tmp:
            data=analyze(source,Path(tmp)/"project",model_dir,engine.gpu,settings.sample_interval_ms/1000,
                settings.similarity_threshold,640,progress,cancel.is_set,filters=filters,engine=engine,persist=False,store_crops=False,representatives=True)
            # Do not export raw embeddings, images, face coordinates or host paths.
            people=[{k:g[k] for k in ("id","name","identity_status","segments","raw_segments","filtered","filter_reasons")} for g in data["people"]]
            summary={k:data[k] for k in ("version","duration","sample_interval","threshold","decoded_frames","analyzed_frames","device","elapsed_seconds")}
            summary.update(people=people,source_sha256=job.source_sha256,
                dominant_face_ratio=settings.dominant_face_ratio,excluded_intervals=data["excluded_intervals"],
                timeline_precision="sample-cell estimate")
            for index,(person,g) in enumerate(zip(people,data["people"]),1):
                if g["filtered"]:continue
                if cancel.is_set():raise InterruptedError("Cancelled")
                thumbnail=g.get("representative")
                if not thumbnail:raise RuntimeError("Eligible person has no representative thumbnail")
                src=Path(tmp)/"project"/thumbnail
                payload=src.read_bytes()
                if not 0<len(payload)<=512*1024 or not payload.startswith(b"\xff\xd8\xff"):raise RuntimeError("Invalid thumbnail")
                name=f"person_{index:03d}.jpg";(output/name).write_bytes(payload)
                person["thumbnail"]=name;thumbnails.append((name,"image/jpeg"))
        if cancel.is_set():raise InterruptedError("Cancelled")
        publish(output,"analysis.json",summary)
        with (output/"timeline.csv").open("x",encoding="utf-8",newline="") as f:
            w=csv.writer(f);w.writerow(["person_id","person","start_seconds","end_seconds"])
            for g in people:
                for a,b in g["segments"]:w.writerow([g["id"],g["name"],a,b])
        artifacts=[]
        for name,media in [("analysis.json","application/json"),("timeline.csv","text/csv"),*thumbnails]:
            p=output/name;artifacts.append({"name":name,"size":p.stat().st_size,"sha256":sha(p,cancel),"media_type":media})
        if cancel.is_set():raise InterruptedError("Cancelled")
        publish(root,"analysis-result.json",{"state":"completed","job_id":job.job_id,"source_sha256":job.source_sha256,"artifacts":artifacts})
    else:raise ValueError("Action incompatible with request")

def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=["scan","export","analyze"]);p.add_argument("directory",type=Path);a=p.parse_args()
    cancel=Event()
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:cancel.set())
    try:run(a.directory,a.action,cancel)
    except Exception as exc:
        event("cancelled" if cancel.is_set() else "failed",0,0,str(exc));return 130 if cancel.is_set() else 1
    return 0

if __name__=="__main__":raise SystemExit(main())
