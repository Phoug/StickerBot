"""Pack mutation ownership and retry-safe publication reconciliation."""
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import HTTPException

from backend.services.bot_api import TelegramAPI
from backend.storage import database, owned_pack

_busy: set[int] = set()


@asynccontextmanager
async def user_operation(user_id: int) -> AsyncIterator[None]:
    if user_id in _busy:
        raise HTTPException(409, "Дождитесь завершения текущей операции")
    _busy.add(user_id)
    try:
        yield
    finally:
        _busy.discard(user_id)


def update_pack(pack_id: str, **fields: object) -> None:
    with database() as db:
        db.execute(
            f"UPDATE packs SET {', '.join(key + '=?' for key in fields)} WHERE id=?",
            [*fields.values(), pack_id],
        )


def find_sticker(actual: dict, sticker_id: str) -> dict:
    sticker = next((
        item for item in actual["stickers"]
        if item["file_unique_id"] == sticker_id
    ), None)
    if sticker is None:
        raise HTTPException(404, "Стикер не найден в этом наборе")
    return sticker


async def publish_render(
    pack: dict, media: dict, emoji: str, replace_id: str | None,
    telegram: TelegramAPI,
) -> dict:
    """Reconcile remote writes before recording one completed publication."""
    if media["kind"] not in {"render", "render_photo"}:
        raise HTTPException(422, "Сначала создайте стикер в редакторе")
    if media["published_pack"]:
        if (
            media["published_pack"] == pack["id"]
            and media["published_replace_id"] == replace_id
        ):
            return owned_pack(pack["id"], pack["user_id"])
        raise HTTPException(409, "Этот стикер уже сохранён для другой публикации")
    if pack["status"] == "import_pending":
        raise HTTPException(409, "Сначала завершите импорт набора")

    uploaded = await telegram.upload(pack["user_id"], Path(media["path"]))
    sticker = {
        "sticker": uploaded["file_id"],
        "format": "static" if media["kind"] == "render_photo" else "video",
        "emoji_list": [emoji],
    }
    try:
        actual = await telegram.call("getStickerSet", name=pack["name"])
    except HTTPException as exc:
        if "STICKERSET_INVALID" not in str(exc.detail):
            raise
        actual = None

    confirmed = True
    if actual:
        already_added = any(
            item["file_unique_id"] == uploaded["file_unique_id"]
            for item in actual["stickers"]
        )
        if replace_id:
            target = next((
                item for item in actual["stickers"]
                if item["file_unique_id"] == replace_id
            ), None)
            if already_added:
                if target and target["file_unique_id"] != uploaded["file_unique_id"]:
                    raise HTTPException(
                        409, "Такой стикер уже есть в наборе. Выберите другое изменение.",
                    )
                # An absent target plus the uploaded file recovers a lost response.
            else:
                old = find_sticker(actual, replace_id)
                confirmed = await telegram.call(
                    "replaceStickerInSet", user_id=pack["user_id"],
                    name=pack["name"], old_sticker=old["file_id"], sticker=sticker,
                )
        elif not already_added:
            if len(actual["stickers"]) >= 120:
                raise HTTPException(422, "В наборе уже 120 стикеров")
            confirmed = await telegram.call(
                "addStickerToSet", user_id=pack["user_id"],
                name=pack["name"], sticker=sticker,
            )
    else:
        if replace_id:
            raise HTTPException(409, "Набор изменился. Откройте его заново.")
        confirmed = await telegram.call(
            "createNewStickerSet", user_id=pack["user_id"], name=pack["name"],
            title=pack["title"], stickers=[sticker],
        )
    if confirmed is not True:
        raise HTTPException(502, "Telegram не подтвердил публикацию")

    actual = await telegram.call("getStickerSet", name=pack["name"])
    with database() as db:
        db.execute(
            "UPDATE packs SET status='ready', count=?, error=NULL WHERE id=?",
            (len(actual["stickers"]), pack["id"]),
        )
        db.execute(
            "UPDATE media SET published_pack=?, published_replace_id=? WHERE id=?",
            (pack["id"], replace_id, media["id"]),
        )
    return owned_pack(pack["id"], pack["user_id"])
