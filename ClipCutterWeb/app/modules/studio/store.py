"""Owner-scoped persistent request ledger. No scheduler and no browser worker callback."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
from uuid import uuid4
from fastapi import HTTPException
from .contracts import JobRequest

KINDS={"extractor","analyzer"}

def safe_dir(path):
    path.mkdir(mode=0o700,parents=True,exist_ok=True)
    st=path.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.geteuid() or stat.S_IMODE(st.st_mode)!=0o700 or path.resolve()!=path:
        raise HTTPException(503,"Unsafe studio storage")
    return path

class Store:
    def __init__(self,owner,root=None):
        self.owner=owner.casefold()
        base=Path(root or os.environ.get("CLIPCUTTER_WEB_DATA_ROOT",""))
        if not base.is_absolute() or not base.is_dir() or base.resolve()!=base:
            raise HTTPException(503,"Studio storage not configured")
        self.root=safe_dir(safe_dir(base/"studio")/hashlib.sha256(self.owner.encode()).hexdigest())
        self.db=self.root/"requests.sqlite3"
        try:
            fd=os.open(self.db,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
            os.close(fd)
        except FileExistsError:
            pass
        st=self.db.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or st.st_uid!=os.geteuid() or stat.S_IMODE(st.st_mode)!=0o600:
            raise HTTPException(503,"Unsafe studio database")
        with self.connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS requests(
                id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, owner TEXT NOT NULL,
                kind TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                progress REAL, message TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outputs(
                job_id TEXT NOT NULL, name TEXT NOT NULL, size INTEGER NOT NULL,
                sha256 TEXT NOT NULL, media_type TEXT NOT NULL,
                PRIMARY KEY(job_id,name), FOREIGN KEY(job_id) REFERENCES requests(id));
            """)

    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.db,timeout=10)
        c.row_factory=sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        try:
            with c: yield c
        finally: c.close()

    def create(self,req:JobRequest):
        payload=json.dumps(req.model_dump(exclude={"request_id"}),sort_keys=True,separators=(",",":"))
        now=int(time.time())
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT * FROM requests WHERE request_id=? AND owner=?",(req.request_id,self.owner)).fetchone()
            if row:
                if row["payload"]!=payload: raise HTTPException(409,"Request ID already used with different settings")
                return self.public(row)
            count=c.execute("SELECT count(*) FROM requests WHERE owner=? AND state='awaiting_input'",(self.owner,)).fetchone()[0]
            if count>=500: raise HTTPException(409,"Pending request limit reached")
            jid=uuid4().hex
            c.execute("INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?,?)",
                (jid,req.request_id,self.owner,req.settings.kind,payload,"awaiting_input",now,now,None,"Saved; Drive input has not been verified"))
            return self.public(c.execute("SELECT * FROM requests WHERE id=?",(jid,)).fetchone())

    def public(self,row):
        return {"id":row["id"],"kind":row["kind"],"state":row["state"],"progress":row["progress"],
                "message":row["message"],"created_at":row["created_at"],"updated_at":row["updated_at"],
                **json.loads(row["payload"])}

    def list(self,kind):
        with self.connect() as c:
            rows=c.execute("SELECT * FROM requests WHERE owner=? AND kind=? ORDER BY created_at DESC,id DESC LIMIT 200",(self.owner,kind)).fetchall()
            return [self.public(r) for r in rows]

    def row(self,c,jid):
        if not re.fullmatch(r"[a-f0-9]{32}",jid): raise HTTPException(404,"Request not found")
        row=c.execute("SELECT * FROM requests WHERE id=? AND owner=?",(jid,self.owner)).fetchone()
        if not row: raise HTTPException(404,"Request not found")
        return row

    def get(self,jid):
        with self.connect() as c: return self.public(self.row(c,jid))

    def cancel(self,jid):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row=self.row(c,jid)
            if row["state"]=="cancelled": return self.public(row)
            if row["state"]!="awaiting_input": raise HTTPException(409,"Request cannot be cancelled by this control")
            c.execute("UPDATE requests SET state='cancelled',message='Cancelled before input intake',updated_at=? WHERE id=? AND owner=?",(int(time.time()),jid,self.owner))
            return self.public(self.row(c,jid))

    def output_list(self,jid):
        with self.connect() as c:
            row=self.row(c,jid)
            if row["state"]!="completed": return []
            return [dict(x) for x in c.execute("SELECT name,size,sha256,media_type FROM outputs WHERE job_id=? ORDER BY name",(jid,))]

    def output_path(self,jid,name):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",name):
            raise HTTPException(404,"Output not found")
        rows=[x for x in self.output_list(jid) if x["name"]==name]
        if not rows: raise HTTPException(404,"Output not found")
        p=self.root/"outputs"/jid/name
        if p.resolve()!=p or not p.is_file() or p.stat().st_nlink!=1 or p.stat().st_size!=rows[0]["size"]:
            raise HTTPException(404,"Verified output unavailable")
        return p,rows[0]
