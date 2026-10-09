import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from telethon import TelegramClient

from backend.config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELETHON_SESSIONS_DIR

logger = logging.getLogger("video_backend.telethon")


@dataclass
class PendingLogin:
    phone: str
    phone_code_hash: str
    created_at: float
    two_factor_required: bool = False


telegram_clients: dict[int, TelegramClient] = {}
telegram_client_locks: dict[int, asyncio.Lock] = {}
pending_logins: dict[int, PendingLogin] = {}
last_code_request: dict[int, float] = {}


def get_user_session_path(user_id: int) -> Path:
    return TELETHON_SESSIONS_DIR / f"user_{user_id}.session"


async def get_telegram_client(user_id: int) -> TelegramClient:
    lock = telegram_client_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        client = telegram_clients.get(user_id)
        if client is None:
            session_path = get_user_session_path(user_id)
            client = TelegramClient(
                str(session_path),
                TELEGRAM_API_ID,
                TELEGRAM_API_HASH,
                use_ipv6=False,
                auto_reconnect=True,
                request_retries=3,
                connection_retries=3,
                timeout=10,
                flood_sleep_threshold=60,
                receive_updates=False,
            )
            await client.connect()
            telegram_clients[user_id] = client
        elif not client.is_connected():
            await client.connect()
        return client


async def ensure_user_telegram_account(user_id: int) -> TelegramClient:
    client = await get_telegram_client(user_id)
    if not await client.is_user_authorized():
        raise HTTPException(status_code=409, detail="Telegram account is not connected")
    me = await client.get_me()
    if not me or me.id != user_id:
        logger.error(
            "Telegram session mismatch: Mini App user=%s, MTProto user=%s",
            user_id,
            getattr(me, "id", None),
        )
        try:
            await client.log_out()
        except Exception:
            pass
        try:
            await client.disconnect()
        except Exception:
            pass
        telegram_clients.pop(user_id, None)
        raise HTTPException(
            status_code=403,
            detail="Telegram session does not belong to the current user",
        )
    return client


async def disconnect_telegram_clients() -> None:
    clients = list(telegram_clients.values())
    telegram_clients.clear()
    for client in clients:
        try:
            await client.disconnect()
        except Exception:
            pass
