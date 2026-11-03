"""One bounded media budget for all endpoints in the single API process."""
import asyncio
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from backend.config import MEDIA_CONCURRENCY, MEDIA_JOB_TIMEOUT
from backend.services.media.commands import job_deadline


class MediaCapacity:
    def __init__(self, limit):
        self.limit = limit
        self.active = 0
        self.completed = 0
        self.failed = 0

    async def __aenter__(self):
        # All admission happens on the API event loop without yielding.
        if self.active >= self.limit:
            raise HTTPException(503, "Сервер занят обработкой. Повторите чуть позже.", headers={"Retry-After": "5"})
        self.active += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.active -= 1
        if exc_type:
            self.failed += 1
        else:
            self.completed += 1


media_capacity = MediaCapacity(MEDIA_CONCURRENCY)


async def run_blocking(function, *args, **kwargs):
    """Keep admission and temporary files alive until a cancelled thread stops."""
    def bounded():
        with job_deadline(MEDIA_JOB_TIMEOUT):
            return function(*args, **kwargs)

    task = asyncio.create_task(run_in_threadpool(bounded))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # A disconnected request must not free a slot while FFmpeg keeps running.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()  # Retrieve an error even though the requester left.
        raise
