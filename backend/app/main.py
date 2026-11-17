import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from . import seed
from .agents.llm import provider_name
from .config import get_settings
from .db import Base, engine, SessionLocal
from .models import AgentRun
from .routers import auth, engagements, controls, audit_log

settings = get_settings()
logging.basicConfig(level=logging.INFO,
                    format='{"t":"%(asctime)s","lvl":"%(levelname)s","log":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("controllens")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed.run(db)
        # Runs interrupted by a restart can never finish; mark them failed
        stuck = db.query(AgentRun).filter(AgentRun.status.in_(("queued", "running"))).all()
        for r in stuck:
            r.status, r.error = "failed", "Interrupted by server restart"
        db.commit()
    log.info("started; AI provider=%s model=%s", provider_name(), settings.llm_model)
    yield


app = FastAPI(title=f"{settings.app_name} API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id", uuid.uuid4().hex[:12])
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:  # noqa: BLE001
        log.exception("unhandled error rid=%s path=%s", rid, request.url.path)
        response = JSONResponse({"detail": "Internal error", "request_id": rid}, status_code=500)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
        log.info("rid=%s %s %s %s %.0fms", rid, request.method, request.url.path, response.status_code,
                 (time.perf_counter() - start) * 1000)
    return response


for r in (auth.router, engagements.router, controls.router, audit_log.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "ai_provider": provider_name(), "model": settings.llm_model}


# Serve the built front end (frontend/dist) from the same server in production
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        f = DIST / full_path
        if full_path and f.is_file() and DIST in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
