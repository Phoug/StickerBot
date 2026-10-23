import asyncio
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from backend.config import DATA_DIR, MAX_SOURCE_SIZE, SOURCE_TTL
from backend.routers.stickers import telegram, update_pack, user_operation
from backend.security import mini_app_user
from backend.services.media.downloader import DownloadFailed, _ydl_opts
from backend.services.media.sticker_converter import StickerConversionError
from backend.services.media.studio_renderer import normalize, render
from backend.storage import database, owned_pack

router = APIRouter(prefix="/api/studio", tags=["Video editor"])
_processing = asyncio.Semaphore(2)
SOCIAL_HOSTS = {"youtube.com", "youtu.be", "instagram.com", "tiktok.com", "vk.com", "vkvideo.ru", "twitter.com", "x.com", "reddit.com", "v.redd.it", "facebook.com", "fb.watch", "vimeo.com", "rutube.ru", "ok.ru"}

class SourceURL(BaseModel):
    url: str = Field(max_length=2048)

class Edit(BaseModel):
    source_id: str
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    shape: Literal["square", "rounded", "circle"] = "square"
    zoom: float = Field(default=1, ge=1, le=3, allow_inf_nan=False)
    x: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    y: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)

class Publish(BaseModel):
    render_id: str
    emoji: str = Field(min_length=1, max_length=32)

def cleanup_expired():
    with database() as db:
        rows = db.execute("SELECT id,path FROM media WHERE created_at<?", (time.time() - SOURCE_TTL,)).fetchall()
        for row in rows:
            Path(row["path"]).unlink(missing_ok=True)
            db.execute("DELETE FROM media WHERE id=?", (row["id"],))


async def maintain_media():
    while True:
        await run_in_threadpool(cleanup_expired)
        await asyncio.sleep(300)

def register(path, user_id, kind, duration):
    media_id = uuid.uuid4().hex
    folder = DATA_DIR / "media"
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / (media_id + path.suffix)
    shutil.move(str(path), destination)
    with database() as db:
        db.execute("INSERT INTO media(id,user_id,path,kind,created_at,duration) VALUES (?,?,?,?,?,?)",
                   (media_id, user_id, str(destination), kind, time.time(), duration))
    return {"id": media_id, "duration": duration}

def owned_media(media_id, user_id, kind=None):
    with database() as db:
        row = db.execute("SELECT * FROM media WHERE id=? AND user_id=?", (media_id, user_id)).fetchone()
    if not row or row["created_at"] < time.time() - SOURCE_TTL or not Path(row["path"]).is_file():
        raise HTTPException(404, "Видео не найдено или истёк срок хранения. Загрузите его заново.")
    if kind and row["kind"] != kind:
        raise HTTPException(422, "Некорректный тип файла")
    return dict(row)

def prepare(source, folder, user_id):
    output = Path(folder) / "source.mp4"
    duration = normalize(source, output)
    return register(output, user_id, "source", duration)

@router.post("/upload", status_code=201)
async def upload(video: UploadFile = File(...), user=Depends(mini_app_user)):
    try:
        async with user_operation(user["id"]), _processing:
            cleanup_expired()
            with tempfile.TemporaryDirectory(prefix="sticker_upload_") as folder:
                source = Path(folder) / "upload"
                size = 0
                with source.open("wb") as target:
                    while chunk := await video.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_SOURCE_SIZE:
                            raise HTTPException(413, "Видео должно быть не больше 50 МБ")
                        target.write(chunk)
                return await run_in_threadpool(prepare, source, folder, user["id"])
    except StickerConversionError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        await video.close()

def download_source(url, user_id):
    # A dedicated limited download; legacy bot downloads retain their own behavior.
    from yt_dlp import YoutubeDL
    with tempfile.TemporaryDirectory(prefix="sticker_link_") as folder:
        def limit(progress):
            if progress.get("downloaded_bytes", 0) > MAX_SOURCE_SIZE:
                raise DownloadFailed("Видео должно быть не больше 50 МБ")
        options = _ydl_opts("bv*[height<=1080]+ba/b[height<=1080]", str(Path(folder) / "download.%(ext)s"))
        options.update({"max_filesize": MAX_SOURCE_SIZE, "progress_hooks": [limit],
                        "match_filter": lambda info, *, incomplete=False: "Видео длиннее 10 минут" if (info.get("duration") or 0) > 600 else None,
                        "concurrent_fragment_downloads": 1, "retries": 1, "extractor_retries": 1})
        try:
            with YoutubeDL(options) as ydl:
                ydl.extract_info(url, download=True)
            files = list(Path(folder).glob("download.*"))
            files = [p for p in files if p.suffix == ".mp4"]
            if not files:
                raise DownloadFailed("Видео недоступно или превышает ограничения")
            source = files[0]
            if source.stat().st_size > MAX_SOURCE_SIZE:
                raise DownloadFailed("Видео должно быть не больше 50 МБ")
            return prepare(source, folder, user_id)
        except StickerConversionError:
            raise
        except Exception as exc:
            raise DownloadFailed("Не удалось скачать видео. Нужна публичная ссылка без авторизации; попробуйте загрузить файл из галереи.") from exc

@router.post("/link", status_code=201)
async def from_link(payload: SourceURL, user=Depends(mini_app_user)):
    try:
        url = urlparse(payload.url.strip())
        host = (url.hostname or "").lower()
        valid = url.scheme == "https" and not url.username and not url.password and url.port in {None, 443} and any(host == h or host.endswith("." + h) for h in SOCIAL_HOSTS)
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(422, "Вставьте HTTPS-ссылку на видео из поддерживаемой соцсети")
    try:
        async with user_operation(user["id"]), _processing:
            cleanup_expired()
            return await run_in_threadpool(download_source, payload.url.strip(), user["id"])
    except (StickerConversionError, DownloadFailed) as exc:
        raise HTTPException(422, str(exc)) from exc

@router.get("/media/{media_id}")
async def get_media(media_id: str, user=Depends(mini_app_user)):
    media = owned_media(media_id, user["id"])
    return FileResponse(media["path"], media_type="video/mp4" if media["kind"] == "source" else "video/webm",
                        headers={"Cache-Control": "private, no-store"})

@router.post("/render", status_code=201)
async def render_sticker(payload: Edit, user=Depends(mini_app_user)):
    async with user_operation(user["id"]), _processing:
        source = owned_media(payload.source_id, user["id"], "source")
        with tempfile.TemporaryDirectory(prefix="sticker_render_") as folder:
            output = Path(folder) / "sticker.webm"
            try:
                await run_in_threadpool(render, source["path"], output, payload.start, payload.end, payload.shape, payload.zoom, payload.x, payload.y)
                return register(output, user["id"], "render", payload.end - payload.start)
            except StickerConversionError as exc:
                raise HTTPException(422, str(exc)) from exc

@router.post("/packs/{pack_id}/publish")
async def publish(pack_id: str, payload: Publish, user=Depends(mini_app_user)):
    async with user_operation(user["id"]):
        pack = owned_pack(pack_id, user["id"])
        media = owned_media(payload.render_id, user["id"], "render")
        if media["published_pack"]:
            if media["published_pack"] == pack_id:
                return owned_pack(pack_id, user["id"])
            raise HTTPException(409, "Этот стикер уже сохранён в другом наборе")
        if pack["status"] == "import_pending":
            raise HTTPException(409, "Сначала завершите импорт набора")
        uploaded = await telegram.upload(user["id"], Path(media["path"]))
        sticker = {"sticker": uploaded["file_id"], "format": "video", "emoji_list": [payload.emoji]}
        # Recover a createNewStickerSet response lost after Telegram accepted it.
        try:
            actual = await telegram.call("getStickerSet", name=pack["name"])
        except HTTPException as exc:
            if "STICKERSET_INVALID" not in str(exc.detail):
                raise
            actual = None
        if actual:
            already_added = any(s["file_unique_id"] == uploaded["file_unique_id"] for s in actual["stickers"])
            if not already_added:
                if len(actual["stickers"]) >= 120:
                    raise HTTPException(422, "В наборе уже 120 стикеров")
                await telegram.call("addStickerToSet", user_id=user["id"], name=pack["name"], sticker=sticker)
        else:
            await telegram.call("createNewStickerSet", user_id=user["id"], name=pack["name"], title=pack["title"], stickers=[sticker])
        actual = await telegram.call("getStickerSet", name=pack["name"])
        update_pack(pack_id, status="ready", count=len(actual["stickers"]), error=None)
        with database() as db:
            db.execute("UPDATE media SET published_pack=? WHERE id=?", (pack_id, payload.render_id))
        return owned_pack(pack_id, user["id"])
