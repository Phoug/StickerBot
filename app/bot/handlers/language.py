from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.language import get_language_keyboard
from app.bot.localization import USER_LANGUAGES, translator_for

router = Router()


@router.message(Command("lang"))
async def lang_command_handler(message: Message, tr):
    await message.answer(
        tr("select_language"),
        reply_markup=get_language_keyboard(),
    )


@router.callback_query(F.data.startswith("set_lang_"))
async def language_callback_handler(callback: CallbackQuery):
    if not callback.from_user or not callback.message or not callback.data:
        await callback.answer()
        return
    lang_code = callback.data.rsplit("_", 1)[-1]
    if lang_code not in {"ru", "en"}:
        await callback.answer()
        return
    USER_LANGUAGES[callback.from_user.id] = lang_code
    await callback.message.edit_text(translator_for(lang_code)("lang_updated"))
    await callback.answer()
