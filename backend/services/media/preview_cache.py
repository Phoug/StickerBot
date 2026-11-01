"""Small process-local cache of private, immutable media (one API worker)."""
import asyncio
import time
from collections import OrderedDict

_items = OrderedDict()
_pending = {}
MAX_BYTES = 32 * 1024 * 1024
TTL = 300


async def cached_media(key, produce):
    now = time.monotonic()
    for old_key, (expires, _) in list(_items.items()):
        if expires <= now:
            _items.pop(old_key)
    if key in _items:
        _items.move_to_end(key)
        return _items[key][1]
    if key in _pending:
        return await asyncio.shield(_pending[key])

    async def load():
        try:
            result = await produce()
            size = len(result[0])
            if size <= MAX_BYTES:
                while _items and (sum(len(item[1][0]) for item in _items.values()) + size > MAX_BYTES or len(_items) >= 256):
                    _items.popitem(last=False)
                _items[key] = (time.monotonic() + TTL, result)
            return result
        finally:
            _pending.pop(key, None)

    pending = asyncio.create_task(load())
    _pending[key] = pending
    return await asyncio.shield(pending)
