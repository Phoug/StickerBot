import asyncio
import re
import time
import uuid
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from emoji import is_emoji
from backend.services.processing import media_capacity as _preview_processing, run_blocking as run_in_threadpool
from backend.security import mini_app_user
from backend.services.bot_api import telegram
from backend.storage import database, owned_pack
from backend.services.file_service import cleanup_files
from backend.services.media.sticker_preview import make_video_preview
from backend.services.media.sticker_converter import StickerConversionError
from backend.services.media.preview_cache import cached_media

router = APIRouter(prefix="/api/packs", tags=["Sticker packs"])
_busy: set[int] = set()
_preview_files: dict[tuple[str, int], tuple[float, set[str]]] = {}


def cache_previews(pack_id, user_id, actual):
    if len(_preview_files) >= 256:
        _preview_files.pop(next(iter(_preview_files)))
    allowed = {(s.get("thumbnail") or s)["file_id"] for s in actual["stickers"]}
    _preview_files[(pack_id, user_id)] = (time.monotonic() + 60, allowed)
    return allowed

@asynccontextmanager
async def user_operation(user_id):
    # Single API worker; reject concurrent writes to avoid duplicate publishing.
    if user_id in _busy:
        raise HTTPException(409, "Дождитесь завершения текущей операции")
    _busy.add(user_id)
    try:
        yield
    finally:
        _busy.discard(user_id)

class CreatePack(BaseModel):
    title: str = Field(min_length=1, max_length=64)
    source: str | None = Field(default=None, max_length=256)


class StickerOrder(BaseModel):
    sticker_ids: list[str] = Field(min_length=1, max_length=120)


class StickerEmoji(BaseModel):
    emoji: str = Field(min_length=1, max_length=32)

    @field_validator("emoji")
    @classmethod
    def valid_emoji(cls, value):
        value = value.strip()
        if not is_emoji(value):
            raise ValueError("Введите один эмодзи")
        return value


def serialize_pack(pack, actual):
    pack = dict(pack)
    pack["stickers"] = [
        {"id": s["file_unique_id"], "emoji": s.get("emoji", "🙂"), "position": index,
         "is_video": bool(s.get("is_video")), "is_animated": bool(s.get("is_animated")),
         "preview_id": (s.get("thumbnail") or s)["file_id"]}
        for index, s in enumerate(actual["stickers"])
    ]
    pack["count"] = len(pack["stickers"])
    update_pack(pack["id"], count=pack["count"])
    cache_previews(pack["id"], pack["user_id"], actual)
    return pack


def find_sticker(actual, sticker_id):
    sticker = next((s for s in actual["stickers"] if s["file_unique_id"] == sticker_id), None)
    if sticker is None:
        raise HTTPException(404, "Стикер не найден в этом наборе")
    return sticker

def parse_pack_name(value):
    value = value.strip()
    if "://" in value:
        url = urlparse(value)
        if url.scheme != "https" or url.hostname not in {"t.me", "telegram.me"}:
            raise HTTPException(422, "Нужна ссылка https://t.me/addstickers/имя")
        parts = url.path.strip("/").split("/")
        if len(parts) != 2 or parts[0] != "addstickers":
            raise HTTPException(422, "Нужна ссылка на обычный стикерпак")
        value = parts[1]
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", value):
        raise HTTPException(422, "Некорректное имя набора")
    return value

def update_pack(pack_id, **fields):
    with database() as db:
        db.execute(f"UPDATE packs SET {', '.join(key + '=?' for key in fields)} WHERE id=?", [*fields.values(), pack_id])

def input_sticker(sticker):
    return {
        "sticker": sticker["file_id"],
        "format": "animated" if sticker.get("is_animated") else "video" if sticker.get("is_video") else "static",
        "emoji_list": [sticker.get("emoji") or "🙂"],
    }

@router.get("")
async def list_packs(user=Depends(mini_app_user)):
    with database() as db:
        rows = db.execute("SELECT * FROM packs WHERE user_id=? ORDER BY created_at DESC", (user["id"],)).fetchall()
    return {"packs": [dict(row) for row in rows]}

@router.post("", status_code=201)
async def create_pack(payload: CreatePack, user=Depends(mini_app_user)):
    title = payload.title.strip()
    if not title:
        raise HTTPException(422, "Введите название набора")
    source_name = parse_pack_name(payload.source) if payload.source else None
    if source_name:
        source = await telegram.call("getStickerSet", name=source_name)
        if source.get("sticker_type") != "regular" or not source.get("stickers"):
            raise HTTPException(422, "Импортируются обычные непустые наборы, без масок и custom emoji")
        if len(source["stickers"]) > 120:
            raise HTTPException(422, "В наборе больше 120 стикеров")
    me = await telegram.call("getMe")
    pack_id = uuid.uuid4().hex
    name = f"s{pack_id[:20]}_by_{me['username']}"
    with database() as db:
        db.execute("INSERT INTO packs(id,user_id,name,title,source_name,status,created_at) VALUES (?,?,?,?,?,?,?)",
                   (pack_id, user["id"], name, title, source_name, "import_pending" if source_name else "draft", time.time()))
    return owned_pack(pack_id, user["id"])

@router.post("/{pack_id}/import")
async def import_pack(pack_id: str, user=Depends(mini_app_user)):
    async with user_operation(user["id"]):
        pack = owned_pack(pack_id, user["id"])
        if not pack["source_name"] or pack["status"] == "ready":
            return pack
        try:
            source = await telegram.call("getStickerSet", name=pack["source_name"])
            if source.get("sticker_type") != "regular" or not source.get("stickers") or len(source["stickers"]) > 120:
                raise HTTPException(422, "Этот набор нельзя импортировать")
            try:
                current = await telegram.call("getStickerSet", name=pack["name"])
            except HTTPException as exc:
                if "STICKERSET_INVALID" not in str(exc.detail):
                    raise
                current = None
            existing = {s["file_unique_id"] for s in current["stickers"]} if current else set()
            pending = [s for s in source["stickers"] if s["file_unique_id"] not in existing]
            if not current:
                initial, pending = pending[:50], pending[50:]
                await telegram.call("createNewStickerSet", user_id=user["id"], name=pack["name"], title=pack["title"],
                                    stickers=[input_sticker(s) for s in initial])
                update_pack(pack_id, count=len(initial))
            for sticker in pending:
                await telegram.call("addStickerToSet", user_id=user["id"], name=pack["name"], sticker=input_sticker(sticker))
                await asyncio.sleep(0.05)
            actual = await telegram.call("getStickerSet", name=pack["name"])
            update_pack(pack_id, count=len(actual["stickers"]), status="ready", error=None)
        except HTTPException as exc:
            update_pack(pack_id, error=str(exc.detail))
            raise
    return owned_pack(pack_id, user["id"])

@router.get("/{pack_id}")
async def get_pack(pack_id: str, user=Depends(mini_app_user)):
    pack = owned_pack(pack_id, user["id"])
    pack["stickers"] = []
    if pack["status"] == "ready":
        actual = await telegram.call("getStickerSet", name=pack["name"])
        return serialize_pack(pack, actual)
    return pack


@router.delete("/{pack_id}", status_code=204)
async def delete_pack(pack_id: str, user=Depends(mini_app_user)):
    async with user_operation(user["id"]):
        pack = owned_pack(pack_id, user["id"])
        try:
            # Also check drafts: Telegram may have accepted an earlier publish/import
            # whose response was lost before its local status could be updated.
            deleted = await telegram.call("deleteStickerSet", name=pack["name"])
            if deleted is not True:
                raise HTTPException(502, "Telegram не подтвердил удаление набора")
        except HTTPException as exc:
            already_absent = any(code in str(exc.detail) for code in ("STICKERSET_INVALID", "STICKERSET_NOT_FOUND"))
            if not already_absent:
                raise
        # Keep the local record on Telegram/network errors, allowing a safe retry.
        with database() as db:
            db.execute("DELETE FROM packs WHERE id=? AND user_id=?", (pack_id, user["id"]))
            db.execute("UPDATE media SET created_at=0 WHERE published_pack=? AND user_id=?", (pack_id, user["id"]))
        _preview_files.pop((pack_id, user["id"]), None)
    return Response(status_code=204)


@router.get("/{pack_id}/cover")
async def cover(pack_id: str, user=Depends(mini_app_user)):
    pack = owned_pack(pack_id, user["id"])
    if pack["status"] != "ready":
        raise HTTPException(404, "Обложка появится после первого стикера")
    actual = await telegram.call("getStickerSet", name=pack["name"])
    first = next(iter(actual["stickers"]), {})
    thumbnail = actual.get("thumbnail") or first.get("thumbnail")
    if not thumbnail and first and not first.get("is_video") and not first.get("is_animated"):
        thumbnail = first
    if not thumbnail:
        raise HTTPException(404, "Обложка недоступна")
    data, mime = await cached_media((user["id"], thumbnail["file_id"]), lambda: telegram.file(thumbnail["file_id"]))
    return Response(data, media_type=mime, headers={"Cache-Control": "private, max-age=60"})


@router.get("/{pack_id}/stickers/{sticker_id}/file")
async def sticker_file(pack_id: str, sticker_id: str, user=Depends(mini_app_user)):
    pack = owned_pack(pack_id, user["id"])
    actual = await telegram.call("getStickerSet", name=pack["name"])
    sticker = find_sticker(actual, sticker_id)
    # TGS uses its thumbnail in the browser; the original animation stays in Telegram.
    if sticker.get("is_animated"):
        if not sticker.get("thumbnail"):
            raise HTTPException(422, "Предпросмотр анимированного стикера недоступен")
        data, mime = await cached_media((user["id"], sticker["thumbnail"]["file_id"]), lambda: telegram.file(sticker["thumbnail"]["file_id"]))
    else:
        data, mime = await cached_media((user["id"], sticker["file_id"]), lambda: telegram.file(sticker["file_id"]))
    if sticker.get("is_video"):
        # H.264 preview works in iOS WebViews too; Telegram retains the original VP9 file.
        async def preview():
            async with _preview_processing:
                try:
                    output = await run_in_threadpool(make_video_preview, data)
                    try:
                        return output.read_bytes(), "video/mp4"
                    finally:
                        cleanup_files(output.parent)
                except StickerConversionError as exc:
                    raise HTTPException(422, "Не удалось подготовить предпросмотр видео") from exc
        data, mime = await cached_media((user["id"], sticker["file_id"], "mp4"), preview)
    return Response(data, media_type=mime, headers={"Cache-Control": "private, max-age=60"})


@router.delete("/{pack_id}/stickers/{sticker_id}")
async def delete_sticker(pack_id: str, sticker_id: str, user=Depends(mini_app_user)):
    async with user_operation(user["id"]):
        pack = owned_pack(pack_id, user["id"])
        actual = await telegram.call("getStickerSet", name=pack["name"])
        sticker = find_sticker(actual, sticker_id)
        if await telegram.call("deleteStickerFromSet", sticker=sticker["file_id"]) is not True:
            raise HTTPException(502, "Telegram не подтвердил удаление стикера")
        _preview_files.pop((pack_id, user["id"]), None)
        try:
            actual = await telegram.call("getStickerSet", name=pack["name"])
        except HTTPException as exc:
            if "STICKERSET_INVALID" not in str(exc.detail):
                raise
            update_pack(pack_id, count=0, status="draft")
            pack.update(count=0, status="draft")
            actual = {"stickers": []}
        return serialize_pack(pack, actual)


@router.put("/{pack_id}/order")
async def reorder_stickers(pack_id: str, payload: StickerOrder, user=Depends(mini_app_user)):
    async with user_operation(user["id"]):
        pack = owned_pack(pack_id, user["id"])
        actual = await telegram.call("getStickerSet", name=pack["name"])
        current = [s["file_unique_id"] for s in actual["stickers"]]
        desired = payload.sticker_ids
        if len(desired) != len(set(desired)) or len(current) != len(desired) or set(current) != set(desired):
            raise HTTPException(409, "Состав набора изменился. Откройте его заново перед изменением порядка.")
        files = {s["file_unique_id"]: s["file_id"] for s in actual["stickers"]}
        try:
            for index, sticker_id in enumerate(desired):
                if current[index] == sticker_id:
                    continue
                if await telegram.call("setStickerPositionInSet", sticker=files[sticker_id], position=index) is not True:
                    raise HTTPException(502, "Telegram не подтвердил перемещение")
                current.remove(sticker_id)
                current.insert(index, sticker_id)
        finally:
            # A failed batch may be partially applied. The next GET always reads Telegram.
            _preview_files.pop((pack_id, user["id"]), None)
        actual = await telegram.call("getStickerSet", name=pack["name"])
        return serialize_pack(pack, actual)


@router.put("/{pack_id}/stickers/{sticker_id}/emoji")
async def change_emoji(pack_id: str, sticker_id: str, payload: StickerEmoji, user=Depends(mini_app_user)):
    async with user_operation(user["id"]):
        pack = owned_pack(pack_id, user["id"])
        actual = await telegram.call("getStickerSet", name=pack["name"])
        sticker = find_sticker(actual, sticker_id)
        if sticker.get("emoji") != payload.emoji:
            if await telegram.call("setStickerEmojiList", sticker=sticker["file_id"], emoji_list=[payload.emoji]) is not True:
                raise HTTPException(502, "Telegram не подтвердил изменение эмодзи")
        return {"id": sticker_id, "emoji": payload.emoji}

@router.get("/{pack_id}/thumbnail/{file_id}")
async def thumbnail(pack_id: str, file_id: str, user=Depends(mini_app_user)):
    pack = owned_pack(pack_id, user["id"])
    cached = _preview_files.get((pack_id, user["id"]))
    if cached and cached[0] > time.monotonic():
        allowed = cached[1]
    else:
        actual = await telegram.call("getStickerSet", name=pack["name"])
        allowed = cache_previews(pack_id, user["id"], actual)
    if file_id not in allowed:
        raise HTTPException(404, "Стикер не найден")
    data, mime = await cached_media((user["id"], file_id), lambda: telegram.file(file_id))
    return Response(data, media_type=mime, headers={"Cache-Control": "private, max-age=300"})
