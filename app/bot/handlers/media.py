from aiogram import F, Router
from aiogram.types import Message

from app.bot.config import MAX_TELEGRAM_DOWNLOAD_SIZE
from app.bot.services.video_service import process_video_download
from app.bot.utils import extract_url

router = Router()


@router.message(F.video)
async def video_handler(message: Message, tr):
    file_size = message.video.file_size or 0
    if file_size > MAX_TELEGRAM_DOWNLOAD_SIZE:
        await message.answer(tr("tg_limit_download"))
        return
    await message.answer(tr("video_received"))


@router.message(F.document)
async def document_handler(message: Message, tr):
    doc = message.document
    if not doc:
        return
    filename = doc.file_name or ""
    mime_type = doc.mime_type or ""
    is_video = mime_type.startswith("video/") or filename.lower().endswith(
        (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")
    )
    if not is_video:
        await message.answer(tr("invalid_doc"))
        return
    if (doc.file_size or 0) > MAX_TELEGRAM_DOWNLOAD_SIZE:
        await message.answer(tr("tg_limit_download"))
        return
    await message.answer(tr("doc_received"))


@router.message(F.text)
async def url_handler(message: Message, tr):
    url = extract_url(message.text or "")
    if not url:
        await message.answer(tr("invalid_url"))
        return
    await process_video_download(message, url, tr)
