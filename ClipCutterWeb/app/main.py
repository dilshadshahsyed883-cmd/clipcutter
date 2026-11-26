"""Independent ClipCutter Web foundation."""
from pathlib import Path
from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.auth import Principal, current_principal
from app.config import load_settings
from app.modules.admin.security import COOKIE, SESSION_COOKIE_MAX_AGE
from app.modules.admin.routes import router as admin_router
from app.modules.dashboard.routes import router as dashboard_router
from app.modules.extractor.routes import router as extractor_router

ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))

def create_app():
    app = FastAPI(title="ClipCutter Web", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = load_settings()
    app.state.identity_resolver = None
    app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
    app.include_router(admin_router)
    app.include_router(dashboard_router)
    app.include_router(extractor_router)

    @app.middleware("http")
    async def renew_cookie(request: Request, call_next):
        response = await call_next(request)
        token = getattr(request.state, "clipcutter_authenticated_token", None)
        if token and response.status_code < 400 and not any(
            v.startswith(COOKIE + "=") for v in response.headers.getlist("set-cookie")
        ):
            response.set_cookie(COOKIE, token, max_age=SESSION_COOKIE_MAX_AGE,
                                secure=True, httponly=True, samesite="lax", path="/")
        if not request.url.path.startswith(("/static/", "/dashboard/assets/")):
            response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.get("/healthz")
    async def health():
        return {"ok": True, "service": "clipcutter-web"}

    @app.get("/")
    async def home(_: Principal = Depends(current_principal)):
        return RedirectResponse("/dashboard", status_code=303)

    @app.get("/api/v1/session")
    async def session(principal: Principal = Depends(current_principal)):
        return {"username": principal.username, "is_admin": principal.is_admin,
                "clipcutter_granted": True}

    def studio(request, principal, key, title, description):
        return templates.TemplateResponse(request=request, name="page.html", context={
            "principal": principal, "page": {"area": "studio", "key": key, "title": title,
                                             "description": description}})

    @app.get("/studio/extractor")
    async def extractor(request: Request, principal: Principal = Depends(current_principal)):
        return studio(request, principal, "extractor", "Clip Extractor", "Extract clips from source videos.")

    @app.get("/studio/analyzer")
    async def analyzer(request: Request, principal: Principal = Depends(current_principal)):
        return studio(request, principal, "analyzer", "Person Analyzer", "Analyze and group people in source videos.")

    return app

app = create_app()
