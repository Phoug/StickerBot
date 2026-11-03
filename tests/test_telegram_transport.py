import asyncio

import aiohttp
import pytest
from fastapi import HTTPException

from backend.services.bot_api import TelegramAPI


class Response:
    def __init__(self, payload):
        self.payload = payload
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass
    async def json(self):
        return self.payload


class Session:
    closed = False
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0
    def post(self, *args, **kwargs):
        self.calls += 1
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return Response(response)
    async def close(self):
        self.closed = True


def test_explicit_rate_limit_is_retried_with_same_session_and_closed(monkeypatch):
    waits = []
    async def sleep(seconds):
        waits.append(seconds)
    monkeypatch.setattr("backend.services.bot_api.asyncio.sleep", sleep)
    async def scenario():
        api = TelegramAPI()
        session = Session([{"ok":False,"error_code":429,"parameters":{"retry_after":1}},
                           {"ok":True,"result":{"stickers":[]}}])
        api._session = session
        assert await api.call("getStickerSet", name="test") == {"stickers": []}
        assert session.calls == 2 and waits == [1]
        await api.close()
        assert session.closed and api._session is None
    asyncio.run(scenario())


def test_ambiguous_write_failure_is_not_replayed():
    async def scenario():
        api = TelegramAPI()
        session = Session([aiohttp.ClientConnectionError("connection was lost")])
        api._session = session
        with pytest.raises(HTTPException) as exc:
            await api.call("addStickerToSet", name="test", sticker={})
        assert exc.value.status_code == 502 and session.calls == 1
        await api.close()
    asyncio.run(scenario())
