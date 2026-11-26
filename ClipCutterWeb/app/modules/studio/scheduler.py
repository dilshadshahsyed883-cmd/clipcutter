"""Dedicated scheduler source; never auto-launch from ASGI or tests.

Enable only after finalization, operator approval and real runtime acceptance.
One root-configured owner, one approved group, one worker. No implicit deployment.
"""
import fcntl
import os
import time
from concurrent.futures import ThreadPoolExecutor
from .store import Store,safe_dir
from .gpu import GPUStore,group_path
from .dispatch import Dispatcher,WorkerClient,DispatchError
from .lifecycle import Lifecycle,SaladAPI,LifecycleError
from .intake import stage

def authorized(store,cfg=None):
    return (os.environ.get("CLIPCUTTER_SCHEDULER_ENABLED")=="1" and
        os.environ.get("CLIPCUTTER_LIFECYCLE_ENABLED")=="1" and
        os.environ.get("CLIPCUTTER_APPROVED_OWNER","").casefold()==store.owner and
        bool(store.owner) and (cfg is None or (group_path(cfg)==os.environ.get("CLIPCUTTER_APPROVED_SALAD_GROUP") and
        cfg.salad_container_group=="clipcutter-gpu" and cfg.parallel==1 and
        cfg.worker_gateway==os.environ.get("CLIPCUTTER_APPROVED_WORKER_GATEWAY"))))

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
    def command(self,action,cfg):
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
    def __init__(self,store,api,worker,cfg,*,intake_fn=stage):
        self.store=store;self.cfg=cfg;self.api=api;self.worker=worker
        self.dispatch=Dispatcher(store,worker);self.lifecycle=Lifecycle(store,cfg,api,worker)
        self.control=Control(store);self.pool=ThreadPoolExecutor(max_workers=1);self.intake_fn=intake_fn;self.future=None
    def close(self):
        self.pool.shutdown(wait=True)
    def _jobs(self):
        with self.store.connect() as c:
            return [dict(x) for x in c.execute("""SELECT r.id,r.state,r.payload,a.phase FROM requests r
             LEFT JOIN gpu_attempts a ON a.job_id=r.id WHERE r.owner=? ORDER BY r.created_at,r.id""",(self.store.owner,))]
    @staticmethod
    def eligible(row):
        import json
        p=json.loads(row["payload"]);s=p["settings"]
        # Do not pay for jobs whose output contract cannot be fulfilled.
        return (p["input"]["source_kind"]=="video" and not p["input"].get("output_folder")
            and not(s["kind"]=="analyzer" and (s.get("reference_link") or s.get("reference_uploads"))))
    def tick(self):
        with self.store.admission():
            rows=self._jobs()
            if self.future is not None and self.future.done():
                try:self.future.result()
                except Exception:
                    self.control.mark("intake_error")
                self.future=None
            if self.future is None:
                pending=next((x for x in rows if x["state"] in ("awaiting_input","staging")),None)
                if pending:self.future=self.pool.submit(self.intake_fn,self.store,pending["id"])
            # Record unsupported jobs explicitly, retain verified inputs.
            for row in rows:
                if row["state"]=="ready" and not row["phase"] and not self.eligible(row):
                    self.store.transition(row["id"],"ready","failed","GPU: input/output contract not yet supported; staged inputs retained")
            controls=self.control.snapshot();paused=controls["paused"];action=controls["action"]
            state=self.lifecycle.tick(paused=paused,manual=action)
            clear=action if (action=="start" and state in ("ready","ready_dispatch_blocked","worker_busy") or
                             action=="stop" and state=="stopped") else None
            self.control.mark(state,clear)
            rows=self._jobs()
            # Existing attempts take priority, including published-but-unacknowledged.
            # Paused mode blocks new start but never stops running/delivery reconciliation.
            current=next((x for x in rows if x["phase"] in ("create_intent","staging","start_intent","processing","delivering","published","scan_receipt","review")),None)
            if current:
                try:
                    result=self.dispatch.tick(current["id"],allow_start=not paused and action!="stop" and state in ("ready","worker_busy"))
                    self.control.mark(result)
                except DispatchError:self.control.mark("worker_reconcile_required")
                return
            if paused or action=="stop" or state!="ready":return
            if any(x["state"] in ("awaiting_input","staging") for x in rows):return
            next_job=next((x for x in rows if x["state"]=="ready" and x["phase"] in (None,"new") and self.eligible(x)),None)
            if next_job:
                try:self.control.mark(self.dispatch.tick(next_job["id"]))
                except DispatchError:self.control.mark("worker_reconcile_required")

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
                # Restart required for config/credential changes; no silent retargeting.
                if gpu.snapshot()!=(cfg,key,token):
                    scheduler.control.mark("configuration_changed_restart_required");break
                try:scheduler.tick()
                except Exception:
                    scheduler.control.mark("scheduler_error_reconcile")
                time.sleep(3)
        finally:
            scheduler.close();worker.close();api.close()

if __name__=="__main__":main()
