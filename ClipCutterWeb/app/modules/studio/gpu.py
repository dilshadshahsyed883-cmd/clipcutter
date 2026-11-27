"""Independent GPU configuration and read-only SaladCloud status.

The actual worker transport and Drive intake are not wired yet. Do not issue
START/STOP/REALLOCATE until a single verified dispatcher owns these operations.
"""
import json
import math
import os
import time
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.auth import Principal, admin_principal
from app.modules.admin.security import require_csrf
from .store import Store

SALAD_API = "https://api.salad.com/api/public"
IDLE_SECONDS = 60
RETRY_CYCLE_SECONDS = 300
BLOCKER = "Live scheduler activation is gated pending finalization and runtime acceptance."

class GPUSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    auto_start: bool = False
    image_pull_threshold: int = Field(default=8, ge=1, le=100)
    image_pull_seconds: int = Field(default=20, ge=5, le=600)
    salad_max_reallocations: int = Field(default=3, ge=0, le=3)
    salad_reallocate_cooldown: int = Field(default=30, ge=5, le=600)
    salad_organization: str = Field(default="", pattern=r"^(?:[a-z][a-z0-9-]{0,61}[a-z0-9])?$")
    salad_project: str = Field(default="", pattern=r"^(?:[a-z][a-z0-9-]{0,61}[a-z0-9])?$")
    salad_container_group: str = Field(default="", pattern=r"^(?:[a-z][a-z0-9-]{0,61}[a-z0-9])?$")
    worker_gateway: str = Field(default="", max_length=512)
    parallel: int = Field(default=1, ge=1, le=2)

    @field_validator("worker_gateway")
    @classmethod
    def validate_gateway(cls, value):
        if value:
            try:
                u = urlsplit(value)
                if u.scheme != "https" or not u.hostname or u.username is not None or u.password is not None or u.query or u.fragment or any(ord(c) <= 32 or ord(c) >= 127 for c in value):
                    raise ValueError()
                _ = u.port
            except ValueError:
                raise ValueError("Use an HTTPS worker gateway without credentials or query") from None
        return value.rstrip("/")

class GPUUpdate(GPUSettings):
    salad_key: str = Field(default="", max_length=512)
    worker_key: str = Field(default="", max_length=512)
    clear_salad_key: bool = False
    clear_worker_key: bool = False

    @field_validator("salad_key", "worker_key")
    @classmethod
    def validate_secret(cls, value, info):
        if value and (len(value) < (32 if info.field_name == "worker_key" else 16) or any(ord(c) < 33 or ord(c) > 126 for c in value)):
            raise ValueError("Invalid credential")
        return value

def image_pull_percent(value):
    # Match Concat's fractional/percentage convention, never infer zero.
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
        return None
    return round(value * 100, 10) if value <= 1 else value

def scheduled_scaling_disabled(group):
    """Safe when explicitly off or enabled with an explicitly empty schedule."""
    flags=[group[k] for k in ("scheduled-scaling-enabled","scheduled_scaling_enabled") if k in group]
    actions=[group[k] for k in ("scaling-actions","scaling_actions") if k in group]
    if not flags or any(type(v) is not bool for v in flags) or len(set(flags))!=1:
        return False
    if any(not isinstance(v,list) for v in actions):
        return False
    if not flags[0]:
        return True
    return bool(actions) and all(v==[] for v in actions)

def group_blocker(group, approved_image=None):
    if type(group.get("replicas")) is not int or group["replicas"]!=1:
        return "requires_one_replica"
    if group.get("autostart_policy") is not False:
        return "disable_salad_autostart"
    if not scheduled_scaling_disabled(group):
        return "scheduled_scaling_active_or_unverified"
    if approved_image is not None and group.get("container",{}).get("image")!=approved_image:
        return "approved_gpu_image_mismatch"
    return None

def group_path(cfg):
    names = (cfg.salad_organization, cfg.salad_project, cfg.salad_container_group)
    return "/organizations/{}/projects/{}/containers/{}".format(*names) if all(names) else None

class GPUStore:
    def __init__(self, store):
        self.store = store
        with store.connect() as con:
            con.execute("CREATE TABLE IF NOT EXISTS gpu_config (id INTEGER PRIMARY KEY CHECK(id=1), settings TEXT NOT NULL, salad_key TEXT NOT NULL, worker_key TEXT NOT NULL)")

    def _read(self, con):
        row = con.execute("SELECT settings,salad_key,worker_key FROM gpu_config WHERE id=1").fetchone()
        return (GPUSettings.model_validate_json(row["settings"]), row["salad_key"], row["worker_key"]) if row else (GPUSettings(), "", "")

    def snapshot(self):
        with self.store.connect() as con:
            cfg, key, worker = self._read(con)
        return cfg, key or os.getenv("CLIPCUTTER_SALAD_API_KEY", ""), worker or os.getenv("CLIPCUTTER_WORKER_API_TOKEN", "")

    def public(self):
        cfg, key, worker = self.snapshot()
        from .scheduler import Control, authorized
        control=Control(self.store).snapshot()
        enabled=authorized(self.store,cfg) and control["online"]
        return {**cfg.model_dump(), "salad_key_configured": bool(key),
                "worker_key_configured": bool(worker), "group_configured": bool(group_path(cfg)),
                "idle_seconds": IDLE_SECONDS, "retry_cycle_seconds": RETRY_CYCLE_SECONDS,
                "dispatch_enabled": enabled, "scheduler": control, "message": ("Scheduler online" if enabled else BLOCKER)}

    def save(self, value):
        cfg = GPUSettings.model_validate(value.model_dump(include=set(GPUSettings.model_fields)))
        with self.store.admission(), self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            old_cfg, old_salad, old_worker = self._read(con)
            key = "" if value.clear_salad_key else value.salad_key or old_salad
            worker = "" if value.clear_worker_key else value.worker_key or old_worker
            if group_path(old_cfg)!=group_path(cfg) or old_salad!=key or old_worker!=worker:
                status_cache_table(con)
                con.execute("DELETE FROM gpu_status_cache")
            con.execute("INSERT INTO gpu_config VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET settings=excluded.settings,salad_key=excluded.salad_key,worker_key=excluded.worker_key", (cfg.model_dump_json(), key, worker))
        return self.public()

def _salad_get(client, path, key):
    with client.stream("GET", SALAD_API + path, headers={"Salad-Api-Key":key, "Accept":"application/json", "Cache-Control":"no-cache"}) as response:
        if response.status_code != 200:
            raise ValueError("Salad API unavailable")
        age, date = response.headers.get("Age"), response.headers.get("Date")
        if age is not None and (not age.isdigit() or int(age) > 3):
            raise ValueError("Cached Salad response")
        if date is not None and not -10 <= time.time() - parsedate_to_datetime(date).timestamp() <= 15:
            raise ValueError("Stale Salad response")
        payload = bytearray()
        for chunk in response.iter_bytes():
            payload.extend(chunk)
            if len(payload) > 1024 * 1024:
                raise ValueError("Salad response too large")
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError("Invalid Salad response")
        return data

def _short_text(value):
    return value[:128] if isinstance(value, str) else None

def status_view(group, approved, instances=()):
    current=group.get("current_state")
    state=_short_text(current.get("status")) if isinstance(current,dict) else None
    replicas=group.get("replicas")
    autostart=group.get("autostart_policy")
    reason=group_blocker(group,approved)
    result={"status":state or "unknown","replicas":replicas if type(replicas) is int else None,
            "autostart_policy":autostart if type(autostart) is bool else None,
            "dedicated_group_compatible":reason is None,"group_blocker":reason,
            "dispatch_enabled":False,"message":BLOCKER,"instances":[]}
    for item in instances[:10]:
        if not isinstance(item,dict):raise ValueError("Invalid instance")
        result["instances"].append({"id":_short_text(item.get("id")),"state":_short_text(item.get("state")),
            "ready":item.get("ready") if type(item.get("ready")) is bool else None,
            "pulling_progress":image_pull_percent(item.get("pulling_progress")),
            "update_time":_short_text(item.get("update_time"))})
    return result

def status_cache_table(c):
    c.execute("CREATE TABLE IF NOT EXISTS gpu_status_cache (id INTEGER PRIMARY KEY CHECK(id=1), path TEXT NOT NULL, observed REAL NOT NULL, payload TEXT NOT NULL)")

def cache_status(store,path,result,observed):
    # Only sanitized status_view/read_status output; no raw group or credentials.
    if not path:return
    with store.connect() as c:
        status_cache_table(c)
        c.execute("""INSERT INTO gpu_status_cache VALUES(1,?,?,?)
          ON CONFLICT(id) DO UPDATE SET path=excluded.path,observed=excluded.observed,payload=excluded.payload
          WHERE gpu_status_cache.path!=excluded.path OR excluded.observed>=gpu_status_cache.observed""",
          (path,observed,json.dumps(result)))

def cached_status(store,path):
    with store.connect() as c:
        status_cache_table(c)
        row=c.execute("SELECT observed,payload FROM gpu_status_cache WHERE id=1 AND path=?",(path,)).fetchone()
    if row:return {**json.loads(row["payload"]),"observed_at":row["observed"],"cached":True}
    return {"status":"not_checked" if path else "not_configured","instances":[],"observed_at":None,"cached":True}

def read_status(cfg, key):
    path = group_path(cfg)
    if not path or not key:
        return {"status":"not_configured", "instances":[], "dispatch_enabled":False, "message":BLOCKER}
    try:
        with httpx.Client(timeout=httpx.Timeout(8, connect=3), follow_redirects=False, trust_env=False) as client:
            group = _salad_get(client, path, key)
            approved=os.environ.get("CLIPCUTTER_APPROVED_GPU_IMAGE")
            result=status_view(group,approved)
            if result["status"] in ("running","deploying"):
                instances=_salad_get(client,path+"/instances",key).get("instances")
                if not isinstance(instances,list):raise ValueError("Invalid instances response")
                result=status_view(group,approved,instances)
            return result
    except (httpx.HTTPError, ValueError, TypeError, OverflowError):
        raise HTTPException(502, "Unable to verify SaladCloud status; check independent group credentials and connectivity") from None

router = APIRouter(prefix="/api/v1/gpu")

def gpu_store(principal:Principal=Depends(admin_principal)):
    return GPUStore(Store(principal.username))

@router.get("/config")
def get_config(s:GPUStore=Depends(gpu_store)):
    return s.public()

@router.post("/config", dependencies=[Depends(require_csrf)])
async def save_config(request:Request, s:GPUStore=Depends(gpu_store)):
    # Avoid exposing credential input in default Pydantic error payloads.
    try:
        value = GPUUpdate.model_validate(await request.json())
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(422, "Invalid GPU configuration; check identifiers, credentials and automation ranges") from None
    return s.save(value)

@router.get("/status")
def status(s:GPUStore=Depends(gpu_store)):
    cfg, key, _ = s.snapshot()
    observed=time.time()
    result=read_status(cfg, key)
    cache_status(s.store,group_path(cfg),result,observed)
    result.update(observed_at=observed,cached=False)
    public=s.public()
    result.update(dispatch_enabled=public["dispatch_enabled"],message=public["message"])
    return result

@router.get("/status/cached")
def local_status(s:GPUStore=Depends(gpu_store)):
    cfg,key,_=s.snapshot()
    result=cached_status(s.store,group_path(cfg)) if key else {"status":"not_configured","instances":[],"cached":True}
    public=s.public()
    result.update(dispatch_enabled=public["dispatch_enabled"],message=public["message"])
    return result

@router.post("/actions/{action}", dependencies=[Depends(require_csrf)])
def action(action:str, s:GPUStore=Depends(gpu_store)):
    if action not in ("start", "stop", "retry", "pause", "resume"):
        raise HTTPException(404, "Unknown worker action")
    from .scheduler import Control
    from .lifecycle import LifecycleError
    try:
        control=Control(s.store)
        if action in ("pause","resume"):return control.set_paused(action=="pause")
        return control.command(action,s.snapshot()[0])
    except LifecycleError as exc:raise HTTPException(409,str(exc)) from None
