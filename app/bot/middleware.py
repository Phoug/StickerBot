from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.localization import get_language, translator_for


class LocalizationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        language = get_language(
            user.id if user else None,
            user.language_code if user else None,
        )
        data["tr"] = translator_for(language)
        data["lang"] = language
        return await handler(event, data)
