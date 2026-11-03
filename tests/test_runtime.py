import asyncio
import json
import logging
import threading
import time

import pytest
from fastapi import HTTPException

from tests.support import auth
from app.bot import health
from backend.observability import RuntimeMiddleware
from backend.services.processing import MediaCapacity, run_blocking, media_capacity
from common.logging import JsonFormatter

def test_readiness_detects_missing_registry_without_recreating_it(client):
    api, _, folder = client
    assert api.get("/ready").status_code == 200
    (folder / "stickerbot.sqlite3").unlink()
    assert api.get("/health").status_code == 200
    assert api.get("/ready").status_code == 503
    assert not (folder / "stickerbot.sqlite3").exists()


def test_metrics_require_api_key_and_requests_have_correlation_ids(client):
    api, _, _ = client
    assert api.get("/metrics").status_code == 401
    response = api.get("/metrics", headers={"X-API-Key": "test-secret"})
    assert response.status_code == 200
    assert "stickerbot_media_jobs_active" in response.text
    assert len(response.headers["x-request-id"]) == 32
    assert api.get("/health").headers["x-request-id"] != response.headers["x-request-id"]


def test_upload_checks_auth_and_capacity_before_multipart_parsing(client, monkeypatch):
    api, _, _ = client
    malformed = {"content-type": "multipart/form-data; boundary=missing"}
    assert api.post("/api/studio/upload", content=b"not multipart", headers=malformed).status_code == 401
    monkeypatch.setattr(media_capacity, "active", media_capacity.limit)
    response = api.post("/api/studio/upload", content=b"not multipart", headers={**malformed, **auth()})
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"


def test_chunked_body_cannot_bypass_size_limit():
    async def scenario():
        messages = iter([{"type": "http.request", "body": b"a" * 8, "more_body": True},
                         {"type": "http.request", "body": b"b" * 8, "more_body": False}])
        sent = []
        async def receive():
            return next(messages)
        async def send(message):
            sent.append(message)
        async def application(scope, receive, send):
            while (await receive()).get("more_body"):
                pass
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})
        await RuntimeMiddleware(application, max_body_size=10)(
            {"type": "http", "method": "POST", "path": "/receive", "headers": []}, receive, send)
        assert sent[0]["status"] == 413
        assert len([m for m in sent if m["type"] == "http.response.start"]) == 1
    asyncio.run(scenario())


def test_streamed_multipart_is_rejected_before_rendering(client, monkeypatch):
    api, _, _ = client
    middleware = api.app.middleware_stack
    while not isinstance(middleware, RuntimeMiddleware):
        middleware = middleware.app
    monkeypatch.setattr(middleware, "max_body_size", 64)
    body = b'--test\r\nContent-Disposition: form-data; name="video"; filename="x.png"\r\nContent-Type: image/png\r\n\r\n' + b'x'*100 + b'\r\n--test--\r\n'
    response = api.post("/api/studio/upload", content=iter([body[:50],body[50:]]),
                        headers={**auth(), "Content-Type": "multipart/form-data; boundary=test"})
    assert response.status_code == 413


def test_cancelled_thread_keeps_capacity_until_its_work_really_finishes():
    async def scenario():
        capacity = MediaCapacity(1)
        entered, release = threading.Event(), threading.Event()
        def work():
            entered.set()
            release.wait(timeout=5)
        async def operation():
            async with capacity:
                await run_blocking(work)
        task = asyncio.create_task(operation())
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            await asyncio.sleep(0)
            assert capacity.active == 1
            with pytest.raises(HTTPException) as exc:
                async with capacity:
                    pass
            assert exc.value.status_code == 503
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert capacity.active == 0
    asyncio.run(scenario())


def test_stalled_upload_is_timed_out_and_releases_capacity():
    async def scenario():
        sent = []
        async def receive():
            await asyncio.sleep(10)
        async def send(message):
            sent.append(message)
        async def application(scope, receive, send):
            await receive()
        before = media_capacity.active
        await RuntimeMiddleware(application, upload_timeout=0.01)(
            {"type": "http", "method": "POST", "path": "/convert/sticker",
             "headers": [(b"x-api-key", b"test-secret")]}, receive, send)
        assert sent[0]["status"] == 408
        assert media_capacity.active == before
    asyncio.run(scenario())


def test_polling_health_requires_successful_getupdates_and_expires(tmp_path, monkeypatch):
    from aiogram.methods import GetMe, GetUpdates
    monkeypatch.setenv("BOT_HEALTH_FILE", str(tmp_path / "health.json"))
    async def success(bot, method):
        return []
    async def failure(bot, method):
        raise RuntimeError("Telegram is unavailable")
    assert not health.is_healthy()
    asyncio.run(health.polling_heartbeat(success, None, GetMe()))
    assert not health.is_healthy()
    with pytest.raises(RuntimeError):
        asyncio.run(health.polling_heartbeat(failure, None, GetUpdates()))
    assert not health.is_healthy()
    asyncio.run(health.polling_heartbeat(success, None, GetUpdates()))
    assert health.is_healthy()
    state = json.loads(health.heartbeat_path().read_text())
    state["last_success"] = time.time() - 300
    health.heartbeat_path().write_text(json.dumps(state))
    assert not health.is_healthy()
    health.clear_heartbeat()
    assert not health.is_healthy()


def test_json_logs_redact_credentials_and_omit_access_query_strings():
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                               ("client", "GET", "/info?url=private-query", "1.1", 200), None)
    output = JsonFormatter(["secret-token"]).format(record)
    assert "private-query" not in output
    record = logging.LogRecord("test", logging.ERROR, "", 0, "URL contains secret-token", (), None)
    output = JsonFormatter(["secret-token"]).format(record)
    assert "secret-token" not in output
    assert "[redacted]" in json.loads(output)["message"]
