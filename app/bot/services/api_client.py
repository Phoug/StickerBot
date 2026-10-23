import logging
from pathlib import Path

import aiohttp

from app.bot.config import (
    API_BASE_URL,
    API_SECRET_TOKEN,
    CHUNK_SIZE,
    HTTP_TIMEOUT,
    MAX_TELEGRAM_UPLOAD_SIZE,
)
from app.bot.utils import get_content_disposition_filename, safe_filename

logger = logging.getLogger("telegram_bot.api")


class BackendClient:
    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    async def open(self) -> None:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
            connector = aiohttp.TCPConnector(limit=20, ttl_dns_cache=300)
            headers = {}
            if API_SECRET_TOKEN:
                headers["X-API-Key"] = API_SECRET_TOKEN
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers=headers,
            )

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        await self.open()
        if self._session is None:
            raise RuntimeError("Backend HTTP session is unavailable.")
        return self._session

    async def get_json(self, endpoint: str, params: dict) -> dict:
        session = await self._get_session()
        try:
            async with session.get(f"{API_BASE_URL}{endpoint}", params=params) as response:
                if response.status == 200:
                    return await response.json()
                try:
                    payload = await response.json()
                except Exception:
                    payload = {}
                detail = payload.get("detail", "Server error")
                logger.error("API GET error [%s]: %s", response.status, detail)
                raise RuntimeError("Failed to fetch video information.")
        except aiohttp.ClientError as exc:
            logger.exception("Backend GET request failed")
            raise RuntimeError("Backend service connection error.") from exc

    async def download_url_to_file(
        self,
        url: str,
        output_dir: str,
        tr,
    ) -> tuple[str, Path, int]:
        session = await self._get_session()
        params = {"url": url, "as_attachment": "true"}
        try:
            async with session.get(f"{API_BASE_URL}/download", params=params) as response:
                if response.status != 200:
                    logger.error("API download error [%s]", response.status)
                    raise RuntimeError(tr("download_failed"))
                filename = (
                    get_content_disposition_filename(
                        response.headers.get("Content-Disposition")
                    )
                    or "video.mp4"
                )
                if not Path(filename).suffix:
                    filename = f"{filename}.mp4"
                filename = safe_filename(filename)
                output_path = Path(output_dir) / filename
                total_size = 0
                with output_path.open("wb") as file:
                    async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                        total_size += len(chunk)
                        if total_size > MAX_TELEGRAM_UPLOAD_SIZE:
                            raise RuntimeError(tr("limit_exceeded"))
                        file.write(chunk)
                return filename, output_path, total_size
        except aiohttp.ClientError as exc:
            logger.exception("Backend download request failed")
            raise RuntimeError("Network error while downloading file.") from exc

    async def upload_sticker(self, input_path: str, start: float, end: float | None) -> bytes:
        session = await self._get_session()
        form = aiohttp.FormData()
        with open(input_path, "rb") as file:
            form.add_field(
                "video",
                file,
                filename=Path(input_path).name,
                content_type="application/octet-stream",
            )
            form.add_field("start", str(start))
            if end is not None:
                form.add_field("end", str(end))
            try:
                async with session.post(
                    f"{API_BASE_URL}/convert/sticker",
                    data=form,
                ) as response:
                    if response.status != 200:
                        try:
                            payload = await response.json()
                            detail = payload.get("detail", "Server processing error")
                        except Exception:
                            detail = "Server processing error"
                        logger.error("API sticker error [%s]: %s", response.status, detail)
                        raise RuntimeError(f"Conversion failed: {detail}")
                    return await response.read()
            except aiohttp.ClientError as exc:
                logger.exception("Backend sticker request failed")
                raise RuntimeError("Network error during sticker conversion.") from exc


backend_client = BackendClient()
