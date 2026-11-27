"""Durable explicit scan approval. Browser never submits arbitrary GPU manifests."""
import hashlib
import json
import os
import time
from uuid import uuid4
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .contracts import Range
from .store import safe_dir
from .dispatch import canonical,sha_file,DispatchError,NAME,SHA

class Approval(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    scan_sha256:str=Field(pattern=r"^[a-f0-9]{64}$")
    ranges:list[Range]=Field(min_length=1,max_length=1000)
    @model_validator(mode="after")
    def check(self):
        ordered=sorted(self.ranges,key=lambda x:x.start_ms)
        if any(a.end_ms>b.start_ms for a,b in zip(ordered,ordered[1:])):
            raise ValueError("Overlapping ranges")
        return self

def _attempt(c,jid):
    if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='gpu_attempts'").fetchone():
        raise HTTPException(409,"No scan result available")
    a=c.execute("SELECT * FROM gpu_attempts WHERE job_id=?",(jid,)).fetchone()
    if not a or not a["review_json"]:raise HTTPException(409,"No scan result available")
    return a

def validated_scan(result,source_sha):
    if (not isinstance(result,dict) or result.get("state") not in ("review","no_match") or
        result.get("source_sha256")!=source_sha or type(result.get("duration_ms")) is not int or
        not 0<result["duration_ms"]<=86400000):
        raise DispatchError("Invalid scan result")
    ranges=result.get("ranges")
    if not isinstance(ranges,list) or len(ranges)>1000 or bool(ranges)!=(result["state"]=="review"):
        raise DispatchError("Invalid scan ranges")
    for x in ranges:
        if not isinstance(x,dict) or type(x.get("start_ms")) is not int or type(x.get("end_ms")) is not int or not 0<=x["start_ms"]<x["end_ms"]<=result["duration_ms"]:
            raise DispatchError("Invalid scan range")
    return result

def record_scan(store,jid,row,manifest,result,digest):
    validated_scan(result,manifest["job"]["source_sha256"])
    with store.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        job=store.row(c,jid)
        a=c.execute("SELECT * FROM gpu_attempts WHERE job_id=?",(jid,)).fetchone()
        if a["attempt_id"]!=row["attempt_id"] or job["state"] not in ("ready","processing","review"):
            raise DispatchError("Stale scan receipt")
        if a["result_sha"] and a["result_sha"]!=digest:raise DispatchError("Scan result changed")
        c.execute("UPDATE gpu_attempts SET phase='scan_receipt',result_sha=?,review_json=? WHERE job_id=?",
            (digest,canonical(result).decode(),jid))
        c.execute("UPDATE requests SET state='review',message='Scan saved; awaiting worker acknowledgement',progress=100,updated_at=? WHERE id=?",(int(time.time()),jid))

def confirm_scan(store,jid,attempt,digest):
    with store.connect() as c:
        c.execute("BEGIN IMMEDIATE");store.row(c,jid)
        n=c.execute("UPDATE gpu_attempts SET phase='review_ready' WHERE job_id=? AND attempt_id=? AND phase='scan_receipt' AND result_sha=?",
                    (jid,attempt,digest)).rowcount
        if n!=1:raise DispatchError("Stale scan acknowledgement")
        c.execute("UPDATE requests SET message='Review scan ranges, then approve export',updated_at=? WHERE id=?",(int(time.time()),jid))

def get_review(store,jid):
    with store.connect() as c:
        job=store.row(c,jid);a=_attempt(c,jid)
        if job["state"]!="review":raise HTTPException(409,"Request not awaiting review")
        result=json.loads(a["review_json"])
        return {"scan_sha256":a["result_sha"],"ready_for_approval":a["phase"]=="review_ready",
                "duration_ms":result["duration_ms"],"state":result["state"],"ranges":result["ranges"]}

def source_preview(store,jid):
    """Owner-local source from a verified, review-ready scan."""
    from .intake import verify_format
    with store.connect() as c:
        job=store.row(c,jid);a=_attempt(c,jid)
        if job["kind"]!="extractor" or job["state"]!="review" or a["phase"]!="review_ready":
            raise HTTPException(409,"Verified review source unavailable")
        m=json.loads(a["manifest"]);mapping=json.loads(a["mapping"])
    if m["action"]!="scan":raise HTTPException(409,"Not a reference scan")
    name=mapping.get("source.video","");item=m["files"]["source.video"]
    if not NAME.fullmatch(name):raise HTTPException(409,"Unsafe preview source")
    p=store.root/"inputs"/jid/name
    media={".mp4":"video/mp4",".m4v":"video/mp4",".mov":"video/quicktime",".webm":"video/webm"}
    try:
        if p.resolve()!=p or not p.is_file() or p.stat().st_nlink!=1 or p.stat().st_size!=item["size"]:
            raise HTTPException(409,"Verified source changed or missing")
        if p.suffix.lower() not in media:
            raise HTTPException(415,"Source container may not play in the browser")
        verify_format(p,"video",p.suffix.lower())
    except (OSError,ValueError,RuntimeError):
        raise HTTPException(409,"Verified preview source unavailable") from None
    return p,media[p.suffix.lower()]

def approve(store,jid,approval):
    with store.admission(),store.connect() as c:
        c.execute("BEGIN IMMEDIATE");job=store.row(c,jid);a=_attempt(c,jid)
        ranges=[x.model_dump() for x in sorted(approval.ranges,key=lambda x:x.start_ms)]
        c.execute("""CREATE TABLE IF NOT EXISTS gpu_scan_history(
            job_id TEXT PRIMARY KEY REFERENCES requests(id),attempt_id TEXT NOT NULL,
            result_sha TEXT NOT NULL,review_json TEXT NOT NULL,approval_json TEXT NOT NULL)""")
        prior=c.execute("SELECT * FROM gpu_scan_history WHERE job_id=?",(jid,)).fetchone()
        if prior:
            if prior["result_sha"]==approval.scan_sha256 and json.loads(prior["approval_json"])==ranges:
                return store.public(job)
            raise HTTPException(409,"Review already approved with different ranges")
        if job["state"]!="review" or a["phase"]!="review_ready" or a["result_sha"]!=approval.scan_sha256:
            raise HTTPException(409,"Scan acknowledgement or review version mismatch")
        m=json.loads(a["manifest"]);mapping=json.loads(a["mapping"]);result=json.loads(a["review_json"])
        if m["action"]!="scan":raise HTTPException(409,"Not a reference scan")
        if any(x["end_ms"]>result["duration_ms"] for x in ranges):raise HTTPException(422,"Range exceeds source duration")
        settings=m["job"]["request"]["settings"]
        options={k:settings[k] for k in ("threshold","scan_quality","stitched","include_audio","quality","max_short_side","framing","minimum_ms","maximum_ms")}
        options["mode"]=settings["cut_mode"]
        payload={"options":options,"source_sha256":m["job"]["source_sha256"],
                 "references_sha256":m["job"]["references_sha256"],"ranges":ranges}
        root=safe_dir(store.root/"inputs"/jid)
        # Reverify the original inputs before authorizing a fresh export attempt.
        for name,item in m["files"].items():
            filename=mapping[name]
            if not NAME.fullmatch(filename):raise HTTPException(409,"Unsafe staged input")
            p=root/filename
            if p.resolve()!=p or not p.is_file() or p.stat().st_size!=item["size"] or sha_file(p)!=item["sha256"]:
                raise HTTPException(409,"Verified scan input changed")
        raw=canonical(payload);target=root/"approved-review.json"
        # A crash before transaction commit leaves an orphan file; overwrite only
        # while the original scan still awaits approval, under the admission lock.
        tmp=root/("approval-"+uuid4().hex+".tmp")
        with tmp.open("xb") as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(tmp,target)
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
        m["action"]="export";m["files"]["approved-review.json"]={"size":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
        mapping["approved-review.json"]="approved-review.json"
        c.execute("INSERT INTO gpu_scan_history VALUES (?,?,?,?,?)",(jid,a["attempt_id"],a["result_sha"],a["review_json"],canonical(ranges).decode()))
        c.execute("UPDATE gpu_attempts SET attempt_id=?,manifest=?,mapping=?,phase='new',result_sha=NULL WHERE job_id=?",
            (uuid4().hex,canonical(m).decode(),canonical(mapping).decode(),jid))
        c.execute("UPDATE requests SET state='ready',progress=100,message='Reviewed ranges approved; export queued',updated_at=? WHERE id=?",
            (int(time.time()),jid))
        return store.public(store.row(c,jid))
