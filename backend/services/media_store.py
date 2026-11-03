"""Owner-scoped media registration, expiry and maintenance health."""
import asyncio
import logging
import shutil
import time
import uuid
from pathlib import Path

from fastapi import HTTPException

from backend import storage
from backend.config import CLEANUP_INTERVAL, SOURCE_TTL
from backend.services.processing import run_blocking
from backend.storage import database

logger = logging.getLogger(__name__)
cleanup_last_success = 0.0
cleanup_last_error = False


def register(
    path: Path, user_id: int, kind: str, duration: float,
    *, original: Path | None = None,
) -> dict:
    media_id = uuid.uuid4().hex
    folder = storage.DATA_DIR / "media"
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / (media_id + path.suffix)
    retained_original = destination.with_suffix(".original.webm")
    try:
        shutil.move(str(path), destination)
        if original is not None:
            shutil.copyfile(original, retained_original)
        with database() as db:
            db.execute(
                "INSERT INTO media(id,user_id,path,kind,created_at,duration) "
                "VALUES (?,?,?,?,?,?)",
                (media_id, user_id, str(destination), kind, time.time(), duration),
            )
    except BaseException:
        destination.unlink(missing_ok=True)
        retained_original.unlink(missing_ok=True)
        raise
    return {"id": media_id, "duration": duration}


def owned_media(media_id: str, user_id: int, kind: str | None = None) -> dict:
    with database() as db:
        row = db.execute(
            "SELECT * FROM media WHERE id=? AND user_id=?", (media_id, user_id),
        ).fetchone()
    if (
        not row or row["created_at"] < time.time() - SOURCE_TTL
        or not Path(row["path"]).is_file()
    ):
        raise HTTPException(
            404, "Файл не найден или истёк срок хранения. Загрузите его заново.",
        )
    if kind and row["kind"] != kind:
        raise HTTPException(422, "Некорректный тип файла")
    media = dict(row)
    original = Path(media["path"]).with_suffix(".original.webm")
    media["render_path"] = original if original.is_file() else Path(media["path"])
    return media


def cleanup_expired() -> None:
    global cleanup_last_success, cleanup_last_error
    with database() as db:
        rows = db.execute(
            "SELECT id,path FROM media WHERE created_at<?",
            (time.time() - SOURCE_TTL,),
        ).fetchall()
        for row in rows:
            path = Path(row["path"])
            path.unlink(missing_ok=True)
            path.with_suffix(".original.webm").unlink(missing_ok=True)
            db.execute("DELETE FROM media WHERE id=?", (row["id"],))
    cleanup_last_success = time.time()
    cleanup_last_error = False


async def maintain_media() -> None:
    global cleanup_last_error
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        try:
            await run_blocking(cleanup_expired)
        except Exception:
            cleanup_last_error = True
            logger.exception("Media cleanup failed; retrying at the next interval")
