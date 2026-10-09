from typing import Any


def sticker_set_to_dict(covered: Any) -> dict[str, Any]:
    sticker_set = getattr(covered, "set", covered)
    access_hash = getattr(sticker_set, "access_hash", None)
    return {
        "id": int(sticker_set.id),
        "access_hash": int(access_hash) if access_hash is not None else None,
        "title": getattr(sticker_set, "title", None) or "",
        "short_name": getattr(sticker_set, "short_name", None) or "",
        "count": int(getattr(sticker_set, "count", 0) or 0),
        "creator": bool(getattr(sticker_set, "creator", False)),
        "animated": bool(getattr(sticker_set, "animated", False)),
        "videos": bool(getattr(sticker_set, "videos", False)),
        "emojis": bool(getattr(sticker_set, "emojis", False)),
        "masks": bool(getattr(sticker_set, "masks", False)),
    }
