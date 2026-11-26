"""Owner-scoped direct reference uploads, never media execution on VPS."""
import hashlib
import json
import os
from pathlib import Path
import shutil
from fastapi import HTTPException
from pydantic import ValidationError
from .contracts import JobRequest
from .store import safe_dir
from .intake import TYPES, RESERVE, verify_format

MAX_IMAGE_BYTES=10*1024**2
MAX_IMAGES=12
MAX_BYTES=MAX_IMAGES*MAX_IMAGE_BYTES
CHUNK=1024**2

def transfer(source,limit,target=None):
    """Read bounded chunks, optionally copy and hash; never buffer a whole upload."""
    digest=hashlib.sha256();size=0
    while True:
        chunk=source.read(min(CHUNK,limit-size+1))
        if not chunk:break
        size+=len(chunk)
        if size>limit:raise HTTPException(413,"Reference image or combined size exceeds limit")
        digest.update(chunk)
        if target is not None:target.write(chunk)
    if not size:raise HTTPException(422,"Empty reference image")
    return size,digest.hexdigest()

def create_uploaded(store,payload,images):
    if not 1<=len(images)<=MAX_IMAGES:
        raise HTTPException(422,"Select 1–12 images")
    try:
        data=json.loads(payload)
        if not isinstance(data,dict) or not isinstance(data.get("settings"),dict):
            raise ValueError()
        if data["settings"].get("reference_link") or data["settings"].get("reference_uploads"):
            raise ValueError()
        records=[]; total=0
        for image in images:
            suffix=Path(image.filename or "").suffix.lower()
            if suffix not in TYPES["image"]: raise ValueError()
            image.file.seek(0)
            size,digest=transfer(image.file,min(MAX_IMAGE_BYTES,MAX_BYTES-total))
            total+=size
            image.file.seek(0)
            records.append((suffix,image.file,digest,size))
        data["settings"]["reference_uploads"]=[x[2] for x in records]
        req=JobRequest.model_validate(data)
    except (ValueError,TypeError,ValidationError):
        raise HTTPException(422,"Invalid reference images or request settings") from None
    with store.admission():
        with store.connect() as c:
            previous=c.execute("SELECT id FROM requests WHERE request_id=? AND owner=?",(req.request_id,store.owner)).fetchone()
        if previous:
            return store._create(req)
        root=safe_dir(store.root/"reference-uploads")
        target=root/req.request_id
        if target.exists(): safe_dir(target);shutil.rmtree(target)
        if shutil.disk_usage(root).free-RESERVE<total:
            raise HTTPException(507,"Insufficient VPS storage reserve")
        safe_dir(target)
        try:
            for i,(suffix,source,digest,size) in enumerate(records,1):
                p=target/f"{i:04d}{suffix}"
                with os.fdopen(os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),"wb") as f:
                    if transfer(source,size,f)!=(size,digest):raise RuntimeError("Upload changed while saving")
                    f.flush();os.fsync(f.fileno())
                verify_format(p,"image",suffix)
            for d in (target,root):
                fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(fd)
                finally:os.close(fd)
            return store._create(req)
        except RuntimeError:
            shutil.rmtree(target)
            raise HTTPException(422,"Reference image format does not match its extension") from None
        except Exception:
            shutil.rmtree(target)
            raise

def stage_uploads(store,jid,digests,tmp,manifest,remaining):
    root=safe_dir(store.root/"reference-uploads"/store.request_key(jid))
    files=sorted(root.iterdir())
    if len(files)!=len(digests):raise RuntimeError("Uploaded reference files missing")
    total=0
    for i,(p,digest) in enumerate(zip(files,digests),1):
        suffix=p.suffix.lower()
        if p.name!=f"{i:04d}{suffix}" or suffix not in TYPES["image"] or p.resolve()!=p or not p.is_file():
            raise RuntimeError("Unsafe uploaded reference")
        size=p.stat().st_size
        if not 0<size<=min(MAX_IMAGE_BYTES,MAX_BYTES-total,remaining-total):
            raise RuntimeError("Uploaded references exceed limits")
        if shutil.disk_usage(tmp).free-RESERVE<size:raise RuntimeError("Insufficient VPS storage reserve")
        name=f"reference-{len(manifest)+1:04d}{suffix}"
        with p.open("rb") as src,(tmp/name).open("xb") as f:
            if transfer(src,size,f)!=(size,digest):raise RuntimeError("Uploaded reference checksum mismatch")
            f.flush();os.fsync(f.fileno())
        total+=size
        verify_format(tmp/name,"image",suffix)
        manifest.append({"role":"reference","file":name,"size":size,"sha256":digest,"original_name":p.name})
    return total

def discard_uploads(store,jid):
    path=store.root/"reference-uploads"/store.request_key(jid)
    if path.exists():
        safe_dir(path)
        shutil.rmtree(path)
