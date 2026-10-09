from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.keyboards.language import get_main_keyboard
from app.localization import MESSAGES
from app.services.video_service import process_video_download
from app.utils import extract_url

router = Router()


@router.message(CommandStart())
async def start_handler(message: Message, tr):
    await message.answer(tr("start"), reply_markup=get_main_keyboard(tr))


@router.message(Command("help"))
async def help_handler(message: Message, tr):
    await message.answer(tr("help"))


@router.message(F.web_app_data)
async def web_app_data_handler(message: Message, tr):
    import json

    try:
        payload = json.loads(message.web_app_data.data)
        if payload.get("action") == "process_url":
            url = payload.get("url")
            if url:
                await process_video_download(message, url, tr)
            else:
                await message.answer(tr("invalid_url"))
    except Exception:
        await message.answer(tr("invalid_url"))
