import asyncio
import re
import time
import uuid
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from backend.security import mini_app_user
from backend.services.bot_api import telegram
from backend.storage import database, owned_pack

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
        cache_previews(pack_id, user["id"], actual)
        pack["stickers"] = [{"emoji": s.get("emoji", "🙂"), "preview_id": (s.get("thumbnail") or s)["file_id"]} for s in actual["stickers"]]
        pack["count"] = len(pack["stickers"])
        update_pack(pack_id, count=pack["count"])
    return pack

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
    data, mime = await telegram.file(file_id)
    return Response(data, media_type=mime, headers={"Cache-Control": "private, max-age=300"})
