import asyncio

import pytest

from backend.services.media import preview_cache as cache


@pytest.fixture(autouse=True)
def empty_cache():
    cache._items.clear()
    cache._pending.clear()
    yield
    cache._items.clear()


def test_overlapping_requests_share_work_and_users_have_separate_keys():
    async def scenario():
        calls = []
        async def produce():
            calls.append(1)
            await asyncio.sleep(0)
            return b"preview", "video/mp4"
        results = await asyncio.gather(cache.cached_media((7, "file"), produce), cache.cached_media((7, "file"), produce))
        assert results[0] == results[1]
        assert len(calls) == 1
        await cache.cached_media((8, "file"), produce)
        assert len(calls) == 2
    asyncio.run(scenario())


def test_failed_previews_can_be_retried():
    async def scenario():
        async def failure():
            raise ValueError("temporary encoder failure")
        with pytest.raises(ValueError):
            await cache.cached_media("file", failure)
        async def success():
            return b"ok", "video/mp4"
        assert await cache.cached_media("file", success) == (b"ok", "video/mp4")
    asyncio.run(scenario())


def test_cache_evicts_media_at_memory_limit_and_expires(monkeypatch):
    monkeypatch.setattr(cache, "MAX_BYTES", 4)
    async def scenario():
        calls = []
        async def produce():
            calls.append(1)
            return b"abc", "image/webp"
        await cache.cached_media("first", produce)
        await cache.cached_media("second", produce)
        await cache.cached_media("first", produce)
        assert len(calls) == 3
        monkeypatch.setattr(cache, "TTL", 0)
        await cache.cached_media("expired", produce)
        await cache.cached_media("expired", produce)
        assert len(calls) == 5
    asyncio.run(scenario())
