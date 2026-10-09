import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.routers import media, stickers, system, telegram
from backend.services.telethon_service import disconnect_telegram_clients
from backend.config import TELETHON_SESSIONS_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("video_backend")


@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info("Backend started")
    logger.info("Telethon sessions directory: %s", TELETHON_SESSIONS_DIR)
    logger.info("Mini App authentication enabled")
    yield
    logger.info("Shutting down Telegram clients...")
    await disconnect_telegram_clients()
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
app.include_router(telegram.router)
app.include_router(stickers.router)

webapp_dir = Path(__file__).resolve().parent / "webapp"
if webapp_dir.is_dir():
    app.mount(
        "/app",
        StaticFiles(directory=str(webapp_dir), html=True),
        name="webapp",
    )
