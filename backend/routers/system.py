from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"ok": True, "service": "video-extractor"}


@router.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/app/", status_code=307)
