from collections import Counter
from contextlib import asynccontextmanager
import logging
from time import perf_counter
from uuid import uuid4
from threading import Lock
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.core.config import settings
from app.core.database import engine
from app.core.vault import vault
from app.core.body_limit import BodyLimitMiddleware
from app.modules import routers
from app.shared.dependencies import require_admin

metrics = Counter()
metrics_lock = Lock()
logger = logging.getLogger("uvicorn.error.health")

@asynccontextmanager
async def lifespan(app):
    if settings.environment not in ("development", "staging", "production"):
        raise RuntimeError("Invalid environment")
    if settings.environment != "development" and not settings.database_url.startswith("postgresql"):
        raise RuntimeError("PostgreSQL is required outside development")
    if settings.environment != "development" and any(not x.startswith("https://") for x in settings.cors_origins):
        raise RuntimeError("HTTPS origins are required outside development")
    vault()
    yield

app = FastAPI(title="Personal Health Assistant API", version="0.5.0", lifespan=lifespan)
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"])

@app.middleware("http")
async def monitor(request, call_next):
    request_id = str(uuid4())
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception as error:
        logger.error("request_failed id=%s type=%s", request_id, type(error).__name__)
        response = JSONResponse({"detail": "Internal error", "request_id": request_id}, status_code=500)
    route = request.scope.get("route")
    label = getattr(route, "path", "unmatched")
    with metrics_lock:
        metrics[(request.method, label, response.status_code)] += 1
    response.headers["X-Request-ID"] = request_id
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    logger.info("request id=%s method=%s route=%s status=%s duration_ms=%.1f",
                request_id, request.method, label, response.status_code, (perf_counter()-started)*1000)
    return response

for router in routers:
    app.include_router(router, prefix="/api/v1")

@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "service": "api"}

@app.get("/ready", tags=["system"])
def ready():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT id FROM users LIMIT 1"))
        vault()
    except Exception:
        raise HTTPException(503, "Database migration or storage configuration is not ready")
    return {"status": "ready"}

@app.get("/api/v1/admin/metrics", tags=["admin"])
def get_metrics(user=Depends(require_admin)):
    with metrics_lock:
        snapshot = list(metrics.items())
    return {"scope": "current_process_since_start", "requests": [
        {"method": key[0], "route": key[1], "status": key[2], "count": count} for key, count in snapshot]}
