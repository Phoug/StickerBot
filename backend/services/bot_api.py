"""Telegram transport: never return token-bearing file URLs to the client."""
import aiohttp
import asyncio
from fastapi import HTTPException
from backend.config import BOT_TOKEN

class TelegramAPI:
    def __init__(self):
        self._session = None

    def session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(limit=20),
                timeout=aiohttp.ClientTimeout(total=90),
                trust_env=False,
            )
        return self._session

    async def close(self):
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def call(self, method: str, **payload):
        try:
            for attempt in range(2):
                async with self.session().post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=payload) as response:
                    data = await response.json()
                retry_after = data.get("parameters", {}).get("retry_after", 0)
                if not (data.get("error_code") == 429 and attempt == 0 and isinstance(retry_after, (int, float)) and 0 < retry_after <= 30):
                    break
                # A 429 explicitly rejects the operation. Ambiguous network failures
                # are never replayed here: writes must reconcile with Telegram.
                await asyncio.sleep(retry_after)
        except (aiohttp.ClientError, TimeoutError):
            raise HTTPException(502, "Telegram недоступен. Повторите операцию.") from None
        if not data.get("ok"):
            detail = data.get("description", "Telegram request failed").replace(BOT_TOKEN, "[redacted]")
            raise HTTPException(502, f"Telegram: {detail}")
        return data["result"]

    async def upload(self, user_id, path):
        form = aiohttp.FormData()
        form.add_field("user_id", str(user_id))
        photo = path.suffix.lower() == ".webp"
        form.add_field("sticker_format", "static" if photo else "video")
        try:
            with path.open("rb") as file:
                form.add_field("sticker", file, filename=path.name, content_type="image/webp" if photo else "video/webm")
                async with self.session().post(f"https://api.telegram.org/bot{BOT_TOKEN}/uploadStickerFile", data=form) as response:
                    result = await response.json()
        except (aiohttp.ClientError, TimeoutError):
            raise HTTPException(502, "Не удалось загрузить стикер в Telegram") from None
        if not result.get("ok"):
            raise HTTPException(502, "Telegram не принял файл стикера")
        return result["result"]

    async def file(self, file_id):
        meta = await self.call("getFile", file_id=file_id)
        try:
            async with self.session().get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{meta['file_path']}", timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    raise HTTPException(502, "Не удалось получить файл Telegram")
                return await response.read(), response.headers.get("Content-Type", "application/octet-stream")
        except (aiohttp.ClientError, TimeoutError):
            raise HTTPException(502, "Не удалось получить файл Telegram") from None

telegram = TelegramAPI()
