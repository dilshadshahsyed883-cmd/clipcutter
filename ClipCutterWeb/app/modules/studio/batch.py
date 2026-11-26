"""Verified batch expansion on VPS; no GPU slot used during extraction.

Each child is a normal single-video request with an immutable local input manifest.
Original batch input remains retained. Database publication is all-or-nothing.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import time
import zipfile
from fastapi import HTTPException
from .contracts import JobRequest
from .store import safe_dir
from .intake import TYPES, LIMIT, JOB_LIMIT, RESERVE, verify_format

MAX_VIDEOS=200
MAX_REFERENCE=16*1024*1024
def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for data in iter(lambda:f.read(1024*1024),b""):h.update(data)
    return h.hexdigest()
def syncdir(p):
    fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
def ident(parent,kind,index):
    return hashlib.sha256(f"clipcutter-batch-v1:{parent}:{kind}:{index}".encode()).hexdigest()[:32]
def copy_verified(src,dst,size,digest):
    if src.resolve()!=src or not src.is_file() or src.stat().st_size!=size or sha(src)!=digest:
        raise RuntimeError("Batch source changed after intake")
    if shutil.disk_usage(dst.parent).free-RESERVE<size:raise RuntimeError("Insufficient VPS batch storage")
    with src.open("rb") as f,dst.open("xb") as o:
        shutil.copyfileobj(f,o,1024*1024);o.flush();os.fsync(o.fileno())
    if dst.stat().st_size!=size or sha(dst)!=digest:raise RuntimeError("Batch copy verification failed")
def unpack(archive,work):
    verify_format(archive,"zip",".zip")
    videos=[];total=0
    with zipfile.ZipFile(archive) as z:
        for entry in z.infolist():
            mode=stat.S_IFMT(entry.external_attr>>16)
            if mode not in (0,stat.S_IFREG,stat.S_IFDIR):raise RuntimeError("Unsupported ZIP member type")
            if entry.is_dir():continue
            suffix=Path(entry.filename).suffix.lower()
            video=suffix in TYPES["video"]
            if video and (not 0<entry.file_size<=LIMIT or len(videos)>=MAX_VIDEOS):
                raise RuntimeError("ZIP video count or size limit exceeded")
            if entry.file_size<0 or total+entry.file_size>JOB_LIMIT:raise RuntimeError("ZIP expanded size limit exceeded")
            if video and shutil.disk_usage(work).free-RESERVE<entry.file_size:raise RuntimeError("Insufficient ZIP extraction storage")
            target=work/f"source-{len(videos)+1:04d}{suffix}" if video else None
            digest=hashlib.sha256();n=0
            # Read every entry to EOF so CRC failure anywhere rejects the batch.
            out=target.open("xb") if target else None
            try:
                with z.open(entry) as src:
                    for data in iter(lambda:src.read(1024*1024),b""):
                        n+=len(data)
                        if n>entry.file_size or total+n>JOB_LIMIT:raise RuntimeError("ZIP member exceeds declared size")
                        if out:out.write(data);digest.update(data)
                if n!=entry.file_size:raise RuntimeError("ZIP member size mismatch")
                if out:out.flush();os.fsync(out.fileno())
            finally:
                if out:out.close()
            total+=n
            if target:
                verify_format(target,"video",suffix)
                videos.append({"role":"source","file":target.name,"size":n,"sha256":digest.hexdigest(),
                               "label":entry.filename[:240]})
    if not videos:raise RuntimeError("ZIP contains no supported videos")
    return videos

def expand(store,parent,root,manifest):
    job=store.get(parent)
    if job["state"]!="staging" or job["input"]["source_kind"] not in ("folder","zip"):
        raise RuntimeError("Invalid batch parent")
    inputs=safe_dir(store.root/"inputs")
    if root!=inputs/parent or root.resolve()!=root:raise RuntimeError("Unsafe batch directory")
    sources=[x for x in manifest if x["role"]=="source"]
    refs=[x for x in manifest if x["role"]=="reference"]
    if len(refs)>12 or any(not 0<x["size"]<=MAX_REFERENCE for x in refs):
        raise RuntimeError("Batch reference count or size limit exceeded")
    if bool(job["settings"].get("reference_link") or job["settings"].get("reference_uploads"))!=bool(refs):raise RuntimeError("Batch reference mismatch")
    for x in manifest:
        if not re.fullmatch(r"(?:source|reference)-[0-9]{4}\.[a-z0-9]+",x["file"]):raise RuntimeError("Unsafe batch filename")
        p=root/x["file"]
        if p.resolve()!=p or not p.is_file() or p.stat().st_size!=x["size"] or sha(p)!=x["sha256"]:
            raise RuntimeError("Batch input digest mismatch")
    work=inputs/(parent+".expand")
    if work.exists():safe_dir(work);shutil.rmtree(work)
    safe_dir(work)
    children=[];moved=[]
    try:
        source_root=root
        if job["input"]["source_kind"]=="zip":
            if len(sources)!=1:raise RuntimeError("One ZIP file required")
            sources=unpack(root/sources[0]["file"],work);source_root=work
        else:
            sources=[{**x,"label":x.get("original_name") or x["file"]} for x in sources]
        if not 1<=len(sources)<=MAX_VIDEOS:raise RuntimeError("Batch must contain 1–200 videos")
        # Bound duplicate reference storage as well as video files.
        required=sum(x["size"] for x in sources)+len(sources)*sum(x["size"] for x in refs)
        if required>JOB_LIMIT or shutil.disk_usage(work).free-RESERVE<required:
            raise RuntimeError("Expanded batch exceeds VPS storage budget")
        for index,item in enumerate(sources,1):
            child=ident(parent,"job",index);request_id=ident(parent,"request",index)
            child_root=safe_dir(work/child);files=[]
            for role,entries,base in [("source",[item],source_root),("reference",refs,root)]:
                for i,x in enumerate(entries,1):
                    suffix=Path(x["file"]).suffix.lower()
                    name=f"{role}-{i:04d}{suffix}"
                    copy_verified(base/x["file"],child_root/name,x["size"],x["sha256"])
                    verify_format(child_root/name,"video" if role=="source" else "image",suffix)
                    files.append({"role":role,"file":name,"size":x["size"],"sha256":x["sha256"]})
            with (child_root/"manifest.json").open("x") as f:
                json.dump({"version":1,"files":files},f);f.flush();os.fsync(f.fileno())
            syncdir(child_root)
            # Folder children reference the exact Drive file; ZIP children retain
            # the archive link as provenance only. Neither is downloaded again.
            inp={**job["input"],"source_kind":"video"}
            if job["input"]["source_kind"]=="folder":
                did=item.get("drive_id","")
                if not re.fullmatch(r"[A-Za-z0-9_-]{10,200}",did):raise RuntimeError("Invalid Drive member ID")
                inp["source"]="https://drive.google.com/file/d/"+did+"/view"
            req=JobRequest.model_validate({"input":inp,"settings":job["settings"],"request_id":request_id})
            children.append((child,req,item["label"][:240],index))
        # All media verified before making any child visible to dispatcher.
        with store.admission(),store.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row=store.row(c,parent)
            if row["state"]!="staging":raise RuntimeError("Stale batch state")
            c.execute("""CREATE TABLE IF NOT EXISTS batch_members(
                parent_id TEXT NOT NULL REFERENCES requests(id),child_id TEXT PRIMARY KEY REFERENCES requests(id),
                ordinal INTEGER NOT NULL,label TEXT NOT NULL,UNIQUE(parent_id,ordinal))""")
            now=int(time.time())
            for child,req,label,index in children:
                if c.execute("SELECT 1 FROM requests WHERE id=? OR request_id=?",(child,req.request_id)).fetchone():
                    raise RuntimeError("Batch child identity collision")
                dest=inputs/child
                # Orphans from a crash before DB commit may be rebuilt; no
                # published job can be removed because the row check precedes it.
                if dest.exists():safe_dir(dest);shutil.rmtree(dest)
                (work/child).rename(dest);moved.append(dest)
                payload=json.dumps(req.model_dump(exclude={"request_id"}),sort_keys=True,separators=(",",":"))
                c.execute("INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?,?)",(child,req.request_id,store.owner,
                    req.settings.kind,payload,"ready",now,now,100,f"Batch {parent[:8]} · video {index}/{len(children)}: {label}"))
                c.execute("INSERT INTO batch_members VALUES (?,?,?,?)",(parent,child,index,label))
                c.execute("INSERT INTO request_identities SELECT ?,identity_id,label,slug FROM request_identities WHERE job_id=?",(child,parent))
            syncdir(inputs)
            c.execute("UPDATE requests SET state='batch_expanded',progress=100,message=?,updated_at=? WHERE id=?",
                      (f"Verified batch: {len(children)} independent video requests",now,parent))
    except Exception:
        # If commit succeeded but response failed, never remove visible children.
        with store.connect() as c:
            for p in moved:
                if not c.execute("SELECT 1 FROM requests WHERE id=?",(p.name,)).fetchone() and p.exists():
                    shutil.rmtree(p)
        raise
    finally:
        if work.exists():shutil.rmtree(work)

def members(store,parent):
    with store.connect() as c:
        store.row(c,parent)
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='batch_members'").fetchone():return []
        rows=c.execute("""SELECT b.ordinal,b.label,r.* FROM batch_members b JOIN requests r ON r.id=b.child_id
                         WHERE b.parent_id=? AND r.owner=? AND r.state!='deleted' ORDER BY b.ordinal""",(parent,store.owner)).fetchall()
        return [{**store.public(x),"ordinal":x["ordinal"],"label":x["label"]} for x in rows]
