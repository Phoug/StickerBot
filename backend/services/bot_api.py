"""Telegram transport: never return token-bearing file URLs to the client."""
import aiohttp
from fastapi import HTTPException
from backend.config import BOT_TOKEN

class TelegramAPI:
    async def call(self, method: str, **payload):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90)) as session:
                async with session.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=payload) as response:
                    data = await response.json()
        except (aiohttp.ClientError, TimeoutError):
            raise HTTPException(502, "Telegram недоступен. Повторите операцию.") from None
        if not data.get("ok"):
            detail = data.get("description", "Telegram request failed").replace(BOT_TOKEN, "[redacted]")
            raise HTTPException(502, f"Telegram: {detail}")
        return data["result"]

    async def upload(self, user_id, path):
        form = aiohttp.FormData()
        form.add_field("user_id", str(user_id))
        form.add_field("sticker_format", "video")
        try:
            with path.open("rb") as file:
                form.add_field("sticker", file, filename="sticker.webm", content_type="video/webm")
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90)) as session:
                    async with session.post(f"https://api.telegram.org/bot{BOT_TOKEN}/uploadStickerFile", data=form) as response:
                        result = await response.json()
        except (aiohttp.ClientError, TimeoutError):
            raise HTTPException(502, "Не удалось загрузить стикер в Telegram") from None
        if not result.get("ok"):
            raise HTTPException(502, "Telegram не принял файл стикера")
        return result["result"]

    async def file(self, file_id):
        meta = await self.call("getFile", file_id=file_id)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{meta['file_path']}") as response:
                    if response.status != 200:
                        raise HTTPException(502, "Не удалось получить файл Telegram")
                    return await response.read(), response.headers.get("Content-Type", "application/octet-stream")
        except (aiohttp.ClientError, TimeoutError):
            raise HTTPException(502, "Не удалось получить файл Telegram") from None

telegram = TelegramAPI()
