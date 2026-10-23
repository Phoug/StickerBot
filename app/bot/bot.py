import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeDefault

from app.bot.config import BOT_TOKEN
from app.bot.handlers import language, media, stickers, start
from app.bot.middleware import LocalizationMiddleware
from app.bot.services.api_client import backend_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("telegram_bot")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

dp = Dispatcher()
dp.update.middleware(LocalizationMiddleware())
dp.include_router(start.router)
dp.include_router(language.router)
dp.include_router(stickers.router)
dp.include_router(media.router)


async def set_bot_commands() -> None:
    commands_en = [
        BotCommand(command="start", description="Bot overview"),
        BotCommand(command="help", description="Command list"),
        BotCommand(command="sticker", description="Convert video to a video sticker"),
        BotCommand(command="lang", description="Change language of application"),
    ]
    commands_ru = [
        BotCommand(command="start", description="Обзор бота"),
        BotCommand(command="help", description="Список команд"),
        BotCommand(command="sticker", description="Преобразовать видео в стикер"),
        BotCommand(command="lang", description="Сменить язык приложения"),
    ]
    await bot.set_my_commands(commands_en, scope=BotCommandScopeDefault())
    await bot.set_my_commands(
        commands_ru,
        scope=BotCommandScopeDefault(),
        language_code="ru",
    )


async def run_bot() -> None:
    await backend_client.open()
    try:
        await set_bot_commands()
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        await backend_client.close()
        await bot.session.close()
