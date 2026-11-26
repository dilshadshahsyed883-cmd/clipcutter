"""Owner-scoped, read-only Drive staging. No GPU or output transport."""
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import socket
import time
import zipfile
import zlib
from fastapi import HTTPException
from .store import safe_dir
from . import youtube

LIMIT = 4 * 1024**3
JOB_LIMIT = 20 * 1024**3
RESERVE = 5_000_000_000
TYPES = {"video": {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"},
         "image": {".jpg", ".jpeg", ".png", ".webp"}, "zip": {".zip"}}
TYPES["source"]=TYPES["video"]|TYPES["zip"]

class Retryable(RuntimeError):
    pass

class UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path, timeout):
        super().__init__("localhost", timeout=timeout)
        self.path = path
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)

class Bridge:
    def __init__(self, path=None):
        self.path = path or os.environ.get("CLIPCUTTER_DRIVE_BRIDGE_SOCKET",
                                          "/run/clipcutter-drive-bridge/intake.sock")
    def request(self, operation, payload, target=None, kind=None, remaining=LIMIT):
        conn = UnixHTTP(self.path, 7500 if target else 5 if operation=="health" else 120)
        try:
            conn.request("POST", "/v1/"+operation, json.dumps(payload), {"Content-Type":"application/json"})
            res = conn.getresponse()
            if res.status != 200:
                if res.status >= 500 or res.status in (408,429):
                    raise Retryable("Drive bridge unavailable or transfer failed")
                raise RuntimeError("Drive source rejected: check link, file type, access and limits")
            if target is None:
                body = res.read(2*1024**2+1)
                if len(body)>2*1024**2:
                    raise ValueError()
                return json.loads(body)
            meta = json.loads(res.getheader("X-File-Meta",""))
            size = meta["size"]
            suffix = Path(meta["name"]).suffix.lower()
            if (type(size) is not int or not 0 < size <= min(LIMIT,remaining)
                    or size != int(res.getheader("Content-Length","0"))
                    or suffix not in TYPES[kind] or not re.fullmatch(r"[a-f0-9]{64}",meta["sha256"])
                    or not re.fullmatch(r"[a-f0-9]{32}",meta["md5"])):
                raise ValueError()
            if shutil.disk_usage(target.parent).free - RESERVE < size:
                raise RuntimeError("Insufficient VPS storage reserve")
            sha, md5, n = hashlib.sha256(), hashlib.md5(usedforsecurity=False), 0
            with target.open("xb") as f:
                while n < size:
                    chunk = res.read(min(1024*1024,size-n))
                    if not chunk:
                        raise Retryable("Incomplete Drive transfer")
                    n += len(chunk); sha.update(chunk); md5.update(chunk); f.write(chunk)
                f.flush(); os.fsync(f.fileno())
            if sha.hexdigest()!=meta["sha256"] or md5.hexdigest()!=meta["md5"]:
                raise Retryable("Drive transfer checksum mismatch")
            row = payload["row"]
            if row["size"] and (size!=row["size"] or meta["md5"]!=row["md5"]):
                raise Retryable("Drive listing checksum mismatch")
            return meta
        except (OSError, http.client.HTTPException):
            raise Retryable("Drive connection or local transfer interrupted") from None
        except (ValueError, TypeError, KeyError, AttributeError):
            raise RuntimeError("Invalid Drive bridge response") from None
        finally:
            conn.close()
    def available(self):
        try:
            return self.request("health",{})=={"ok":True,"protocol":1}
        except RuntimeError:
            return False
    def discover(self, link, kind):
        data=self.request("scan",{"link":link,"kind":kind})
        rows=data.get("files") if isinstance(data,dict) else None
        if not isinstance(rows,list) or not 1<=len(rows)<=200:
            raise RuntimeError("No supported files found or folder exceeds 200 files")
        seen=set()
        for row in rows:
            if (not isinstance(row,dict) or set(row)!={"id","name","size","md5","keys"}
                    or not isinstance(row["id"],str) or not re.fullmatch(r"[A-Za-z0-9_-]{10,200}",row["id"])
                    or row["id"] in seen or type(row["size"]) is not int or not 0<=row["size"]<=LIMIT
                    or not all(isinstance(row[k],str) for k in ("name","md5","keys"))
                    or (row["size"] and not re.fullmatch(r"[a-f0-9]{32}",row["md5"]))):
                raise RuntimeError("Invalid Drive listing")
            seen.add(row["id"])
        return rows

def verify_format(path, kind, suffix):
    # Basic container signatures only; no decoding or model execution on VPS.
    with path.open("rb") as f:
        header=f.read(16)
    if kind=="image":
        ok=(suffix in (".jpg",".jpeg") and header.startswith(b"\xff\xd8\xff")
            or suffix==".png" and header.startswith(b"\x89PNG\r\n\x1a\n")
            or suffix==".webp" and header[:4]==b"RIFF" and header[8:12]==b"WEBP")
    elif kind=="video":
        ok=(suffix in (".mp4",".mov",".m4v") and header[4:8]==b"ftyp"
            or suffix in (".mkv",".webm") and header.startswith(b"\x1a\x45\xdf\xa3")
            or suffix==".avi" and header[:4]==b"RIFF" and header[8:12]==b"AVI ")
    else:
        # Bound the central directory before ZipFile allocates it. No extraction.
        with path.open("rb") as f:
            end=zipfile._EndRecData(f)
        ok=bool(end and 0<end[zipfile._ECD_ENTRIES_TOTAL]<=20000
                and end[zipfile._ECD_SIZE]<=32*1024**2)
        if ok:
            with zipfile.ZipFile(path) as z:
                entries=z.infolist()
                ok=(len({e.filename for e in entries})==len(entries)
                    and sum(e.file_size for e in entries)<=JOB_LIMIT
                    and all(not e.flag_bits&1 and not (e.external_attr>>16)&0o170000==0o120000
                            and not e.filename.startswith(("/", "\\"))
                            and "\\" not in e.filename and ".." not in e.filename.split("/")
                            and ":" not in e.filename for e in entries))
    if not ok:
        raise RuntimeError("Input file format does not match selected type")

def retry(fn):
    for attempt in range(5):
        try:
            return fn()
        except Retryable:
            if attempt==4:
                raise
            time.sleep(20)

def stage(store, jid, bridge=None):
    """Explicit background intake. Lock prevents concurrent/restarted requests
    from mutating the same job; a manual retry recovers interrupted staging."""
    bridge=bridge or Bridge()
    locks=safe_dir(store.root/"intake-locks")
    lockpath=locks/(jid+".lock")
    # jid was validated by owner-scoped route; validate independently as well.
    if not re.fullmatch(r"[a-f0-9]{32}",jid):
        raise HTTPException(404,"Request not found")
    with os.fdopen(os.open(lockpath,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600),"a") as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            return
        with store.admission():
            job=store.get(jid)
            if job["state"] not in ("awaiting_input","staging","failed"):
                return
            if job["state"]=="failed" and not job["message"].startswith(("Drive intake:","YouTube intake:")):
                return
            is_youtube=job["input"]["source_kind"]=="youtube"
            label="YouTube" if is_youtube else "Drive"
            if job["state"]!="staging":
                store.transition(jid,job["state"],"staging","Discovering "+label+" input")
        parent=safe_dir(store.root/"inputs")
        tmp=parent/(jid+".partial")
        final=parent/jid
        try:
            for p in (tmp,final):
                if p.exists():
                    safe_dir(p)
                    shutil.rmtree(p)
            safe_dir(tmp)
            kind={"zip":"zip","auto":"source"}.get(job["input"]["source_kind"],"video")
            sources=[] if is_youtube else [("source",job["input"]["source"],kind)]
            if job["settings"].get("reference_link"):
                sources.append(("reference",job["settings"]["reference_link"],"image"))
            plan=[(role,k,row) for role,link,k in sources
                  for row in retry(lambda:bridge.discover(link,k))]
            if is_youtube:
                plan.insert(0,("source","youtube",{"id":job["input"]["source"].split("=")[-1],"size":0}))
            if len(plan)>200 or sum(row["size"] for _,_,row in plan)>JOB_LIMIT:
                raise RuntimeError("Input exceeds job limits")
            manifest=[]; total=0
            for index,(role,k,row) in enumerate(plan,1):
                part=tmp/"transfer.part"
                def download():
                    part.unlink(missing_ok=True)
                    return bridge.request("download",{"row":row,"kind":k},part,k,JOB_LIMIT-total)
                if k=="youtube":
                    store.intake_progress(jid,0,"Downloading YouTube video (1080p maximum, no audio)")
                    meta=youtube.download(store,job["input"]["source"],part,JOB_LIMIT-total)
                else:
                    meta=retry(download)
                suffix=Path(meta["name"]).suffix.lower()
                detected="zip" if suffix==".zip" else "video"
                verify_format(part,detected if k=="source" else "video" if k=="youtube" else k,suffix)
                if k=="source":
                    if detected=="zip" and job["settings"].get("mode")=="manual":
                        raise RuntimeError("Manual ranges require a single video source")
                    store.resolve_source(jid,detected)
                    job=store.get(jid)
                name=f"{role}-{index:04d}{suffix}"
                part.rename(tmp/name)
                total+=meta["size"]
                manifest.append({"role":role,("youtube_id" if k=="youtube" else "drive_id"):row["id"],"file":name,
                                 "size":meta["size"],"sha256":meta["sha256"],"md5":meta["md5"],"original_name":meta["name"]})
                store.intake_progress(jid, min(99,round(index/len(plan)*100,1)),
                                      f"Verified {index}/{len(plan)} input files")
            if job["settings"].get("reference_uploads"):
                from .uploads import stage_uploads
                total+=stage_uploads(store,jid,job["settings"]["reference_uploads"],tmp,manifest,JOB_LIMIT-total)
            with (tmp/"manifest.json").open("x") as f:
                json.dump({"version":1,"files":manifest},f)
                f.flush(); os.fsync(f.fileno())
            tmp.rename(final)
            fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
            try: os.fsync(fd)
            finally: os.close(fd)
            if job["input"]["source_kind"] in ("folder","zip"):
                from .batch import expand
                expand(store,jid,final,manifest)
            else:
                store.transition(jid,"staging","ready",("YouTube inputs verified; GPU dispatch not supported yet" if is_youtube else "Drive inputs verified"),100)
            from .uploads import discard_uploads
            discard_uploads(store,jid)
        except (RuntimeError,OSError,ValueError,zipfile.BadZipFile,HTTPException,NotImplementedError,EOFError,zlib.error) as exc:
            if tmp.exists():
                shutil.rmtree(tmp)
            detail=str(exc) if type(exc) in (RuntimeError,Retryable) else "Input verification or storage operation failed"
            if store.get(jid)["state"]=="staging":
                store.transition(jid,"staging","failed",label+" intake: "+detail[:300])
