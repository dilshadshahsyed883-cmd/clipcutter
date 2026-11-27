"""Independent CPU extraction, without model loading or GPU calls.
Only whole-picture clips are supported. Durable attempt phases survive restart.
"""
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path
from uuid import uuid4
from .store import safe_dir
from .drive_delivery import deliver_one,DeliveryError
from .output_names import allocate
from .intake import RESERVE
from .dispatch import DispatchError,sha_file,NAME,canonical

def local_job(job):
    settings=job.get("settings",{})
    return settings.get("kind")=="extractor" and settings.get("gpu_clip_extraction") is False and settings.get("mode")=="manual"

def local_row(row):
    phase=row.get("phase") or ""
    return phase.startswith("vps_") or (not phase and local_job(json.loads(row["payload"])))

def probe(path):
    p=subprocess.run(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(path)],
                     capture_output=True,text=True,timeout=30,check=True)
    data=json.loads(p.stdout)
    video=next(x for x in data["streams"] if x["codec_type"]=="video")
    return video,round(float(video.get("duration") or data["format"]["duration"])*1000)

def partitions(start,end,lo,hi):
    if lo is None:return [(start,end)]
    total=end-start;n=min(total//lo,(total+hi-1)//hi)
    if not n:return []
    usable=min(total,n*hi);base,extra=divmod(usable,n)
    out=[]
    for i in range(n):
        stop=start+base+(i<extra);out.append((start,stop));start=stop
    return out

def run_command(args,cancel):
    with subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True) as p:
        deadline=time.monotonic()+6*3600
        try:
            while p.poll() is None:
                if cancel():raise InterruptedError("VPS extraction cancelled")
                if time.monotonic()>deadline:raise RuntimeError("VPS encoding timed out")
                time.sleep(.2)
            if p.returncode:raise RuntimeError("FFmpeg failed; check input and installed encoders")
        finally:
            if p.poll() is None:
                p.terminate()
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:p.kill();p.wait()

def encode(source,settings,ranges,out,cancel,progress):
    if settings["framing"]!="whole":raise ValueError("VPS extraction requires Whole picture framing")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):raise RuntimeError("Install FFmpeg and ffprobe on VPS")
    video,duration=probe(source)
    limits=(settings.get("minimum_ms"),settings.get("maximum_ms"))
    if any(not 0<=x["start_ms"]<x["end_ms"]<=duration for x in ranges):raise ValueError("Range exceeds source duration")
    cuts=[p for x in sorted(ranges,key=lambda x:x["start_ms"]) for p in partitions(x["start_ms"],x["end_ms"],*limits)]
    if not cuts or len(cuts)>1000:raise ValueError("No eligible clips or too many clips")
    limit=settings["max_short_side"];quality=settings["quality"]
    copy=settings["cut_mode"]=="copy" and not limit and quality==100
    if copy:
        # Match keyframe-aligned mode: use the last keyframe at or before each requested start.
        raw=subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-skip_frame","nokey",
            "-show_frames","-show_entries","frame=best_effort_timestamp_time","-of","json",str(source)],
            capture_output=True,text=True,check=True,timeout=120)
        keys=sorted(round(float(x["best_effort_timestamp_time"])*1000) for x in json.loads(raw.stdout).get("frames",[]) if "best_effort_timestamp_time" in x)
        cuts=[(max((k for k in keys if 0<=k<=a),default=0),b) for a,b in cuts]
    files=[]
    for i,(a,b) in enumerate(cuts,1):
        if cancel():raise InterruptedError("VPS extraction cancelled")
        if shutil.disk_usage(out).free<RESERVE:raise RuntimeError("Insufficient VPS storage reserve")
        path=out/("clip_%03d.mp4"%i)
        cmd=["ffmpeg","-nostdin","-v","error","-n","-ss",f"{a/1000:.3f}","-i",str(source),
             "-t",f"{(b-a)/1000:.3f}","-map","0:v:0"]
        cmd+=["-map","0:a:0?"] if settings["include_audio"] else ["-an"]
        if copy:cmd+=["-c","copy","-avoid_negative_ts","make_zero"]
        else:
            w,h=video["width"],video["height"]
            factor=min(1,limit/min(w,h)) if limit else 1
            width=max(2,int(w*factor)//2*2);height=max(2,int(h*factor)//2*2)
            crf=round(16+(95-max(50,min(95,quality)))*.4)+2
            cmd+=["-vf",f"scale={width}:{height}","-c:v","libx265","-preset","medium","-crf",str(crf),
                  "-pix_fmt","yuv420p","-tag:v","hvc1","-threads","2","-x265-params","pools=2:frame-threads=2:log-level=error","-c:a","aac"]
        run_command(cmd+["-movflags","+faststart",str(path)],cancel)
        files.append((path,b-a));progress(i,len(cuts))
    if settings["stitched"] and len(files)>1:
        listing=out/"segments.txt";listing.write_text("".join("file "+p.name+"\n" for p,_ in files))
        target=out/"clip_stitched.mp4"
        run_command(["ffmpeg","-nostdin","-v","error","-n","-f","concat","-safe","1","-i",str(listing),
                     "-c","copy","-movflags","+faststart",str(target)],cancel)
        total=sum(d for _,d in files)
        for p,_ in files:p.unlink()
        listing.unlink();files=[(target,total)]
    items=[]
    for path,expected in files:
        _,actual=probe(path)
        if actual<=0 or (not copy and abs(actual-expected)>max(1000,round(expected*.03))):
            raise RuntimeError("Output duration verification failed")
        if limits[0] is not None and not limits[0]<=actual<=limits[1]:raise RuntimeError("Output violates strict duration limits")
        run_command(["ffmpeg","-nostdin","-v","error","-xerror","-ss",str(max(0,actual/1000-2)),"-i",str(path),
                     "-map","0:v:0","-frames:v","2","-f","null","-"],cancel)
        items.append({"name":path.name,"size":path.stat().st_size,"sha256":sha_file(path),
                      "media_type":"video/mp4","duration_ms":actual})
    return items

def terminal(d,jid,row,state,message):
    with d.store.connect() as c:
        c.execute("BEGIN IMMEDIATE");d.store.row(c,jid)
        c.execute("UPDATE requests SET state=?,message=?,updated_at=? WHERE id=? AND owner=?",
                  (state,message[:500],int(time.time()),jid,d.store.owner))
        c.execute("UPDATE gpu_attempts SET phase=? WHERE job_id=? AND attempt_id=?",("vps_"+state,jid,row["attempt_id"]))
        c.execute("DELETE FROM gpu_commands WHERE job_id=?",(jid,))
    return "vps_"+state

def tick(d,jid,row,allow_start=True):
    store=d.store;phase=row["phase"];command=d.command(jid)
    m=json.loads(row["manifest"]);mapping=json.loads(row["mapping"]);settings=m["job"]["request"]["settings"]
    work=safe_dir(safe_dir(store.root/"vps-export")/row["attempt_id"])
    receipt=work/"result.json";out=work/"outputs"
    dest=safe_dir(store.root/"outputs")/jid
    if phase=="vps_failed" and command=="retry":
        if dest.exists():raise DispatchError("Existing output requires reconciliation")
        with store.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("UPDATE gpu_attempts SET attempt_id=?,phase='vps_new' WHERE job_id=?",(uuid4().hex,jid))
            c.execute("UPDATE requests SET state='ready',message='VPS retry queued',updated_at=? WHERE id=? AND owner=?",(int(time.time()),jid,store.owner))
            c.execute("DELETE FROM gpu_commands WHERE job_id=?",(jid,))
        return "retry_queued"
    if phase in ("vps_failed","vps_cancelled"):return phase
    if phase=="vps_new":
        if command=="cancel":return terminal(d,jid,row,"cancelled","Cancelled before VPS extraction")
        if not allow_start:return "paused"
        with store.admission():
            from .scheduler import Control
            if Control(store).snapshot()["paused"]:return "paused"
            if d.command(jid)=="cancel":return terminal(d,jid,row,"cancelled","Cancelled before VPS extraction")
            with store.connect() as c:
                c.execute("BEGIN IMMEDIATE")
                if store.row(c,jid)["state"]!="ready":raise DispatchError("VPS admission state changed")
                c.execute("UPDATE requests SET state='processing',progress=0,message='VPS encoding',updated_at=? WHERE id=? AND owner=?",(int(time.time()),jid,store.owner))
                c.execute("UPDATE gpu_attempts SET phase='vps_processing' WHERE job_id=? AND attempt_id=?",(jid,row["attempt_id"]))
        try:
            root=store.root/"inputs"/jid
            for n,item in m["files"].items():
                name=mapping[n];p=root/name
                if not NAME.fullmatch(name) or p.resolve()!=p or not p.is_file() or p.stat().st_size!=item["size"] or sha_file(p)!=item["sha256"]:
                    raise RuntimeError("Verified input changed")
            source=root/mapping["source.video"]
            ranges=settings["ranges"] if settings["mode"]=="manual" else json.loads((root/mapping["approved-review.json"]).read_text())["ranges"]
            safe_dir(out)
            items=encode(source,settings,ranges,out,lambda:d.command(jid)=="cancel",
              lambda i,n:store.gpu_stage_progress(jid,"processing",100*i//n,"VPS encoding"))
            if d.command(jid)=="cancel":raise InterruptedError("Cancelled")
            tmp=work/"result.tmp"
            with tmp.open("xb") as f:f.write(canonical(items));f.flush();os.fsync(f.fileno())
            os.replace(tmp,receipt)
            fd=os.open(work,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
        except Exception as exc:
            return terminal(d,jid,row,"cancelled" if d.command(jid)=="cancel" else "failed","VPS: "+str(exc))
        phase="vps_processing"
    if phase=="vps_processing":
        if not receipt.is_file():
            return terminal(d,jid,row,"cancelled" if command=="cancel" else "failed","Interrupted VPS extraction; retry uses retained inputs")
        with store.admission():
            if d.command(jid)=="cancel" and not dest.exists():return terminal(d,jid,row,"cancelled","Cancelled before delivery")
            with store.connect() as c:
                c.execute("BEGIN IMMEDIATE")
                if store.row(c,jid)["state"]!="processing":raise DispatchError("VPS delivery state changed")
                c.execute("UPDATE requests SET state='delivering',progress=100,message='Verified VPS outputs',updated_at=? WHERE id=? AND owner=?",(int(time.time()),jid,store.owner))
                c.execute("UPDATE gpu_attempts SET phase='vps_delivering' WHERE job_id=? AND attempt_id=?",(jid,row["attempt_id"]))
        phase="vps_delivering"
    if phase=="vps_delivering":
        items=json.loads(receipt.read_bytes())
        if not dest.exists():
            os.rename(out,dest)
            for folder_path in (work,dest.parent):
                fd=os.open(folder_path,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(fd)
                finally:os.close(fd)
        if out.exists():raise DispatchError("VPS output conflict")
        for item in items:
            p=dest/item["name"]
            if p.resolve()!=p or not p.is_file() or p.stat().st_size!=item["size"] or sha_file(p)!=item["sha256"]:raise DispatchError("VPS output verification failed")
        allocate(store,jid,items,settings["stitched"])
        folder=m["job"]["request"]["input"].get("output_folder")
        if folder:
            try:
                if not deliver_one(store,jid,folder,dest,items):return "vps_delivering"
            except DeliveryError as exc:raise DispatchError(str(exc)) from None
        if store.get(jid)["state"]!="completed":store.publish_verified_outputs(jid,items)
        d._phase(jid,"acknowledged")
        d.clear_command(jid,"cancel")
        return "acknowledged"
    return phase
