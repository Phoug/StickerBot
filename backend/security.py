import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException, Security
from fastapi.security import APIKeyHeader
from starlette.status import HTTP_401_UNAUTHORIZED

from backend.config import API_SECRET_TOKEN, BOT_TOKEN, MINI_APP_AUTH_MAX_AGE

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    if not api_key or not hmac.compare_digest(api_key, API_SECRET_TOKEN):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        )
    return api_key


def validate_telegram_init_data(init_data: str) -> dict[str, Any]:
    if not init_data:
        raise HTTPException(status_code=401, detail="Missing Telegram initData")

    try:
        pairs = parse_qsl(init_data, keep_blank_values=True)
        if len({key for key, _ in pairs}) != len(pairs):
            raise ValueError("Duplicate initData fields")
        data = dict(pairs)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid Telegram initData") from exc

    received_hash = data.pop("hash", None)
    if not received_hash or len(received_hash) != 64 or any(c not in "0123456789abcdef" for c in received_hash):
        raise HTTPException(status_code=401, detail="Invalid or missing Telegram initData hash")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret_key = hmac.new(
        key=b"WebAppData",
        msg=BOT_TOKEN.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    calculated_hash = hmac.new(
        key=secret_key,
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid Telegram initData")

    auth_date_raw = data.get("auth_date")
    if not auth_date_raw:
        raise HTTPException(status_code=401, detail="Telegram auth_date is missing")

    try:
        auth_date = int(auth_date_raw)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid Telegram auth_date") from exc

    current_time = int(time.time())
    if current_time - auth_date > MINI_APP_AUTH_MAX_AGE:
        raise HTTPException(status_code=401, detail="Telegram initData has expired")
    if auth_date > current_time + 60:
        raise HTTPException(status_code=401, detail="Invalid Telegram auth_date")

    user_raw = data.get("user")
    if not user_raw:
        raise HTTPException(status_code=401, detail="Telegram user data is missing")

    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=401, detail="Invalid Telegram user data") from exc

    if not isinstance(user, dict) or (type(user.get("id")) is not int or user["id"] <= 0):
        raise HTTPException(status_code=401, detail="Invalid Telegram user ID")

    return {"user": user, "auth_date": auth_date}


def get_mini_app_user(init_data: str | None) -> dict[str, Any]:
    if not init_data:
        raise HTTPException(status_code=401, detail="Missing X-Telegram-Init-Data header")
    return validate_telegram_init_data(init_data)["user"]


def mini_app_user(x_telegram_init_data: str | None = Header(default=None)):
    return get_mini_app_user(x_telegram_init_data)
