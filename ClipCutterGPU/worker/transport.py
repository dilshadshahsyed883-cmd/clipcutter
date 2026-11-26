"""Verified chunk transport with explicitly configured one or two processing slots."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
from threading import RLock, Thread
from .job import Staged
from .web_contract import Analyzer, Extractor
from .extractor.runner import MAX_JSON, MAX_REFERENCE, MAX_VIDEO

CHUNK=8*1024*1024
ACTIVE={"queued","running","cancelling"}
TERMINAL={"completed","failed","cancelled"}
ID=re.compile(r"[a-f0-9]{32}")
SHA=re.compile(r"[a-f0-9]{64}")
NAME=re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
class ApiError(Exception):
    def __init__(self,code,message):
        super().__init__(message);self.code=code

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()

def digest(p,cancel=lambda:False):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            if cancel():raise InterruptedError("Cancelled")
            h.update(b)
    return h.hexdigest()

class Worker:
    def __init__(self,root,ready,launch=None,concurrency=None):
        if concurrency is None:concurrency=int(os.environ.get("CLIPCUTTER_GPU_CONCURRENCY","1"))
        if type(concurrency) is not int or concurrency not in (1,2):raise ValueError("GPU concurrency must be 1 or 2")
        self.concurrency=concurrency
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.ready=ready;self.launch=launch or self._launch
        self.lock=RLock();self.records={};self.threads={};self.stopping=False
        for p in self.root.iterdir():
            if not ID.fullmatch(p.name) or not p.is_dir() or p.is_symlink():continue
            rec=json.loads((p/"state.json").read_text())
            if rec["attempt_id"]!=p.name:raise RuntimeError("Attempt state mismatch")
            self.records[p.name]=rec
            if rec["state"] in ACTIVE:self.change(rec,state="failed",error="Interrupted by worker restart; reconcile with VPS")
    def folder(self,a):
        if not isinstance(a,str) or not ID.fullmatch(a):raise ApiError(400,"Invalid attempt ID")
        return self.root/a
    def get(self,a):
        self.folder(a)
        if a not in self.records:raise ApiError(404,"Attempt not found")
        return self.records[a]
    def change(self,rec,**kw):
        new={**rec,**kw,"updated_at":time.time()}
        p=self.folder(new["attempt_id"])
        with (p/"state.tmp").open("wb") as f:
            f.write(canonical(new));f.flush();os.fsync(f.fileno())
        os.replace(p/"state.tmp",p/"state.json")
        rec.clear();rec.update(new)
    def snapshot(self,a):
        with self.lock:
            rec=self.get(a);out={k:v for k,v in rec.items() if k!="manifest"}
            root=self.folder(a)/"input"
            out["uploaded"]={n:(root/n).stat().st_size if (root/n).is_file() else 0 for n in rec["files"]}
            return json.loads(canonical(out))
    def metrics(self):
        with self.lock:
            return {"active_renders":sum(r["state"] in ACTIVE for r in self.records.values()),"concurrency":self.concurrency,"pipeline_version":1,
                "staging":sum(r["state"]=="staging" for r in self.records.values()),
                "undelivered":sum(r["state"]=="completed" and not r["purged"] for r in self.records.values())}
    def create(self,a,body):
        self.folder(a)
        try:
            if not isinstance(body,dict) or set(body)!={"job","action","files"}:raise ValueError("Expected job, action, files")
            job=Staged.model_validate_json(canonical(body["job"]));action=body["action"];s=job.request.settings
            if not ((isinstance(s,Analyzer) and action=="analyze") or (isinstance(s,Extractor) and
                (action=="export" or (action=="scan" and s.mode=="reference")))):raise ValueError("Action incompatible")
            expected={"source.video":(job.source_sha256,MAX_VIDEO)}
            expected.update({f"reference-{i:02d}.img":(sha,MAX_REFERENCE) for i,sha in enumerate(job.references_sha256,1)})
            if isinstance(s,Extractor) and s.mode=="reference" and action=="export":expected["approved-review.json"]=(None,MAX_JSON)
            files=body["files"]
            if not isinstance(files,dict) or set(files)!=set(expected):raise ValueError("Unexpected staged files")
            for n,(sha,cap) in expected.items():
                x=files[n]
                if not isinstance(x,dict) or set(x)!={"size","sha256"} or type(x["size"]) is not int or not 0<x["size"]<=cap:
                    raise ValueError("Invalid file descriptor")
                if not isinstance(x["sha256"],str) or not SHA.fullmatch(x["sha256"]) or (sha and sha!=x["sha256"]):
                    raise ValueError("Invalid file digest")
            manifest={"job":job.model_dump(mode="json"),"action":action,"files":files}
            fingerprint=hashlib.sha256(canonical(manifest)).hexdigest()
        except (ValueError,TypeError,KeyError) as e:raise ApiError(400,str(e)[:500]) from None
        with self.lock:
            if a in self.records:
                if self.get(a)["fingerprint"]!=fingerprint:raise ApiError(409,"Attempt manifest conflict")
                return self.snapshot(a)
            if self.stopping or not self.ready():raise ApiError(503,"Worker not ready")
            if len(self.records)>=64:raise ApiError(429,"Attempt capacity reached; recycle idle worker")
            reserved=sum(sum(x["size"] for x in rec["files"].values()) for rec in self.records.values() if not rec["purged"])
            size=sum(x["size"] for x in files.values())
            if reserved+size>24*1024**3 or shutil.disk_usage(self.root).free<size+2*1024**3:raise ApiError(507,"Insufficient staging storage")
            p=self.folder(a);p.mkdir(mode=0o700)
            try:
                (p/"input").mkdir(mode=0o700);(p/"input"/"job.json").write_bytes(canonical(manifest["job"]))
                rec={"attempt_id":a,"job_id":job.job_id,"action":action,"state":"staging","files":files,
                    "manifest":manifest,"fingerprint":fingerprint,"purged":False}
                self.change(rec);self.records[a]=rec
            except Exception:shutil.rmtree(p);raise
            return self.snapshot(a)
    def put(self,a,name,offset,data,sha):
        if not 0<len(data)<=CHUNK or hashlib.sha256(data).hexdigest()!=sha:raise ApiError(400,"Invalid chunk SHA256 or size")
        with self.lock:
            rec=self.get(a)
            if rec["state"]!="staging" or self.stopping:raise ApiError(409,"Attempt not accepting uploads")
            if name not in rec["files"]:raise ApiError(404,"Unknown staged file")
            p=self.folder(a)/"input"/name;size=p.stat().st_size if p.exists() else 0
            if offset<0 or offset>size or offset+len(data)>rec["files"][name]["size"]:raise ApiError(409,"Invalid offset or length")
            if offset<size:
                with p.open("rb") as f:f.seek(offset);old=f.read(len(data))
                if old!=data:raise ApiError(409,"Conflicting replay")
                return {"offset":size}
            with p.open("ab") as f:
                try:f.write(data);f.flush();os.fsync(f.fileno())
                except BaseException:f.truncate(size);raise
            return {"offset":size+len(data)}
    def start(self,a):
        with self.lock:
            rec=self.get(a)
            if rec["state"]!="staging":return self.snapshot(a)
            if self.stopping or not self.ready():raise ApiError(503,"Worker not ready")
            if self.metrics()["active_renders"]>=self.concurrency:raise ApiError(429,"GPU slots busy")
            for n,x in rec["files"].items():
                p=self.folder(a)/"input"/n
                if not p.is_file() or p.stat().st_size!=x["size"]:raise ApiError(409,"Incomplete staged input")
            self.change(rec,state="queued",error=None)
            t=Thread(target=self.process,args=(a,),daemon=True);self.threads[a]=t;t.start()
            return self.snapshot(a)
    def cancelled(self,a):
        with self.lock:return self.stopping or self.get(a)["state"]=="cancelling"
    def process(self,a):
        root=self.folder(a)/"input"
        try:
            with self.lock:
                rec=self.get(a)
                if self.cancelled(a):raise InterruptedError("Cancelled")
                self.change(rec,state="running");action=rec["action"];files=rec["files"]
            for n,x in files.items():
                if digest(root/n,lambda:self.cancelled(a))!=x["sha256"]:raise ValueError("Staged digest mismatch: "+n)
            self.launch(a,root,action)
            p=root/{"scan":"scan-result.json","export":"export-result.json","analyze":"analysis-result.json"}[action]
            if not p.is_file() or p.stat().st_size>MAX_JSON:raise RuntimeError("Missing or oversized result manifest")
            result=json.loads(p.read_text())
            if result.get("source_sha256")!=files["source.video"]["sha256"]:raise RuntimeError("Result source mismatch")
            if result.get("state") not in ({"review","no_match"} if action=="scan" else {"completed"}):raise RuntimeError("Invalid result state")
            items=result.get("artifacts",[])
            if action!="scan" and (not isinstance(items,list) or not items):raise RuntimeError("Missing outputs")
            seen=set()
            for x in items:
                n=x["name"]
                if not NAME.fullmatch(n) or n in seen:raise RuntimeError("Unsafe output name")
                seen.add(n);p=root/"outputs"/n
                if p.is_symlink() or not p.is_file() or p.stat().st_size!=x["size"] or digest(p,lambda:self.cancelled(a))!=x["sha256"]:
                    raise RuntimeError("Output verification failed: "+n)
            with self.lock:
                if self.cancelled(a):raise InterruptedError("Cancelled")
                self.change(self.get(a),state="completed",result=result,result_sha256=hashlib.sha256(canonical(result)).hexdigest())
        except Exception as e:
            with self.lock:self.change(self.get(a),state="cancelled" if self.cancelled(a) else "failed",error=str(e)[:1000])
        finally:
            with self.lock:self.threads.pop(a,None)
    def _launch(self,a,root,action):
        proc=subprocess.Popen([sys.executable,"-m","worker.job",action,str(root)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            env=dict(os.environ,CLIPCUTTER_USE_GPU="1"),start_new_session=True)
        error=[];last=[0.]
        def drain():
            while True:
                line=proc.stdout.readline(65536)
                if not line:break
                try:
                    ev=json.loads(line)
                    if not isinstance(ev,dict) or not isinstance(ev.get("stage"),str):continue
                    msg=str(ev.get("message",""))[:1000]
                    if ev["stage"] in {"failed","cancelled"}:error[:]=[msg]
                    if time.monotonic()-last[0]>=1:
                        with self.lock:self.change(self.get(a),progress={"stage":ev["stage"][:80],"message":msg,
                            "done":int(ev.get("done",0)),"total":int(ev.get("total",0))})
                        last[0]=time.monotonic()
                except (ValueError,TypeError,OverflowError):continue
        reader=Thread(target=drain,daemon=True);reader.start();deadline=time.monotonic()+6*3600
        def kill(sig):
            try:os.killpg(proc.pid,sig)
            except ProcessLookupError:pass
        try:
            while proc.poll() is None:
                if self.cancelled(a) or time.monotonic()>deadline:
                    kill(signal.SIGTERM)
                    try:proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:kill(signal.SIGKILL);proc.wait()
                    if self.cancelled(a):raise InterruptedError("Cancelled")
                    raise RuntimeError("Processing time limit reached")
                time.sleep(.2)
            reader.join(timeout=5)
            if proc.returncode:raise RuntimeError(error[-1] if error else f"Worker exit code {proc.returncode}")
        finally:
            kill(signal.SIGKILL)
            if proc.poll() is None:proc.wait()
            reader.join(timeout=5);proc.stdout.close()
    def cancel(self,a):
        with self.lock:
            rec=self.get(a)
            if rec["state"]=="staging":self.change(rec,state="cancelled",error="Cancelled before dispatch")
            elif rec["state"] in {"queued","running"}:self.change(rec,state="cancelling")
            return self.snapshot(a)
    def fetch(self,a,name,offset,length):
        with self.lock:
            rec=self.get(a)
            if rec["state"]!="completed" or rec["purged"]:raise ApiError(409,"Result unavailable")
            item=next((x for x in rec["result"].get("artifacts",[]) if x["name"]==name),None)
            if not item:raise ApiError(404,"Unknown output")
            if offset<0 or not 0<length<=CHUNK or offset+length>item["size"]:raise ApiError(416,"Invalid chunk range")
            with (self.folder(a)/"input"/"outputs"/name).open("rb") as f:f.seek(offset);data=f.read(length)
            if len(data)!=length:raise ApiError(500,"Incomplete result chunk")
            return data
    def purge(self,a,confirmation):
        with self.lock:
            rec=self.get(a)
            if rec["state"] not in TERMINAL:raise ApiError(409,"Attempt not terminal")
            required=rec.get("result_sha256") if rec["state"]=="completed" else "discard-failed"
            if confirmation!=required:raise ApiError(409,"Verified receipt or explicit discard required")
            if not rec["purged"]:
                path=self.folder(a)/"input"
                if path.exists():shutil.rmtree(path)
                self.change(rec,purged=True)
            return self.snapshot(a)
    def shutdown(self):
        with self.lock:self.stopping=True;threads=list(self.threads.values())
        for t in threads:t.join(timeout=15)
