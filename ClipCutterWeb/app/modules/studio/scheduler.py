"""Dedicated scheduler source; never auto-launch from ASGI or tests.

Enable only after finalization, operator approval and real runtime acceptance.
One root-configured owner, one approved group, one worker. No implicit deployment.
"""
from concurrent.futures import ThreadPoolExecutor
import fcntl
import os
import time
from .store import Store,safe_dir
from .gpu import GPUStore,group_path
from .dispatch import Dispatcher,WorkerClient,DispatchError
from .lifecycle import Lifecycle,SaladAPI,LifecycleError
from .eligibility import blocker
from .vps_export import local_row

def authorized(store,cfg=None):
    return (os.environ.get("CLIPCUTTER_SCHEDULER_ENABLED")=="1" and
        os.environ.get("CLIPCUTTER_LIFECYCLE_ENABLED")=="1" and
        os.environ.get("CLIPCUTTER_APPROVED_OWNER","").casefold()==store.owner and
        bool(store.owner) and (cfg is None or (group_path(cfg)==os.environ.get("CLIPCUTTER_APPROVED_SALAD_GROUP") and
        cfg.salad_container_group=="clipcutter-gpu" and cfg.parallel in (1,2) and
        cfg.worker_gateway==os.environ.get("CLIPCUTTER_APPROVED_WORKER_GATEWAY"))))

POLICY_FIELDS={"auto_start","image_pull_threshold","image_pull_seconds",
               "salad_max_reallocations","salad_reallocate_cooldown","parallel"}

def policy_only_change(old,new):
    return old.model_dump(exclude=POLICY_FIELDS)==new.model_dump(exclude=POLICY_FIELDS)

class Control:
    def __init__(self,store):
        self.store=store
        with store.connect() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS scheduler_control (
              id INTEGER PRIMARY KEY CHECK(id=1), paused INTEGER NOT NULL, action TEXT,
              status TEXT NOT NULL, heartbeat REAL NOT NULL)""")
            c.execute("INSERT OR IGNORE INTO scheduler_control VALUES (1,0,NULL,'offline',0)")
    def snapshot(self):
        with self.store.connect() as c:
            row=dict(c.execute("SELECT paused,action,status,heartbeat FROM scheduler_control WHERE id=1").fetchone())
        row["paused"]=bool(row["paused"])
        row["online"]=0<=time.time()-row["heartbeat"]<90
        return row
    def set_paused(self,paused):
        """Owner queue control, independent of paid GPU authorization."""
        with self.store.admission(),self.store.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT action FROM scheduler_control WHERE id=1").fetchone()
            if not paused and row["action"]=="stop":raise LifecycleError("Stop confirmation pending")
            c.execute("UPDATE scheduler_control SET paused=?,action=CASE WHEN ?=1 AND action='start' THEN NULL ELSE action END WHERE id=1",(int(paused),int(paused)))
        return self.snapshot()
    def command(self,action,cfg):
        if action in ("pause","resume"):return self.set_paused(action=="pause")
        if not authorized(self.store,cfg):raise LifecycleError("Scheduler activation gate closed")
        with self.store.admission(),self.store.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT * FROM scheduler_control WHERE id=1").fetchone()
            if not 0<=time.time()-row["heartbeat"]<90:raise LifecycleError("Scheduler offline")
            pending=row["action"]
            if action in ("start","stop"):
                if cfg.auto_start:raise LifecycleError("Select Manual mode first")
                if pending and pending!=action:raise LifecycleError("Wait for pending worker action")
                c.execute("UPDATE scheduler_control SET paused=?,action=? WHERE id=1",(int(action=="stop"),action))
            elif action=="pause":
                c.execute("UPDATE scheduler_control SET paused=1,action=CASE WHEN action='start' THEN NULL ELSE action END WHERE id=1")
            elif action=="resume":
                if pending=="stop":raise LifecycleError("Stop confirmation pending")
                c.execute("UPDATE scheduler_control SET paused=0 WHERE id=1")
            elif action=="retry":
                # Never clear ambiguous mutation/attempt journals. Retry means poll,
                # not authorize duplicate POST or discard data.
                c.execute("UPDATE scheduler_control SET status='recheck_requested' WHERE id=1")
            else:raise LifecycleError("Unknown scheduler command")
        return self.snapshot()
    def mark(self,status,clear=None):
        with self.store.connect() as c:
            c.execute("UPDATE scheduler_control SET status=?,heartbeat=? WHERE id=1",(status,time.time()))
            if clear:c.execute("UPDATE scheduler_control SET action=NULL WHERE id=1 AND action=?",(clear,))

class Scheduler:
    def __init__(self,store,api,worker,cfg):
        self.store=store;self.cfg=cfg;self.api=api;self.worker=worker
        self.dispatch=Dispatcher(store,worker);self.lifecycle=Lifecycle(store,cfg,api,worker)
        self.control=Control(store)
        self.pool=ThreadPoolExecutor(max_workers=4,thread_name_prefix="studio-lane")
        self.flights={};self.cursor=0;self.closing=False
        self.last_error=None;self.last_error_until=0
    def close(self):
        self.closing=True
        self.pool.shutdown(wait=True)
        self.dispatch.close()  # VPS intake is owned by the independent web-process queue.
    def _jobs(self):
        with self.store.connect() as c:
            return [dict(x) for x in c.execute("""SELECT r.id,r.state,r.payload,a.phase,g.action AS command FROM requests r
             LEFT JOIN gpu_attempts a ON a.job_id=r.id LEFT JOIN gpu_commands g ON g.job_id=r.id WHERE r.owner=? ORDER BY r.created_at,r.id""",(self.store.owner,))]
    @staticmethod
    def eligible(row):
        import json
        return blocker(json.loads(row["payload"])) is None
    def _may_start(self,limit):
        ctl=self.control.snapshot()
        rec=self.lifecycle.snapshot()
        return (not self.closing and not ctl["paused"] and ctl["action"]!="stop"
                and self.cfg.parallel==limit and rec.get("status") in ("ready","worker_busy")
                and type(rec.get("concurrency")) is int and rec["concurrency"]>=limit)

    def _launch(self,lane,jid,*,limit,admit=False,observe=False):
        if lane in self.flights or jid in {job for job,_ in self.flights.values()}:return False
        options=dict(allow_start=admit,allow_during_intake=admit,render_limit=limit,observe_only=observe)
        if admit:options["may_start"]=lambda:self._may_start(limit)
        future=self.pool.submit(self.dispatch.tick,jid,**options)
        self.flights[lane]=(jid,future)
        return True

    def _reap(self):
        for lane,(jid,future) in list(self.flights.items()):
            if not future.done():continue
            del self.flights[lane]
            try:future.result()
            except DispatchError as exc:
                self.last_error="worker_reconcile_required: "+str(exc)[:250]
                self.last_error_until=time.monotonic()+10
            except Exception:
                self.last_error="scheduler_error_reconcile"
                self.last_error_until=time.monotonic()+10

    def tick(self):
        self._reap()
        with self.store.admission():
            controls=self.control.snapshot();paused=controls["paused"];action=controls["action"]
            state=self.lifecycle.tick(paused=paused,manual=action)
            clear=action if (action=="start" and state in ("ready","ready_dispatch_blocked","worker_busy") or
                             action=="stop" and state=="stopped") else None
            record=self.lifecycle.snapshot()
            capacity=record.get("concurrency",1)
            pipeline=record.get("pipeline_version")==1
            limit=self.cfg.parallel
            supported=type(capacity) is int and capacity>=limit and (limit==1 or pipeline)
            admit=not paused and action!="stop" and state in ("ready","worker_busy") and supported
            rows=self._jobs()
            local=[x for x in rows if local_row(x)]
            rows=[x for x in rows if not local_row(x)]
            active_phases={"create_intent","staging","start_intent","processing","output_ready","delivering","published","scan_receipt","review"}
            output_phases={"output_ready","delivering","published","scan_receipt","review"}
            upload_phases={"create_intent","staging"}
            observe_phases={"start_intent","processing"}
            active=[x for x in rows if x["phase"] in active_phases]
            counts=record.get("worker_counts",{})
            # Unknown remote work must not be treated as free capacity.
            known={"active_renders":sum(x["phase"] in {"start_intent","processing","staging"} for x in active),
                   "staging":sum(x["phase"] in upload_phases|{"start_intent"} for x in active),
                   "undelivered":sum(x["phase"] in observe_phases|output_phases for x in active)}
            matched=all(type(counts.get(k)) is int and 0<=counts[k]<=known[k] for k in known)
            occupied={jid for jid,_ in self.flights.values()}
            available=lambda x:x["id"] not in occupied
            def launch(lane,row,**kw):
                if row and self._launch(lane,row["id"],limit=limit,**kw):
                    occupied.add(row["id"])
            # Independent CPU lane; never occupies GPU render slots.
            cpu=next((x for x in local if available(x) and
                (x["command"] or x["phase"] in ("vps_processing","vps_delivering") or
                 (not paused and action!="stop" and x["state"]=="ready" and self.eligible(x)))),None)
            if cpu and "vps" not in self.flights:
                self.flights["vps"]=(cpu["id"],self.pool.submit(self.dispatch.tick,cpu["id"],
                    allow_start=not paused and action!="stop",allow_during_intake=True))
                occupied.add(cpu["id"])
            # One download lane, one polling/control lane, one upload/start lane.
            # A legacy worker remains serial; existing jobs still reconcile while paused.
            if pipeline or not self.flights:
                delivery=next((x for x in active if x["phase"] in output_phases and available(x)),None)
                launch("delivery",delivery)
            if pipeline or not self.flights:
                observe=[x for x in rows if available(x) and (x["command"] or x["phase"] in observe_phases|{"failed","cancelled"})]
                if observe:
                    commands=[x for x in observe if x["command"]]
                    candidates=commands or observe
                    item=candidates[self.cursor%len(candidates)]
                    self.cursor+=1
                    launch("observe",item,observe=True)
            if pipeline or not self.flights:
                uploading=next((x for x in active if x["phase"] in upload_phases and not x["command"]),None)
                if uploading:
                    if available(uploading):launch("upload",uploading,admit=admit and matched)
                elif admit and matched and (pipeline or not active) and not any(x["phase"] in upload_phases for x in active):
                    # Max one preloaded job beyond render slots; bound output backlog.
                    outstanding=sum(x["phase"] in observe_phases|upload_phases for x in active)
                    backlog=sum(x["phase"] in output_phases for x in active)
                    if outstanding<limit+int(pipeline) and backlog<2:
                        candidate=next((x for x in rows if available(x) and not x["command"] and x["state"]=="ready"
                                        and x["phase"] in (None,"new") and self.eligible(x)),None)
                        launch("upload",candidate,admit=True)
            status=("worker_capacity_mismatch" if state in ("ready","worker_busy") and not supported else
                    "worker_unknown_remote_work" if admit and not matched else state)
            if self.last_error and time.monotonic()<self.last_error_until:status=self.last_error
            elif self.flights:status="pipeline_active" if pipeline else "dispatch_active"
            self.control.mark(status,clear)
            for row in rows:
                if row["state"]!="ready" or row["phase"] not in (None,"new") or row["id"] in occupied:continue
                import json
                reason=blocker(json.loads(row["payload"]))
                message=("Verified inputs held: "+reason if reason else
                         "Waiting for GPU: "+("queue_paused" if paused else status))
                with self.store.connect() as c:
                    c.execute("UPDATE requests SET message=?,updated_at=? WHERE id=? AND owner=? AND state='ready' AND message!=?",
                              (message,int(time.time()),row["id"],self.store.owner,message))
            return "pipeline_active" if self.flights else None

def main():
    owner=os.environ.get("CLIPCUTTER_APPROVED_OWNER","")
    if not owner or not os.environ.get("CLIPCUTTER_WEB_DATA_ROOT"):raise SystemExit("Approved owner and storage required")
    store=Store(owner);gpu=GPUStore(store);cfg,key,token=gpu.snapshot()
    if not authorized(store,cfg):raise SystemExit("Scheduler activation gate closed")
    lockdir=safe_dir(store.root/"orchestration-locks")
    with os.fdopen(os.open(lockdir/"scheduler.lock",os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600),"a") as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit("Scheduler already running")
        api=SaladAPI(cfg,key)
        worker=WorkerClient(cfg.worker_gateway,token,key,os.environ.get("CLIPCUTTER_APPROVED_WORKER_SHA",""))
        scheduler=Scheduler(store,api,worker,cfg)
        try:
            while True:
                # Reload only automation policy, never credentials or destination.
                updated,new_key,new_token=gpu.snapshot()
                if (updated,new_key,new_token)!=(cfg,key,token):
                    if (new_key,new_token)!=(key,token) or not policy_only_change(cfg,updated) or not authorized(store,updated):
                        scheduler.control.mark("configuration_changed_restart_required");break
                    # Complete pending manual start/stop under its original mode.
                    if not scheduler.control.snapshot()["action"]:
                        cfg=updated
                        scheduler.cfg=cfg
                        scheduler.lifecycle.cfg=cfg
                        scheduler.lifecycle.idle_since=None
                result=None
                try:result=scheduler.tick()
                except Exception:
                    scheduler.control.mark("scheduler_error_reconcile")
                # Release admission lock and recheck pause/config between acknowledged chunks.
                time.sleep(0.2 if result=="pipeline_active" else 3)
        finally:
            with store.connect() as c:
                c.execute("UPDATE scheduler_control SET heartbeat=0 WHERE id=1")
            scheduler.close();worker.close();api.close()

if __name__=="__main__":main()
