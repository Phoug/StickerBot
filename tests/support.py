"""Shared Telegram adapter and signed test authentication."""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from fastapi import HTTPException

from backend.config import BOT_TOKEN

def auth(user_id=7):
    data = {"auth_date": str(int(time.time())), "user": json.dumps({"id": user_id, "first_name": "Test"})}
    check = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return {"X-Telegram-Init-Data": urlencode(data)}

class FakeTelegram:
    def __init__(self):
        self.sets = {}
        self.fail_add = False
        self.created = 0
        self.added = 0
        self.deleted = []
        self.fail_delete = False
        self.moves = []
        self.fail_move_at = None
        self.removed_stickers = []

    async def call(self, method, **payload):
        if method == "getMe":
            return {"username": "test_studio_bot"}
        if method in {"deleteStickerFromSet", "setStickerPositionInSet", "setStickerEmojiList"}:
            target = next((pack["stickers"] for pack in self.sets.values()
                           if any(s["file_id"] == payload["sticker"] for s in pack["stickers"])), None)
            if target is None:
                raise HTTPException(502, "STICKER_INVALID")
            item = next(s for s in target if s["file_id"] == payload["sticker"])
            if method == "deleteStickerFromSet":
                self.removed_stickers.append(payload["sticker"])
                target.remove(item)
                return True
            if method == "setStickerEmojiList":
                item["emoji"] = payload["emoji_list"][0]
                return True
            if self.fail_move_at is not None and len(self.moves) == self.fail_move_at:
                raise HTTPException(502, "Telegram недоступен")
            self.moves.append((payload["sticker"], payload["position"]))
            target.remove(item)
            target.insert(payload["position"], item)
            return True
        if method == "deleteStickerSet":
            if self.fail_delete:
                raise HTTPException(502, "Telegram недоступен")
            if payload["name"] not in self.sets:
                raise HTTPException(502, "Telegram: STICKERSET_INVALID")
            self.deleted.append(payload["name"])
            del self.sets[payload["name"]]
            return True
        if method == "getStickerSet":
            if payload["name"] not in self.sets:
                raise HTTPException(502, "Telegram: Bad Request: STICKERSET_INVALID")
            return self.sets[payload["name"]]
        if method == "createNewStickerSet":
            self.created += 1
            self.sets[payload["name"]] = {"sticker_type": "regular", "stickers": [self.sticker(s) for s in payload["stickers"]]}
            return True
        if method == "replaceStickerInSet":
            target = self.sets[payload["name"]]["stickers"]
            index = next(i for i, item in enumerate(target) if item["file_id"] == payload["old_sticker"])
            target[index] = self.sticker(payload["sticker"])
            return True
        if method == "addStickerToSet":
            if self.fail_add:
                self.fail_add = False
                raise HTTPException(502, "Temporary import error")
            self.added += 1
            target = self.sets[payload["name"]]["stickers"]
            sticker = self.sticker(payload["sticker"])
            if sticker["file_id"] not in {s["file_id"] for s in target}:
                target.append(sticker)
            return True
        raise AssertionError(method)

    def sticker(self, input_sticker):
        file_id = input_sticker["sticker"]
        return {"file_id": file_id, "file_unique_id": file_id, "emoji": input_sticker["emoji_list"][0],
                "is_video": input_sticker["format"] == "video", "is_animated": input_sticker["format"] == "animated"}

    async def upload(self, user_id, path):
        file_id = hashlib.sha256(path.read_bytes()).hexdigest()
        return {"file_id": file_id, "file_unique_id": file_id}

    async def file(self, file_id):
        return b"test-image-bytes", "image/webp"
