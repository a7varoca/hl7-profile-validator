import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from fastapi import Request
from pathlib import Path

from app.config import settings
from app.routers import profiles, reference, validator, backup, hl7standard
from app.services import db as profile_db
from app.services import profile_service


def _warm_cache() -> None:
    """Pre-load all profiles into the in-memory cache."""
    try:
        summaries = profile_service.list_profiles()
        for s in summaries:
            try:
                profile_service.get_profile(s.id)
            except Exception:
                pass
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    profile_db.init_db()
    threading.Thread(target=_warm_cache, daemon=True).start()
    yield


app = FastAPI(
    title=settings.app_title,
    description="HL7 v2.x Profile Editor & Validator",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(profiles.router, prefix="/api/profiles", tags=["Profiles"])
app.include_router(reference.router, prefix="/api/reference", tags=["Reference"])
app.include_router(validator.router, prefix="/api/validate", tags=["Validator"])
app.include_router(backup.router, prefix="/api/backup", tags=["Backup"])
app.include_router(hl7standard.router, prefix="/api/hl7standard", tags=["HL7Standard"])

static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.get("/", response_class=FileResponse, include_in_schema=False)
def serve_spa():
    return str(static_dir / "index.html")


@app.get("/{full_path:path}", response_class=FileResponse, include_in_schema=False)
def spa_fallback(full_path: str):
    index = static_dir / "index.html"
    if index.exists():
        return str(index)
    return FileResponse(str(index))
