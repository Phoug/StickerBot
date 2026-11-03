import sqlite3
import time
from fastapi import APIRouter, HTTPException, Security
from fastapi.responses import RedirectResponse, Response
from backend.config import CLEANUP_INTERVAL
from backend.security import verify_api_key
from backend.storage import check_ready

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"ok": True, "service": "video-extractor"}


@router.get("/ready")
def ready() -> dict:
    from backend.services import media_store
    try:
        check_ready()
    except (OSError, sqlite3.Error):
        raise HTTPException(503, "Storage is not ready") from None
    if media_store.cleanup_last_error or time.time() - media_store.cleanup_last_success > CLEANUP_INTERVAL * 3:
        raise HTTPException(503, "Media maintenance is not ready")
    return {"ok": True, "service": "video-extractor"}


@router.get("/metrics", dependencies=[Security(verify_api_key)])
def metrics():
    from backend.observability import metrics_text
    return Response(metrics_text(), media_type="text/plain; version=0.0.4")


@router.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/app/", status_code=307)
