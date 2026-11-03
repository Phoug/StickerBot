import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.routers import studio
from backend.services.media import preview_cache, sticker_preview
from backend.services.processing import media_capacity


def test_cancelled_editor_keeps_preview_capacity_until_render_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered, release = threading.Event(), threading.Event()

    def render_preview(data: bytes) -> Path:
        entered.set()
        if not release.wait(timeout=5):
            raise TimeoutError("Test renderer was not released")
        folder = tmp_path / "preview"
        folder.mkdir()
        output = folder / "preview.mp4"
        output.write_bytes(b"preview")
        return output

    async def call(method: str, **payload: object) -> dict:
        return {"stickers": [{
            "file_unique_id": "sticker", "file_id": "video", "is_video": True,
        }]}

    async def file(file_id: str) -> tuple[bytes, str]:
        return b"original", "video/webm"

    monkeypatch.setattr(studio, "owned_pack", lambda *args: {"name": "pack"})
    monkeypatch.setattr(studio, "telegram", SimpleNamespace(call=call, file=file))
    monkeypatch.setattr(sticker_preview, "make_video_preview", render_preview)
    monkeypatch.setattr(media_capacity, "limit", 1)
    preview_cache._items.clear()
    studio._edit_sources.clear()

    async def scenario() -> None:
        operation = asyncio.create_task(studio.edit_existing(
            "pack", "sticker", user={"id": 7},
        ))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            operation.cancel()
            with pytest.raises(asyncio.CancelledError):
                await operation
            assert media_capacity.active == 1
            with pytest.raises(HTTPException) as error:
                async with media_capacity:
                    pass
            assert error.value.status_code == 503
        finally:
            release.set()
            await asyncio.gather(operation, return_exceptions=True)
            await asyncio.gather(*list(preview_cache._pending.values()))
            preview_cache._items.clear()
        assert media_capacity.active == 0
        assert not (tmp_path / "preview").exists()

    asyncio.run(scenario())
