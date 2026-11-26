"""Opt-in separate VPS Drive writer. No changes to read-only intake identity.

Use a dedicated owner-approved Drive remote and explicit folder allowlist.
Stable per-job remote names; an uncertain write is never automatically repeated.
"""
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time
from urllib.parse import urlsplit
import fcntl
from .store import safe_dir

RCLONE=Path("/usr/bin/rclone")
MAX_JSON=2*1024**2
class DeliveryError(RuntimeError):pass

def settings(folder):
    if os.environ.get("CLIPCUTTER_DRIVE_DELIVERY_ENABLED")!="1":
        raise DeliveryError("Drive delivery not enabled")
    u=urlsplit(folder)
    match=re.fullmatch(r"/drive/(?:u/\d+/)?folders/([A-Za-z0-9_-]{10,200})/?",u.path)
    if u.scheme!="https" or u.netloc!="drive.google.com" or u.fragment or not match:
        raise DeliveryError("Invalid Drive delivery destination")
    fid=match.group(1)
    if fid not in os.environ.get("CLIPCUTTER_APPROVED_DRIVE_OUTPUT_FOLDERS","").split(","):
        raise DeliveryError("Drive destination is not approved")
    base=Path(os.environ.get("CLIPCUTTER_WEB_DATA_ROOT",""))
    conf=base/"drive-delivery"/"rclone.conf"
    remote=os.environ.get("CLIPCUTTER_DRIVE_DELIVERY_REMOTE","")
    try:
        st=conf.lstat()
        if (not base.is_absolute() or conf.resolve()!=conf or not stat.S_ISREG(st.st_mode)
            or st.st_uid!=os.geteuid() or stat.S_IMODE(st.st_mode)!=0o600
            or st.st_nlink!=1 or not 0<st.st_size<=1024**2
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",remote)
            or not RCLONE.is_file() or not os.access(RCLONE,os.X_OK)):
            raise ValueError()
        parser=configparser.RawConfigParser()
        parser.read(conf)
        if parser.get(remote,"type",fallback="")!="drive":raise ValueError()
    except (OSError,ValueError,configparser.Error):
        raise DeliveryError("Dedicated private Drive writer configuration unavailable") from None
    return fid,conf,remote

def allowed(folder):
    try:settings(folder);return True
    except DeliveryError:return False

def call(folder,args,timeout=60):
    fid,conf,remote=settings(folder)
    cmd=[str(RCLONE),"--config",str(conf),"--drive-root-folder-id",fid,
         "--retries","1","--low-level-retries","1","--contimeout","10s","--timeout","60s",*args(remote+":")]
    try:
        with tempfile.TemporaryFile() as out:
            proc=subprocess.run(cmd,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.DEVNULL,
                timeout=timeout,env={"PATH":"/usr/bin:/bin","HOME":str(conf.parent),"LANG":"C.UTF-8"})
            if proc.returncode:raise DeliveryError("Drive writer command failed; verify permissions and remote state")
            out.seek(0);raw=out.read(MAX_JSON+1)
            if len(raw)>MAX_JSON:raise DeliveryError("Drive metadata exceeds limit")
            return raw
    except (OSError,subprocess.SubprocessError):
        raise DeliveryError("Drive writer interrupted; remote state must be reconciled") from None

def listing(folder,name=None):
    # Exact include filter, safe names generated from trusted artifact descriptors.
    def args(root):
        return ["lsjson",root,"--max-depth","1","--files-only","--hash",*(["--include","/"+name] if name else [])]
    try:
        rows=json.loads(call(folder,args))
        if not isinstance(rows,list) or any(not isinstance(x,dict) for x in rows):raise ValueError()
        return rows
    except (ValueError,TypeError):raise DeliveryError("Invalid Drive verification metadata") from None

def preflight(folder):
    # Read permission is checked before dispatch. Write permission still needs live acceptance.
    listing(folder,"clipcutter-preflight-nonexistent")

def local_hash(path):
    h=hashlib.md5(usedforsecurity=False)
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()

def verify_remote(folder,name,item,md5):
    rows=listing(folder,name)
    if not rows:return False
    if len(rows)!=1:raise DeliveryError("Duplicate destination names; manual reconciliation required")
    row=rows[0];hashes=row.get("Hashes")
    if (row.get("Name")!=name or row.get("IsDir") is not False or row.get("Size")!=item["size"]
        or not isinstance(hashes,dict) or str(hashes.get("MD5",hashes.get("md5",""))).lower()!=md5):
        raise DeliveryError("Existing Drive output does not match verified VPS file")
    return True

def deliver_one(store,jid,folder,dest,items):
    locks=safe_dir(store.root/"orchestration-locks")
    with os.fdopen(os.open(locks/"drive-delivery.lock",os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600),"a") as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise DeliveryError("Another Drive delivery is active") from None
        return _deliver_one(store,jid,folder,dest,items)

def _deliver_one(store,jid,folder,dest,items):
    settings(folder)
    with store.connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS drive_delivery (
          job_id TEXT NOT NULL REFERENCES requests(id),name TEXT NOT NULL,folder TEXT NOT NULL,
          sha256 TEXT NOT NULL,phase TEXT NOT NULL,PRIMARY KEY(job_id,name))""")
    for item in items:
        name=item["name"];path=dest/name
        from .output_names import alias_for
        remote_name=alias_for(store,jid,name) or "clipcutter-"+jid+"-"+name
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",name)
            or path.resolve()!=path or not path.is_file() or path.stat().st_size!=item["size"]):
            raise DeliveryError("Unsafe or changed VPS output")
        with store.connect() as c:
            row=c.execute("SELECT * FROM drive_delivery WHERE job_id=? AND name=?",(jid,name)).fetchone()
        if row and (row["folder"]!=folder or row["sha256"]!=item["sha256"]):
            raise DeliveryError("Recorded Drive destination or checksum changed")
        if row and row["phase"]=="verified":continue
        md5=local_hash(path)
        if not verify_remote(folder,remote_name,item,md5):
            if row:raise DeliveryError("Unconfirmed prior upload; manual reconciliation required")
            with store.connect() as c:
                c.execute("INSERT INTO drive_delivery VALUES(?,?,?,?,'intent')",(jid,name,folder,item["sha256"]))
            call(folder,lambda root:["copyto",str(path),root+remote_name,"--immutable","--checksum"],timeout=7200)
            if not verify_remote(folder,remote_name,item,md5):
                raise DeliveryError("Uploaded file not yet verified")
        with store.connect() as c:
            c.execute("INSERT INTO drive_delivery VALUES(?,?,?,?,'verified') ON CONFLICT(job_id,name) DO UPDATE SET phase='verified'",(jid,name,folder,item["sha256"]))
            c.execute("UPDATE requests SET message=?,updated_at=? WHERE id=? AND owner=? AND state='delivering'",("Drive output verified: "+name,int(time.time()),jid,store.owner))
        return False
    return True
