"""Polling heartbeat and Docker healthcheck; contains no credential loading."""
import json
import os
import time
from pathlib import Path


def heartbeat_path():
    return Path(os.getenv("BOT_HEALTH_FILE", "/tmp/stickerbot-bot-health.json"))


def clear_heartbeat():
    heartbeat_path().unlink(missing_ok=True)


def mark_healthy():
    path = heartbeat_path()
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as output:
            json.dump({"pid": os.getpid(), "last_success": time.time()}, output)
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


async def polling_heartbeat(make_request, bot, method):
    from aiogram.methods import GetUpdates
    result = await make_request(bot, method)
    if isinstance(method, GetUpdates):
        mark_healthy()
    return result


def is_healthy():
    try:
        data = json.loads(heartbeat_path().read_text())
        age = time.time() - data["last_success"]
        max_age = int(os.getenv("BOT_HEALTH_MAX_AGE_SECONDS", "120"))
        process_exists = not Path("/proc").is_dir() or (Path("/proc") / str(data["pid"])).is_dir()
        return type(data["pid"]) is int and data["pid"] > 0 and process_exists and 0 <= age <= max_age
    except (OSError, ValueError, KeyError, TypeError):
        return False


if __name__ == "__main__":
    raise SystemExit(0 if is_healthy() else 1)
