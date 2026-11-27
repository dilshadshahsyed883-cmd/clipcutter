"""Owner-local GPU timing reports; never export remote payloads or credentials."""
from datetime import datetime, timezone
import json
import math
import re
import time

FIELDS=("staging_at","queued_at","running_at","input_verified_at","processing_started_at",
        "processing_finished_at","completed_at","failed_at","cancelled_at","purged_at")
STATES={"staging","queued","running","cancelling","completed","failed","cancelled"}
ACTIONS={"scan","export","analyze"}

METRIC_LIMITS={"peak_active_slots":2,"worker_capacity":2,"gpu_samples":1000000,
 "gpu_utilization_mean_pct":100,"gpu_utilization_peak_pct":100,"gpu_vram_peak_mib":1048576,"gpu_vram_total_mib":1048576,
 "nvenc_frames":1000000000,"cpu_frames":1000000000,"nvenc_seconds":86400,"cpu_seconds":86400,
 "scan_refine_seconds":86400,"tracking_seconds":86400,"export_wall_seconds":86400}

def safe_metrics(remote):
    out={}
    for source in (remote.get("telemetry"),(remote.get("result") or {}).get("performance") if isinstance(remote.get("result"),dict) else None):
        if not isinstance(source,dict):continue
        for key,limit in METRIC_LIMITS.items():
            v=source.get(key)
            if type(v) in (int,float) and math.isfinite(v) and 0<=v<=limit:out[key]=v
        name=source.get("gpu_model")
        if isinstance(name,str) and re.fullmatch(r"[A-Za-z0-9 ._()+-]{1,100}",name):out["gpu_model"]=name
    return out

def details_table(c):
    c.execute("CREATE TABLE IF NOT EXISTS gpu_performance_details(attempt_id TEXT PRIMARY KEY, metrics TEXT NOT NULL)")

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
        details_table(c)
        metrics=safe_metrics(remote)
        if metrics:
            prev=c.execute("SELECT metrics FROM gpu_performance_details WHERE attempt_id=?",(a,)).fetchone()
            if prev:metrics={**json.loads(prev[0]),**metrics}
            c.execute("INSERT INTO gpu_performance_details VALUES (?,?) ON CONFLICT(attempt_id) DO UPDATE SET metrics=excluded.metrics",(a,json.dumps(metrics)))
        old=c.execute("SELECT timing, parallel_limit FROM gpu_performance WHERE attempt_id=? AND job_id=?",(a,jid)).fetchone()
        if old:
            timing={**timing,**json.loads(old["timing"])}
            if old["parallel_limit"] is not None:parallel_limit=old["parallel_limit"]
        if parallel_limit not in (1,2) or (remote["state"]=="staging" and not (old and old["parallel_limit"] is not None)):parallel_limit=None
        c.execute("""INSERT INTO gpu_performance VALUES (?,?,?,?,?,?,?)
          ON CONFLICT(attempt_id) DO UPDATE SET state=excluded.state,timing=excluded.timing,
          observed_at=excluded.observed_at,parallel_limit=excluded.parallel_limit""",
          (a,jid,remote["action"],remote["state"],json.dumps(timing),int(time.time()),parallel_limit))

def report(store,hours):
    now=time.time()
    with store.connect() as c:
        details_table(c)
        rows=c.execute("""SELECT * FROM gpu_performance WHERE observed_at>=?
                          ORDER BY observed_at DESC,attempt_id LIMIT 20000""",(int(now-hours*3600),)).fetchall()
        details={x["attempt_id"]:json.loads(x["metrics"]) for x in c.execute("SELECT d.* FROM gpu_performance_details d JOIN gpu_performance p USING(attempt_id) WHERE p.observed_at>=?",(int(now-hours*3600),))}
    lines=["ClipCutter performance report (UTC)",f"Last {hours} hours by last observation",
           "Worker phase timings; unavailable measurements are not zero.",
           "Parallel limit is the recorded scheduler limit; peak occupied slots are observed by the worker.",
           "GPU utilization and VRAM are device-wide samples, shared during parallel jobs; sampled peaks are not absolute peaks.",
           "FPS is successful FFmpeg encoded frames / measured encoding command seconds; stream copy is not encoding.",
           "GPU startup and VPS export metrics are not collected by this report.",
           "Older workers without timing support cannot be reconstructed.",
           f"Attempts: {len(rows)}"]
    groups={1:[],2:[]}
    for row in rows:
        timing=json.loads(row["timing"])
        lines.extend(["",f"Job {row['job_id']} | Attempt {row['attempt_id']} | {row['action']} | {row['state']}",
                      f"Configured parallel limit: {row['parallel_limit'] or 'unavailable'}"])
        m=details.get(row["attempt_id"],{})
        for k,v in m.items():lines.append(f"{k}: {v:.3f}" if type(v) is float else f"{k}: {v}")
        for encoder in ("nvenc","cpu"):
            frames=m.get(encoder+"_frames",0);seconds=m.get(encoder+"_seconds",0)
            if frames>0 and seconds>0:lines.append(f"{encoder} average encoding FPS: {frames/seconds:.2f}")
        if row["state"]=="completed" and row["action"]=="export" and row["parallel_limit"] in groups:
            if m.get("nvenc_frames",0)>0 and m.get("nvenc_seconds",0)>0:
                groups[row["parallel_limit"]].append((m["nvenc_frames"],m["nvenc_seconds"],m.get("peak_active_slots")))
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
    lines.extend(["","Parallel comparison (successful NVENC exports only; per-job weighted FPS, not aggregate GPU throughput)"])
    for limit,items in groups.items():
        if items:lines.append(f"Parallel {limit}: {len(items)} attempts, {sum(f for f,s,n in items)/sum(s for f,s,n in items):.2f} weighted FPS; observed two-slot overlap in {sum(n==2 for f,s,n in items)} attempts")
        else:lines.append(f"Parallel {limit}: unavailable")
    return "\n".join(lines)+"\n"
