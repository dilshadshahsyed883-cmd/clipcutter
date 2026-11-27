"""Queue exact cuts from a completed anonymous analysis; reuse verified local source."""
import hashlib
import json
import math
import os
import re
import shutil
import time
from uuid import uuid4
from typing import Literal
from fastapi import HTTPException
from pydantic import Field, ValidationError
from .contracts import Strict,JobRequest
from .store import safe_dir
from .batch import copy_verified,syncdir
from .dispatch import sha_file,NAME,SHA
from .intake import LIMIT,verify_format

class PersonExtraction(Strict):
    request_id:str=Field(pattern=r"^[a-f0-9]{32}$")
    gpu_clip_extraction:bool=True
    stitched:bool=False
    include_audio:bool=True
    quality:int=Field(default=100,ge=50,le=100)
    max_short_side:Literal[0,720,1080,1440]=0
    output_folder:str|None=Field(default=None,max_length=2048)

def ready_parent(store,c,jid):
    row=store.row(c,jid)
    attempt=c.execute("SELECT phase FROM gpu_attempts WHERE job_id=?",(jid,)).fetchone() if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='gpu_attempts'").fetchone() else None
    if row["kind"]!="analyzer" or row["state"]!="completed" or not attempt or attempt["phase"]!="acknowledged":
        raise HTTPException(409,"Wait for verified analyzer delivery and GPU acknowledgement")
    return store.public(row)

def queue_person(store,jid,person_id,data):
    if not re.fullmatch(r"[a-f0-9]{12}",person_id):raise HTTPException(404,"Person not found")
    with store.connect() as c:
        parent=ready_parent(store,c,jid)
    path,meta=store.output_path(jid,"analysis.json")
    if meta["size"]>8*1024*1024 or sha_file(path)!=meta["sha256"]:raise HTTPException(409,"Analysis summary changed")
    try:
        summary=json.loads(path.read_bytes())
        if not isinstance(summary.get("people"),list):raise ValueError()
        people=[p for p in summary["people"] if p.get("id")==person_id]
        if len(people)!=1:raise HTTPException(404,"Person not found")
        p=people[0]
        # Never accept unfiltered legacy analysis or browser-supplied timestamps.
        if p.get("filtered") is not False or summary.get("timeline_precision")!="sample-cell estimate" or not p.get("segments"):
            raise HTTPException(409,"No accepted dominant-face timeline; run updated analysis")
        duration=summary["duration"]
        if type(duration) not in (int,float) or not math.isfinite(duration) or not 0<duration<=7200.1:raise ValueError()
        ranges=[]
        for a,b in p["segments"]:
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in (a,b)) or not 0<=a<b<=duration+.001:raise ValueError()
            # Conservative integer-ms rounding keeps the cut inside accepted samples.
            start=math.ceil(a*1000-1e-7);end=math.floor(b*1000+1e-7)
            if end>start:ranges.append({"start_ms":start,"end_ms":end})
        if not ranges:raise ValueError()
        label=p["name"]
        if not isinstance(label,str) or not re.fullmatch(r"Person [1-9][0-9]{0,2}",label):raise ValueError()
        inp={**parent["input"],"output_folder":data.output_folder}
        if inp["source_kind"] not in ("video","youtube"):raise ValueError()
        opts=data.model_dump(exclude={"request_id","output_folder"})
        if inp["source_kind"]=="youtube":opts["include_audio"]=False
        req=JobRequest.model_validate({"request_id":data.request_id,"input":inp,
            "settings":{"kind":"extractor","mode":"manual","ranges":ranges,"cut_mode":"accurate","framing":"whole",**opts}})
        root=store.root/"inputs"/jid
        manifest=json.loads((root/"manifest.json").read_bytes())
        source=[x for x in manifest["files"] if x["role"]=="source"]
        if manifest.get("version")!=1 or len(source)!=1:raise ValueError()
        item=source[0];name=item["file"]
        if not NAME.fullmatch(name) or type(item["size"]) is not int or not 0<item["size"]<=LIMIT or not SHA.fullmatch(item["sha256"]) or summary.get("source_sha256")!=item["sha256"]:raise ValueError()
        source_path=root/name
        if source_path.resolve()!=source_path or not source_path.is_file() or source_path.stat().st_size!=item["size"]:raise ValueError()
    except HTTPException:raise
    except (OSError,ValueError,TypeError,KeyError,AttributeError,ValidationError):
        raise HTTPException(409,"Invalid verified source or accepted timeline; extraction not queued") from None
    payload=json.dumps(req.model_dump(exclude={"request_id"}),sort_keys=True,separators=(",",":"))
    # Anonymous identity snapshot for unique Person_N naming, not a library enrollment.
    identity=hashlib.sha256(("analysis-person:"+jid+":"+person_id).encode()).hexdigest()[:32]
    slug=label.replace(" ","_")+"_"+jid[:8]
    def existing(c):
        prior=c.execute("SELECT * FROM requests WHERE request_id=? AND owner=?",(data.request_id,store.owner)).fetchone()
        if not prior:return None
        snap=c.execute("SELECT identity_id FROM request_identities WHERE job_id=?",(prior["id"],)).fetchone()
        if prior["payload"]!=payload or not snap or snap[0]!=identity:
            raise HTTPException(409,"Request ID already used with different settings")
        return store.public(prior)
    with store.connect() as c:
        old=existing(c)
        if old:return old
    inputs=safe_dir(store.root/"inputs")
    child=uuid4().hex
    work=safe_dir(inputs/(child+".person"))
    dest=inputs/child
    try:
        copy_verified(source_path,work/name,item["size"],item["sha256"])
        verify_format(work/name,"video",(work/name).suffix.lower())
        with (work/"manifest.json").open("x") as f:
            json.dump({"version":1,"files":[{"role":"source","file":name,"size":item["size"],"sha256":item["sha256"]}]},f)
            f.flush();os.fsync(f.fileno())
        syncdir(work)
        with store.admission(),store.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            ready_parent(store,c,jid)
            old=existing(c)
            if old:return old
            count=c.execute("SELECT count(*) FROM requests WHERE owner=? AND state IN ('ready','awaiting_input','staging')",(store.owner,)).fetchone()[0]
            if count>=500:raise HTTPException(409,"Pending request limit reached")
            work.rename(dest);syncdir(inputs)
            now=int(time.time())
            c.execute("INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?,?)",(child,req.request_id,store.owner,"extractor",payload,"ready",now,now,100,
                "Verified local source · "+label+" · accepted analyzer ranges"))
            c.execute("INSERT INTO request_identities VALUES(?,?,?,?)",(child,identity,label+" ("+jid[:8]+")",slug))
            return store.public(store.row(c,child))
    except HTTPException:raise
    except (OSError,RuntimeError,ValueError) as exc:
        raise HTTPException(409,"Could not stage verified local source: "+str(exc)[:200]) from None
    finally:
        if work.exists():shutil.rmtree(work)
        if dest.exists():
            with store.connect() as c:
                if not c.execute("SELECT 1 FROM requests WHERE id=?",(child,)).fetchone():shutil.rmtree(dest)
