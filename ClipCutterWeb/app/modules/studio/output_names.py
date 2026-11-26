"""Durable display names; verified GPU artifact paths and receipt rows never change."""
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from fastapi import HTTPException
from pydantic import BaseModel,Field
from .store import safe_dir
from .intake import RESERVE

class Change(BaseModel):
    action:str
    ids:list[str]=Field(min_length=1,max_length=1000)
    name:str|None=None

def init(s):
    with s.connect() as c:
        c.executescript("""CREATE TABLE IF NOT EXISTS identity_counters(identity_id TEXT PRIMARY KEY,next_number INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS output_names(job_id TEXT NOT NULL REFERENCES requests(id),original TEXT NOT NULL,display TEXT NOT NULL COLLATE NOCASE,deleted INTEGER NOT NULL DEFAULT 0,duration_ms INTEGER,PRIMARY KEY(job_id,original));
        CREATE TABLE IF NOT EXISTS reserved_output_names(name TEXT PRIMARY KEY COLLATE NOCASE);""")

def allocate(s,jid,items,stitched=False):
    init(s)
    with s.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        r=c.execute("SELECT * FROM request_identities WHERE job_id=?",(jid,)).fetchone()
        if not r:return
        counter=c.execute("SELECT next_number FROM identity_counters WHERE identity_id=?",(r["identity_id"],)).fetchone()
        n=counter[0] if counter else 1
        for item in items:
            if item["media_type"]!="video/mp4":continue
            if c.execute("SELECT 1 FROM output_names WHERE job_id=? AND original=?",(jid,item["name"])).fetchone():continue
            while True:
                name=f'{r["slug"]}{"_Stitched" if stitched else ""}_{n:03d}.mp4';n+=1
                if not c.execute("SELECT 1 FROM reserved_output_names WHERE name=?",(name,)).fetchone():break
            c.execute("INSERT INTO reserved_output_names VALUES(?)",(name,))
            duration=item.get("duration_ms")
            if type(duration) is not int or duration<0:duration=None
            c.execute("INSERT INTO output_names VALUES(?,?,?,0,?)",(jid,item["name"],name,duration))
        c.execute("INSERT INTO identity_counters VALUES(?,?) ON CONFLICT(identity_id) DO UPDATE SET next_number=excluded.next_number",(r["identity_id"],n))

def alias_for(s,jid,name):
    init(s)
    with s.connect() as c:
        row=c.execute("SELECT display FROM output_names WHERE job_id=? AND original=?",(jid,name)).fetchone()
        return row[0] if row else None

def visible(s,jid):
    init(s);outputs=s.output_list(jid)
    if not outputs:return {"outputs":[]}
    with s.connect() as c:
        r=c.execute("SELECT label,identity_id FROM request_identities WHERE job_id=?",(jid,)).fetchone()
        aliases={x["original"]:dict(x) for x in c.execute("SELECT * FROM output_names WHERE job_id=?",(jid,))}
        table=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='gpu_attempts'").fetchone()
        attempt=c.execute("SELECT phase FROM gpu_attempts WHERE job_id=?",(jid,)).fetchone() if table else None
    out=[]
    for item in outputs:
        a=aliases.get(item["name"],{})
        if a.get("deleted"):continue
        out.append({**item,"id":item["name"],"name":a.get("display",item["name"]),"duration_ms":a.get("duration_ms")})
    return {"outputs":out,"identity":r["label"] if r else None,"identity_id":r["identity_id"] if r else None,"editable":bool(attempt and attempt["phase"]=="acknowledged")}

def download(s,jid,name):
    row=next((x for x in visible(s,jid)["outputs"] if x["id"]==name),None)
    if not row:raise HTTPException(404,"Output not found")
    p,raw=s.output_path(jid,name);return p,raw,row["name"]

def change(s,jid,data):
    with s.admission():
        view=visible(s,jid)
        if not view["editable"]:raise HTTPException(409,"Wait for verified worker acknowledgement")
        lookup={x["id"]:x for x in view["outputs"] if x["media_type"]=="video/mp4"}
        ids=list(dict.fromkeys(data.ids))
        if any(i not in lookup for i in ids):raise HTTPException(404,"Clip not found")
        with s.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            for i in ids:
                x=lookup[i]
                c.execute("INSERT OR IGNORE INTO output_names VALUES(?,?,?,0,?)",(jid,i,x["name"],x["duration_ms"]))
            if data.action=="delete":
                c.executemany("UPDATE output_names SET deleted=1 WHERE job_id=? AND original=?",[(jid,i) for i in ids])
            elif data.action=="rename" and len(ids)==1:
                name=data.name or ""
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,123}\.mp4",name):raise HTTPException(422,"Use a safe MP4 filename")
                if name.casefold()!=lookup[ids[0]]["name"].casefold():
                    if c.execute("SELECT 1 FROM reserved_output_names WHERE name=?",(name,)).fetchone() or any(x["name"].casefold()==name.casefold() for x in view["outputs"]):
                        raise HTTPException(409,"Filename already reserved")
                    c.execute("INSERT INTO reserved_output_names VALUES(?)",(name,))
                c.execute("UPDATE output_names SET display=? WHERE job_id=? AND original=?",(name,jid,ids[0]))
            else:raise HTTPException(422,"Invalid output action")
    return {"ok":True}

def make_zip(s,jid,ids):
    view=visible(s,jid);lookup={x["id"]:x for x in view["outputs"]};ids=list(dict.fromkeys(ids))
    if any(i not in lookup for i in ids):raise HTTPException(404,"Output not found")
    total=sum(lookup[i]["size"] for i in ids)
    root=safe_dir(s.root/"output-zips")
    if total>2*1024**3 or shutil.disk_usage(root).free-RESERVE<total+1024**2:raise HTTPException(507,"ZIP exceeds storage budget")
    fd,raw=tempfile.mkstemp(suffix=".zip",dir=root);os.close(fd);p=Path(raw)
    try:
        with zipfile.ZipFile(p,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as z:
            for i in ids:
                path,_,name=download(s,jid,i);z.write(path,name)
        return p
    except Exception:
        p.unlink(missing_ok=True);raise
