"""Owner-private, immutable reference sets. No raw embeddings are persisted."""
import hashlib
import json
import os
import re
import time
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,Field,field_validator
from .intake import TYPES,verify_format
from .store import safe_dir

MAX_REF=16*1024**2
MAX_SET=64*1024**2
ID=re.compile(r"[a-f0-9]{32}")

class SaveProfile(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    job_id:str=Field(pattern=r"^[a-f0-9]{32}$")
    label:str=Field(min_length=1,max_length=80)
    @field_validator("label")
    @classmethod
    def clean(cls,v):
        v=v.strip()
        if not v or any(ord(ch)<32 or ord(ch)==127 for ch in v):raise ValueError("Invalid label")
        return v

def init(c):
    c.execute("""CREATE TABLE IF NOT EXISTS analyzer_profiles(
        id TEXT PRIMARY KEY,label TEXT NOT NULL,label_key TEXT NOT NULL UNIQUE,
        source_job TEXT NOT NULL REFERENCES requests(id),created INTEGER NOT NULL,
        fingerprint TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS analyzer_profile_refs(
        profile_id TEXT NOT NULL REFERENCES analyzer_profiles(id) ON DELETE CASCADE,
        ordinal INTEGER NOT NULL,suffix TEXT NOT NULL,sha256 TEXT NOT NULL,content BLOB NOT NULL,
        PRIMARY KEY(profile_id,ordinal))""")

def exists(c,pid):
    init(c)
    return bool(ID.fullmatch(pid) and c.execute("SELECT 1 FROM analyzer_profiles WHERE id=?",(pid,)).fetchone())

def listing(store):
    with store.connect() as c:
        init(c)
        return [dict(r) for r in c.execute("""SELECT p.id,p.label,p.source_job,p.created,p.fingerprint,
            count(r.ordinal) AS reference_count FROM analyzer_profiles p JOIN analyzer_profile_refs r ON p.id=r.profile_id
            GROUP BY p.id ORDER BY p.label_key""")]

def save(store,value):
    with store.admission(),store.connect() as c:
        c.execute("BEGIN IMMEDIATE");init(c);job=store.row(c,value.job_id)
        settings=json.loads(job["payload"])["settings"]
        if job["state"] not in ("ready","processing","completed","batch_expanded") or not settings.get("reference_link"):
            raise HTTPException(409,"Choose a request with verified explicit reference images")
        root=store.root/"inputs"/value.job_id
        try:
            manifest=json.loads((root/"manifest.json").read_text())
            refs=[x for x in manifest["files"] if x["role"]=="reference"]
            if not 1<=len(refs)<=12:raise ValueError()
            if sum(x["size"] for x in refs)>MAX_SET:raise ValueError()
            contents=[];seen=set()
            for x in refs:
                name=x["file"];suffix=Path(name).suffix.lower()
                if not re.fullmatch(r"reference-[0-9]{4}\.[a-z0-9]+",name) or suffix not in TYPES["image"] or not 0<x["size"]<=MAX_REF:raise ValueError()
                p=root/name
                if p.resolve()!=p or not p.is_file() or p.stat().st_size!=x["size"]:raise ValueError()
                verify_format(p,"image",suffix);blob=p.read_bytes();digest=hashlib.sha256(blob).hexdigest()
                if digest!=x["sha256"]:raise ValueError()
                if digest not in seen:contents.append((suffix,digest,blob));seen.add(digest)
        except (OSError,RuntimeError,ValueError,KeyError,TypeError) as exc:
            raise HTTPException(409,"Verified reference files unavailable or exceed profile limits") from exc
        fingerprint=hashlib.sha256(json.dumps(sorted(seen),separators=(",",":")).encode()).hexdigest()
        old=c.execute("SELECT * FROM analyzer_profiles WHERE label_key=?",(value.label.casefold(),)).fetchone()
        if old:
            if old["fingerprint"]!=fingerprint:raise HTTPException(409,"Profile label already exists; choose a distinct label")
            return {"id":old["id"],"label":old["label"],"reference_count":len(contents),"fingerprint":fingerprint}
        if c.execute("SELECT count(*) FROM analyzer_profiles").fetchone()[0]>=100:raise HTTPException(409,"Profile limit reached")
        import shutil
        stored=c.execute("SELECT COALESCE(sum(length(content)),0) FROM analyzer_profile_refs").fetchone()[0]
        size=sum(len(x[2]) for x in contents)
        from .intake import RESERVE
        if stored+size>512*1024**2 or shutil.disk_usage(store.root).free-RESERVE<3*size:
            raise HTTPException(409,"Profile storage budget exceeded")
        pid=uuid4().hex
        c.execute("INSERT INTO analyzer_profiles VALUES(?,?,?,?,?,?)",(pid,value.label,value.label.casefold(),value.job_id,int(time.time()),fingerprint))
        c.executemany("INSERT INTO analyzer_profile_refs VALUES(?,?,?,?,?)",[(pid,i,*x) for i,x in enumerate(contents,1)])
        return {"id":pid,"label":value.label,"reference_count":len(contents),"fingerprint":fingerprint}

def copy_refs(store,pid,target,start,remaining):
    # Read under the same admission lock as deletion. Job copies are immutable
    # snapshots; deleting the reusable set does not erase previous project inputs.
    with store.admission(),store.connect() as c:
        if not exists(c,pid):raise RuntimeError("Saved reference set not found")
        refs=c.execute("SELECT suffix,sha256,content FROM analyzer_profile_refs WHERE profile_id=? ORDER BY ordinal",(pid,)).fetchall()
        if not 1<=len(refs)<=12 or sum(len(r["content"]) for r in refs)>min(MAX_SET,remaining):raise RuntimeError("Profile snapshot exceeds limits")
        out=[]
        for i,row in enumerate(refs,start):
            blob=row["content"];suffix=row["suffix"]
            if suffix not in TYPES["image"] or not 0<len(blob)<=MAX_REF or hashlib.sha256(blob).hexdigest()!=row["sha256"]:
                raise RuntimeError("Saved reference checksum mismatch")
            import shutil
            from .intake import RESERVE
            if shutil.disk_usage(target).free-RESERVE<len(blob):raise RuntimeError("Insufficient VPS storage reserve")
            name=f"reference-{i:04d}{suffix}";p=target/name
            with p.open("xb") as f:f.write(blob);f.flush();os.fsync(f.fileno())
            verify_format(p,"image",suffix)
            out.append({"role":"reference","file":name,"size":len(blob),"sha256":row["sha256"],"profile_id":pid})
        return out

def delete(store,pid):
    with store.admission(),store.connect() as c:
        c.execute("PRAGMA secure_delete=ON");c.execute("BEGIN IMMEDIATE")
        if not exists(c,pid):raise HTTPException(404,"Reference set not found")
        for row in c.execute("SELECT payload FROM requests WHERE owner=? AND state IN ('awaiting_input','staging')",(store.owner,)):
            if json.loads(row["payload"])["settings"].get("profile_id")==pid:
                raise HTTPException(409,"Reference set is needed by an unfinished intake")
        c.execute("DELETE FROM analyzer_profiles WHERE id=?",(pid,))
        return {"deleted":True,"existing_job_snapshots_retained":True}
