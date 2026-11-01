import aiohttp
import asyncio
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from emoji import is_emoji
from starlette.concurrency import run_in_threadpool
from backend.services.file_service import cleanup_files
from backend.services.media.sticker_preview import make_video_preview

from backend.config import DATA_DIR, MAX_SOURCE_SIZE, SOURCE_TTL
from backend.routers.stickers import telegram, update_pack, user_operation, find_sticker
from backend.security import mini_app_user
from backend.services.media.downloader import DownloadFailed, _ydl_opts
from backend.services.media.sticker_converter import StickerConversionError
from backend.services.media.studio_renderer import normalize, render, probe
from backend.services.media.photo_renderer import normalize_photo, render_photo
from backend.services.media.preview_cache import cached_media
from backend.storage import database, owned_pack
from backend.services.media.photo_links import validate_url, resolve_tiktok, fetch_public, MAX_BYTES

router = APIRouter(prefix="/api/studio", tags=["Sticker editor"])
_processing = asyncio.Semaphore(2)
_edit_sources = {}
_link_sources = {}

def remember_link(key, result):
    if len(_link_sources)>=64: _link_sources.pop(next(iter(_link_sources)))
    _link_sources[key] = (time.monotonic()+300,result)
    return result

SOCIAL_HOSTS = {"youtube.com", "youtu.be", "instagram.com", "tiktok.com", "vk.com", "vkvideo.ru", "twitter.com", "x.com", "reddit.com", "v.redd.it", "facebook.com", "fb.watch", "vimeo.com", "rutube.ru", "ok.ru"}

class SourceURL(BaseModel):
    url: str = Field(max_length=2048)

class Edit(BaseModel):
    source_id: str
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    shape: Literal["original", "square", "rounded", "circle"] = "original"
    zoom: float = Field(default=1, ge=1, le=3, allow_inf_nan=False)
    x: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    y: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)

class Publish(BaseModel):
    render_id: str
    replace_id: str | None = None
    emoji: str = Field(min_length=1, max_length=32)

    @field_validator("emoji")
    @classmethod
    def valid_emoji(cls, value):
        value = value.strip()
        if not is_emoji(value):
            raise ValueError("Введите один эмодзи")
        return value

def cleanup_expired():
    with database() as db:
        rows = db.execute("SELECT id,path FROM media WHERE created_at<?", (time.time() - SOURCE_TTL,)).fetchall()
        for row in rows:
            Path(row["path"]).unlink(missing_ok=True)
            Path(row["path"]).with_suffix(".original.webm").unlink(missing_ok=True)
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
        raise HTTPException(404, "Файл не найден или истёк срок хранения. Загрузите его заново.")
    if kind and row["kind"] != kind:
        raise HTTPException(422, "Некорректный тип файла")
    return dict(row)

def prepare(source, folder, user_id, photo=False):
    if photo:
        output = Path(folder) / "source.png"
        width, height = normalize_photo(source, output)
        return {**register(output, user_id, "photo", 0), "kind": "photo", "width": width, "height": height}
    output = Path(folder) / "source.mp4"
    duration = normalize(source, output)
    return {**register(output, user_id, "source", duration), "kind": "video"}

@router.post("/upload", status_code=201)
async def upload(video: UploadFile = File(...), user=Depends(mini_app_user)):
    try:
        async with user_operation(user["id"]), _processing:
            await run_in_threadpool(cleanup_expired)
            with tempfile.TemporaryDirectory(prefix="sticker_upload_") as folder:
                source = Path(folder) / "upload"
                size = 0
                with source.open("wb") as target:
                    while chunk := await video.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_SOURCE_SIZE:
                            raise HTTPException(413, "Файл должен быть не больше 50 МБ")
                        target.write(chunk)
                return await run_in_threadpool(prepare, source, folder, user["id"], (video.content_type or "").startswith("image/"))
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
        url = validate_url(payload.url.strip())
        host = url.hostname.lower()
        social = any(host == h or host.endswith("." + h) for h in SOCIAL_HOSTS)
        async with user_operation(user["id"]), _processing:
            await run_in_threadpool(cleanup_expired)
            key = (user["id"],payload.url.strip())
            previous = _link_sources.get(key)
            if previous and previous[0]>time.monotonic():
                result = previous[1]
                try:
                    for media in result.get("photos",[result]): owned_media(media["id"],user["id"])
                    return result
                except HTTPException:
                    _link_sources.pop(key,None)
            photos = None
            if (host == "tiktok.com" or host.endswith(".tiktok.com")) and "/video/" not in url.path:
                try:
                    photos = await resolve_tiktok(payload.url.strip())
                except (StickerConversionError, aiohttp.ClientError, TimeoutError, OSError):
                    if "/photo/" in url.path:
                        raise
                    photos = []
            if not social:
                photos = [payload.url.strip()]
            if photos:
                results = []
                total = 0
                with tempfile.TemporaryDirectory(prefix="sticker_photos_") as folder:
                    try:
                        async with asyncio.timeout(120):
                            stored = 0
                            for index, photo_url in enumerate(photos):
                                data, _ = await fetch_public(photo_url, limit=MAX_BYTES-total, image=True)
                                total += len(data)
                                path = Path(folder) / (str(index)+".image")
                                path.write_bytes(data)
                                results.append(await run_in_threadpool(prepare, path, folder, user["id"], True))
                                stored += Path(owned_media(results[-1]["id"],user["id"])["path"]).stat().st_size
                                if stored > MAX_BYTES:
                                    raise StickerConversionError("Подготовленные фото занимают больше 50 МБ")
                        return remember_link(key, results[0] if len(results)==1 else {"kind":"album", "photos":results})
                    except BaseException:
                        # A failed carousel never leaves half an import behind.
                        with database() as db:
                            for result in results:
                                row = db.execute("SELECT path FROM media WHERE id=? AND user_id=?", (result["id"],user["id"])).fetchone()
                                if row: Path(row["path"]).unlink(missing_ok=True)
                                db.execute("DELETE FROM media WHERE id=? AND user_id=?", (result["id"],user["id"]))
                        raise
            return remember_link(key, await run_in_threadpool(download_source, payload.url.strip(), user["id"]))
    except (StickerConversionError, DownloadFailed, aiohttp.ClientError, TimeoutError, OSError) as exc:
        message = str(exc) if isinstance(exc, (StickerConversionError, DownloadFailed)) else "Не удалось загрузить файл по ссылке. Попробуйте галерею."
        raise HTTPException(422, message) from exc

@router.get("/media/{media_id}")
async def get_media(media_id: str, preview: bool = False, thumbnail: bool = False, user=Depends(mini_app_user)):
    media = owned_media(media_id, user["id"])
    if thumbnail and media["kind"] == "photo":
        async def photo_thumbnail():
            def encode():
                from io import BytesIO
                from PIL import Image
                with Image.open(media["path"]) as image:
                    image.thumbnail((180,180))
                    output = BytesIO()
                    image.save(output, "WEBP", quality=75)
                    return output.getvalue(), "image/webp"
            async with _processing:
                return await run_in_threadpool(encode)
        data, mime = await cached_media((user["id"], media_id, "thumbnail"), photo_thumbnail)
        return Response(data, media_type=mime, headers={"Cache-Control":"private, no-store"})
    if preview and media["kind"] == "render":
        async def preview_bytes():
            async with _processing:
                try:
                    output = await run_in_threadpool(make_video_preview, Path(media["path"]).read_bytes())
                    try:
                        return output.read_bytes(), "video/mp4"
                    finally:
                        cleanup_files(output.parent)
                except StickerConversionError as exc:
                    raise HTTPException(422, "Не удалось подготовить предпросмотр") from exc
        data, mime = await cached_media((user["id"], media_id, "render-preview"), preview_bytes)
        return Response(data, media_type=mime, headers={"Cache-Control": "private, no-store"})
    mime = {"source": "video/mp4", "photo": "image/png", "render_photo": "image/webp", "render": "video/webm"}[media["kind"]]
    return FileResponse(media["path"], media_type=mime,
                        headers={"Cache-Control": "private, no-store"})

@router.post("/render", status_code=201)
async def render_sticker(payload: Edit, user=Depends(mini_app_user)):
    async with user_operation(user["id"]), _processing:
        source = owned_media(payload.source_id, user["id"])
        if source["kind"] not in {"source", "photo"}:
            raise HTTPException(422, "Некорректный тип исходника")
        photo = source["kind"] == "photo"
        with tempfile.TemporaryDirectory(prefix="sticker_render_") as folder:
            output = Path(folder) / ("sticker.webp" if photo else "sticker.webm")
            try:
                if photo:
                    await run_in_threadpool(render_photo, source["path"], output, payload.shape, payload.zoom, payload.x, payload.y)
                else:
                    original = Path(source["path"]).with_suffix(".original.webm")
                    render_source = original if original.is_file() else source["path"]
                    await run_in_threadpool(render, render_source, output, payload.start, payload.end, payload.shape, payload.zoom, payload.x, payload.y)
                return {**register(output, user["id"], "render_photo" if photo else "render", 0 if photo else payload.end - payload.start), "kind": "photo" if photo else "video"}
            except StickerConversionError as exc:
                raise HTTPException(422, str(exc)) from exc

@router.post("/packs/{pack_id}/publish")
async def publish(pack_id: str, payload: Publish, user=Depends(mini_app_user)):
    async with user_operation(user["id"]):
        pack = owned_pack(pack_id, user["id"])
        media = owned_media(payload.render_id, user["id"])
        if media["kind"] not in {"render", "render_photo"}:
            raise HTTPException(422, "Сначала создайте стикер в редакторе")
        if media["published_pack"]:
            if media["published_pack"] == pack_id:
                return owned_pack(pack_id, user["id"])
            raise HTTPException(409, "Этот стикер уже сохранён в другом наборе")
        if pack["status"] == "import_pending":
            raise HTTPException(409, "Сначала завершите импорт набора")
        uploaded = await telegram.upload(user["id"], Path(media["path"]))
        sticker = {"sticker": uploaded["file_id"], "format": "static" if media["kind"] == "render_photo" else "video", "emoji_list": [payload.emoji]}
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
                if payload.replace_id:
                    old = find_sticker(actual, payload.replace_id)
                    await telegram.call("replaceStickerInSet", user_id=user["id"], name=pack["name"], old_sticker=old["file_id"], sticker=sticker)
                elif len(actual["stickers"]) >= 120:
                    raise HTTPException(422, "В наборе уже 120 стикеров")
                else:
                    await telegram.call("addStickerToSet", user_id=user["id"], name=pack["name"], sticker=sticker)
        else:
            if payload.replace_id:
                raise HTTPException(409, "Набор изменился. Откройте его заново.")
            await telegram.call("createNewStickerSet", user_id=user["id"], name=pack["name"], title=pack["title"], stickers=[sticker])
        actual = await telegram.call("getStickerSet", name=pack["name"])
        update_pack(pack_id, status="ready", count=len(actual["stickers"]), error=None)
        with database() as db:
            db.execute("UPDATE media SET published_pack=? WHERE id=?", (pack_id, payload.render_id))
        return owned_pack(pack_id, user["id"])


@router.post("/packs/{pack_id}/stickers/{sticker_id}/edit", status_code=201)
async def edit_existing(pack_id: str, sticker_id: str, user=Depends(mini_app_user)):
    async with user_operation(user["id"]), _processing:
        pack = owned_pack(pack_id, user["id"])
        actual = await telegram.call("getStickerSet", name=pack["name"])
        sticker = find_sticker(actual, sticker_id)
        if sticker.get("is_animated"):
            raise HTTPException(422, "Редактор поддерживает фото и видео. TGS-анимацию можно посмотреть в Telegram.")
        cache_key = (user["id"],pack_id,sticker_id,sticker["file_id"])
        previous = _edit_sources.get(cache_key)
        if previous:
            try:
                owned_media(previous["id"],user["id"])
                return previous
            except HTTPException:
                _edit_sources.pop(cache_key,None)
        data, _ = await cached_media((user["id"], sticker["file_id"]), lambda: telegram.file(sticker["file_id"]))
        with tempfile.TemporaryDirectory(prefix="sticker_edit_") as folder:
            source = Path(folder) / "original"
            source.write_bytes(data)
            try:
                if not sticker.get("is_video"):
                    result = await run_in_threadpool(prepare, source, folder, user["id"], True)
                    if len(_edit_sources)>=128: _edit_sources.pop(next(iter(_edit_sources)))
                    _edit_sources[cache_key] = result
                    return result
                # Use a composited H.264 copy in the browser and retain the
                # original VP9 with alpha for rendering. Both expire together.
                async def preview_bytes():
                    preview = await run_in_threadpool(make_video_preview, data)
                    try:
                        return preview.read_bytes(), "video/mp4"
                    finally:
                        cleanup_files(preview.parent)
                # Share the immutable MP4 already used by the sticker viewer.
                preview_data, _ = await cached_media((user["id"],sticker["file_id"],"mp4"),preview_bytes)
                preview = Path(folder)/"preview.mp4"
                preview.write_bytes(preview_data)
                duration = (await run_in_threadpool(probe, preview))[0]
                result = register(preview,user["id"],"source",duration)
                registered = owned_media(result["id"], user["id"])
                shutil.copyfile(source, Path(registered["path"]).with_suffix(".original.webm"))
                result = {**result, "kind": "video"}
                if len(_edit_sources)>=128: _edit_sources.pop(next(iter(_edit_sources)))
                _edit_sources[cache_key] = result
                return result
            except StickerConversionError as exc:
                raise HTTPException(422, str(exc)) from exc
