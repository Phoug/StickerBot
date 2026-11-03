import logging
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.routers import media, stickers, system, studio
from backend import storage
from backend.config import BOT_TOKEN, API_SECRET_TOKEN
from backend.maintenance import exclusive_access
from backend.observability import RuntimeMiddleware
from backend.services.bot_api import telegram
from backend.services.processing import run_blocking
from common.logging import configure_logging

configure_logging(BOT_TOKEN, API_SECRET_TOKEN)
logger = logging.getLogger("video_backend")


@asynccontextmanager
async def lifespan(application: FastAPI):
    with exclusive_access(storage.DATA_DIR):
        storage.initialize()
        await run_blocking(studio.cleanup_expired)
        cleanup_task = asyncio.create_task(studio.maintain_media())
        logger.info("Backend started; Mini App authentication enabled")
        try:
            yield
        finally:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            await telegram.close()
            logger.info("Backend stopped")


app = FastAPI(
    title="Video Extractor API",
    version="2.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.add_middleware(RuntimeMiddleware)

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
