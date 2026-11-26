"""Authenticated option validation only. No CPU/GPU jobs admitted yet."""
from fastapi import APIRouter, Depends
from app.auth import Principal, current_principal
from app.modules.admin.security import require_csrf
from worker.extractor.contracts import Options

router=APIRouter(prefix="/api/v1/extractor")

@router.get("/capabilities")
def capabilities(_: Principal=Depends(current_principal)):
    return {"dispatch_enabled":False,"review_enabled":False,"local_preview":True,
            "options":Options().model_dump(),
            "message":"Worker transport is not connected. No jobs are accepted."}

@router.post("/options",dependencies=[Depends(require_csrf)])
def validate_options(options:Options,_:Principal=Depends(current_principal)):
    return {"options":options.model_dump(),"dispatch_enabled":False}
