from fastapi import APIRouter, Depends, HTTPException, File, Form, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from .performance import report
from starlette.background import BackgroundTask
from . import identity_library as lib, output_names as names
from typing import Literal
from app.auth import Principal,current_principal
from app.modules.admin.security import require_csrf
from .contracts import JobRequest
from .store import Store
from .intake import Bridge
from .scheduler import Control
from .lifecycle import LifecycleError
from . import youtube
from .review import Approval, get_review, approve, source_preview
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
def upload(payload:str=Form(...),images:list[UploadFile]=File(default=[]),s:Store=Depends(store)):
    import json
    try:data=json.loads(payload)
    except ValueError:raise HTTPException(422,"Invalid upload payload") from None
    if isinstance(data,dict) and data.get("library_action"):
        return lib.upload_action(s,data,images)
    return create_uploaded(s,payload,images)

@router.get("/identities")
def identities(s:Store=Depends(store)):return {"identities":lib.listing(s)}

@router.post("/identities",dependencies=[Depends(require_csrf)],status_code=201)
def add_identity(data:lib.Name,s:Store=Depends(store)):return lib.create(s,data.name)

@router.patch("/identities/{identity}",dependencies=[Depends(require_csrf)])
def rename_identity(identity:str,data:lib.Name,s:Store=Depends(store)):return lib.rename(s,identity,data.name)

@router.delete("/identities/{identity}",dependencies=[Depends(require_csrf)])
def delete_identity(identity:str,s:Store=Depends(store)):return lib.delete(s,identity)

@router.get("/identities/{identity}/images/{image}")
def image_preview(identity:str,image:str,s:Store=Depends(store)):
    p,row=lib.image_path(s,identity,image)
    return FileResponse(p,media_type={".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png",".webp":"image/webp"}[p.suffix],headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})

@router.patch("/identities/{identity}/images/{image}",dependencies=[Depends(require_csrf)])
def rename_image(identity:str,image:str,data:lib.Name,s:Store=Depends(store)):return lib.rename_image(s,identity,image,data.name)

@router.post("/identities/{identity}/images/delete",dependencies=[Depends(require_csrf)])
def delete_images(identity:str,data:lib.Selection,s:Store=Depends(store)):return lib.delete_images(s,identity,data.ids)

@router.post("/identity-requests",dependencies=[Depends(require_csrf)],status_code=201)
def identity_request(data:lib.IdentityRequest,s:Store=Depends(store)):return lib.create_request(s,data)

@router.get("/requests")
def listing(kind:Literal["extractor","analyzer"],s:Store=Depends(store)):
    rows=s.list(kind)
    with s.connect() as c:
        snapshots={r["job_id"]:dict(r) for r in c.execute("SELECT job_id,identity_id,label FROM request_identities")}
    for row in rows:
        if row["id"] in snapshots:
            x=snapshots[row["id"]];row.update(identity_id=x["identity_id"],identity_name=x["label"])
    return {"requests":rows,"paused":Control(s).snapshot()["paused"]}

@router.post("/queue/{action}",dependencies=[Depends(require_csrf)])
def queue_action(action:Literal["pause","resume"],s:Store=Depends(store)):
    try:return {"paused":Control(s).set_paused(action=="pause")["paused"]}
    except LifecycleError as e:raise HTTPException(409,str(e)) from None

@router.post("/requests/{job}/intake",dependencies=[Depends(require_csrf)],status_code=202)
def intake(job:str,s:Store=Depends(store)):
    # Requeue only a failed intake. Never start another active transfer from HTTP.
    with s.admission():
        row=s.get(job)
        if row["state"]!="failed" or not row["message"].startswith(("Drive intake:","YouTube intake:")):
            raise HTTPException(409,"Retry is available only for failed input downloads")
        s.transition(job,"failed","awaiting_input","Queued for input retry")
    return {"accepted":True}

@router.get("/performance-report")
def performance_report(hours:Literal["1","24","168"]="24",s:Store=Depends(store)):
    return PlainTextResponse(report(s,int(hours)),headers={"Content-Disposition":"attachment; filename=clipcutter-performance.txt",
        "Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})

@router.get("/requests/{job}")
def detail(job:str,s:Store=Depends(store)): return s.get(job)

@router.post("/requests/{job}/cancel",dependencies=[Depends(require_csrf)])
def cancel(job:str,s:Store=Depends(store)):
    with s.admission():
        row=s.cancel(job)
        discard_uploads(s,job)
        return row

@router.post("/requests/{job}/gpu/{action}",dependencies=[Depends(require_csrf)],status_code=202)
def gpu_action(job:str,action:Literal["cancel","retry"],s:Store=Depends(store)):
    return s.gpu_command(job,action)

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

@router.get("/requests/{job}/review/source")
def review_source(job:str,s:Store=Depends(store)):
    path,media=source_preview(s,job)
    return FileResponse(path,media_type=media,headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})

@router.post("/requests/{job}/review",dependencies=[Depends(require_csrf)])
def approve_review(job:str,value:Approval,s:Store=Depends(store)): return approve(s,job,value)

@router.get("/requests/{job}/outputs")
def outputs(job:str,s:Store=Depends(store)): return names.visible(s,job)

@router.post("/requests/{job}/outputs/manage",dependencies=[Depends(require_csrf)])
def manage_outputs(job:str,data:names.Change,s:Store=Depends(store)):return names.change(s,job,data)

@router.post("/requests/{job}/outputs/zip",dependencies=[Depends(require_csrf)])
def zip_outputs(job:str,data:lib.Selection,s:Store=Depends(store)):
    path=names.make_zip(s,job,data.ids)
    return FileResponse(path,media_type="application/zip",filename="clips-"+job[:8]+".zip",background=BackgroundTask(path.unlink,missing_ok=True))

@router.get("/requests/{job}/outputs/{name}")
def download(job:str,name:str,preview:bool=False,s:Store=Depends(store)):
    path,row,display=names.download(s,job,name)
    # Only allow inline playback for verified MP4; all other types are attachment.
    inline=preview and row["media_type"]=="video/mp4"
    return FileResponse(path,media_type="video/mp4" if row["media_type"]=="video/mp4" else "application/octet-stream",
        filename=display,content_disposition_type="inline" if inline else "attachment",
        headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})
