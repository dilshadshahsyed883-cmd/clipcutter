from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, File, Form, UploadFile
from fastapi.responses import FileResponse
from typing import Literal
from app.auth import Principal,current_principal
from app.modules.admin.security import require_csrf
from .contracts import JobRequest
from .store import Store
from .intake import Bridge, stage
from . import youtube
from .review import Approval, get_review, approve
from .uploads import create_uploaded, discard_uploads

router=APIRouter(prefix="/api/v1/studio")
def store(principal:Principal=Depends(current_principal)):
    return Store(principal.username)

@router.get("/capabilities")
def capabilities(_:Principal=Depends(current_principal)):
    available=Bridge().available()
    yt=youtube.available()
    return {"input_intake":available,"youtube_intake":yt,"worker_dispatch":False,"output_receiver":False,
            "request_storage":True,"message":("Drive intake available." if available else "Drive intake bridge unavailable.")+
            (" YouTube runtime configured (authentication verified on download)." if yt else " YouTube intake not configured.")+
            " GPU transport not connected."}

@router.post("/requests",dependencies=[Depends(require_csrf)],status_code=201)
def create(req:JobRequest,s:Store=Depends(store)):
    if req.settings.reference_uploads: raise HTTPException(422,"Use the reference upload endpoint")
    return s.create(req)

@router.post("/requests/upload",dependencies=[Depends(require_csrf)],status_code=201)
def upload(payload:str=Form(...),images:list[UploadFile]=File(...),s:Store=Depends(store)):
    return create_uploaded(s,payload,images)

@router.get("/requests")
def listing(kind:Literal["extractor","analyzer"],s:Store=Depends(store)): return {"requests":s.list(kind)}

@router.post("/requests/{job}/intake",dependencies=[Depends(require_csrf)],status_code=202)
def intake(job:str,tasks:BackgroundTasks,s:Store=Depends(store)):
    row=s.get(job)
    if row["state"] not in ("awaiting_input","staging","failed") or (row["state"]=="failed" and not row["message"].startswith(("Drive intake:","YouTube intake:"))):
        raise HTTPException(409,"Intake not available in this state")
    is_youtube=row["input"]["source_kind"]=="youtube"
    if is_youtube and not youtube.available():
        raise HTTPException(503,"YouTube runtime or private cookies not configured")
    if (not is_youtube or row["settings"].get("reference_link")) and not Bridge().available():
        raise HTTPException(503,"Drive intake bridge unavailable")
    tasks.add_task(stage,s,job)
    return {"accepted":True}

@router.get("/requests/{job}")
def detail(job:str,s:Store=Depends(store)): return s.get(job)

@router.post("/requests/{job}/cancel",dependencies=[Depends(require_csrf)])
def cancel(job:str,s:Store=Depends(store)):
    with s.admission():
        row=s.cancel(job)
        discard_uploads(s,job)
        return row

@router.delete("/requests/{job}",dependencies=[Depends(require_csrf)])
def delete(job:str,s:Store=Depends(store)):
    with s.admission():
        row=s.delete_request(job)
        discard_uploads(s,job)
        return row

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
