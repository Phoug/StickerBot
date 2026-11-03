from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.bot.keyboards.language import get_main_keyboard

router = Router()


@router.message(CommandStart())
async def start_handler(message: Message, tr):
    await message.answer(tr("start"), reply_markup=get_main_keyboard(tr))


@router.message(Command("help"))
async def help_handler(message: Message, tr):
    await message.answer(tr("help"))
