"""ClipCutter-only lifecycle controller, adapted from Concat's journaled rules.

Internal tick API, not started by the web process. No paid operations without a
root-approved deployment, exact dedicated group and immutable image digest.
"""
from datetime import datetime
import fcntl
import json
import os
import re
import time
from uuid import UUID
import httpx
from .gpu import SALAD_API, _salad_get, group_path, image_pull_percent
from .store import safe_dir

class LifecycleError(RuntimeError):pass

class SaladAPI:
    def __init__(self,cfg,key,*,transport=None):
        self.path=group_path(cfg)
        self.approved=os.environ.get("CLIPCUTTER_APPROVED_SALAD_GROUP","")
        self.image=os.environ.get("CLIPCUTTER_APPROVED_GPU_IMAGE","")
        if (os.environ.get("CLIPCUTTER_LIFECYCLE_ENABLED")!="1" or not key or
            not self.path or self.path!=self.approved or cfg.salad_container_group!="clipcutter-gpu" or
            not re.fullmatch(r"ghcr\.io/dilshadshahsyed883-cmd/clipcutter-gpu-private-test@sha256:[a-f0-9]{64}",self.image)):
            raise LifecycleError("Live lifecycle is not authorized")
        self.key=key
        self.client=httpx.Client(timeout=httpx.Timeout(8,connect=3),follow_redirects=False,trust_env=False,transport=transport)
    def close(self):self.client.close()
    def group(self):return _salad_get(self.client,self.path,self.key)
    def instances(self):return _salad_get(self.client,self.path+"/instances",self.key)["instances"]
    def instance(self,i):return _salad_get(self.client,self.path+"/instances/"+str(UUID(i)),self.key)
    def mutate(self,action,i=None):
        if action not in ("start","stop","reallocate"):raise LifecycleError("Invalid action")
        suffix="/instances/"+str(UUID(i))+"/reallocate" if action=="reallocate" else "/"+action
        res=self.client.post(SALAD_API+self.path+suffix,headers={"Salad-Api-Key":self.key,"Cache-Control":"no-cache"})
        if res.status_code not in (200,202,204):raise LifecycleError("Mutation unconfirmed; reconcile before retry")

def timestamp(s,now):
    d=datetime.fromisoformat(s.replace("Z","+00:00"))
    if d.tzinfo is None or not 0<d.timestamp()<=now:raise ValueError("Invalid instance timestamp")
    return d.timestamp()

def identity(i):
    version=i.get("version")
    if version is None:raise ValueError("Missing instance version")
    return "/".join((str(UUID(i["id"])),str(UUID(i["machine_id"])),str(version)))

def zero_metrics(caps):
    return all(type(caps.get(k)) is int and caps[k]==0 for k in ("active_renders","staging","undelivered"))

class Lifecycle:
    """All tick callers must use the same owner store. One cross-process lock.
    Journal is saved before every POST; ambiguous results never repeat.
    """
    def __init__(self,store,cfg,api,worker,clock=time.time):
        self.store=store;self.cfg=cfg;self.api=api;self.worker=worker;self.clock=clock
        self.idle_since=None
        with store.connect() as c:
            c.execute("CREATE TABLE IF NOT EXISTS gpu_lifecycle (id INTEGER PRIMARY KEY CHECK(id=1), record TEXT NOT NULL)")
            c.execute("INSERT OR IGNORE INTO gpu_lifecycle VALUES(1,'{}')")
    def _record(self):
        with self.store.connect() as c:return json.loads(c.execute("SELECT record FROM gpu_lifecycle WHERE id=1").fetchone()[0])
    def _save(self,r,state):
        r["status"]=state
        with self.store.connect() as c:c.execute("UPDATE gpu_lifecycle SET record=? WHERE id=1",(json.dumps(r),))
        return state
    def snapshot(self):return self._record()
    def _work(self):
        with self.store.connect() as c:
            rows=c.execute("SELECT state,payload FROM requests WHERE owner=?",(self.store.owner,)).fetchall()
            states=[x["state"] for x in rows]
            eligible=0
            for x in rows:
                if x["state"]!="ready":continue
                p=json.loads(x["payload"]);s=p["settings"]
                if p["input"]["source_kind"]=="video" and not p["input"].get("output_folder"):eligible+=1
            # A failed/cancelled/review attempt may still contain unacknowledged data.
            # Unknown phases conservatively block mutation.
            table=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='gpu_attempts'").fetchone()
            unresolved=bool(table and c.execute("SELECT 1 FROM gpu_attempts WHERE phase NOT IN ('acknowledged','review_ready','new') LIMIT 1").fetchone())
        return {"intake":any(s in ("awaiting_input","staging") for s in states),"eligible":eligible,
            "busy":unresolved or any(s in ("processing","delivering") for s in states),
            "empty":all(s in ("completed","failed","cancelled","review","batch_expanded") for s in states) and not unresolved}
    def _post(self,r,action,i=None):
        self._save(r,action+"_requested")
        try:self.api.mutate(action,i)
        except (httpx.HTTPError,LifecycleError,ValueError):
            return self._save(r,action+"_pending_confirmation")
        return self._save(r,action+"_pending_confirmation")
    def tick(self,*,paused=False,manual=None):
        if manual not in (None,"start","stop"):raise LifecycleError("Invalid manual action")
        lockdir=safe_dir(self.store.root/"lifecycle-locks")
        with os.fdopen(os.open(lockdir/"lifecycle.lock",os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600),"a") as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return "busy"
            return self._tick(paused,manual)
    def _tick(self,paused,manual):
        now=self.clock();r=self._record()
        def done(state,reset_idle=True):
            if reset_idle:self.idle_since=None
            return self._save(r,state)
        if r.get("group") not in (None,self.api.path):return done("group_changed_reconcile")
        r["group"]=self.api.path
        if manual and self.cfg.auto_start:return done("select_manual_mode")
        if now<r.get("poll_after",0):return r.get("status","waiting")
        r["poll_after"]=now+3
        work=self._work()
        try:
            group=self.api.group()
            if (type(group.get("replicas")) is not int or group["replicas"]!=1 or
                group.get("autostart_policy") is not False or group.get("scheduled_scaling_enabled") is not False or
                group.get("container",{}).get("image")!=self.api.image):
                return done("dedicated_group_or_image_mismatch")
            state=group.get("current_state",{}).get("status")
            if group.get("pending_change"):return done("group_change_pending")
            if state=="stopped":
                if r.get("stop_intent"):
                    r.pop("stop_intent",None);r.pop("start_intent",None)
                    return done("stopped")
                if r.get("start_intent"):return done("start_pending_confirmation")
                if manual=="stop":return done("stopped")
                if paused or work["intake"] or work["busy"]:return done("waiting_for_drive_or_reconciliation")
                if manual!="start" and not self.cfg.auto_start:return done("manual_mode")
                if not work["eligible"] and manual!="start":return done("idle_stopped")
                r["start_intent"]=True
                # Recheck ledger before mutating. Atomic cross-admission gate still required
                # before enabling live scheduler.
                latest=self._work()
                if latest["intake"] or latest["busy"]:
                    r.pop("start_intent",None);return done("waiting_for_drive_or_reconciliation")
                return self._post(r,"start")
            if state not in ("running","deploying"):return done("waiting_for_group")
            if r.get("stop_intent"):return done("stop_pending_confirmation")
            instances=self.api.instances()
            if not isinstance(instances,list) or len(instances)!=1:return done("waiting_for_instance")
            inst=instances[0];ident=identity(inst);updated=timestamp(inst["update_time"],now)
            if ident!=r.get("instance"):
                r.update(instance=ident,latest_update=None,download_transition=None,accepted=False,progress=None)
            if r.get("latest_update") is not None and updated<r["latest_update"]:return done("stale_instance_response")
            r["latest_update"]=updated
            stage=inst.get("state")
            if stage=="running" and inst.get("ready") is True:
                caps=self.worker.capabilities() # exact worker source + protocol + authenticated health
                r.update(start_intent=False,attempts=0,accepted=True,progress=100)
                r.pop("retry_after",None)
                if not zero_metrics(caps) or work["busy"]:return done("worker_busy")
                if manual=="stop" or (self.cfg.auto_start and work["empty"]):
                    if work["intake"] or work["busy"] or (manual!="stop" and not work["empty"]):return done("draining")
                    if manual!="stop":
                        if self.idle_since is None:self.idle_since=now
                        if now-self.idle_since<60:return done("idle_countdown",False)
                    latest=self._work()
                    if latest["intake"] or latest["busy"] or (manual!="stop" and not latest["empty"]):return done("draining")
                    if not zero_metrics(self.worker.capabilities()):return done("worker_busy")
                    r["stop_intent"]=True;self.idle_since=None
                    return self._post(r,"stop")
                if paused or work["intake"]:return done("ready_dispatch_blocked")
                return done("ready")
            if stage!="downloading":
                r.update(download_transition=None,accepted=False,progress=None)
                return done("waiting_for_"+str(stage) if stage in ("allocating","creating","stopping") else "instance_uncertain")
            transition=inst["update_time"]
            if transition!=r.get("download_transition"):
                r.update(download_transition=transition,download_since=updated,accepted=False)
            progress=image_pull_percent(inst.get("pulling_progress"));r["progress"]=progress
            if progress is None:return done("download_progress_unavailable")
            if progress>=self.cfg.image_pull_threshold:r["accepted"]=True
            if r["accepted"]:return done("downloading_healthy")
            if now-r["download_since"]<self.cfg.image_pull_seconds:return done("checking_download")
            if manual or not self.cfg.auto_start or paused or work["intake"] or work["busy"]:return done("slow_download_no_reallocation")
            key=ident+"/"+transition
            if key in r.get("reallocated",[]):return done("waiting_for_reallocation")
            if now<r.get("cooldown_until",0):return done("reallocation_cooldown")
            budget=self.cfg.salad_max_reallocations
            if budget==0:return done("reallocation_disabled")
            if r.get("attempts",0)>=budget:
                r.setdefault("retry_after",now+300)
                if now<r["retry_after"]:return done("retry_cycle_cooldown")
                r["attempts"]=0;r.pop("retry_after",None)
            fresh=self.api.instance(inst["id"])
            if (identity(fresh)!=ident or fresh.get("update_time")!=transition or
                fresh.get("state")!="downloading" or fresh.get("ready") is not False):
                return done("instance_changed_rechecking")
            confirmed=image_pull_percent(fresh.get("pulling_progress"));r["progress"]=confirmed
            if confirmed is None:return done("download_progress_unavailable")
            if confirmed>=self.cfg.image_pull_threshold:
                r["accepted"]=True;return done("downloading_healthy")
            latest=self._work()
            if latest["intake"] or latest["busy"]:return done("waiting_for_drive_or_reconciliation")
            # Keep complete journal for this group. Refuse mutation instead of dropping old entries.
            actions=r.setdefault("reallocated",[])
            if len(actions)>=4096:return done("journal_capacity_reconcile")
            actions.append(key);r["attempts"]=r.get("attempts",0)+1
            r["cooldown_until"]=now+self.cfg.salad_reallocate_cooldown
            return self._post(r,"reallocate",inst["id"])
        except (httpx.HTTPError,LifecycleError,RuntimeError,ValueError,TypeError,KeyError,AttributeError):
            return done("api_or_worker_unavailable")
