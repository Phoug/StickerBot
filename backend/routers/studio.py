import aiohttp
import asyncio
import tempfile
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from emoji import is_emoji
from backend.services.processing import media_capacity as _processing, run_blocking as run_in_threadpool
from backend.services.media.sticker_preview import video_preview

from backend.config import MAX_SOURCE_SIZE
from backend.services.media_store import register, owned_media, cleanup_expired
from backend.services.bot_api import telegram
from backend.services.publication import publish_render, user_operation, find_sticker
from backend.security import mini_app_user
from backend.services.media.downloader import DownloadFailed, _ydl_opts
from backend.services.media.sticker_converter import StickerConversionError
from backend.services.media.studio_renderer import normalize, render, probe
from backend.services.media.photo_renderer import normalize_photo, render_photo
from backend.services.media.preview_cache import cached_media
from backend.storage import database, owned_pack
from backend.services.media.photo_links import validate_url, resolve_tiktok, fetch_public, MAX_BYTES

router = APIRouter(prefix="/api/studio", tags=["Sticker editor"])
_edit_sources = {}
_link_sources = {}

def remember_link(key, result):
    if len(_link_sources)>=64: _link_sources.pop(next(iter(_link_sources)))
    _link_sources[key] = (time.monotonic()+300,result)
    return result

SOCIAL_HOSTS = {
    "youtube.com", "youtu.be", "instagram.com", "tiktok.com",
    "vk.com", "vk.ru", "vkvideo.ru", "twitter.com", "x.com",
    "reddit.com", "v.redd.it", "facebook.com", "fb.watch",
    "vimeo.com", "rutube.ru", "ok.ru", "twitch.tv",
    "dailymotion.com", "dai.ly", "pinterest.com", "pin.it",
    "bilibili.com", "b23.tv", "bsky.app", "streamable.com", "coub.com",
}

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

def prepare(source: Path, folder: str | Path, user_id: int, photo: bool = False) -> dict:
    if photo:
        output = Path(folder) / "source.png"
        width, height = normalize_photo(source, output)
        return {**register(output, user_id, "photo", 0), "kind": "photo", "width": width, "height": height}
    output = Path(folder) / "source.mp4"
    duration = normalize(source, output)
    _, width, height = probe(output)
    return {
        **register(output, user_id, "source", duration, original=Path(source)),
        "kind": "video", "width": width, "height": height,
    }

@router.post("/upload", status_code=201)
async def upload(video: UploadFile = File(...), user=Depends(mini_app_user)):
    try:
        async with user_operation(user["id"]):
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

def download_source(url: str, user_id: int) -> dict:
    # A dedicated limited download; legacy bot downloads retain their own behavior.
    from backend.services.media.ytdlp import extract
    with tempfile.TemporaryDirectory(prefix="sticker_link_") as folder:
        options = _ydl_opts(
            "b[ext=mp4][vcodec^=avc1][height<=720]/"
            "bv*[ext=mp4][vcodec^=avc1][height<=720]/"
            "bv*[height<=1080]/b[height<=1080]",
            str(Path(folder) / "download.%(ext)s"),
        )
        try:
            extract(url, options, download=True)
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
    if media["kind"] == "photo" and (thumbnail or preview):
        async def photo_preview() -> tuple[bytes, str]:
            def encode() -> tuple[bytes, str]:
                from io import BytesIO
                from PIL import Image
                with Image.open(media["path"]) as image:
                    edge = 180 if thumbnail else 1280
                    image.thumbnail((edge, edge))
                    output = BytesIO()
                    image.save(output, "WEBP", quality=75 if thumbnail else 85, method=1)
                    return output.getvalue(), "image/webp"
            async with _processing:
                return await run_in_threadpool(encode)
        variant = "thumbnail" if thumbnail else "editor-preview"
        data, mime = await cached_media((user["id"], media_id, variant), photo_preview)
        return Response(data, media_type=mime, headers={"Cache-Control":"private, no-store"})
    if preview and media["kind"] == "render":
        data, mime = await video_preview(
            user["id"], media_id, Path(media["path"]).read_bytes(),
        )
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
                    render_source = source["render_path"]
                    await run_in_threadpool(render, render_source, output, payload.start, payload.end, payload.shape, payload.zoom, payload.x, payload.y)
                return {**register(output, user["id"], "render_photo" if photo else "render", 0 if photo else payload.end - payload.start), "kind": "photo" if photo else "video"}
            except StickerConversionError as exc:
                raise HTTPException(422, str(exc)) from exc

@router.post("/packs/{pack_id}/publish")
async def publish(
    pack_id: str, payload: Publish, user: dict = Depends(mini_app_user),
) -> dict:
    async with user_operation(user["id"]):
        pack = owned_pack(pack_id, user["id"])
        media = owned_media(payload.render_id, user["id"])
        return await publish_render(pack, media, payload.emoji, payload.replace_id, telegram)


@router.post("/packs/{pack_id}/stickers/{sticker_id}/edit", status_code=201)
async def edit_existing(
    pack_id: str, sticker_id: str, user: dict = Depends(mini_app_user),
) -> dict:
    async with user_operation(user["id"]):
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
            source = Path(folder) / ("original.webm" if sticker.get("is_video") else "original")
            source.write_bytes(data)
            try:
                if not sticker.get("is_video"):
                    async with _processing:
                        result = await run_in_threadpool(prepare, source, folder, user["id"], True)
                    if len(_edit_sources)>=128: _edit_sources.pop(next(iter(_edit_sources)))
                    _edit_sources[cache_key] = result
                    return result
                # Use a composited H.264 copy in the browser and retain the
                # original VP9 with alpha for rendering. Both expire together.
                preview_data, _ = await video_preview(user["id"], sticker["file_id"], data)
                preview = Path(folder)/"preview.mp4"
                preview.write_bytes(preview_data)
                async with _processing:
                    duration = (await run_in_threadpool(probe, preview))[0]
                result = register(preview, user["id"], "source", duration, original=source)
                result = {**result, "kind": "video"}
                if len(_edit_sources)>=128: _edit_sources.pop(next(iter(_edit_sources)))
                _edit_sources[cache_key] = result
                return result
            except StickerConversionError as exc:
                raise HTTPException(422, str(exc)) from exc
