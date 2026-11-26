"""Private owner-scoped library and immutable request snapshots."""
import fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager,ExitStack
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException,UploadFile
from pydantic import BaseModel,Field
from .store import safe_dir
from .uploads import transfer,create_uploaded,MAX_IMAGE_BYTES,MAX_BYTES,MAX_IMAGES
from .intake import Bridge,verify_format,TYPES,RESERVE
from .contracts import drive_link

class Name(BaseModel):
    name:str=Field(min_length=1,max_length=100)
class Selection(BaseModel):
    ids:list[str]=Field(min_length=1,max_length=1000)
class IdentityRequest(BaseModel):
    identity_id:str
    request:dict

def label(value):
    value=value.strip() if isinstance(value,str) else ""
    if not value or len(value)>100 or any(ord(x)<32 for x in value) or "/" in value or "\\" in value:
        raise HTTPException(422,"Invalid name")
    return value

def slug(value):
    out=re.sub(r"[^A-Za-z0-9]+","_",value).strip("_")[:64]
    if not out:raise HTTPException(422,"Identity needs at least one ASCII letter or number for filenames")
    return out

def init(s):
    with s.connect() as c:
        c.executescript("""CREATE TABLE IF NOT EXISTS identities(id TEXT PRIMARY KEY,name TEXT NOT NULL COLLATE NOCASE UNIQUE,slug TEXT NOT NULL COLLATE NOCASE UNIQUE,deleted INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS identity_images(id TEXT PRIMARY KEY,identity_id TEXT NOT NULL REFERENCES identities(id),name TEXT NOT NULL,suffix TEXT NOT NULL,size INTEGER NOT NULL,sha256 TEXT NOT NULL,deleted INTEGER NOT NULL DEFAULT 0);""")
    return safe_dir(s.root/"identity-library")

@contextmanager
def locked(s):
    root=init(s)
    with os.fdopen(os.open(root/"library.lock",os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600),"a") as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        yield root

def identity(c,i):
    row=c.execute("SELECT * FROM identities WHERE id=? AND deleted=0",(i,)).fetchone()
    if row is None:raise HTTPException(404,"Identity not found")
    return row

def listing(s):
    init(s)
    with s.connect() as c:
        return [{**dict(row),"images":[dict(x) for x in c.execute("SELECT id,name,size,sha256 FROM identity_images WHERE identity_id=? AND deleted=0 ORDER BY rowid",(row["id"],))]} for row in c.execute("SELECT id,name,slug FROM identities WHERE deleted=0 ORDER BY name")]

def create(s,name):
    name=label(name);prefix=slug(name)
    with locked(s),s.connect() as c:
        if c.execute("SELECT 1 FROM identities WHERE name=? OR slug=?",(name,prefix)).fetchone():raise HTTPException(409,"Identity name or filename prefix already reserved")
        if c.execute("SELECT count(*) FROM identities WHERE deleted=0").fetchone()[0]>=500:raise HTTPException(409,"Identity limit reached")
        i=uuid4().hex;c.execute("INSERT INTO identities VALUES(?,?,?,0)",(i,name,prefix))
    return {"id":i,"name":name,"slug":prefix}

def rename(s,i,name):
    name=label(name);prefix=slug(name)
    with locked(s),s.connect() as c:
        identity(c,i)
        if c.execute("SELECT 1 FROM identities WHERE id!=? AND (name=? OR slug=?)",(i,name,prefix)).fetchone():raise HTTPException(409,"Identity name or prefix reserved")
        c.execute("UPDATE identities SET name=?,slug=? WHERE id=?",(name,prefix,i))
    return {"id":i,"name":name}

def delete(s,i):
    with locked(s),s.connect() as c:
        identity(c,i);c.execute("UPDATE identities SET deleted=1 WHERE id=?",(i,))
        c.execute("UPDATE identity_images SET deleted=1 WHERE identity_id=?",(i,))
    return {"deleted":True}

def image_row(c,i,img):
    identity(c,i)
    r=c.execute("SELECT * FROM identity_images WHERE id=? AND identity_id=? AND deleted=0",(img,i)).fetchone()
    if r is None:raise HTTPException(404,"Image not found")
    return r

def checked(root,row):
    p=root/(row["id"]+row["suffix"])
    if p.resolve()!=p or not p.is_file() or p.stat().st_size!=row["size"]:raise HTTPException(409,"Reference image unavailable")
    return p

def image_path(s,i,img):
    root=init(s)
    with s.connect() as c:
        row=image_row(c,i,img);return checked(root,row),dict(row)

def rename_image(s,i,img,name):
    with locked(s),s.connect() as c:
        r=image_row(c,i,img);name=label(name)
        if not name.lower().endswith(r["suffix"]):name+=r["suffix"]
        if c.execute("SELECT 1 FROM identity_images WHERE identity_id=? AND deleted=0 AND id!=? AND name=? COLLATE NOCASE",(i,img,name)).fetchone():raise HTTPException(409,"Image name already used")
        c.execute("UPDATE identity_images SET name=? WHERE id=?",(name,img))
    return {"renamed":True}

def delete_images(s,i,ids):
    with locked(s),s.connect() as c:
        for img in set(ids):image_row(c,i,img)
        c.executemany("UPDATE identity_images SET deleted=1 WHERE id=?",[(img,) for img in set(ids)])
    return {"deleted":len(set(ids))}

def add_files(s,i,images,replace_id=None):
    if not 1<=len(images)<=MAX_IMAGES:raise HTTPException(422,"Choose 1–12 images")
    with locked(s) as root,s.connect() as c:
        identity(c,i)
        if replace_id and len(images)!=1:raise HTTPException(422,"Replace one image at a time")
        old=image_row(c,i,replace_id) if replace_id else None
        count=c.execute("SELECT count(*) FROM identity_images WHERE identity_id=? AND deleted=0",(i,)).fetchone()[0]
        if count+len(images)-bool(old)>MAX_IMAGES:raise HTTPException(409,"Maximum 12 images per identity")
        created=[];total=0
        try:
            for im in images:
                name=label(im.filename or "");suffix=Path(name).suffix.lower()
                if suffix not in TYPES["image"]:raise HTTPException(422,"Unsupported image format")
                im.file.seek(0)
                size,digest=transfer(im.file,min(MAX_IMAGE_BYTES,MAX_BYTES-total));total+=size;im.file.seek(0)
                if c.execute("SELECT 1 FROM identity_images WHERE identity_id=? AND deleted=0 AND id!=? AND (sha256=? OR name=? COLLATE NOCASE)",(i,replace_id or "",digest,name)).fetchone():raise HTTPException(409,"Duplicate image content or filename")
                if shutil.disk_usage(root).free-RESERVE<size:raise HTTPException(507,"Insufficient storage")
                img=uuid4().hex;p=root/(img+suffix);created.append(p)
                with p.open("xb") as f:
                    if transfer(im.file,size,f)!=(size,digest):raise HTTPException(409,"Image changed")
                    f.flush();os.fsync(f.fileno())
                try:verify_format(p,"image",suffix)
                except RuntimeError:raise HTTPException(422,"Image format mismatch") from None
                if old:c.execute("UPDATE identity_images SET deleted=1 WHERE id=?",(old["id"],))
                c.execute("INSERT INTO identity_images VALUES(?,?,?,?,?,?,0)",(img,i,name,suffix,size,digest))
            fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
            c.commit()
        except Exception:
            c.rollback()
            for p in created:p.unlink(missing_ok=True)
            raise
    return {"saved":len(images)}

def upload_action(s,data,images):
    i=data.get("identity_id")
    if data["library_action"]=="upload":return add_files(s,i,images,data.get("replace_id"))
    if data["library_action"]!="import" or images:raise HTTPException(422,"Invalid library action")
    try:link=drive_link(data.get("link"))
    except (ValueError,TypeError,AttributeError):raise HTTPException(422,"Invalid Drive image link") from None
    bridge=Bridge();root=init(s)
    try:
        rows=bridge.discover(link,"image")
        if len(rows)>MAX_IMAGES:raise HTTPException(422,"Maximum 12 images per identity")
        with tempfile.TemporaryDirectory(dir=root) as tmp,ExitStack() as stack:
            files=[];total=0
            for n,row in enumerate(rows):
                path=Path(tmp)/str(n)
                meta=bridge.request("download",{"row":row,"kind":"image"},path,"image",min(MAX_IMAGE_BYTES,MAX_BYTES-total))
                total+=meta["size"]
                files.append(UploadFile(filename=meta["name"],file=stack.enter_context(path.open("rb"))))
            return add_files(s,i,files)
    except RuntimeError as exc:raise HTTPException(502,str(exc)[:200]) from None

def create_request(s,data):
    with locked(s) as root,ExitStack() as stack:
        with s.connect() as c:
            row=identity(c,data.identity_id);snapshot=(row["id"],row["name"],row["slug"])
            rows=c.execute("SELECT * FROM identity_images WHERE identity_id=? AND deleted=0 ORDER BY rowid",(row["id"],)).fetchall()
        if not rows:raise HTTPException(422,"Identity has no images")
        if data.request.get("settings",{}).get("kind")!="extractor":raise HTTPException(422,"Identity library is for Clip Extractor")
        files=[]
        for r in rows:
            p=checked(root,r);f=stack.enter_context(p.open("rb"))
            if transfer(f,r["size"])!=(r["size"],r["sha256"]):raise HTTPException(409,"Reference digest changed")
            f.seek(0);files.append(UploadFile(filename=r["name"],file=f))
        return create_uploaded(s,json.dumps(data.request),files,snapshot)
