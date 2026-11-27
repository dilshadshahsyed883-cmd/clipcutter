"""Owner-local GPU timing reports; never export remote payloads or credentials."""
from datetime import datetime, timezone
import json
import math
import time

FIELDS=("staging_at","queued_at","running_at","input_verified_at","processing_started_at",
        "processing_finished_at","completed_at","failed_at","cancelled_at","purged_at")
STATES={"staging","queued","running","cancelling","completed","failed","cancelled"}
ACTIONS={"scan","export","analyze"}

def record(store,jid,remote,parallel_limit=None):
    raw=remote.get("timing")
    if not isinstance(raw,dict):return
    timing={k:raw[k] for k in FIELDS if type(raw.get(k)) in (int,float)
            and math.isfinite(raw[k]) and 0<raw[k]<253402300799}
    if not timing or remote.get("state") not in STATES or remote.get("action") not in ACTIONS:return
    with store.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        store.row(c,jid)
        a=remote["attempt_id"]
        old=c.execute("SELECT timing, parallel_limit FROM gpu_performance WHERE attempt_id=? AND job_id=?",(a,jid)).fetchone()
        if old:
            timing={**timing,**json.loads(old["timing"])}
            if old["parallel_limit"] is not None:parallel_limit=old["parallel_limit"]
        if parallel_limit not in (1,2):parallel_limit=None
        c.execute("""INSERT INTO gpu_performance VALUES (?,?,?,?,?,?,?)
          ON CONFLICT(attempt_id) DO UPDATE SET state=excluded.state,timing=excluded.timing,
          observed_at=excluded.observed_at,parallel_limit=excluded.parallel_limit""",
          (a,jid,remote["action"],remote["state"],json.dumps(timing),int(time.time()),parallel_limit))

def report(store,hours):
    now=time.time()
    with store.connect() as c:
        rows=c.execute("""SELECT * FROM gpu_performance WHERE observed_at>=?
                          ORDER BY observed_at DESC,attempt_id LIMIT 20000""",(int(now-hours*3600),)).fetchall()
    lines=["ClipCutter performance report (UTC)",f"Last {hours} hours by last observation",
           "Worker phase timings; unavailable measurements are not zero.",
           "Parallel limit is the configured scheduler limit at first observation, not measured concurrency.",
           "GPU startup, FPS, GPU utilization, VRAM, VPS export and individual scan/encode phases: not collected.",
           "Older workers without timing support cannot be reconstructed.",
           f"Attempts: {len(rows)}"]
    for row in rows:
        timing=json.loads(row["timing"])
        lines.extend(["",f"Job {row['job_id']} | Attempt {row['attempt_id']} | {row['action']} | {row['state']}",
                      f"Configured parallel limit: {row['parallel_limit'] or 'unavailable'}"])
        for k in FIELDS:
            if k in timing:lines.append(f"{k}: {datetime.fromtimestamp(timing[k],timezone.utc).isoformat()}")
        for label,a,b in (("Staging to queue (transfer + wait)","staging_at","queued_at"),
            ("Input verification","running_at","input_verified_at"),
            ("Worker subprocess (all processing)","processing_started_at","processing_finished_at"),
            ("Output verification","processing_finished_at","completed_at"),
            ("Receipt and purge interval","completed_at","purged_at"),
            ("Total attempt including receipt","staging_at","purged_at")):
            if a in timing and b in timing and timing[b]>=timing[a]:
                lines.append(f"{label}: {timing[b]-timing[a]:.3f} s")
            else:lines.append(f"{label}: unavailable")
    return "\n".join(lines)+"\n"
