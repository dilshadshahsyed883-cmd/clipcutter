"""Best-effort single-device NVIDIA metrics; device-wide, not process attribution."""
import math
import re
import subprocess

def gpu_sample():
    try:
        p=subprocess.run(["nvidia-smi","--query-gpu=name,utilization.gpu,memory.used,memory.total",
            "--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=2,check=True)
        rows=p.stdout.strip().splitlines()
        if len(rows)!=1:return None
        name,util,used,total=(x.strip() for x in rows[0].split(","))
        util,used,total=map(float,(util,used,total))
        if not re.fullmatch(r"[A-Za-z0-9 ._()+-]{1,100}",name) or not all(map(math.isfinite,(util,used,total))) or not 0<=util<=100 or not 0<=used<=total<=1048576:return None
        return {"gpu_model":name,"utilization":util,"vram_used_mib":used,"vram_total_mib":total}
    except (OSError,ValueError,subprocess.SubprocessError):return None

def accumulate(previous,sample):
    stats=dict(previous)
    n=stats.get("gpu_samples",0)
    stats.update(gpu_model=sample["gpu_model"],gpu_samples=n+1,
        gpu_utilization_mean_pct=(stats.get("gpu_utilization_mean_pct",0)*n+sample["utilization"])/(n+1),
        gpu_utilization_peak_pct=max(stats.get("gpu_utilization_peak_pct",0),sample["utilization"]),
        gpu_vram_peak_mib=max(stats.get("gpu_vram_peak_mib",0),sample["vram_used_mib"]),
        gpu_vram_total_mib=sample["vram_total_mib"])
    return stats
