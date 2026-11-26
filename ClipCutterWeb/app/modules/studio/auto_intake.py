"""Single-owner VPS intake loop, independent of GPU authorization and browser lifetime."""
import fcntl
import logging
import os
from threading import Event,Thread
from .store import Store,safe_dir
from .scheduler import Control
from .intake import stage

log=logging.getLogger(__name__)

def run_once(store,stage_fn=stage):
    # One intake at a time, including across web-process restarts.
    locks=safe_dir(store.root/"orchestration-locks")
    with os.fdopen(os.open(locks/"auto-intake.lock",os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600),"a") as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return False
        with store.admission():
            if Control(store).snapshot()["paused"]:return False
            with store.connect() as c:
                row=c.execute("""SELECT id FROM requests WHERE owner=? AND state IN ('awaiting_input','staging')
                    ORDER BY CASE state WHEN 'staging' THEN 0 ELSE 1 END,created_at,rowid LIMIT 1""",(store.owner,)).fetchone()
            if row is None:return False
            jid=row["id"]
        # stage rechecks pause under admission and takes its own per-job lock.
        try:stage_fn(store,jid)
        except Exception:
            log.exception("Input intake failed unexpectedly")
            with store.admission():
                row=store.get(jid)
                if row["state"]=="staging":
                    label="YouTube" if row["input"]["source_kind"]=="youtube" else "Drive"
                    store.transition(jid,"staging","failed",label+" intake: Unexpected intake error; retry after checking service logs")
        return True

def start():
    """Only called by production run.py, never by imported ASGI apps or source tests."""
    stop=Event()
    from app.modules.admin.security import _valid_username
    owner=os.environ.get("CLIPCUTTER_ADMIN_USERNAME","")
    if os.environ.get("CLIPCUTTER_AUTH_MODE")!="local-admin" or not _valid_username(owner) or not os.environ.get("CLIPCUTTER_WEB_DATA_ROOT"):
        log.error("Automatic intake requires configured local owner and storage")
        return stop
    def loop():
        while not stop.is_set():
            try:run_once(Store(owner))
            except Exception:log.exception("Automatic intake queue unavailable")
            stop.wait(3)
    Thread(target=loop,name="clipcutter-intake",daemon=True).start()
    return stop
