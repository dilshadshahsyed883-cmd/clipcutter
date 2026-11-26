"""Internal, owner-scoped Web/GPU protocol adapter. No Salad mutations or browser callbacks.

Call tick from a single trusted scheduler after deployment/worker approval.
Never recreate a lost attempt automatically; the VPS keeps verified inputs.
"""
import fcntl
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time
from urllib.parse import urlsplit
from uuid import uuid4
import httpx
from .store import safe_dir
from .intake import verify_format, RESERVE
from .eligibility import blocker
from .drive_delivery import DeliveryError, deliver_one, preflight

CHUNK=8*1024*1024
MAX_JSON=8*1024*1024
SHA=re.compile(r"[a-f0-9]{64}")
ID=re.compile(r"[a-f0-9]{32}")
NAME=re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
MEDIA={"video/mp4","application/json","text/csv"}
class DispatchError(RuntimeError):pass
class RemoteError(DispatchError):
    def __init__(self,code):
        self.code=code;super().__init__(f"Worker HTTP {code}; reconcile recorded attempt")

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def sha_file(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

class WorkerClient:
    """Only the root-approved HTTPS Salad origin; no redirects or ambient proxy."""
    def __init__(self,gateway,worker_key,salad_key,expected_sha,*,approved_gateway=None,transport=None):
        approved_gateway=approved_gateway or os.environ.get("CLIPCUTTER_APPROVED_WORKER_GATEWAY","")
        u=urlsplit(gateway)
        if (gateway!=approved_gateway or u.scheme!="https" or not u.hostname or
            not u.hostname.endswith(".salad.cloud") or u.username is not None or u.password is not None or
            u.port not in (None,443) or u.path not in ("","/") or u.query or u.fragment):
            raise DispatchError("Worker gateway must match approved HTTPS Salad origin")
        if not re.fullmatch(r"[a-f0-9]{40}",expected_sha) or len(worker_key)<32 or not salad_key:
            raise DispatchError("Worker SHA and independent credentials required")
        self.origin=gateway.rstrip("/");self.expected_sha=expected_sha
        self.client=httpx.Client(base_url=self.origin,timeout=httpx.Timeout(45,connect=5),
            follow_redirects=False,trust_env=False,transport=transport,
            headers={"Authorization":"Bearer "+worker_key,"Salad-Api-Key":salad_key,"Cache-Control":"no-cache"})
    def close(self):self.client.close()
    def request(self,method,path,body=None,*,chunk=None,limit=MAX_JSON,binary=False):
        headers={}
        if chunk is not None:headers={"X-Chunk-SHA256":hashlib.sha256(chunk).hexdigest(),"Content-Type":"application/octet-stream"}
        try:
            with self.client.stream(method,path,json=body,content=chunk,headers=headers) as res:
                if res.status_code!=200:raise RemoteError(res.status_code)
                data=bytearray()
                for part in res.iter_bytes():
                    data.extend(part)
                    if len(data)>limit:raise DispatchError("Worker response exceeds limit")
                if binary:
                    if hashlib.sha256(data).hexdigest()!=res.headers.get("X-Chunk-SHA256"):raise DispatchError("Worker chunk digest mismatch")
                    return bytes(data)
                value=json.loads(data)
                if not isinstance(value,dict):raise DispatchError("Invalid worker response")
                return value
        except (httpx.HTTPError,ValueError,TypeError) as exc:
            raise DispatchError("Worker transfer interrupted or invalid response; retain attempt") from None
    def capabilities(self):
        x=self.request("GET","/api/capabilities")
        if (x.get("source_sha")!=self.expected_sha or x.get("contract_version")!=2 or
            x.get("transport")!="verified-chunks-v1" or x.get("chunk_bytes")!=CHUNK or
            x.get("ready") is not True or x.get("dispatch_enabled") is not True or (type(x.get("concurrency")) is not int or x["concurrency"] not in (1,2))):
            raise DispatchError("Approved worker version not ready")
        return x
    def create(self,a,m):return self.request("POST","/api/jobs/"+a,m)
    def status(self,a):return self.request("GET","/api/jobs/"+a)
    def put(self,a,n,offset,data):return self.request("PUT",f"/api/jobs/{a}/input/{n}?offset={offset}",chunk=data)
    def start(self,a):return self.request("POST",f"/api/jobs/{a}/start")
    def cancel(self,a):return self.request("POST",f"/api/jobs/{a}/cancel")
    def fetch(self,a,n,offset,length):
        return self.request("GET",f"/api/jobs/{a}/output/{n}?offset={offset}&length={length}",limit=length,binary=True)
    def purge(self,a,confirmation):return self.request("POST",f"/api/jobs/{a}/purge",{"confirmation":confirmation})

class Dispatcher:
    def __init__(self,store,client):
        self.store=store;self.client=client
        self.delivery_pool=None;self.delivery_future=None;self.delivery_job=None
        with store.connect() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS gpu_attempts(
              job_id TEXT PRIMARY KEY REFERENCES requests(id), attempt_id TEXT UNIQUE NOT NULL,
              manifest TEXT NOT NULL, mapping TEXT NOT NULL, phase TEXT NOT NULL,
              worker_sha TEXT NOT NULL, gateway TEXT NOT NULL, result_sha TEXT,
              review_json TEXT)""")
    def close(self):
        if self.delivery_pool:self.delivery_pool.shutdown(wait=True)

    def drive_delivery_tick(self,jid,folder,dest,items):
        # Large network writes cannot hold the owner admission lock or block queue
        # controls. The durable intent is committed by the one delivery thread.
        if self.delivery_future is not None:
            if self.delivery_job!=jid:raise DeliveryError("Another Drive receipt is pending")
            if not self.delivery_future.done():return False
            future=self.delivery_future
            self.delivery_future=None;self.delivery_job=None
            return future.result()
        if self.delivery_pool is None:self.delivery_pool=ThreadPoolExecutor(max_workers=1)
        self.delivery_job=jid
        self.delivery_future=self.delivery_pool.submit(deliver_one,self.store,jid,folder,dest,items)
        return False

    def _row(self,jid):
        with self.store.connect() as c:
            self.store.row(c,jid)
            r=c.execute("SELECT * FROM gpu_attempts WHERE job_id=?",(jid,)).fetchone()
            return dict(r) if r else None
    def _phase(self,jid,phase,result_sha=None,review=None):
        with self.store.connect() as c:
            c.execute("BEGIN IMMEDIATE");self.store.row(c,jid)
            c.execute("UPDATE gpu_attempts SET phase=?,result_sha=COALESCE(?,result_sha),review_json=COALESCE(?,review_json) WHERE job_id=?",
                      (phase,result_sha,canonical(review).decode() if review is not None else None,jid))
    def command(self,jid):
        with self.store.connect() as c:
            row=c.execute("SELECT action FROM gpu_commands WHERE job_id=?",(jid,)).fetchone()
            return row["action"] if row else None
    def clear_command(self,jid,action):
        with self.store.connect() as c:
            c.execute("DELETE FROM gpu_commands WHERE job_id=? AND action=?",(jid,action))
    def clean_terminal(self,jid,row,m,remote):
        state=remote.get("state")
        if state not in ("failed","cancelled"):raise DispatchError("Terminal cleanup requires confirmed failure/cancellation")
        # Keep verified VPS sources and any local partial outputs; only discard
        # worker scratch for a confirmed terminal attempt with a durable ledger.
        ack=self.client.purge(row["attempt_id"],"discard-failed")
        self._validate(ack,row,m)
        if ack.get("state")!=state or ack.get("purged") is not True:
            raise DispatchError("Terminal attempt cleanup unconfirmed")
        with self.store.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            self.store.row(c,jid)
            c.execute("INSERT OR IGNORE INTO gpu_attempt_history VALUES (?,?,?,?)",(row["attempt_id"],jid,state,int(time.time())))
            c.execute("UPDATE gpu_attempts SET phase=? WHERE job_id=? AND attempt_id=?",(state+"_clean",jid,row["attempt_id"]))
            c.execute("DELETE FROM gpu_commands WHERE job_id=? AND action='cancel'",(jid,))
        return state+"_clean"

    def retry_failed(self,jid,row,m):
        a=row["attempt_id"]
        if row["phase"]!="failed_clean":raise DispatchError("Retry requires confirmed failed attempt cleanup")
        # Never overwrite partial delivery or published output.
        for folder in ("outputs","delivery-parts"):
            p=self.store.root/folder/jid
            if p.exists() and any(p.iterdir()):raise DispatchError("Existing output requires manual reconciliation")
        root=safe_dir(self.store.root/"inputs"/jid);mapping=json.loads(row["mapping"])
        for name,item in m["files"].items():
            filename=mapping[name]
            if not NAME.fullmatch(filename):raise DispatchError("Unsafe staged input")
            p=root/filename
            if p.resolve()!=p or not p.is_file() or p.stat().st_size!=item["size"] or sha_file(p)!=item["sha256"]:
                raise DispatchError("Verified inputs changed; retry held")
        with self.store.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            current=self.store.row(c,jid)
            if current["state"]!="failed":raise DispatchError("Retry state changed")
            c.execute("INSERT OR IGNORE INTO gpu_attempt_history VALUES (?,?,?,?)",(a,jid,"failed",int(time.time())))
            changed=c.execute("UPDATE gpu_attempts SET attempt_id=?,phase='new',result_sha=NULL,worker_sha=?,gateway=? WHERE job_id=? AND attempt_id=? AND phase='failed_clean'",(uuid4().hex,self.client.expected_sha,self.client.origin,jid,a)).rowcount
            if changed!=1:raise DispatchError("Retry attempt changed")
            c.execute("UPDATE requests SET state='ready',progress=100,message='Verified inputs retained; GPU retry queued',updated_at=? WHERE id=? AND owner=?",(int(time.time()),jid,self.store.owner))
            c.execute("DELETE FROM gpu_commands WHERE job_id=? AND action='retry'",(jid,))
        return "retry_queued"

    def _pending(self,c):
        return c.execute("SELECT count(*) FROM requests WHERE owner=? AND state IN ('awaiting_input','staging')",(self.store.owner,)).fetchone()[0]
    def prepare(self,jid,*,allow_during_intake=False):
        """Single-video only. Explicitly reject unsupported ZIP/folder fan-out and analyzer profile matching."""
        with self.store.connect() as c:
            row=self.store.row(c,jid);request=json.loads(row["payload"]);request["request_id"]=row["request_id"]
            if row["state"]!="ready":raise DispatchError("Drive inputs not ready")
            if not allow_during_intake and self._pending(c):raise DispatchError("All pending Drive intake must finish before dispatch")
        reason=blocker(request)
        if reason:raise DispatchError(reason)
        if request["input"].get("output_folder"):
            try:preflight(request["input"]["output_folder"])
            except DeliveryError as exc:raise DispatchError(str(exc)) from None
        settings=request["settings"]
        if settings["kind"]=="analyzer" and (settings.get("reference_link") or settings.get("reference_uploads")):raise DispatchError("Analyzer profile reference input is not implemented")
        root=safe_dir(self.store.root/"inputs"/jid)
        data=json.loads((root/"manifest.json").read_text())
        if data.get("version")!=1 or not isinstance(data.get("files"),list):raise DispatchError("Invalid intake manifest")
        source=[x for x in data["files"] if x.get("role")=="source"]
        refs=[x for x in data["files"] if x.get("role")=="reference"]
        if len(source)!=1 or len(refs)>12 or len(source)+len(refs)!=len(data["files"]):raise DispatchError("Unsupported staged file count")
        if bool((settings.get("reference_link") or settings.get("reference_uploads")))!=bool(refs):raise DispatchError("Reference staging mismatch")
        if settings.get("reference_uploads") and settings["reference_uploads"]!=[x["sha256"] for x in refs]:raise DispatchError("Uploaded reference digest mismatch")
        if not settings.get("reference_uploads"):settings.pop("reference_uploads",None)
        mapping={};files={}
        for name,item in [("source.video",source[0])]+[(f"reference-{i:02d}.img",x) for i,x in enumerate(refs,1)]:
            filename=item["file"]
            if not isinstance(filename,str) or not NAME.fullmatch(filename):raise DispatchError("Unsafe staged filename")
            path=root/filename
            if (path.resolve()!=path or not path.is_file() or type(item["size"]) is not int or
                path.stat().st_size!=item["size"] or not SHA.fullmatch(item["sha256"]) or sha_file(path)!=item["sha256"]):
                raise DispatchError("Verified input changed; retain staged data")
            mapping[name]=filename;files[name]={"size":item["size"],"sha256":item["sha256"]}
        action="analyze" if settings["kind"]=="analyzer" else "scan" if settings["mode"]=="reference" else "export"
        m={"action":action,"job":{"version":1,"job_id":jid,"request":request,
            "source_sha256":files["source.video"]["sha256"],"references_sha256":[x["sha256"] for x in refs]},"files":files}
        with self.store.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            if self.store.row(c,jid)["state"]!="ready" or (not allow_during_intake and self._pending(c)):raise DispatchError("Intake/queue state changed")
            if c.execute("SELECT 1 FROM gpu_attempts WHERE job_id=?",(jid,)).fetchone():return
            c.execute("INSERT INTO gpu_attempts VALUES (?,?,?,?,?,?,?,NULL,NULL)",
                      (jid,uuid4().hex,canonical(m).decode(),canonical(mapping).decode(),"new",self.client.expected_sha,self.client.origin))
    def tick(self,jid,*,allow_start=True,allow_during_intake=False,render_limit=1,observe_only=False,may_start=None):
        if not ID.fullmatch(jid):raise DispatchError("Invalid job id")
        locks=safe_dir(self.store.root/"dispatch-locks")
        # One operation per durable job; scheduler owns cross-job lane admission.
        with os.fdopen(os.open(locks/(jid+".lock"),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600),"a") as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return "busy"
            row=self._row(jid)
            if not row:
                if not allow_start or observe_only or (may_start and not may_start()):return "paused"
                self.client.capabilities();self.prepare(jid,allow_during_intake=allow_during_intake);row=self._row(jid)
            command=self.command(jid)
            a=row["attempt_id"];m=json.loads(row["manifest"])
            if row["phase"]=="failed_clean" and command=="retry":
                return self.retry_failed(jid,row,m)
            if (row["gateway"],row["worker_sha"])!=(self.client.origin,self.client.expected_sha):
                raise DispatchError("Worker configuration changed; reconcile recorded attempt")
            if row["phase"]=="new" and command=="cancel":
                with self.store.connect() as c:
                    c.execute("BEGIN IMMEDIATE")
                    if self.store.row(c,jid)["state"]!="ready":raise DispatchError("Local cancellation state changed")
                    c.execute("UPDATE requests SET state='cancelled',message='Cancelled before GPU dispatch; inputs retained',updated_at=? WHERE id=? AND owner=?",(int(time.time()),jid,self.store.owner))
                    c.execute("UPDATE gpu_attempts SET phase='cancelled_clean' WHERE job_id=? AND attempt_id=?",(jid,a))
                    c.execute("DELETE FROM gpu_commands WHERE job_id=? AND action='cancel'",(jid,))
                return "cancelled_clean"
            if row["phase"] in ("review_ready","acknowledged","failed_clean","cancelled_clean") and not command:return row["phase"]
            caps=self.client.capabilities()
            if row["phase"] in ("failed","cancelled"):
                remote=self.client.status(a);self._validate(remote,row,m)
                if remote.get("state")!=row["phase"]:raise DispatchError("Terminal attempt status changed")
                return self.clean_terminal(jid,row,m,remote)
            if row["phase"]=="new":
                if not allow_start or observe_only or (may_start and not may_start()):return "paused"
                if render_limit>1 and (caps.get("pipeline_version")!=1 or caps.get("concurrency")!=2):raise DispatchError("Worker capacity mismatch")
                if m["job"]["request"]["input"]["source_kind"]=="youtube" and "youtube" not in caps.get("source_kinds",[]):
                    raise DispatchError("Approved worker does not advertise YouTube support")
                with self.store.connect() as c:
                    if not allow_during_intake and self._pending(c):return "intake_pending"
                # Persist intent before any remote side effect. If the remote is missing
                # after ambiguity, do not silently recreate; require reconciliation.
                with self.store.admission() if may_start else nullcontext():
                    if may_start and not may_start():return "paused"
                    if self.command(jid)=="cancel":return "cancel_pending"
                    self._phase(jid,"create_intent")
                    remote=self.client.create(a,m)
            else:remote=self.client.status(a)
            self._validate(remote,row,m)
            state=remote["state"];local=self.store.get(jid)["state"]
            if command=="cancel" and state in ("staging","queued","running"):
                remote=self.client.cancel(a);self._validate(remote,row,m)
                state=remote["state"]
            if command=="cancel" and state=="completed":
                self.clear_command(jid,"cancel") # completion wins; preserve output
            if state=="staging":
                if row["phase"] in ("processing","output_ready","delivering","published"):
                    raise DispatchError("Remote reverted to staging; reconcile")
                # Same immutable attempt, verified staging state: replaying start
                # is safe because the worker starts each attempt only once.
                self._phase(jid,"staging")
                offsets=remote.get("uploaded")
                if not isinstance(offsets,dict):raise DispatchError("Invalid remote offsets")
                total=sum(item["size"] for item in m["files"].values())
                for name,item in m["files"].items():
                    offset=offsets.get(name)
                    if type(offset) is not int or not 0<=offset<=item["size"]:raise DispatchError("Invalid remote offset")
                acknowledged=sum(offsets[name] for name in m["files"])
                self.store.gpu_upload_progress(jid,acknowledged,total)
                if not allow_start or observe_only or (may_start and not may_start()):return "paused"
                if render_limit>1 and (caps.get("pipeline_version")!=1 or caps.get("concurrency")!=2):raise DispatchError("Worker capacity mismatch")
                with self.store.connect() as c:
                    if not allow_during_intake and self._pending(c):return "intake_pending"
                root=safe_dir(self.store.root/"inputs"/jid);mapping=json.loads(row["mapping"])
                for name,item in m["files"].items():
                    offset=offsets[name]
                    if offset<item["size"]:
                        path=root/mapping[name]
                        if path.resolve()!=path or not path.is_file() or path.stat().st_size!=item["size"]:raise DispatchError("Staged input changed")
                        with path.open("rb") as f:f.seek(offset);chunk=f.read(min(CHUNK,item["size"]-offset))
                        if not chunk:raise DispatchError("Staged input truncated")
                        result=self.client.put(a,name,offset,chunk)
                        if type(result.get("offset")) is not int or result["offset"]!=offset+len(chunk):raise DispatchError("Unexpected upload acknowledgement")
                        self.store.gpu_upload_progress(jid,acknowledged+len(chunk),total)
                        return "staging"
                active=caps.get("active_renders")
                if type(active) is not int or not 0<=active<min(render_limit,caps.get("concurrency",1)):
                    return "preloaded"
                if may_start and not may_start():return "paused"
                with self.store.connect() as c:
                    if not allow_during_intake and self._pending(c):return "intake_pending"
                with self.store.admission() if may_start else nullcontext():
                    if may_start and not may_start():return "paused"
                    if self.command(jid)=="cancel":return "cancel_pending"
                    self._phase(jid,"start_intent")
                    remote=self.client.start(a)
                self._validate(remote,row,m)
                state=remote["state"]
            if state in ("queued","running","cancelling"):
                if local=="ready":self.store.transition(jid,"ready","processing","GPU accepted verified inputs",0)
                self._phase(jid,"processing")
                progress=remote.get("progress")
                if isinstance(progress,dict):
                    done,total=progress.get("done"),progress.get("total")
                    if type(done) is int and type(total) is int and 0<=done<=total and total>0:
                        label=str(progress.get("stage") or "processing")[:80]
                        message=str(progress.get("message") or "")[:350]
                        self.store.gpu_stage_progress(jid,"processing",100*done//total,
                            "GPU "+label+(": "+message if message else ""))
                return state
            if state in ("failed","cancelled"):
                if local in ("ready","processing","delivering"):
                    target="cancelled" if state=="cancelled" and local!="delivering" else "failed"
                    self.store.transition(jid,local,target,"GPU: "+str(remote.get("error") or state)[:500])
                self._phase(jid,state)
                return self.clean_terminal(jid,row,m,remote)
            if state=="completed":
                if observe_only:
                    self._phase(jid,"output_ready");return "output_ready"
                return self.receive(jid,row,m,remote)
            raise DispatchError("Unknown worker state")
    def _validate(self,remote,row,m):
        if (remote.get("attempt_id")!=row["attempt_id"] or remote.get("job_id")!=row["job_id"] or
            remote.get("action")!=m["action"] or remote.get("files")!=m["files"]):
            raise DispatchError("Worker attempt identity mismatch")
    def receive(self,jid,row,m,remote):
        result=remote.get("result");digest=remote.get("result_sha256")
        if (not isinstance(result,dict) or hashlib.sha256(canonical(result)).hexdigest()!=digest or
            result.get("source_sha256")!=m["job"]["source_sha256"]):raise DispatchError("Invalid result manifest")
        local=self.store.get(jid)["state"]
        if m["action"]=="scan":
            from .review import record_scan,confirm_scan
            record_scan(self.store,jid,row,m,result,digest)
            # The full scan result is durable on VPS before remote deletion.
            # Repeat acknowledgement safely if its response was lost.
            ack=self.client.purge(row["attempt_id"],digest)
            if not isinstance(ack,dict) or ack.get("attempt_id")!=row["attempt_id"] or ack.get("purged") is not True:
                raise DispatchError("Scan acknowledgement unconfirmed")
            confirm_scan(self.store,jid,row["attempt_id"],digest)
            return "review_ready"
        if result.get("state")!="completed":raise DispatchError("Unexpected output state")
        items=result.get("artifacts")
        if not isinstance(items,list) or not 1<=len(items)<=1000:raise DispatchError("Invalid artifact list")
        names=set()
        for item in items:
            if not isinstance(item,dict):raise DispatchError("Invalid artifact")
            n=item.get("name");size=item.get("size");sha=item.get("sha256");media=item.get("media_type")
            if (not isinstance(n,str) or not NAME.fullmatch(n) or n in names or type(size) is not int or
                not 0<size<=20*1024**3 or not isinstance(sha,str) or not SHA.fullmatch(sha) or media not in MEDIA):
                raise DispatchError("Invalid artifact descriptor")
            names.add(n)
        if local=="ready":self.store.transition(jid,"ready","processing","GPU completed",100);local="processing"
        if local=="processing":self.store.transition(jid,"processing","delivering","Receiving verified GPU outputs",0);local="delivering"
        if local=="completed":
            # Reconcile crash after local commit, before remote acknowledgement.
            expected=[{k:x[k] for k in ("name","size","sha256","media_type")} for x in items]
            if sorted(self.store.output_list(jid),key=lambda x:x["name"])!=sorted(expected,key=lambda x:x["name"]):
                raise DispatchError("Published output mismatch")
            for x in expected:
                p,_=self.store.output_path(jid,x["name"])
                if sha_file(p)!=x["sha256"]:raise DispatchError("Published output changed")
            self.client.purge(row["attempt_id"],digest);self._phase(jid,"acknowledged",digest);return "acknowledged"
        if local!="delivering":raise DispatchError("Unexpected local delivery state")
        self._phase(jid,"delivering",digest)
        dest=safe_dir(safe_dir(self.store.root/"outputs")/jid)
        scratch=safe_dir(safe_dir(self.store.root/"delivery-parts")/jid)
        total=sum(item["size"] for item in items)
        received=0
        for item in items:
            n=item["name"];p=dest/n;part=scratch/n
            if p.exists():
                if p.resolve()!=p or not p.is_file() or p.stat().st_size!=item["size"] or sha_file(p)!=item["sha256"]:raise DispatchError("Existing result mismatch")
                received+=item["size"]
                continue
            offset=part.stat().st_size if part.exists() else 0
            if offset>item["size"] or part.is_symlink():raise DispatchError("Unsafe delivery partial")
            if offset<item["size"]:
                length=min(CHUNK,item["size"]-offset)
                if shutil.disk_usage(scratch).free-RESERVE<length:raise DispatchError("Insufficient VPS storage reserve")
                chunk=self.client.fetch(row["attempt_id"],n,offset,length)
                if len(chunk)!=length:raise DispatchError("Incomplete output chunk")
                with part.open("ab") as f:f.write(chunk);f.flush();os.fsync(f.fileno())
                self.store.gpu_stage_progress(jid,"delivering",100*(received+offset+length)//total,
                    f"GPU downloading: {received+offset+length:,} / {total:,} bytes received")
                return "delivering"
            if sha_file(part)!=item["sha256"]:raise DispatchError("Complete output digest mismatch; retain partial")
            if item["media_type"]=="video/mp4":verify_format(part,"video",".mp4")
            elif item["media_type"]=="application/json":
                if item["size"]>MAX_JSON:raise DispatchError("JSON output too large")
                json.loads(part.read_bytes())
            part.rename(p);received+=item["size"]
        from .output_names import allocate
        allocate(self.store,jid,items,m["job"]["request"]["settings"].get("stitched",False))
        folder=m["job"]["request"]["input"].get("output_folder")
        if folder:
            try:
                # Upload at most one artifact per tick. An ambiguous write is
                # reconciled by metadata only; never repeat an uncertain POST.
                if not self.drive_delivery_tick(jid,folder,dest,items):return "delivering_drive"
            except DeliveryError as exc:
                with self.store.connect() as c:
                    c.execute("UPDATE requests SET message=?,updated_at=? WHERE id=? AND owner=? AND state='delivering'",("Drive delivery held: "+str(exc)[:300],int(time.time()),jid,self.store.owner))
                raise DispatchError(str(exc)) from None
        self.store.publish_verified_outputs(jid,items)
        self._phase(jid,"published",digest)
        # A separate tick acknowledges only after persisted receipt.
        return "published"
