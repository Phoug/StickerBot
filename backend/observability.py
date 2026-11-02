"""Bound request bodies before multipart spooling; expose bounded HTTP metrics."""
import logging
import asyncio
import time
import uuid
from collections import Counter

from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse
from fastapi import HTTPException

from backend.config import MAX_REQUEST_SIZE, MEDIA_JOB_TIMEOUT
from backend.services.media.commands import job_deadline
from common.logging import request_id
from backend.security import get_mini_app_user, verify_api_key
from backend.services.processing import media_capacity

logger = logging.getLogger("video_backend.requests")
requests = Counter()
duration_sum = Counter()


class BodyTooLarge(MultiPartException):
    pass


class BodyReadTimeout(MultiPartException):
    pass


class RuntimeMiddleware:
    def __init__(self, app, max_body_size=MAX_REQUEST_SIZE, upload_timeout=MEDIA_JOB_TIMEOUT):
        self.app = app
        self.max_body_size = max_body_size
        self.upload_timeout = upload_timeout

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        identifier = uuid.uuid4().hex
        token = request_id.set(identifier)
        started = time.monotonic()
        method = scope["method"] if scope["method"] in {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"} else "OTHER"
        size = 0
        too_large = False
        too_slow = False
        upload = scope["method"] == "POST" and scope["path"] in {"/api/studio/upload", "/convert/sticker"}
        answered = False
        status = 500

        async def reject():
            nonlocal answered, status
            if not answered:
                answered, status = True, 408 if too_slow else 413
                detail = "Превышено время загрузки файла" if too_slow else "Размер запроса превышает допустимый лимит"
                response = JSONResponse({"detail": detail}, status_code=status,
                                        headers={"X-Request-ID": identifier})
                await response(scope, receive, send)

        async def bounded_receive():
            nonlocal size, too_large, too_slow
            if upload:
                try:
                    remaining = max(0.001, started + self.upload_timeout - time.monotonic())
                    message = await asyncio.wait_for(receive(), timeout=remaining)
                except TimeoutError:
                    too_slow = True
                    raise BodyReadTimeout("Upload deadline expired") from None
            else:
                message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > self.max_body_size:
                    too_large = True
                    # MultiPartParser closes its spool files for this exception.
                    raise BodyTooLarge("Request body exceeds the configured limit")
            return message

        async def traced_send(message):
            nonlocal status, answered
            if too_large or too_slow:
                return await reject()
            if message["type"] == "http.response.start":
                status = message["status"]
                answered = True
                message = {**message, "headers": [*message.get("headers", []), (b"x-request-id", identifier.encode())]}
            await send(message)

        try:
            headers = dict(scope.get("headers", []))
            length = headers.get(b"content-length")
            if length is not None and not length.isdigit():
                await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(scope, receive, traced_send)
            elif length is not None and (len(length) > 20 or int(length) > self.max_body_size):
                await reject()
            else:
                try:
                    if upload:
                        # Authenticate and reserve capacity before Starlette spools
                        # multipart bodies; endpoint dependencies validate again.
                        if scope["path"] == "/api/studio/upload":
                            get_mini_app_user(headers.get(b"x-telegram-init-data", b"").decode("latin-1"))
                        else:
                            verify_api_key(headers.get(b"x-api-key", b"").decode("latin-1"))
                        with job_deadline(self.upload_timeout):
                            async with media_capacity:
                                await self.app(scope, bounded_receive, traced_send)
                    else:
                        await self.app(scope, bounded_receive, traced_send)
                except HTTPException as exc:
                    await JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)(scope, receive, traced_send)
                except Exception:
                    if not (too_large or too_slow):
                        raise
                    await reject()
        finally:
            route = getattr(scope.get("route"), "path", "unmatched")
            elapsed = time.monotonic() - started
            key = (method, route, status)
            requests[key] += 1
            duration_sum[(method, route)] += elapsed
            logger.info("HTTP request", extra={"method": method, "route": route,
                                             "status": status, "duration_ms": round(elapsed * 1000, 2)})
            request_id.reset(token)


def metrics_text():
    from backend.routers import studio
    from backend.services.processing import media_capacity
    lines = [
        "# TYPE stickerbot_media_jobs_active gauge",
        f"stickerbot_media_jobs_active {media_capacity.active}",
        f"stickerbot_media_jobs_capacity {media_capacity.limit}",
        f"stickerbot_media_jobs_completed_total {media_capacity.completed}",
        f"stickerbot_media_jobs_failed_total {media_capacity.failed}",
        f"stickerbot_cleanup_last_success_timestamp_seconds {studio.cleanup_last_success}",
    ]
    counts, totals = requests.copy(), duration_sum.copy()
    for (method, route, status), count in sorted(counts.items()):
        lines.append(f'stickerbot_http_requests_total{{method="{method}",route="{route}",status="{status}"}} {count}')
    for (method, route), total in sorted(totals.items()):
        count = sum(n for (m, r, _), n in counts.items() if (m, r) == (method, route))
        labels = f'method="{method}",route="{route}"'
        lines.extend([f"stickerbot_http_request_duration_seconds_sum{{{labels}}} {total}",
                      f"stickerbot_http_request_duration_seconds_count{{{labels}}} {count}"])
    return "\n".join(lines) + "\n"
