from typing import Any

from fastapi import APIRouter, Header
from telethon import functions, types

from backend.config import MAX_STICKER_SETS
from backend.models import StickerSetsResponse
from backend.security import get_mini_app_user
from backend.services.sticker_service import sticker_set_to_dict
from backend.services.telethon_service import ensure_user_telegram_account

router = APIRouter(prefix="/api/sticker-sets", tags=["Sticker sets"])


@router.get("", response_model=StickerSetsResponse)
async def get_my_sticker_sets(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
):
    user = get_mini_app_user(x_telegram_init_data)
    user_id = int(user["id"])
    client = await ensure_user_telegram_account(user_id)
    all_sets: list[Any] = []
    offset_id = 0
    page_limit = 100

    while len(all_sets) < MAX_STICKER_SETS:
        result = await client(
            functions.messages.GetMyStickersRequest(offset_id=offset_id, limit=page_limit)
        )
        sets = getattr(result, "sets", [])
        if not sets:
            break
        all_sets.extend(sets)
        if len(sets) < page_limit:
            break
        last_set = getattr(sets[-1], "set", sets[-1])
        last_id = getattr(last_set, "id", None)
        if last_id is None:
            break
        next_offset = int(last_id)
        if next_offset == offset_id:
            break
        offset_id = next_offset
        if len(all_sets) >= getattr(result, "count", len(all_sets)):
            break

    serialized_sets = [sticker_set_to_dict(item) for item in all_sets[:MAX_STICKER_SETS]]
    return {"count": len(serialized_sets), "sets": serialized_sets}


@router.get("/{short_name}")
async def get_sticker_set(
    short_name: str,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
):
    user = get_mini_app_user(x_telegram_init_data)
    user_id = int(user["id"])
    client = await ensure_user_telegram_account(user_id)
    result = await client(
        functions.messages.GetStickerSetRequest(
            stickerset=types.InputStickerSetShortName(short_name=short_name),
            hash=0,
        )
    )
    sticker_set = result.set
    documents = []
    for document in result.documents:
        document_date = getattr(document, "date", None)
        access_hash = getattr(document, "access_hash", None)
        documents.append(
            {
                "id": int(document.id),
                "access_hash": int(access_hash) if access_hash is not None else None,
                "mime_type": getattr(document, "mime_type", None),
                "size": getattr(document, "size", None),
                "date": document_date.isoformat() if document_date else None,
                "attributes": [str(attribute) for attribute in getattr(document, "attributes", [])],
            }
        )

    packs = []
    for pack in getattr(result, "packs", []):
        packs.append(
            {
                "emoticon": getattr(pack, "emoticon", ""),
                "documents": [
                    int(document_id) for document_id in getattr(pack, "documents", [])
                ],
            }
        )

    access_hash = getattr(sticker_set, "access_hash", None)
    return {
        "set": {
            "id": int(sticker_set.id),
            "access_hash": int(access_hash) if access_hash is not None else None,
            "title": sticker_set.title,
            "short_name": sticker_set.short_name,
            "count": int(getattr(sticker_set, "count", 0) or 0),
            "creator": bool(getattr(sticker_set, "creator", False)),
            "animated": bool(getattr(sticker_set, "animated", False)),
            "videos": bool(getattr(sticker_set, "videos", False)),
            "emojis": bool(getattr(sticker_set, "emojis", False)),
            "masks": bool(getattr(sticker_set, "masks", False)),
        },
        "documents": documents,
        "packs": packs,
    }
