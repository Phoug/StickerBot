import logging
import time

from fastapi import APIRouter, Header, HTTPException
from telethon.errors import (
    FloodWaitError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)

from backend.config import LOGIN_CODE_COOLDOWN, LOGIN_CODE_TTL
from backend.models import TelegramLoginRequest, TelegramUserResponse, TelegramVerifyRequest
from backend.security import get_mini_app_user
from backend.services.telethon_service import (
    PendingLogin,
    get_telegram_client,
    get_user_session_path,
    last_code_request,
    pending_logins,
    telegram_clients,
)

logger = logging.getLogger("video_backend.telegram")
router = APIRouter(prefix="/api/telegram", tags=["Telegram account"])


def _get_user(init_data: str | None) -> tuple[dict, int]:
    user = get_mini_app_user(init_data)
    return user, int(user["id"])


@router.get("/status", response_model=TelegramUserResponse)
async def telegram_status(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
):
    user, user_id = _get_user(x_telegram_init_data)
    client = await get_telegram_client(user_id)
    if not await client.is_user_authorized():
        return TelegramUserResponse(connected=False)
    me = await client.get_me()
    if not me:
        return TelegramUserResponse(connected=False)
    if me.id != user_id:
        try:
            await client.log_out()
        except Exception:
            pass
        return TelegramUserResponse(connected=False)
    return TelegramUserResponse(
        connected=True,
        user_id=me.id,
        username=me.username,
        first_name=me.first_name,
        last_name=me.last_name,
    )


@router.post("/login/request-code")
async def telegram_request_code(
    payload: TelegramLoginRequest,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
):
    _, user_id = _get_user(x_telegram_init_data)
    current_time = time.time()
    last_request = last_code_request.get(user_id, 0)
    if current_time - last_request < LOGIN_CODE_COOLDOWN:
        remaining = int(LOGIN_CODE_COOLDOWN - (current_time - last_request))
        raise HTTPException(
            status_code=429,
            detail=f"Please wait {max(remaining, 1)} seconds before requesting another code.",
        )

    client = await get_telegram_client(user_id)
    if await client.is_user_authorized():
        me = await client.get_me()
        if me and me.id == user_id:
            return {"status": "already_connected", "user_id": me.id}

    phone = payload.phone.strip()
    if not phone.startswith("+"):
        raise HTTPException(status_code=400, detail="Phone number must start with +")

    try:
        sent_code = await client.send_code_request(phone)
    except PhoneNumberInvalidError as exc:
        raise HTTPException(status_code=400, detail="Invalid phone number") from exc
    except FloodWaitError as exc:
        raise HTTPException(
            status_code=429,
            detail=f"Telegram requires waiting {exc.seconds} seconds.",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to request Telegram login code")
        raise HTTPException(status_code=502, detail="Failed to request Telegram login code") from exc

    pending_logins[user_id] = PendingLogin(
        phone=phone,
        phone_code_hash=sent_code.phone_code_hash,
        created_at=current_time,
    )
    last_code_request[user_id] = current_time
    return {"status": "code_sent", "expires_in": LOGIN_CODE_TTL}


@router.post("/login/verify")
async def telegram_verify_code(
    payload: TelegramVerifyRequest,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
):
    _, user_id = _get_user(x_telegram_init_data)
    pending = pending_logins.get(user_id)
    if not pending:
        raise HTTPException(status_code=400, detail="No active Telegram login request")
    if time.time() - pending.created_at > LOGIN_CODE_TTL:
        pending_logins.pop(user_id, None)
        raise HTTPException(status_code=400, detail="Telegram login code has expired")

    client = await get_telegram_client(user_id)
    try:
        if pending.two_factor_required:
            if not payload.password:
                raise HTTPException(status_code=400, detail="Telegram 2FA password is required")
            me = await client.sign_in(password=payload.password)
        else:
            if not payload.code:
                raise HTTPException(status_code=400, detail="Telegram login code is required")
            try:
                me = await client.sign_in(
                    phone=pending.phone,
                    code=payload.code,
                    phone_code_hash=pending.phone_code_hash,
                )
            except SessionPasswordNeededError:
                pending.two_factor_required = True
                return {"status": "2fa_required"}
    except PhoneCodeInvalidError as exc:
        raise HTTPException(status_code=400, detail="Invalid Telegram login code") from exc
    except PhoneCodeExpiredError as exc:
        pending_logins.pop(user_id, None)
        raise HTTPException(status_code=400, detail="Telegram login code has expired") from exc
    except FloodWaitError as exc:
        raise HTTPException(
            status_code=429,
            detail=f"Telegram requires waiting {exc.seconds} seconds.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to sign in Telegram user %s", user_id)
        raise HTTPException(status_code=502, detail="Failed to sign in Telegram account") from exc
    finally:
        if payload.password:
            payload.password = None

    if not me:
        raise HTTPException(status_code=502, detail="Telegram did not return user information")
    if me.id != user_id:
        logger.warning(
            "Telegram account mismatch during login: Mini App user=%s, logged-in account=%s",
            user_id,
            me.id,
        )
        try:
            await client.log_out()
        except Exception:
            pass
        pending_logins.pop(user_id, None)
        raise HTTPException(
            status_code=403,
            detail=(
                "The Telegram account you connected does not match the account "
                "that opened the Mini App."
            ),
        )

    pending_logins.pop(user_id, None)
    return {
        "status": "connected",
        "user_id": me.id,
        "username": me.username,
        "first_name": me.first_name,
        "last_name": me.last_name,
    }


@router.post("/logout")
async def telegram_logout(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
):
    _, user_id = _get_user(x_telegram_init_data)
    client = telegram_clients.get(user_id)
    if client:
        try:
            if await client.is_user_authorized():
                await client.log_out()
        except Exception:
            logger.exception("Error during Telegram logout for %s", user_id)
        try:
            await client.disconnect()
        except Exception:
            pass
    telegram_clients.pop(user_id, None)
    pending_logins.pop(user_id, None)
    session_path = get_user_session_path(user_id)
    try:
        if session_path.exists():
            session_path.unlink()
    except OSError:
        logger.exception("Failed to remove Telegram session file")
    return {"status": "logged_out"}
