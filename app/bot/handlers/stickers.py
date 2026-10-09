from html import escape as html_quote

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.services.sticker_service import process_sticker_generation
from app.utils import parse_sticker_args

router = Router()


@router.message(Command("sticker"))
async def sticker_command_handler(message: Message, bot, tr):
    target_message = None
    if message.video or message.document:
        target_message = message
    elif message.reply_to_message and (
        message.reply_to_message.video or message.reply_to_message.document
    ):
        target_message = message.reply_to_message
    if not target_message:
        await message.answer(tr("no_target"))
        return
    try:
        caption_or_text = message.caption or message.text
        start, end = parse_sticker_args(caption_or_text, tr)
    except ValueError as exc:
        await message.answer(
            tr("invalid_timestamp", error=html_quote(str(exc)))
        )
        return
    await process_sticker_generation(
        bot,
        target_message,
        message,
        start,
        end,
        tr,
    )
