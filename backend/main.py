import logging
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.routers import media, stickers, system, studio
from backend.storage import initialize

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("video_backend")


@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info("Backend started")
    initialize()
    cleanup_task = asyncio.create_task(studio.maintain_media())
    logger.info("Mini App authentication enabled")
    yield
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("Backend stopped")


app = FastAPI(
    title="Video Extractor API",
    version="2.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

app.include_router(system.router)
app.include_router(media.router)
app.include_router(studio.router)
app.include_router(stickers.router)

PROJECT_DIR = Path(__file__).resolve().parent.parent
webapp_dir = PROJECT_DIR / "app" / "webapp"

if webapp_dir.is_dir():
    app.mount(
        "/app",
        StaticFiles(directory=str(webapp_dir), html=True),
        name="webapp",
    )
else:
    logger.warning("Mini App directory not found: %s", webapp_dir)
