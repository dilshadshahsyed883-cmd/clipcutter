from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from typing import Literal
from app.auth import Principal,current_principal
from app.modules.admin.security import require_csrf
from .contracts import JobRequest
from .store import Store
from .intake import Bridge, stage
from .review import Approval, get_review, approve
from .profiles import SaveProfile, listing as profile_listing, save as profile_save, delete as profile_delete

router=APIRouter(prefix="/api/v1/studio")
def store(principal:Principal=Depends(current_principal)):
    return Store(principal.username)

@router.get("/capabilities")
def capabilities(_:Principal=Depends(current_principal)):
    available=Bridge().available()
    return {"input_intake":available,"worker_dispatch":False,"output_receiver":False,
            "request_storage":True,"message":("Drive intake available; GPU transport not connected." if available else "Drive intake bridge unavailable; requests may be saved.")}

@router.get("/profiles")
def profiles(s:Store=Depends(store)):return {"profiles":profile_listing(s)}

@router.post("/profiles",dependencies=[Depends(require_csrf)])
def save_profile(value:SaveProfile,s:Store=Depends(store)):return profile_save(s,value)

@router.delete("/profiles/{pid}",dependencies=[Depends(require_csrf)])
def delete_profile(pid:str,s:Store=Depends(store)):return profile_delete(s,pid)

@router.post("/requests",dependencies=[Depends(require_csrf)],status_code=201)
def create(req:JobRequest,s:Store=Depends(store)): return s.create(req)

@router.get("/requests")
def listing(kind:Literal["extractor","analyzer"],s:Store=Depends(store)): return {"requests":s.list(kind)}

@router.post("/requests/{job}/intake",dependencies=[Depends(require_csrf)],status_code=202)
def intake(job:str,tasks:BackgroundTasks,s:Store=Depends(store)):
    row=s.get(job)
    if row["state"] not in ("awaiting_input","staging","failed") or (row["state"]=="failed" and not row["message"].startswith("Drive intake:")):
        raise HTTPException(409,"Intake not available in this state")
    if not Bridge().available():
        raise HTTPException(503,"Drive intake bridge unavailable")
    tasks.add_task(stage,s,job)
    return {"accepted":True}

@router.get("/requests/{job}")
def detail(job:str,s:Store=Depends(store)): return s.get(job)

@router.post("/requests/{job}/cancel",dependencies=[Depends(require_csrf)])
def cancel(job:str,s:Store=Depends(store)): return s.cancel(job)

@router.get("/requests/{job}/batch")
def batch(job:str,s:Store=Depends(store)):
    from .batch import members
    return {"requests":members(s,job)}

@router.get("/requests/{job}/review")
def review(job:str,s:Store=Depends(store)): return get_review(s,job)

@router.post("/requests/{job}/review",dependencies=[Depends(require_csrf)])
def approve_review(job:str,value:Approval,s:Store=Depends(store)): return approve(s,job,value)

@router.get("/requests/{job}/outputs")
def outputs(job:str,s:Store=Depends(store)): return {"outputs":s.output_list(job)}

@router.get("/requests/{job}/outputs/{name}")
def download(job:str,name:str,preview:bool=False,s:Store=Depends(store)):
    path,row=s.output_path(job,name)
    # Only allow inline playback for verified MP4; all other types are attachment.
    inline=preview and row["media_type"]=="video/mp4"
    return FileResponse(path,media_type="video/mp4" if row["media_type"]=="video/mp4" else "application/octet-stream",
        filename=name,content_disposition_type="inline" if inline else "attachment",
        headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})
