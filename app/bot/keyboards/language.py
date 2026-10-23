from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.bot.config import WEBAPP_URL


def get_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Русский 🇷🇺", callback_data="set_lang_ru"),
                InlineKeyboardButton(text="English 🇬🇧", callback_data="set_lang_en"),
            ]
        ]
    )


def get_main_keyboard(tr) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=tr("open_webapp"),
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            ]
        ]
    )
