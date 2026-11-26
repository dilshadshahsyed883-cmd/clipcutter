"""Authenticated read-only host dashboard."""
from pathlib import Path
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from app.auth import Principal, current_principal
from .system_metrics import system_dashboard_snapshot

router = APIRouter()
_root = Path(__file__).parent
_templates = Jinja2Templates(directory=str(_root / "templates"))
_NO_STORE = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}

@router.get("/dashboard")
async def dashboard(request: Request, principal: Principal = Depends(current_principal)):
    return _templates.TemplateResponse(request=request, name="dashboard.html",
        context={"principal": principal}, headers=_NO_STORE)

@router.get("/api/v1/dashboard/system")
async def system_dashboard(_principal: Principal = Depends(current_principal)):
    try:
        payload = await run_in_threadpool(system_dashboard_snapshot)
    except Exception:
        logging.getLogger(__name__).exception("Host metrics unavailable")
        raise HTTPException(503, "System monitoring unavailable", headers=_NO_STORE) from None
    return JSONResponse(payload, headers=_NO_STORE)

@router.get("/dashboard/assets/dashboard.css")
async def dashboard_css():
    return FileResponse(_root / "static/dashboard.css", media_type="text/css")

@router.get("/dashboard/assets/dashboard.js")
async def dashboard_js():
    return FileResponse(_root / "static/dashboard.js", media_type="application/javascript")
