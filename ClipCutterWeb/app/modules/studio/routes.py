from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from typing import Literal
from app.auth import Principal,current_principal
from app.modules.admin.security import require_csrf
from .contracts import JobRequest
from .store import Store

router=APIRouter(prefix="/api/v1/studio")
def store(principal:Principal=Depends(current_principal)):
    return Store(principal.username)

@router.get("/capabilities")
def capabilities(_:Principal=Depends(current_principal)):
    return {"input_intake":False,"worker_dispatch":False,"output_receiver":False,
            "request_storage":True,"message":"Requests are saved; Drive intake and worker transport are not connected."}

@router.post("/requests",dependencies=[Depends(require_csrf)],status_code=201)
def create(req:JobRequest,s:Store=Depends(store)): return s.create(req)

@router.get("/requests")
def listing(kind:Literal["extractor","analyzer"],s:Store=Depends(store)): return {"requests":s.list(kind)}

@router.get("/requests/{job}")
def detail(job:str,s:Store=Depends(store)): return s.get(job)

@router.post("/requests/{job}/cancel",dependencies=[Depends(require_csrf)])
def cancel(job:str,s:Store=Depends(store)): return s.cancel(job)

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
